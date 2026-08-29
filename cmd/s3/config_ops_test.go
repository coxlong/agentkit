package main

import (
	"testing"

	"github.com/coxlong/agentkit/internal/s3x"
)

// tempHome points HOME and XDG_CONFIG_HOME at a temp dir so Dir() resolves
// deterministically to <temp>/.config/agentkit regardless of the host env.
func tempHome(t *testing.T) {
	t.Helper()
	t.Setenv("HOME", t.TempDir())
	t.Setenv("XDG_CONFIG_HOME", "")
}

func TestAddServicePersists(t *testing.T) {
	tempHome(t)

	cfg, err := s3x.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if err := addService(cfg, "minio", "http://localhost:9000", "us-east-1", "ak", nil, "sk"); err != nil {
		t.Fatalf("addService: %v", err)
	}

	got, err := s3x.Load()
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if got.Services["minio"].Region != "us-east-1" || got.Services["minio"].AccessKeyID != "ak" {
		t.Errorf("service not persisted: %+v", got.Services["minio"])
	}
	secrets, err := s3x.LoadSecrets(s3x.SecretsPath())
	if err != nil {
		t.Fatalf("LoadSecrets: %v", err)
	}
	if secrets["minio"].SecretAccessKey != "sk" {
		t.Errorf("secret not persisted: %+v", secrets["minio"])
	}
}

func TestUpdateServiceKeepsSecretUnlessGiven(t *testing.T) {
	tempHome(t)

	cfg, err := s3x.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if err := addService(cfg, "minio", "http://old", "us-east-1", "ak", nil, "sk"); err != nil {
		t.Fatalf("addService: %v", err)
	}

	// Update endpoint/AK without touching the secret.
	cfg2, err := s3x.Load()
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if err := updateService(cfg2, "minio", "http://new", "us-east-1", "ak2", nil, ""); err != nil {
		t.Fatalf("updateService: %v", err)
	}

	got, err := s3x.Load()
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if got.Services["minio"].Endpoint != "http://new" || got.Services["minio"].AccessKeyID != "ak2" {
		t.Errorf("service not updated: %+v", got.Services["minio"])
	}
	secrets, err := s3x.LoadSecrets(s3x.SecretsPath())
	if err != nil {
		t.Fatalf("LoadSecrets: %v", err)
	}
	if secrets["minio"].SecretAccessKey != "sk" {
		t.Errorf("secret should be kept when not given: %+v", secrets["minio"])
	}
}

func TestDeleteServiceCascadesBuckets(t *testing.T) {
	tempHome(t)

	cfg, err := s3x.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if err := addService(cfg, "minio", "http://localhost:9000", "us-east-1", "ak", nil, "sk"); err != nil {
		t.Fatalf("addService: %v", err)
	}
	if err := addBucket(cfg, "my-archive-bucket", "archive", "minio", "long-term"); err != nil {
		t.Fatalf("addBucket: %v", err)
	}
	// A second bucket that stays on another service must survive.
	if err := addService(cfg, "aws", "http://aws", "us-east-1", "ak2", nil, "sk2"); err != nil {
		t.Fatalf("addService(aws): %v", err)
	}
	if err := addBucket(cfg, "reports", "", "aws", "reports"); err != nil {
		t.Fatalf("addBucket: %v", err)
	}

	if err := deleteService(cfg, "minio"); err != nil {
		t.Fatalf("deleteService: %v", err)
	}
	got, err := s3x.Load()
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if _, ok := got.Services["minio"]; ok {
		t.Error("service should be removed")
	}
	for _, b := range got.Buckets {
		if b.Name() == "archive" {
			t.Error("the service's bucket should be removed with it (cascade)")
		}
	}
	if _, ok := got.Services["aws"]; !ok || len(got.Buckets) != 1 {
		t.Errorf("an unrelated service and bucket should be untouched, got services=%v buckets=%+v", got.Services, got.Buckets)
	}
}

func TestDeleteBucketRemovesFromConfig(t *testing.T) {
	tempHome(t)

	cfg, err := s3x.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if err := addService(cfg, "minio", "http://localhost:9000", "us-east-1", "ak", nil, "sk"); err != nil {
		t.Fatalf("addService: %v", err)
	}
	if err := addBucket(cfg, "my-archive-bucket", "archive", "minio", "long-term"); err != nil {
		t.Fatalf("addBucket: %v", err)
	}

	if err := deleteBucket(cfg, "archive"); err != nil {
		t.Fatalf("deleteBucket: %v", err)
	}
	got, err := s3x.Load()
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if len(got.Buckets) != 0 {
		t.Errorf("bucket should be removed, got %+v", got.Buckets)
	}
}
