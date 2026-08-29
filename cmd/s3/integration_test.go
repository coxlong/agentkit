package main

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/crowdsecurity/machineid"
	"github.com/johannesboyne/gofakes3"
	"github.com/johannesboyne/gofakes3/backend/s3mem"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"

	"github.com/coxlong/agentkit/internal/s3x"
)

// requireMachineID skips tests that need the machine-ID-derived encryption key
// when the host has none (slim containers, CI), so `go test ./...` still passes
// there. The runtime behavior is unchanged: the tool still errors without one.
func requireMachineID(t *testing.T) {
	t.Helper()
	if _, err := machineid.ID(); err != nil {
		t.Skipf("no machine ID available, skipping: %v", err)
	}
}

// setupFakeS3 starts an in-process S3 service and points HOME at a temp dir,
// so both the config and the secrets land in an isolated location.
func setupFakeS3(t *testing.T) {
	t.Helper()
	requireMachineID(t)

	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("XDG_CONFIG_HOME", "")

	backend := s3mem.New()
	if err := backend.CreateBucket("my-archive-bucket"); err != nil {
		t.Fatalf("failed to create test bucket: %v", err)
	}
	ts := httptest.NewServer(gofakes3.New(backend).Server())
	t.Cleanup(ts.Close)

	forcePathStyle := true
	cfg := &s3x.Config{
		Services: map[string]s3x.Service{
			"test": {
				Endpoint:       ts.URL,
				Region:         "us-east-1",
				AccessKeyID:    "test-ak",
				ForcePathStyle: &forcePathStyle,
			},
		},
		Buckets: []s3x.Bucket{{
			Bucket:  "my-archive-bucket",
			Alias:   "archive",
			Service: "test",
			Desc:    "long-term archive for historical reports, mostly read-only",
		}},
	}
	if err := cfg.Save(); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}
	if err := s3x.SaveSecrets(s3x.SecretsPath(), s3x.Secrets{
		"test": {SecretAccessKey: "test-sk"},
	}); err != nil {
		t.Fatalf("failed to write secrets: %v", err)
	}
}

// resetFlags restores every flag on the command tree to its default.
//
// The commands are package-level singletons, so flag state lingers between
// Execute calls (for example the --json of one command would affect the next);
// tests must clear it explicitly.
func resetFlags(t *testing.T) {
	t.Helper()
	var reset func(c *cobra.Command)
	reset = func(c *cobra.Command) {
		c.Flags().VisitAll(func(f *pflag.Flag) {
			if err := f.Value.Set(f.DefValue); err != nil {
				t.Fatalf("failed to reset flag %s: %v", f.Name, err)
			}
			f.Changed = false
		})
		for _, sub := range c.Commands() {
			reset(sub)
		}
	}
	reset(rootCmd)
}

// run executes a command and returns its output.
func run(t *testing.T, args ...string) string {
	t.Helper()
	resetFlags(t)
	var buf bytes.Buffer
	rootCmd.SetOut(&buf)
	rootCmd.SetErr(&buf)
	rootCmd.SetArgs(args)
	if err := rootCmd.Execute(); err != nil {
		t.Fatalf("s3 %s failed: %v", strings.Join(args, " "), err)
	}
	return buf.String()
}

// runErr executes a command expected to fail and returns the error message.
func runErr(t *testing.T, args ...string) string {
	t.Helper()
	resetFlags(t)
	var buf bytes.Buffer
	rootCmd.SetOut(&buf)
	rootCmd.SetErr(&buf)
	rootCmd.SetArgs(args)
	err := rootCmd.Execute()
	if err == nil {
		t.Fatalf("s3 %s should have failed but succeeded", strings.Join(args, " "))
	}
	return err.Error()
}

func TestBuckets(t *testing.T) {
	setupFakeS3(t)

	out := run(t, "buckets")
	if !strings.Contains(out, "archive") {
		t.Errorf("output should contain the bucket name archive:\n%s", out)
	}
	if !strings.Contains(out, "long-term archive") {
		t.Errorf("output should contain the description:\n%s", out)
	}
	// The agent must not see any credentials or the real bucket name.
	for _, leak := range []string{"test-ak", "test-sk", "my-archive-bucket", "service"} {
		if strings.Contains(out, leak) {
			t.Errorf("output leaked %q:\n%s", leak, out)
		}
	}
}

func TestBucketsJSON(t *testing.T) {
	setupFakeS3(t)

	var views []bucketView
	if err := json.Unmarshal([]byte(run(t, "buckets", "--json")), &views); err != nil {
		t.Fatalf("failed to parse JSON: %v", err)
	}
	if len(views) != 1 || views[0].Bucket != "archive" {
		t.Fatalf("expected one bucket named archive, got %v", views)
	}
	if views[0].Desc == "" {
		t.Error("desc should not be empty; it is what the agent chooses on")
	}
}

func TestUnknownBucketListsAvailable(t *testing.T) {
	setupFakeS3(t)

	err := runErr(t, "cat", "s3://2026/report.pdf")
	if !strings.Contains(err, "archive") {
		t.Errorf("error should list available buckets for self-correction, got: %s", err)
	}
	if !strings.Contains(err, "long-term") {
		t.Errorf("error should carry the description, got: %s", err)
	}
}

func TestPutGetCatLsRm(t *testing.T) {
	setupFakeS3(t)
	dir := t.TempDir()

	src := filepath.Join(dir, "report.txt")
	if err := os.WriteFile(src, []byte("hello agentkit"), 0o600); err != nil {
		t.Fatal(err)
	}

	run(t, "put", src, "s3://archive/2026/report.txt")

	// cat should output the content verbatim
	if got := run(t, "cat", "s3://archive/2026/report.txt"); got != "hello agentkit" {
		t.Errorf("cat output = %q", got)
	}

	// get downloads to disk
	dst := filepath.Join(dir, "downloaded.txt")
	run(t, "get", "s3://archive/2026/report.txt", dst)
	body, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if string(body) != "hello agentkit" {
		t.Errorf("downloaded content = %q", string(body))
	}

	// ls should list the uploaded object
	if out := run(t, "ls", "s3://archive/", "--recursive"); !strings.Contains(out, "2026/report.txt") {
		t.Errorf("ls did not list the uploaded object:\n%s", out)
	}

	// structured --json output
	var objs []objectView
	if err := json.Unmarshal([]byte(run(t, "ls", "s3://archive/", "--recursive", "--json")), &objs); err != nil {
		t.Fatalf("failed to parse ls JSON: %v", err)
	}
	if len(objs) != 1 || objs[0].Key != "2026/report.txt" || objs[0].Size != int64(len("hello agentkit")) {
		t.Errorf("ls JSON mismatch: %+v", objs)
	}

	// after rm, the object should be gone
	run(t, "rm", "s3://archive/2026/report.txt")
	if out := run(t, "ls", "s3://archive/", "--recursive"); strings.Contains(out, "report.txt") {
		t.Errorf("object still listed after delete:\n%s", out)
	}
}

func TestAddBucketRejectsDuplicateAlias(t *testing.T) {
	setupFakeS3(t)

	// A duplicate alias must be rejected at save time, not written out as a
	// config that subsequent commands cannot load. The menu path is interactive,
	// so exercise the mutator directly.
	cfg, err := s3x.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	err = addBucket(cfg, "other-bucket", "archive", "test", "x")
	if err == nil || !strings.Contains(err.Error(), "conflict") {
		t.Errorf("a duplicate alias should report a conflict, got: %v", err)
	}

	// The config on disk must still be usable and hold exactly one bucket.
	var views []bucketView
	if err := json.Unmarshal([]byte(run(t, "buckets", "--json")), &views); err != nil {
		t.Fatalf("failed to parse JSON: %v", err)
	}
	if len(views) != 1 || views[0].Bucket != "archive" {
		t.Errorf("config should be unchanged, got %v", views)
	}
}

func TestAddBucketRequiresExistingService(t *testing.T) {
	setupFakeS3(t)
	cfg, err := s3x.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	err = addBucket(cfg, "other-bucket", "other", "no-such-service", "x")
	if err == nil || !strings.Contains(err.Error(), "no-such-service") {
		t.Errorf("an undefined service should be rejected, got: %v", err)
	}
}

func TestPutLargeFileMultipart(t *testing.T) {
	setupFakeS3(t)
	dir := t.TempDir()

	// Over the uploader's default part-threshold (5MiB), verifying the
	// multipart path works against a compatible endpoint (path-style +
	// custom endpoint).
	src := filepath.Join(dir, "big.bin")
	body := bytes.Repeat([]byte("0123456789abcdef"), 6*1024*1024/16)
	if err := os.WriteFile(src, body, 0o600); err != nil {
		t.Fatal(err)
	}

	run(t, "put", src, "s3://archive/big.bin")

	dst := filepath.Join(dir, "big.out")
	run(t, "get", "s3://archive/big.bin", dst)
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, body) {
		t.Errorf("content mismatch after multipart round trip: got %d bytes, want %d bytes", len(got), len(body))
	}
}

func TestInteractiveNeedsTTY(t *testing.T) {
	setupFakeS3(t)

	// go test's stdin is not a terminal: the config menu should give an
	// actionable error instead of reading from a non-TTY stdin.
	err := runErr(t, "config")
	if !strings.Contains(err, "interactive terminal") {
		t.Errorf("config without a terminal should ask for one, got: %s", err)
	}
}

func TestLsFoldsByDelimiter(t *testing.T) {
	setupFakeS3(t)
	dir := t.TempDir()

	src := filepath.Join(dir, "x.txt")
	os.WriteFile(src, []byte("x"), 0o600)
	run(t, "put", src, "s3://archive/2026/a/x.txt")
	run(t, "put", src, "s3://archive/2026/b/x.txt")

	// Non-recursive should fold to a single level of prefixes
	out := run(t, "ls", "s3://archive/2026/")
	if !strings.Contains(out, "PRE") || !strings.Contains(out, "a/") {
		t.Errorf("non-recursive ls should fold at /:\n%s", out)
	}
	if strings.Contains(out, "a/x.txt") {
		t.Errorf("non-recursive ls should not expand to leaves:\n%s", out)
	}

	// Recursive should expand
	rec := run(t, "ls", "s3://archive/2026/", "--recursive")
	if !strings.Contains(rec, "a/x.txt") || !strings.Contains(rec, "b/x.txt") {
		t.Errorf("recursive ls should list all leaves:\n%s", rec)
	}
}

func TestRmRecursive(t *testing.T) {
	setupFakeS3(t)
	dir := t.TempDir()

	src := filepath.Join(dir, "x.txt")
	os.WriteFile(src, []byte("x"), 0o600)
	run(t, "put", src, "s3://archive/2026/a/x.txt")
	run(t, "put", src, "s3://archive/2026/b/x.txt")

	run(t, "rm", "s3://archive/2026/", "--recursive")
	if out := run(t, "ls", "s3://archive/", "--recursive"); strings.TrimSpace(out) != "" {
		t.Errorf("recursive delete should leave nothing:\n%s", out)
	}
}

func TestEmptyPrefixRecursiveDeleteIsNoop(t *testing.T) {
	setupFakeS3(t)

	out := run(t, "rm", "s3://archive/no-such-prefix/", "--recursive")
	if !strings.Contains(out, "no objects") {
		t.Errorf("an empty prefix delete should report no objects, got: %s", out)
	}
}

func TestMissingKeyIsRejected(t *testing.T) {
	setupFakeS3(t)

	err := runErr(t, "cat", "s3://archive")
	if !strings.Contains(err, "missing key") {
		t.Errorf("should report a missing key, got: %s", err)
	}
}

func TestBareAddressIsAccepted(t *testing.T) {
	setupFakeS3(t)
	dir := t.TempDir()

	src := filepath.Join(dir, "x.txt")
	os.WriteFile(src, []byte("bare"), 0o600)

	// Bare format (without s3://) is also accepted, absorbing the occasional
	// LLM typo where the scheme is omitted.
	run(t, "put", src, "archive/bare.txt")
	if got := run(t, "cat", "archive/bare.txt"); got != "bare" {
		t.Errorf("bare-address cat output = %q", got)
	}
}

func TestAliasRequiredWhenConfigured(t *testing.T) {
	setupFakeS3(t)

	// A bucket with an alias is addressed only by the alias; the real name is
	// no longer accepted.
	err := runErr(t, "ls", "s3://my-archive-bucket/")
	if !strings.Contains(err, "unknown bucket") {
		t.Errorf("the real bucket name should not be accepted, got: %s", err)
	}
}
