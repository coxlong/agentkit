package main

import (
	"context"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/spf13/cobra"
)

// syncConcurrency caps how many transfers (and metadata HEADs) run at once.
const syncConcurrency = 8

var syncCmd = &cobra.Command{
	Use:   "sync <local dir> s3://<bucket>/<prefix>  |  sync s3://<bucket>/<prefix> <local dir>",
	Short: "Sync a local directory and a remote prefix",
	Long: `Synchronize a local directory and a remote prefix, transferring only what
differs. The direction follows the s3:// argument: a remote destination
uploads, a remote source downloads.

  s3 sync ./reports s3://archive/2026/    # upload
  s3 sync s3://archive/2026/ ./reports    # download

What transfers: objects missing on the destination, and objects whose size
differs. For equal sizes the mtime stamped into object metadata by put/sync
decides; objects without it (or --size-only) fall back to comparing the
timestamps, which can misjudge when clocks differ.

Nothing is deleted unless --delete is given, which removes entries that only
exist on the destination after reporting how many. --dry-run prints the plan
without touching anything, and --json emits it (or the result) as JSON.

Unlike the other commands, the s3:// prefix is required here and treated as
a folder (a missing trailing slash is added): with --delete in play, a
mis-parsed argument must not be silently absorbed.`,
	Args: cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return err
		}

		// Exactly one argument must carry the explicit s3:// scheme. The bare
		// form tolerated elsewhere is refused: a local path like "archive/2026"
		// would parse as a bucket address, and guessing the direction of a
		// command that can delete is how accidents happen.
		remoteIdx := -1
		for i, a := range args {
			if strings.HasPrefix(a, "s3://") {
				if remoteIdx >= 0 {
					return fmt.Errorf("only one s3:// address is allowed; got %q and %q", args[0], args[1])
				}
				remoteIdx = i
			}
		}
		if remoteIdx < 0 {
			return fmt.Errorf("one argument must be an s3:// address; got %q and %q", args[0], args[1])
		}
		// A remote destination (second argument) uploads; a remote source
		// (first argument) downloads.
		upload := remoteIdx == 1
		localDir := args[1-remoteIdx]

		b, prefix, err := cfg.ResolveAddr(args[remoteIdx])
		if err != nil {
			return err
		}
		// The prefix is a folder: keys are prefix + relative path. Root of the
		// bucket is the empty prefix.
		if prefix != "" && !strings.HasSuffix(prefix, "/") {
			prefix += "/"
		}

		client, err := cfg.ClientFor(context.Background(), b)
		if err != nil {
			return err
		}
		ctx := context.Background()

		if upload {
			if info, err := os.Stat(localDir); err != nil || !info.IsDir() {
				return fmt.Errorf("%q is not an existing directory", localDir)
			}
		}

		local, err := scanLocal(localDir, upload)
		if err != nil {
			return err
		}
		remote, err := listRemote(ctx, client, b.Bucket, prefix)
		if err != nil {
			return err
		}

		deleteOnly, _ := cmd.Flags().GetBool("delete")
		dryRun, _ := cmd.Flags().GetBool("dry-run")
		sizeOnly, _ := cmd.Flags().GetBool("size-only")
		jsonOut, _ := cmd.Flags().GetBool("json")

		p, errs := buildPlan(ctx, client, b.Bucket, upload, deleteOnly, !sizeOnly, localDir, prefix, local, remote)

		out := cmd.ErrOrStderr()
		view := syncView{
			Direction:  map[bool]string{true: "upload", false: "download"}[upload],
			DryRun:     dryRun,
			Uploaded:   []string{},
			Downloaded: []string{},
			Deleted:    []string{},
			Errors:     []string{},
		}

		// Same contract as rm --recursive: a destructive delete is never
		// silent. The warning also survives --json, the one stderr line that
		// does.
		if !dryRun && deleteOnly {
			switch {
			case upload && len(p.deleteRemote) > 0:
				fmt.Fprintf(out, "deleting %d object(s) under s3://%s/%s\n", len(p.deleteRemote), b.Name(), prefix)
			case !upload && len(p.deleteLocal) > 0:
				fmt.Fprintf(out, "deleting %d local file(s) under %s\n", len(p.deleteLocal), localDir)
			}
		}

		// With --json the per-operation chatter moves into the view entirely.
		say := func(format string, a ...any) {
			if !jsonOut {
				fmt.Fprintf(out, format+"\n", a...)
			}
		}

		for _, t := range p.transfers {
			if dryRun {
				if upload {
					say("would upload %s -> s3://%s/%s", t.localPath, b.Name(), t.key)
				} else {
					say("would download s3://%s/%s -> %s", b.Name(), t.key, t.localPath)
				}
				continue
			}
			if upload {
				err := uploadFile(ctx, client, b.Bucket, t.key, t.localPath)
				if err == nil {
					view.Uploaded = append(view.Uploaded, t.key)
					say("uploaded %s -> s3://%s/%s", t.localPath, b.Name(), t.key)
				} else {
					errs = append(errs, fmt.Sprintf("s3://%s/%s: %v", b.Name(), t.key, err))
				}
			} else {
				err := downloadFile(ctx, client, b.Bucket, t.key, t.localPath)
				if err == nil {
					view.Downloaded = append(view.Downloaded, t.key)
					say("downloaded s3://%s/%s -> %s", b.Name(), t.key, t.localPath)
				} else {
					errs = append(errs, fmt.Sprintf("s3://%s/%s: %v", b.Name(), t.key, err))
				}
			}
		}

		if upload {
			if len(p.deleteRemote) > 0 && !dryRun {
				// Report what actually got deleted: on a mid-batch failure the
				// confirmed deletions are still real.
				deleted, err := deleteKeysBatch(client, b.Bucket, p.deleteRemote)
				for _, key := range deleted {
					view.Deleted = append(view.Deleted, key)
					say("deleted s3://%s/%s", b.Name(), key)
				}
				if err != nil {
					errs = append(errs, err.Error())
				}
			}
			for _, key := range p.deleteRemote {
				if dryRun {
					say("would delete s3://%s/%s", b.Name(), key)
				}
			}
		} else {
			for _, rel := range p.deleteLocal {
				path := filepath.Join(localDir, filepath.FromSlash(rel))
				if dryRun {
					say("would delete %s (local)", path)
					continue
				}
				if err := os.Remove(path); err != nil {
					errs = append(errs, fmt.Sprintf("%s: %v", path, err))
					continue
				}
				view.Deleted = append(view.Deleted, rel)
				say("deleted %s (local)", path)
			}
		}

		view.Skipped = p.skipped
		view.Errors = errs

		if jsonOut {
			if err := emitJSON(cmd.OutOrStdout(), view); err != nil {
				return err
			}
		} else if dryRun {
			var uploads, downloads int
			if upload {
				uploads = len(p.transfers)
			} else {
				downloads = len(p.transfers)
			}
			fmt.Fprintf(out, "dry run: %d upload(s), %d download(s), %d delete(s), %d skipped\n",
				uploads, downloads, len(p.deleteRemote)+len(p.deleteLocal), p.skipped)
		} else {
			fmt.Fprintf(out, "sync complete: %d uploaded, %d downloaded, %d deleted, %d skipped\n",
				len(view.Uploaded), len(view.Downloaded), len(view.Deleted), p.skipped)
		}
		if len(errs) > 0 {
			return fmt.Errorf("%d operation(s) failed", len(errs))
		}
		return nil
	},
}

func init() {
	syncCmd.Flags().Bool("delete", false, "Delete destination entries that do not exist in the source")
	syncCmd.Flags().Bool("dry-run", false, "Print what would be done without touching anything")
	syncCmd.Flags().Bool("size-only", false, "Compare sizes only; skip the mtime check for equal sizes")
	syncCmd.Flags().Bool("json", false, "JSON result on stdout")
}

// localFile is what the diff needs to know about a local file.
type localFile struct {
	size    int64
	modTime time.Time
}

// remoteObj is what the diff needs to know about a stored object.
type remoteObj struct {
	size         int64
	lastModified time.Time
}

// transfer is one planned copy: the object key and where it maps to locally.
type transfer struct {
	key       string // full object key
	rel       string // path relative to the sync root, slash-separated
	localPath string
}

type plan struct {
	transfers    []transfer // sorted by key
	deleteRemote []string   // keys
	deleteLocal  []string   // rel paths
	skipped      int
}

type syncView struct {
	Direction  string   `json:"direction"`
	DryRun     bool     `json:"dry_run"`
	Uploaded   []string `json:"uploaded"`
	Downloaded []string `json:"downloaded"`
	Deleted    []string `json:"deleted"`
	Skipped    int      `json:"skipped"`
	Errors     []string `json:"errors"`
}

// buildPlan diffs the two sides. When useMeta is set, equal-size pairs
// present on both sides are resolved with a metadata HEAD; otherwise they are
// decided from the listing timestamps alone (--size-only). Errors are
// returned as strings so one bad key does not abort the whole sync.
func buildPlan(ctx context.Context, client *s3.Client, bucket string, upload, deleteOnly, useMeta bool,
	localDir, prefix string, local map[string]localFile, remote map[string]remoteObj,
) (plan, []string) {
	var p plan
	var errs []string

	// resolveEqualSize decides the equal-size pairs. The HEADs run in
	// parallel; a failed HEAD is an error for that key and the key is left
	// untouched (transferring on an unknown state would hide the failure).
	type pending struct {
		t  transfer
		lf localFile
		ro remoteObj
	}
	var pendingPairs []pending
	decided := func(t transfer) { p.transfers = append(p.transfers, t) }

	if upload {
		localKeys := make(map[string]struct{}, len(local))
		for rel, lf := range local {
			localKeys[rel] = struct{}{}
			t := transfer{key: prefix + rel, rel: rel, localPath: filepath.Join(localDir, filepath.FromSlash(rel))}
			ro, ok := remote[t.key]
			if !ok || ro.size != lf.size {
				decided(t)
			} else if useMeta {
				pendingPairs = append(pendingPairs, pending{t, lf, ro})
			} else {
				p.skipped++
			}
		}
		if deleteOnly {
			for key := range remote {
				rel := strings.TrimPrefix(key, prefix)
				if _, ok := localKeys[rel]; !ok {
					p.deleteRemote = append(p.deleteRemote, key)
				}
			}
		}
	} else {
		remoteRels := make(map[string]struct{}, len(remote))
		for key, ro := range remote {
			rel := strings.TrimPrefix(key, prefix)
			if rel == "" {
				continue // the prefix's own directory marker
			}
			remoteRels[rel] = struct{}{}
			t := transfer{key: key, rel: rel, localPath: filepath.Join(localDir, filepath.FromSlash(rel))}
			lf, ok := local[rel]
			if !ok || lf.size != ro.size {
				decided(t)
			} else if useMeta {
				pendingPairs = append(pendingPairs, pending{t, lf, ro})
			} else {
				p.skipped++
			}
		}
		if deleteOnly {
			for rel := range local {
				if _, ok := remoteRels[rel]; !ok {
					p.deleteLocal = append(p.deleteLocal, rel)
				}
			}
		}
	}

	if len(pendingPairs) > 0 {
		mtimes := make([]time.Time, len(pendingPairs))
		headErrs := runPool(syncConcurrency, len(pendingPairs), func(i int) error {
			t, ok, err := headMtime(ctx, client, bucket, pendingPairs[i].t.key)
			if err != nil {
				return fmt.Errorf("failed to stat s3://%s/%s: %w", bucket, pendingPairs[i].t.key, err)
			}
			if ok {
				mtimes[i] = t
			}
			return nil
		})
		for i, pd := range pendingPairs {
			if headErrs[i] != nil {
				errs = append(errs, headErrs[i].Error())
				continue
			}
			// A zero time means no parseable fingerprint was stored.
			var m *time.Time
			if !mtimes[i].IsZero() {
				m = &mtimes[i]
			}
			if decideEqualSize(upload, pd.lf, pd.ro, m) {
				decided(pd.t)
			} else {
				p.skipped++
			}
		}
	}

	sort.Slice(p.transfers, func(i, j int) bool { return p.transfers[i].key < p.transfers[j].key })
	sort.Strings(p.deleteRemote)
	sort.Strings(p.deleteLocal)
	return p, errs
}

// decideEqualSize reports whether an object present on both sides with equal
// size must still be transferred. It extends s5cmd's size-and-mtime truth
// table (sync when the source is newer or the sizes differ) with the
// uploader-stored mtime fingerprint, which closes the clock-skew blind spot:
// the timestamps are read on two machines' clocks, the fingerprint is not.
//
//	upload:   fingerprint == local mtime                → skip (exact match)
//	          fingerprint present, differs              → upload (stored copy is stale)
//	          no fingerprint, local > remote timestamp  → upload
//	          no fingerprint, otherwise                 → skip
//	download: fingerprint == local mtime                → skip (exact round trip)
//	          remote timestamp > local mtime            → download
//	          otherwise                                 → skip (a local edit is
//	                                                      preserved unless the
//	                                                      sizes differ)
func decideEqualSize(upload bool, lf localFile, ro remoteObj, meta *time.Time) bool {
	if upload {
		if meta != nil {
			return !lf.modTime.Equal(*meta)
		}
		return lf.modTime.After(ro.lastModified)
	}
	if meta != nil && lf.modTime.Equal(*meta) {
		return false
	}
	return ro.lastModified.After(lf.modTime)
}

// scanLocal walks the directory and maps each regular file's slash-separated
// relative path to its diff facts. Symlinks and other non-regular entries are
// skipped — a link's target has no place of its own in a flat key space. For
// a download the directory may not exist yet, which simply means everything
// is missing locally.
func scanLocal(root string, mustExist bool) (map[string]localFile, error) {
	if _, err := os.Stat(root); err != nil {
		if !mustExist && os.IsNotExist(err) {
			return map[string]localFile{}, nil
		}
		return nil, fmt.Errorf("%q is not an existing directory", root)
	}
	files := make(map[string]localFile)
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || !d.Type().IsRegular() {
			return nil
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		files[filepath.ToSlash(rel)] = localFile{size: info.Size(), modTime: info.ModTime()}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("failed to walk %s: %w", root, err)
	}
	return files, nil
}

// listRemote maps every object under the prefix to its diff facts. Directory
// markers (zero-byte keys ending in /) are not files and are skipped.
func listRemote(ctx context.Context, client *s3.Client, bucket, prefix string) (map[string]remoteObj, error) {
	objects := make(map[string]remoteObj)
	input := &s3.ListObjectsV2Input{Bucket: &bucket}
	if prefix != "" {
		input.Prefix = &prefix
	}
	paginator := s3.NewListObjectsV2Paginator(client, input)
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(ctx)
		if err != nil {
			return nil, fmt.Errorf("failed to list s3://%s/%s: %w", bucket, prefix, err)
		}
		for _, o := range page.Contents {
			key := *o.Key
			if strings.HasSuffix(key, "/") {
				continue
			}
			var ro remoteObj
			if o.Size != nil {
				ro.size = *o.Size
			}
			if o.LastModified != nil {
				ro.lastModified = *o.LastModified
			}
			objects[key] = ro
		}
	}
	return objects, nil
}

// headMtime reads the mtime fingerprint from an object's metadata. ok is
// false when the object carries no parseable fingerprint (uploaded by an
// older put, or by another tool).
func headMtime(ctx context.Context, client *s3.Client, bucket, key string) (time.Time, bool, error) {
	out, err := client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: &bucket,
		Key:    &key,
	})
	if err != nil {
		return time.Time{}, false, err
	}
	if v, ok := out.Metadata[mtimeMetaKey]; ok {
		if t, err := time.Parse(time.RFC3339Nano, v); err == nil {
			return t, true, nil
		}
	}
	return time.Time{}, false, nil
}

// runPool runs fn(i) for i in [0, count) with at most n in flight and returns
// the errors indexed by i, so callers can map a failure back to its item
// without a mutex.
func runPool(n, count int, fn func(i int) error) []error {
	errs := make([]error, count)
	var wg sync.WaitGroup
	sem := make(chan struct{}, n)
	for i := 0; i < count; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			errs[i] = fn(i)
		}(i)
	}
	wg.Wait()
	return errs
}
