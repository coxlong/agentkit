// Command s3 is an object-storage tool for use by agents.
//
// An agent sees a single S3 service: addresses are always s3://<bucket>/<key>,
// and a bucket must be one of the names declared in the config file.
// Credentials, endpoints, and S3 services are invisible to the agent.
package main

import (
	"errors"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/coxlong/agentkit/internal/s3x"
)

var rootCmd = &cobra.Command{
	Use:   "s3",
	Short: "Object storage operations (for agents)",
	// Errors are printed once by main. cobra's default "Error: …" plus the full
	// usage repeats three times, which is noise for an agent that relies on the
	// error text to self-correct.
	SilenceUsage:  true,
	SilenceErrors: true,
	Long: `Operates on object storage, compatible with AWS S3, MinIO, R2, OSS, COS, etc.

Discover buckets first:

  s3 buckets

Then address objects by name:

  s3 ls    s3://archive/2026/
  s3 put   ./report.pdf s3://archive/2026/report.pdf
  s3 get   s3://archive/2026/report.pdf ./report.pdf
  s3 cat   s3://archive/2026/report.pdf
  s3 rm    s3://archive/2026/report.pdf
  s3 sync  ./reports s3://archive/2026/

A bucket is never optional; only buckets declared in the config are usable.`,
}

func main() {
	err := rootCmd.Execute()
	if err == nil {
		return
	}
	// Ctrl+C in an interactive form is an intentional cancel, so print just
	// "canceled" without the "error:" prefix.
	if errors.Is(err, errCanceled) {
		fmt.Fprintln(os.Stderr, errCanceled)
		os.Exit(1)
	}
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}

func init() {
	rootCmd.AddCommand(bucketsCmd)
	rootCmd.AddCommand(lsCmd)
	rootCmd.AddCommand(putCmd)
	rootCmd.AddCommand(getCmd)
	rootCmd.AddCommand(catCmd)
	rootCmd.AddCommand(rmCmd)
	rootCmd.AddCommand(syncCmd)
	rootCmd.AddCommand(configCmd)
}

// loadConfig reads the config. Any config error should terminate the command
// outright rather than degrade.
func loadConfig() (*s3x.Config, error) {
	cfg, err := s3x.Load()
	if err != nil {
		return nil, err
	}
	if len(cfg.Buckets) == 0 {
		return nil, fmt.Errorf("no buckets configured yet; run \"s3 config\" to add some")
	}
	return cfg, nil
}
