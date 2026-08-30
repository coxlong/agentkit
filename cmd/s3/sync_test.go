package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestDecideEqualSize(t *testing.T) {
	// The truth table from decideEqualSize's comment: s5cmd's size-and-mtime
	// table refined with the uploader-stored fingerprint.
	localNow := time.Now()
	remoteOld := localNow.Add(-time.Hour)
	localOld := remoteOld.Add(-time.Minute)
	remoteNow := localNow.Add(time.Hour)

	lf := localFile{size: 10, modTime: localNow}
	lfOld := localFile{size: 10, modTime: localOld}
	ro := remoteObj{size: 10, lastModified: remoteOld}
	roNew := remoteObj{size: 10, lastModified: remoteNow}

	cases := []struct {
		name   string
		upload bool
		lf     localFile
		ro     remoteObj
		meta   *time.Time
		want   bool
	}{
		{"upload: fingerprint matches, skip", true, lf, ro, &localNow, false},
		{"upload: fingerprint differs, the stored copy is stale", true, lf, ro, &localOld, true},
		{"upload: no fingerprint, local newer", true, lf, ro, nil, true},
		{"upload: no fingerprint, local not newer", true, lfOld, ro, nil, false},
		{"download: fingerprint matches, exact round trip", false, lf, ro, &localNow, false},
		{"download: fingerprint differs, remote newer", false, lf, roNew, &localOld, true},
		{"download: fingerprint differs, remote older", false, lf, ro, &remoteOld, false},
		{"download: no fingerprint, remote newer", false, lf, roNew, nil, true},
		{"download: no fingerprint, remote older", false, lf, ro, nil, false},
	}
	for _, c := range cases {
		if got := decideEqualSize(c.upload, c.lf, c.ro, c.meta); got != c.want {
			t.Errorf("%s: decideEqualSize = %v, want %v", c.name, got, c.want)
		}
	}
}

func TestScanLocalSkipsSymlinks(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "real.txt"), []byte("x"), 0o600)
	os.Symlink(filepath.Join(dir, "real.txt"), filepath.Join(dir, "link.txt"))

	files, err := scanLocal(dir, true)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := files["real.txt"]; !ok {
		t.Errorf("regular file missing: %v", files)
	}
	if _, ok := files["link.txt"]; ok {
		t.Errorf("symlink must be skipped: %v", files)
	}
}

func TestSyncUploadDownloadRoundTrip(t *testing.T) {
	setupFakeS3(t)
	srcDir := t.TempDir()

	old := time.Now().Add(-time.Hour)
	writeSyncFile(t, srcDir, "a.txt", "alpha", old)
	os.MkdirAll(filepath.Join(srcDir, "sub"), 0o755)
	writeSyncFile(t, srcDir, "sub/b.txt", "beta", old)

	// Initial upload.
	out := run(t, "sync", srcDir, "s3://archive/2026/")
	for _, want := range []string{"uploaded", "a.txt", "sub/b.txt", "sync complete: 2 uploaded, 0 downloaded, 0 deleted, 0 skipped"} {
		if !strings.Contains(out, want) {
			t.Errorf("initial sync output should contain %q:\n%s", want, out)
		}
	}

	// A no-change sync transfers nothing, even though the remote LastModified
	// (upload instant) is newer than the local mtimes: the fingerprint
	// decides, and it matches.
	out = run(t, "sync", srcDir, "s3://archive/2026/")
	if !strings.Contains(out, "sync complete: 0 uploaded, 0 downloaded, 0 deleted, 2 skipped") {
		t.Errorf("second sync should transfer nothing:\n%s", out)
	}

	// Dry-run on the same state: same plan, nothing executed.
	out = run(t, "sync", srcDir, "s3://archive/2026/", "--dry-run")
	if !strings.Contains(out, "dry run: 0 upload(s), 0 download(s), 0 delete(s), 2 skipped") || strings.Contains(out, "would upload") {
		t.Errorf("dry run should plan nothing:\n%s", out)
	}

	// Same size, new mtime: only the fingerprint catches this, sizes do not.
	writeSyncFile(t, srcDir, "a.txt", "ALPHA", time.Now())
	out = run(t, "sync", srcDir, "s3://archive/2026/")
	if !strings.Contains(out, "sync complete: 1 uploaded, 0 downloaded, 0 deleted, 1 skipped") {
		t.Errorf("same-size edit should re-upload exactly one file:\n%s", out)
	}

	// Round trip down, then a no-change download.
	dstDir := t.TempDir()
	run(t, "sync", "s3://archive/2026/", dstDir)
	if got := readSyncFile(t, dstDir, "a.txt"); got != "ALPHA" {
		t.Errorf("downloaded a.txt = %q", got)
	}
	if got := readSyncFile(t, dstDir, "sub/b.txt"); got != "beta" {
		t.Errorf("downloaded sub/b.txt = %q", got)
	}
	out = run(t, "sync", "s3://archive/2026/", dstDir)
	if !strings.Contains(out, "sync complete: 0 uploaded, 0 downloaded, 0 deleted, 2 skipped") {
		t.Errorf("download sync should transfer nothing:\n%s", out)
	}
}

func TestSyncDeleteRemote(t *testing.T) {
	setupFakeS3(t)
	srcDir := t.TempDir()
	old := time.Now().Add(-time.Hour)
	writeSyncFile(t, srcDir, "a.txt", "alpha", old)
	writeSyncFile(t, srcDir, "b.txt", "beta", old)
	run(t, "sync", srcDir, "s3://archive/2026/")

	// Without --delete the remote copy survives.
	os.Remove(filepath.Join(srcDir, "b.txt"))
	run(t, "sync", srcDir, "s3://archive/2026/")
	if out := run(t, "ls", "s3://archive/2026/", "--recursive"); !strings.Contains(out, "b.txt") {
		t.Errorf("no --delete must never delete:\n%s", out)
	}

	// With --delete the count is reported before the deletion.
	out := run(t, "sync", srcDir, "s3://archive/2026/", "--delete")
	if !strings.Contains(out, "deleting 1 object(s) under s3://archive/2026/") || !strings.Contains(out, "deleted s3://archive/2026/b.txt") {
		t.Errorf("--delete should report count and deletion:\n%s", out)
	}
	if out := run(t, "ls", "s3://archive/2026/", "--recursive"); strings.Contains(out, "b.txt") {
		t.Errorf("b.txt should be gone after --delete:\n%s", out)
	}
}

func TestSyncDeleteLocal(t *testing.T) {
	setupFakeS3(t)
	srcDir := t.TempDir()
	old := time.Now().Add(-time.Hour)
	writeSyncFile(t, srcDir, "a.txt", "alpha", old)
	writeSyncFile(t, srcDir, "b.txt", "beta", old)
	run(t, "sync", srcDir, "s3://archive/2026/")

	dstDir := t.TempDir()
	run(t, "sync", "s3://archive/2026/", dstDir)

	// The remote copy disappears; --delete prunes the local stray.
	run(t, "rm", "s3://archive/2026/b.txt")
	out := run(t, "sync", "s3://archive/2026/", dstDir, "--delete")
	if !strings.Contains(out, "deleting 1 local file(s) under") || !strings.Contains(out, "b.txt (local)") {
		t.Errorf("--delete should prune local-only files:\n%s", out)
	}
	if _, err := os.Stat(filepath.Join(dstDir, "b.txt")); !os.IsNotExist(err) {
		t.Errorf("local b.txt should be gone")
	}
	if _, err := os.Stat(filepath.Join(dstDir, "a.txt")); err != nil {
		t.Errorf("local a.txt should survive")
	}
}

func TestSyncJSON(t *testing.T) {
	setupFakeS3(t)
	srcDir := t.TempDir()
	writeSyncFile(t, srcDir, "a.txt", "alpha", time.Now().Add(-time.Hour))

	out := run(t, "sync", srcDir, "s3://archive/2026/", "--json")
	var view syncView
	if err := json.Unmarshal([]byte(out), &view); err != nil {
		t.Fatalf("failed to parse sync JSON: %v\n%s", err, out)
	}
	if view.Direction != "upload" || len(view.Uploaded) != 1 || view.Uploaded[0] != "2026/a.txt" {
		t.Errorf("unexpected view: %+v", view)
	}
	if view.Skipped != 0 || len(view.Errors) != 0 {
		t.Errorf("unexpected counts: %+v", view)
	}

	// A no-change sync reports the skips in JSON too.
	out = run(t, "sync", srcDir, "s3://archive/2026/", "--json")
	view = syncView{}
	if err := json.Unmarshal([]byte(out), &view); err != nil {
		t.Fatalf("failed to parse sync JSON: %v\n%s", err, out)
	}
	if len(view.Uploaded) != 0 || view.Skipped != 1 {
		t.Errorf("no-change sync should upload nothing and skip one: %+v", view)
	}
}

func TestSyncRejectsAmbiguousArgs(t *testing.T) {
	setupFakeS3(t)
	dir := t.TempDir()

	// The bare address form tolerated by the other commands is refused here:
	// a local path like "archive/2026" would parse as a bucket address, and
	// guessing the direction of a command that can delete is how accidents
	// happen.
	err := runErr(t, "sync", "archive/", filepath.Join(dir, "out"))
	if !strings.Contains(err, "must be an s3:// address") {
		t.Errorf("bare address should be rejected, got: %s", err)
	}
	err = runErr(t, "sync", "s3://archive/a", "s3://archive/b")
	if !strings.Contains(err, "only one s3:// address") {
		t.Errorf("two remote args should be rejected, got: %s", err)
	}
	err = runErr(t, "sync", filepath.Join(dir, "missing"), "s3://archive/")
	if !strings.Contains(err, "not an existing directory") {
		t.Errorf("missing local dir should be rejected, got: %s", err)
	}
}

// writeSyncFile creates a file with an explicit mtime, so the fingerprint
// comparisons in the sync tests are deterministic.
func writeSyncFile(t *testing.T, root, rel, content string, modTime time.Time) {
	t.Helper()
	path := filepath.Join(root, filepath.FromSlash(rel))
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chtimes(path, modTime, modTime); err != nil {
		t.Fatal(err)
	}
}

func readSyncFile(t *testing.T, root, rel string) string {
	t.Helper()
	body, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(rel)))
	if err != nil {
		t.Fatal(err)
	}
	return string(body)
}
