package s3x

import (
	"errors"
	"os"
	"strings"
	"testing"
)

func TestParseAddr(t *testing.T) {
	cases := []struct {
		in     string
		bucket string
		key    string
		ok     bool
	}{
		{"s3://archive/2026/report.pdf", "archive", "2026/report.pdf", true},
		{"s3://archive", "archive", "", true},
		{"s3://archive/", "archive", "", true},
		{"archive/2026/report.pdf", "archive", "2026/report.pdf", true}, // bare format
		{"", "", "", false},
		{"s3://", "", "", false},
	}
	for _, c := range cases {
		bucket, key, err := ParseAddr(c.in)
		if c.ok != (err == nil) {
			t.Errorf("ParseAddr(%q) error-state mismatch: err=%v", c.in, err)
			continue
		}
		if bucket != c.bucket || key != c.key {
			t.Errorf("ParseAddr(%q) = (%q, %q), want (%q, %q)", c.in, bucket, key, c.bucket, c.key)
		}
	}
}

func testConfig() *Config {
	return &Config{
		Services: map[string]Service{"minio": {Region: "us-east-1"}},
		Buckets: []Bucket{
			{Bucket: "my-archive-bucket", Alias: "archive", Service: "minio", Desc: "long-term archive"},
			{Bucket: "incoming", Service: "minio", Desc: "user uploads"},
		},
	}
}

// tempHome points HOME and XDG_CONFIG_HOME at a temp dir so Dir() resolves
// deterministically to <temp>/.config/agentkit regardless of the host env.
func tempHome(t *testing.T) {
	t.Helper()
	t.Setenv("HOME", t.TempDir())
	t.Setenv("XDG_CONFIG_HOME", "")
}

func TestValidateAndLookup(t *testing.T) {
	c := testConfig()
	if err := c.validate(); err != nil {
		t.Fatalf("a valid config should pass validation: %v", err)
	}

	// A bucket with an alias is addressed by its alias.
	b, err := c.LookupBucket("archive")
	if err != nil {
		t.Fatalf("lookup by alias failed: %v", err)
	}
	if b.Bucket != "my-archive-bucket" {
		t.Errorf("alias archive should point at my-archive-bucket, got %s", b.Bucket)
	}

	// A bucket without an alias is addressed by its real name.
	if _, err := c.LookupBucket("incoming"); err != nil {
		t.Errorf("lookup by real name failed: %v", err)
	}

	// The real name is no longer accepted once an alias is configured.
	if _, err := c.LookupBucket("my-archive-bucket"); err == nil {
		t.Error("the real bucket name should not be accepted once an alias is set")
	}
}

func TestValidateRejectsDuplicateNames(t *testing.T) {
	c := testConfig()
	c.Buckets = append(c.Buckets, Bucket{Bucket: "other", Alias: "archive", Service: "minio"})
	err := c.validate()
	if err == nil || !strings.Contains(err.Error(), "archive") {
		t.Errorf("duplicate names should be rejected, got: %v", err)
	}
}

func TestValidateRejectsBadName(t *testing.T) {
	c := testConfig()
	c.Buckets[1].Bucket = "Incoming-Bucket"
	if err := c.validate(); err == nil {
		t.Error("a name with uppercase letters should be rejected")
	}
}

func TestValidateRejectsDotOnRealName(t *testing.T) {
	// Dots are legal in S3 bucket names and must be allowed on the real name.
	c := testConfig()
	c.Buckets[1].Bucket = "incoming.example.com"
	if err := c.validate(); err != nil {
		t.Errorf("a dotted bucket name should be accepted, got: %v", err)
	}
}

func TestValidateRejectsBadAlias(t *testing.T) {
	// The alias is validated against the same legal-bucket-name rules.
	c := testConfig()
	c.Buckets[0].Alias = "Arch-ive" // uppercase
	if err := c.validate(); err == nil {
		t.Error("an alias with uppercase letters should be rejected")
	}
	c = testConfig()
	c.Buckets[0].Alias = "x" // too short
	if err := c.validate(); err == nil {
		t.Error("a too-short alias should be rejected")
	}
}

func TestValidateRejectsUnknownService(t *testing.T) {
	c := testConfig()
	c.Buckets[0].Service = "nope"
	err := c.validate()
	if err == nil || !strings.Contains(err.Error(), "nope") {
		t.Errorf("reference to an undefined service should be rejected, got: %v", err)
	}
}

func TestBucketHintsUsedInError(t *testing.T) {
	c := testConfig()
	if err := c.validate(); err != nil {
		t.Fatal(err)
	}
	_, err := c.LookupBucket("does-not-exist")
	if err == nil {
		t.Fatal("an unconfigured bucket should error")
	}
	msg := err.Error()
	for _, want := range []string{"archive", "long-term", "incoming", "user uploads", "s3 buckets"} {
		if !strings.Contains(msg, want) {
			t.Errorf("error should contain %q, got: %s", want, msg)
		}
	}
}

func TestLookupBucketSelfHealsNilIndex(t *testing.T) {
	c := testConfig()
	// Bypass validate() so index stays nil.
	if _, err := c.LookupBucket("archive"); err != nil {
		t.Errorf("LookupBucket should self-heal a nil index, got: %v", err)
	}
}

func TestSaveRejectsInvalidConfig(t *testing.T) {
	tempHome(t)

	c := testConfig()
	c.Buckets = append(c.Buckets, Bucket{Bucket: "other", Alias: "archive", Service: "minio"})
	if err := c.Save(); err == nil || !strings.Contains(err.Error(), "archive") {
		t.Fatalf("a config with a duplicate alias should refuse to save, got: %v", err)
	}
	if _, err := os.Stat(ConfigPath()); !errors.Is(err, os.ErrNotExist) {
		t.Error("no config file should be left behind after a rejected save")
	}
}

func TestConfigRoundTrip(t *testing.T) {
	tempHome(t)

	want := testConfig()
	if err := want.Save(); err != nil {
		t.Fatalf("Save: %v", err)
	}

	got, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(got.Buckets) != len(want.Buckets) {
		t.Fatalf("bucket count mismatch: got %d want %d", len(got.Buckets), len(want.Buckets))
	}
	for i := range want.Buckets {
		if got.Buckets[i] != want.Buckets[i] {
			t.Errorf("buckets[%d] mismatch:\ngot  %+v\nwant %+v", i, got.Buckets[i], want.Buckets[i])
		}
	}
	if got.Services["minio"].Region != "us-east-1" {
		t.Errorf("service mismatch after round trip: %+v", got.Services["minio"])
	}
}
