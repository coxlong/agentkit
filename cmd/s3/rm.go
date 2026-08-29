package main

import (
	"context"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"

	"github.com/coxlong/agentkit/internal/s3x"
	"github.com/spf13/cobra"
)

var rmCmd = &cobra.Command{
	Use:   "rm s3://<bucket>/<key>",
	Short: "Delete an object",
	Long: `Delete a single object. Add --recursive to delete by prefix.

  s3 rm s3://archive/2026/report.pdf
  s3 rm s3://archive/2026/ --recursive`,
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

		recursive, _ := cmd.Flags().GetBool("recursive")
		if !recursive {
			return deleteOne(cmd, cfg, b, key)
		}
		return deletePrefix(cmd, cfg, b, key)
	},
}

func deleteOne(cmd *cobra.Command, cfg *s3x.Config, b *s3x.Bucket, key string) error {
	client, err := cfg.ClientFor(context.Background(), b)
	if err != nil {
		return err
	}
	if _, err := client.DeleteObject(context.Background(), &s3.DeleteObjectInput{
		Bucket: &b.Bucket,
		Key:    &key,
	}); err != nil {
		return fmt.Errorf("failed to delete %s/%s: %w", b.Name(), key, err)
	}
	fmt.Fprintf(cmd.ErrOrStderr(), "deleted s3://%s/%s\n", b.Name(), key)
	return nil
}

// deletePrefix deletes every object under a prefix. The keys are gathered
// first (so the count can be reported before anything is deleted), then removed
// in batches of at most 1000 (the S3 DeleteObjects limit).
func deletePrefix(cmd *cobra.Command, cfg *s3x.Config, b *s3x.Bucket, prefix string) error {
	client, err := cfg.ClientFor(context.Background(), b)
	if err != nil {
		return err
	}

	var keys []string
	paginator := s3.NewListObjectsV2Paginator(client, &s3.ListObjectsV2Input{
		Bucket: &b.Bucket,
		Prefix: &prefix,
	})
	for paginator.HasMorePages() {
		page, err := paginator.NextPage(context.Background())
		if err != nil {
			return fmt.Errorf("failed to list %s/%s: %w", b.Name(), prefix, err)
		}
		for _, o := range page.Contents {
			keys = append(keys, *o.Key)
		}
	}

	if len(keys) == 0 {
		fmt.Fprintf(cmd.ErrOrStderr(), "no objects under s3://%s/%s\n", b.Name(), prefix)
		return nil
	}

	// Report the impact before deleting anything.
	fmt.Fprintf(cmd.ErrOrStderr(), "deleting %d object(s) under s3://%s/%s\n", len(keys), b.Name(), prefix)

	for start := 0; start < len(keys); start += 1000 {
		end := min(start+1000, len(keys))
		batch := keys[start:end]
		objects := make([]types.ObjectIdentifier, 0, len(batch))
		for _, k := range batch {
			objects = append(objects, types.ObjectIdentifier{Key: aws.String(k)})
		}
		out, err := client.DeleteObjects(context.Background(), &s3.DeleteObjectsInput{
			Bucket: &b.Bucket,
			Delete: &types.Delete{Objects: objects, Quiet: aws.Bool(true)},
		})
		if err != nil {
			return fmt.Errorf("failed to batch delete: %w", err)
		}
		for _, e := range out.Errors {
			return fmt.Errorf("failed to delete %s: %s", aws.ToString(e.Key), aws.ToString(e.Message))
		}
	}

	fmt.Fprintf(cmd.ErrOrStderr(), "deleted s3://%s/%s (%d object(s))\n", b.Name(), prefix, len(keys))
	return nil
}

func init() {
	rmCmd.Flags().Bool("recursive", false, "Delete by prefix")
}
