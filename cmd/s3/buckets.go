package main

import (
	"fmt"
	"text/tabwriter"

	"github.com/spf13/cobra"
)

// bucketView is what the agent sees for a bucket: only the name and
// description, with no credential info. Whether the underlying config uses an
// alias or a real bucket name, this column is what the agent sees as the
// bucket.
type bucketView struct {
	Bucket string `json:"bucket"`
	Desc   string `json:"desc"`
}

var bucketsCmd = &cobra.Command{
	Use:   "buckets",
	Short: "List configured buckets",
	Long: `List the buckets declared in the config file, along with their descriptions.

This is the agent's discovery entry point: use it first to pick a bucket, then
operate with the returned names.`,
	Args: cobra.NoArgs,
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := loadConfig()
		if err != nil {
			return err
		}

		views := make([]bucketView, 0, len(cfg.Buckets))
		for i := range cfg.Buckets {
			views = append(views, bucketView{
				Bucket: cfg.Buckets[i].Name(),
				Desc:   cfg.Buckets[i].Desc,
			})
		}

		if jsonOut, _ := cmd.Flags().GetBool("json"); jsonOut {
			return emitJSON(cmd.OutOrStdout(), views)
		}

		w := tabwriter.NewWriter(cmd.OutOrStdout(), 0, 0, 2, ' ', 0)
		fmt.Fprintln(w, "BUCKET\tDESC")
		for _, v := range views {
			fmt.Fprintf(w, "%s\t%s\n", v.Bucket, v.Desc)
		}
		return w.Flush()
	},
}

func init() {
	bucketsCmd.Flags().Bool("json", false, "JSON output")
}
