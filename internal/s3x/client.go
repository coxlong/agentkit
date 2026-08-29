// Package s3x wraps S3 client construction, config loading, and secret storage
// for use by cmd/s3.
//
// Secrets have exactly one source: ~/.config/agentkit/s3/secrets.age
// (encrypted with a machine-ID-derived key). No credential environment
// variables are read and the AWS SDK's default credential chain is not enabled
// — a single source of credentials avoids implicit overrides. The config
// directory itself does follow the XDG convention ($XDG_CONFIG_HOME).
package s3x

import (
	"context"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// ClientFor builds an S3 client for the service a bucket belongs to.
//
// The secret is used only in memory; it never lands on disk or on the command
// line.
func (c *Config) ClientFor(ctx context.Context, b *Bucket) (*s3.Client, error) {
	svc, ok := c.Services[b.Service]
	if !ok {
		return nil, fmt.Errorf("bucket %q references undefined service %q", b.Name(), b.Service)
	}
	if svc.Region == "" {
		return nil, fmt.Errorf("service %q is missing region", b.Service)
	}

	secrets, err := LoadSecrets(SecretsPath())
	if err != nil {
		return nil, err
	}
	secret, ok := secrets[b.Service]
	if !ok || secret.SecretAccessKey == "" {
		return nil, fmt.Errorf("service %q has no secret_access_key; set it via \"s3 config\"", b.Service)
	}

	// Self-hosted services (MinIO/R2/OSS) need path-style; AWS official
	// endpoints need virtual-hosted-style.
	forcePathStyle := svc.Endpoint != ""
	if svc.ForcePathStyle != nil {
		forcePathStyle = *svc.ForcePathStyle
	}

	client := s3.NewFromConfig(aws.Config{
		Region: svc.Region,
		Credentials: credentials.NewStaticCredentialsProvider(
			svc.AccessKeyID, secret.SecretAccessKey, secret.SessionToken,
		),
	}, func(o *s3.Options) {
		if svc.Endpoint != "" {
			o.BaseEndpoint = aws.String(svc.Endpoint)
		}
		o.UsePathStyle = forcePathStyle
	})
	return client, nil
}
