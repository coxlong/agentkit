package main

import (
	"context"
	"fmt"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/spf13/cobra"
)

// objectView is the structured output of ls.
type objectView struct {
	Key          string    `json:"key"`
	Size         int64     `json:"size"`
	LastModified time.Time `json:"last_modified"`
	IsPrefix     bool      `json:"is_prefix"`
}

var lsCmd = &cobra.Command{
	Use:   "ls s3://<bucket>/<prefix>",
	Short: "List objects",
	Long: `List objects, non-recursive by default (folded at /), matching aws s3 ls.

  s3 ls s3://archive/2026/
  s3 ls s3://archive/2026/ --recursive
  s3 ls s3://archive/2026/ --json

A bucket is never optional.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return err
		}
		b, prefix, err := cfg.ResolveAddr(args[0])
		if err != nil {
			return err
		}

		recursive, _ := cmd.Flags().GetBool("recursive")
		jsonOut, _ := cmd.Flags().GetBool("json")

		client, err := cfg.ClientFor(context.Background(), b)
		if err != nil {
			return err
		}

		input := &s3.ListObjectsV2Input{Bucket: &b.Bucket}
		if prefix != "" {
			input.Prefix = &prefix
		}
		if !recursive {
			input.Delimiter = aws.String("/")
		}

		// displayPrefix is what we strip from a key to show it relative to the
		// requested prefix. Only strip when the prefix ends with "/"; otherwise
		// a prefix like "2026" would truncate keys such as "2026/x.txt" into
		// "26/x.txt".
		displayPrefix := ""
		if strings.HasSuffix(prefix, "/") {
			displayPrefix = prefix
		}

		var views []objectView
		paginator := s3.NewListObjectsV2Paginator(client, input)
		for paginator.HasMorePages() {
			page, err := paginator.NextPage(context.Background())
			if err != nil {
				return fmt.Errorf("failed to list %s: %w", b.Name(), err)
			}
			for _, p := range page.CommonPrefixes {
				views = append(views, objectView{
					Key:      strings.TrimPrefix(*p.Prefix, displayPrefix),
					IsPrefix: true,
				})
			}
			for _, o := range page.Contents {
				v := objectView{
					Key:      strings.TrimPrefix(*o.Key, displayPrefix),
					IsPrefix: false,
				}
				if o.Size != nil {
					v.Size = *o.Size
				}
				if o.LastModified != nil {
					v.LastModified = *o.LastModified
				}
				views = append(views, v)
			}
		}

		if jsonOut {
			if views == nil {
				views = []objectView{}
			}
			return emitJSON(cmd.OutOrStdout(), views)
		}
		if len(views) == 0 {
			return nil
		}

		w := tabwriter.NewWriter(cmd.OutOrStdout(), 0, 0, 2, ' ', 0)
		for _, v := range views {
			if v.IsPrefix {
				fmt.Fprintf(w, "%s\t%s\t%s\n", "", "PRE", v.Key)
				continue
			}
			fmt.Fprintf(w, "%s\t%d\t%s\n",
				v.LastModified.Local().Format("2006-01-02 15:04:05"), v.Size, v.Key)
		}
		return w.Flush()
	},
}

func init() {
	lsCmd.Flags().Bool("recursive", false, "Recursively list, without folding at /")
	lsCmd.Flags().Bool("json", false, "JSON output")
}
