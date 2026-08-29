package main

import (
	"context"
	"fmt"
	"mime"
	"os"
	"path/filepath"
	"strings"

	"github.com/aws/aws-sdk-go-v2/feature/s3/manager"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/spf13/cobra"
)

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

		f, err := os.Open(args[0])
		if err != nil {
			return fmt.Errorf("failed to open local file: %w", err)
		}
		defer f.Close()

		client, err := cfg.ClientFor(context.Background(), b)
		if err != nil {
			return err
		}

		input := &s3.PutObjectInput{
			Bucket: &b.Bucket,
			Key:    &key,
			Body:   f,
		}
		// Infer Content-Type from the extension so downloaders and browsers do
		// not have to guess.
		if ct := mime.TypeByExtension(filepath.Ext(args[0])); ct != "" {
			input.ContentType = &ct
		}
		if _, err := manager.NewUploader(client).Upload(context.Background(), input); err != nil {
			return fmt.Errorf("failed to upload to %s/%s: %w", b.Name(), key, err)
		}

		fmt.Fprintf(cmd.ErrOrStderr(), "uploaded %s -> s3://%s/%s\n", args[0], b.Name(), key)
		return nil
	},
}
