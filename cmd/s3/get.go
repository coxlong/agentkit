package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/aws/aws-sdk-go-v2/feature/s3/manager"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/spf13/cobra"
)

var getCmd = &cobra.Command{
	Use:   "get s3://<bucket>/<key> <local path>",
	Short: "Download a file",
	Long: `Download an object to a local path. The local path is required; the
filename is not inferred from the key. Large objects are downloaded in
concurrent parts; the data is written to a temp file first, then atomically
renamed on success, so a failure never leaves a half-written file.

  s3 get s3://archive/2026/report.pdf ./report.pdf`,
	Args: cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return err
		}
		b, key, err := cfg.ResolveAddr(args[0])
		if err != nil {
			return err
		}
		if key == "" {
			return fmt.Errorf("missing key; format: s3://%s/<key>", b.Name())
		}

		client, err := cfg.ClientFor(context.Background(), b)
		if err != nil {
			return err
		}

		dst := args[1]
		dir := filepath.Dir(dst)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return fmt.Errorf("failed to create directory %s: %w", dir, err)
		}
		tmp, err := os.CreateTemp(dir, "."+filepath.Base(dst)+".tmp")
		if err != nil {
			return fmt.Errorf("failed to create temp file: %w", err)
		}
		tmpName := tmp.Name()
		// After a successful rename the path no longer exists, so this cleanup
		// only fails harmlessly.
		defer os.Remove(tmpName)

		_, err = manager.NewDownloader(client).Download(context.Background(), tmp, &s3.GetObjectInput{
			Bucket: &b.Bucket,
			Key:    &key,
		})
		// Sync so the data is durable before the rename makes it visible.
		if err == nil {
			err = tmp.Sync()
		}
		if cerr := tmp.Close(); err == nil {
			err = cerr
		}
		if err != nil {
			return fmt.Errorf("failed to download %s/%s: %w", b.Name(), key, err)
		}
		if err := os.Rename(tmpName, dst); err != nil {
			return fmt.Errorf("failed to write %s: %w", dst, err)
		}

		fmt.Fprintf(cmd.ErrOrStderr(), "downloaded s3://%s/%s -> %s\n", b.Name(), key, dst)
		return nil
	},
}
