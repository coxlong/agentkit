package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var urlCmd = &cobra.Command{
	Use:   "url s3://<bucket>/<key>",
	Short: "Print the public URL of an object",
	Long: `Print the address an object is served at, for handing a link to a human.

The URL is only built, never signed or verified: a private bucket answers 403
there, and an unbound custom domain does not resolve.`,
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
		u, err := cfg.ObjectURL(b, key)
		if err != nil {
			return err
		}
		_, err = fmt.Fprintln(cmd.OutOrStdout(), u)
		return err
	},
}
