package s3x

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"

	"filippo.io/age"
	"github.com/crowdsecurity/machineid"
)

// buildSalt is a compile-time injectable extra salt, empty by default.
//
//	go build -ldflags "-X github.com/coxlong/agentkit/internal/s3x.buildSalt=<random>"
//
// Injecting it changes the derived key on every recompile, so previously stored
// ciphertext becomes undecryptable. It stops "reproducing the key from the
// public source" but is not a security boundary: a -X string lives plaintext in
// the binary's data segment and can be extracted with `strings`.
var buildSalt = ""

const appSalt = "agentkit/s3/v1"

// scryptWorkFactor is below age's default of 18. The key is derived from a
// 256-bit HMAC output that already has enough entropy; scrypt here is just a
// wrapper around the standard format, so the default cost is unnecessary.
const scryptWorkFactor = 15

// ServiceSecret holds the secret fields for a single S3 service.
type ServiceSecret struct {
	SecretAccessKey string `json:"secret_access_key"`
	SessionToken    string `json:"session_token"`
}

// Secrets is the secret-key table organized by service, i.e. the plaintext
// structure of a decrypted secrets.age file.
type Secrets map[string]ServiceSecret

// deriveKey derives the age passphrase from the machine ID.
func deriveKey(machineID string) string {
	mac := hmac.New(sha256.New, []byte(machineID))
	mac.Write([]byte(appSalt + buildSalt))
	return hex.EncodeToString(mac.Sum(nil))
}

// LoadSecrets reads and decrypts the secret-key table. A missing file returns
// an empty table and is not an error — having no service configured yet is a
// valid state.
func LoadSecrets(path string) (Secrets, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return Secrets{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to read %s: %w", path, err)
	}
	return decryptSecrets(bytes.NewReader(data))
}

// SaveSecrets encrypts and writes the secret-key table with 0600 permissions.
func SaveSecrets(path string, s Secrets) error {
	plain, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to serialize secret-key table: %w", err)
	}

	machineID, err := machineid.ID()
	if err != nil {
		return fmt.Errorf("failed to get machine ID: %w", err)
	}
	password := deriveKey(machineID)

	recipient, err := age.NewScryptRecipient(password)
	if err != nil {
		return fmt.Errorf("failed to create age recipient: %w", err)
	}
	recipient.SetWorkFactor(scryptWorkFactor)

	var buf bytes.Buffer
	w, err := age.Encrypt(&buf, recipient)
	if err != nil {
		return fmt.Errorf("failed to encrypt: %w", err)
	}
	if _, err := w.Write(plain); err != nil {
		return fmt.Errorf("failed to encrypt: %w", err)
	}
	if err := w.Close(); err != nil {
		return fmt.Errorf("failed to encrypt: %w", err)
	}

	if err := atomicWrite(path, buf.Bytes(), 0o600); err != nil {
		return err
	}
	return nil
}

func decryptSecrets(src io.Reader) (Secrets, error) {
	machineID, err := machineid.ID()
	if err != nil {
		return nil, fmt.Errorf("failed to get machine ID: %w", err)
	}

	identity, err := age.NewScryptIdentity(deriveKey(machineID))
	if err != nil {
		return nil, fmt.Errorf("failed to create age identity: %w", err)
	}
	identity.SetMaxWorkFactor(scryptWorkFactor)

	r, err := age.Decrypt(src, identity)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt secret-key table (machine ID changed since encryption?): %w", err)
	}
	plain, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt secret-key table: %w", err)
	}

	var s Secrets
	if err := json.Unmarshal(plain, &s); err != nil {
		return nil, fmt.Errorf("failed to parse secret-key table: %w", err)
	}
	return s, nil
}
