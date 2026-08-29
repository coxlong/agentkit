package s3x

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/crowdsecurity/machineid"
)

// requireMachineID skips a test that derives the encryption key when the host
// has no machine ID (e.g. slim containers, CI), so `go test ./...` still passes
// there. The runtime behavior is unchanged: the tool still errors out without a
// machine ID.
func requireMachineID(t *testing.T) {
	t.Helper()
	if _, err := machineid.ID(); err != nil {
		t.Skipf("no machine ID available, skipping: %v", err)
	}
}

func TestSecretsRoundTrip(t *testing.T) {
	requireMachineID(t)
	path := filepath.Join(t.TempDir(), "secrets.age")

	want := Secrets{
		"minio":  {SecretAccessKey: "s3cr3t-minio", SessionToken: ""},
		"aliyun": {SecretAccessKey: "s3cr3t-aliyun", SessionToken: "token-123"},
	}
	if err := SaveSecrets(path, want); err != nil {
		t.Fatalf("SaveSecrets: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("ciphertext permissions = %o, want 600", perm)
	}

	got, err := LoadSecrets(path)
	if err != nil {
		t.Fatalf("LoadSecrets: %v", err)
	}
	if got["minio"] != want["minio"] || got["aliyun"] != want["aliyun"] {
		t.Errorf("content mismatch after round trip: got %v, want %v", got, want)
	}
}

func TestSaveCreatesMissingDir(t *testing.T) {
	requireMachineID(t)
	// On the first add run the config dir does not exist yet, so SaveSecrets
	// must create it, or an operator's first config on a fresh machine would
	// fail.
	path := filepath.Join(t.TempDir(), "agentkit", "secrets.age")

	want := Secrets{"minio": {SecretAccessKey: "s3cr3t"}}
	if err := SaveSecrets(path, want); err != nil {
		t.Fatalf("SaveSecrets should create the missing directory: %v", err)
	}
	got, err := LoadSecrets(path)
	if err != nil {
		t.Fatalf("LoadSecrets: %v", err)
	}
	if got["minio"] != want["minio"] {
		t.Errorf("content mismatch after round trip: got %v, want %v", got, want)
	}
}

func TestLoadSecretsMissingFileIsEmpty(t *testing.T) {
	got, err := LoadSecrets(filepath.Join(t.TempDir(), "nope.age"))
	if err != nil {
		t.Fatalf("a missing file should return an empty table, got an error: %v", err)
	}
	if len(got) != 0 {
		t.Errorf("want an empty table, got %v", got)
	}
}

func TestSecretsAreNotPlaintext(t *testing.T) {
	requireMachineID(t)
	path := filepath.Join(t.TempDir(), "secrets.age")
	secret := "super-secret-key-value"
	if err := SaveSecrets(path, Secrets{"p": {SecretAccessKey: secret}}); err != nil {
		t.Fatal(err)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), secret) {
		t.Error("plaintext secret appeared in the ciphertext")
	}
}
