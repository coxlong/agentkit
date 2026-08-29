package s3x

import (
	"bytes"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"

	"github.com/BurntSushi/toml"
)

// Service is one S3-compatible service (AWS S3, MinIO, R2, OSS, COS, ...):
// its connection parameters and identity. It is never exposed to the agent.
type Service struct {
	Endpoint       string `toml:"endpoint"`
	Region         string `toml:"region"`
	AccessKeyID    string `toml:"access_key_id"`
	ForcePathStyle *bool  `toml:"force_path_style"`
}

// Bucket maps an agent-visible name to a real bucket and the S3 service it
// belongs to.
type Bucket struct {
	Bucket  string `toml:"bucket"`
	Alias   string `toml:"alias"`
	Service string `toml:"service"`
	Desc    string `toml:"desc"`
}

// Name returns the agent-visible name: the alias if set, otherwise the real
// bucket name.
func (b Bucket) Name() string {
	if b.Alias != "" {
		return b.Alias
	}
	return b.Bucket
}

// Config corresponds to ~/.config/agentkit/s3/config.toml and holds no secrets.
type Config struct {
	Services map[string]Service `toml:"services"`
	Buckets  []Bucket           `toml:"buckets"`

	index map[string]*Bucket
}

// Dir returns the base config directory for the agentkit tools.
//
// It follows the XDG base-directory convention: $XDG_CONFIG_HOME/agentkit when
// set, otherwise ~/.config/agentkit. Each tool owns a subdirectory (e.g. s3)
// under it, leaving room for future tools.
func Dir() string {
	if xdg := os.Getenv("XDG_CONFIG_HOME"); xdg != "" {
		return filepath.Join(xdg, "agentkit")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join(".config", "agentkit")
	}
	return filepath.Join(home, ".config", "agentkit")
}

// ConfigPath returns the s3 config file path.
func ConfigPath() string { return filepath.Join(Dir(), "s3", "config.toml") }

// SecretsPath returns the s3 encrypted secret-key-table path.
func SecretsPath() string { return filepath.Join(Dir(), "s3", "secrets.age") }

// Load reads and validates the config. A missing config file returns an empty
// config; it is up to the individual command to report an error as needed.
func Load() (*Config, error) {
	var c Config
	if _, err := toml.DecodeFile(ConfigPath(), &c); err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			return nil, fmt.Errorf("failed to read %s: %w", ConfigPath(), err)
		}
	}
	if err := c.validate(); err != nil {
		return nil, err
	}
	return &c, nil
}

// Save validates and writes the config with 0600 permissions via an atomic
// replace. It refuses to write an invalid config to disk — a corrupt config
// would break every subsequent command.
func (c *Config) Save() error {
	if err := c.validate(); err != nil {
		return err
	}
	var buf bytes.Buffer
	if err := toml.NewEncoder(&buf).Encode(c); err != nil {
		return fmt.Errorf("failed to serialize config: %w", err)
	}
	return atomicWrite(ConfigPath(), buf.Bytes(), 0o600)
}

// validBucketName reports whether name is a legal S3 bucket name. It applies
// to both the real bucket name and the agent-visible alias.
//
// Rules: 3-63 characters, lowercase letters / digits / dots / hyphens only,
// must start and end with a letter or digit, no adjacent dots, not in IP
// address form, and not prefixed with "xn--".
func validBucketName(name string) bool {
	if name == "" || len(name) < 3 || len(name) > 63 {
		return false
	}
	if name[0] == '.' || name[0] == '-' || name[len(name)-1] == '.' || name[len(name)-1] == '-' {
		return false
	}
	if strings.Contains(name, "..") {
		return false
	}
	if strings.HasPrefix(name, "xn--") {
		return false
	}
	if net.ParseIP(name) != nil {
		return false
	}
	for _, r := range name {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9', r == '.', r == '-':
		default:
			return false
		}
	}
	return true
}

// validate checks the config and builds the bucket name index.
//
// Constraints: bucket names are unique globally (across services), match legal
// S3 bucket names, and each bucket's service must be defined. Duplicate names
// are rejected outright rather than resolved implicitly.
func (c *Config) validate() error {
	c.index = make(map[string]*Bucket, len(c.Buckets))
	for i := range c.Buckets {
		b := &c.Buckets[i]
		name := b.Name()

		if b.Bucket == "" {
			return fmt.Errorf("buckets[%d]: missing bucket field", i)
		}
		if !validBucketName(b.Bucket) {
			return fmt.Errorf("bucket name %q is not a valid S3 bucket name (3-63 chars, lowercase letters, digits, dots and hyphens, start/end with a letter or digit, no adjacent dots, not an IP address)", b.Bucket)
		}
		if b.Alias != "" && !validBucketName(b.Alias) {
			return fmt.Errorf("alias %q is not a valid name (3-63 chars, lowercase letters, digits, dots and hyphens, start/end with a letter or digit, no adjacent dots, not an IP address)", b.Alias)
		}
		if b.Service == "" {
			return fmt.Errorf("bucket %q: missing service field", name)
		}
		if _, ok := c.Services[b.Service]; !ok {
			if len(c.Services) == 0 {
				return fmt.Errorf("bucket %q references service %q, but no service is defined yet", name, b.Service)
			}
			return fmt.Errorf("bucket %q references undefined service %q", name, b.Service)
		}
		if prev, ok := c.index[name]; ok {
			if prev.Bucket == b.Bucket && prev.Alias == b.Alias {
				return fmt.Errorf("bucket name %q is defined more than once", name)
			}
			return fmt.Errorf("bucket name %q conflicts: %q and %q resolve to the same name", name, prev.Bucket, b.Bucket)
		}
		c.index[name] = b
	}
	return nil
}

// LookupBucket finds a bucket by its agent-visible name.
//
// A bucket with an alias is addressed only by the alias; the real name is no
// longer accepted — a bucket exposes exactly one name.
func (c *Config) LookupBucket(name string) (*Bucket, error) {
	if c.index == nil {
		if err := c.validate(); err != nil {
			return nil, err
		}
	}
	if b, ok := c.index[name]; ok {
		return b, nil
	}
	return nil, fmt.Errorf("unknown bucket %q; available: %s\nrun \"s3 buckets\" for the full list", name, c.BucketHints())
}

// BucketHints joins the available buckets and their descriptions into one
// line, embedded in errors so the agent can self-correct.
func (c *Config) BucketHints() string {
	if len(c.Buckets) == 0 {
		return "(no buckets configured yet; run \"s3 config\" to add some)"
	}
	parts := make([]string, 0, len(c.Buckets))
	for i := range c.Buckets {
		b := &c.Buckets[i]
		if b.Desc == "" {
			parts = append(parts, b.Name())
			continue
		}
		desc := b.Desc
		if len([]rune(desc)) > 16 {
			desc = string([]rune(desc)[:16]) + "…"
		}
		parts = append(parts, fmt.Sprintf("%s (%s)", b.Name(), desc))
	}
	return strings.Join(parts, ", ")
}

// ParseAddr parses s3://<bucket>/<key>.
//
// A bare archive/key address (without the scheme) is also accepted, absorbing
// the occasional LLM typo where the scheme is omitted.
func ParseAddr(addr string) (bucket, key string, err error) {
	rest := strings.TrimPrefix(strings.TrimSpace(addr), "s3://")
	rest = strings.TrimPrefix(rest, "/")
	if rest == "" {
		return "", "", fmt.Errorf("empty address; format: s3://<bucket>/<key>")
	}
	bucket, key, _ = strings.Cut(rest, "/")
	if bucket == "" {
		return "", "", fmt.Errorf("cannot parse a bucket from %q", addr)
	}
	return bucket, key, nil
}

// ResolveAddr parses an address and looks up the corresponding bucket config.
func (c *Config) ResolveAddr(addr string) (*Bucket, string, error) {
	name, key, err := ParseAddr(addr)
	if err != nil {
		return nil, "", err
	}
	b, err := c.LookupBucket(name)
	if err != nil {
		return nil, "", err
	}
	return b, key, nil
}
