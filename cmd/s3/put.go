package main

import (
	"context"
	"fmt"
	"mime"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/feature/s3/manager"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/spf13/cobra"
)

// mtimeMetaKey is the object-metadata key stamping the source file's
// modification time at upload. It is the fingerprint s3 sync compares: equal
// sizes prove nothing when a file is edited in place, and the remote
// LastModified is an upload timestamp read on the server's clock, not the
// source file's mtime.
const mtimeMetaKey = "mtime"

// platformMimeMisses covers common formats that mime.TypeByExtension misses:
// they are absent from its builtin table, so it falls back to system files
// (/etc/mime.types and friends), which slim container images do not ship —
// there .md would upload as application/octet-stream. A system table, when
// present, still wins via TypeByExtension; this only fills the gaps.
var platformMimeMisses = map[string]string{
	".md":       "text/markdown; charset=utf-8",
	".markdown": "text/markdown; charset=utf-8",
	".yaml":     "application/yaml",
	".yml":      "application/yaml",
	".toml":     "application/toml",
}

// contentType infers the Content-Type of a local file from its extension.
func contentType(path string) string {
	ext := strings.ToLower(filepath.Ext(path))
	if ct := mime.TypeByExtension(ext); ct != "" {
		return ct
	}
	return platformMimeMisses[ext]
}

var putCmd = &cobra.Command{
	Use:   "put <local file> s3://<bucket>/<key>",
	Short: "Upload a file",
	Long: `Upload a local file to object storage. Files above the multipart
threshold are automatically split into parts.

  s3 put ./report.pdf s3://archive/2026/report.pdf`,
	Args: cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return err
		}
		b, key, err := cfg.ResolveAddr(args[1])
		if err != nil {
			return err
		}
		if key == "" {
			return fmt.Errorf("missing key; format: s3://%s/<key>", b.Name())
		}
		if strings.HasSuffix(key, "/") {
			return fmt.Errorf("key %q must not end with a slash", key)
		}

		client, err := cfg.ClientFor(context.Background(), b)
		if err != nil {
			return err
		}

		if err := uploadFile(context.Background(), client, b.Bucket, key, args[0]); err != nil {
			return err
		}

		fmt.Fprintf(cmd.ErrOrStderr(), "uploaded %s -> s3://%s/%s\n", args[0], b.Name(), key)
		return nil
	},
}

// uploadFile uploads one local file to bucket/key. Files above the multipart
// threshold are split automatically; Content-Type is inferred from the
// extension, and the file's mtime is stamped into the object metadata (the
// fingerprint s3 sync compares).
func uploadFile(ctx context.Context, client *s3.Client, bucket, key, path string) error {
	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("failed to open local file: %w", err)
	}
	defer f.Close()

	input := &s3.PutObjectInput{
		Bucket: &bucket,
		Key:    &key,
		Body:   f,
	}
	// Infer Content-Type from the extension so downloaders and browsers do
	// not have to guess.
	if ct := contentType(path); ct != "" {
		input.ContentType = &ct
	}
	if info, err := f.Stat(); err == nil {
		input.Metadata = map[string]string{
			mtimeMetaKey: info.ModTime().UTC().Format(time.RFC3339Nano),
		}
	}
	if _, err := manager.NewUploader(client).Upload(ctx, input); err != nil {
		return fmt.Errorf("failed to upload to %s/%s: %w", bucket, key, err)
	}
	return nil
}
