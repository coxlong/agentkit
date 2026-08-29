package main

import (
	"context"
	"fmt"
	"io"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/spf13/cobra"
)

var catCmd = &cobra.Command{
	Use:   "cat s3://<bucket>/<key>",
	Short: "Write object content to stdout",
	Long: `Write an object's content to stdout, for easy viewing or piping into the
next command.

  s3 cat s3://archive/2026/report.md`,
	Args: cobra.ExactArgs(1),
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

		out, err := client.GetObject(context.Background(), &s3.GetObjectInput{
			Bucket: &b.Bucket,
			Key:    &key,
		})
		if err != nil {
			return fmt.Errorf("failed to read %s/%s: %w", b.Name(), key, err)
		}
		defer out.Body.Close()

		if _, err := io.Copy(cmd.OutOrStdout(), out.Body); err != nil {
			return fmt.Errorf("failed to output %s/%s: %w", b.Name(), key, err)
		}
		return nil
	},
}
