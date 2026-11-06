package s3x

import "testing"

func TestEscapeKey(t *testing.T) {
	cases := []struct{ in, want string }{
		{"report.pdf", "report.pdf"},
		{"2026/11/report.pdf", "2026/11/report.pdf"},
		{"dir/a b.txt", "dir/a%20b.txt"},
		{"报告.pdf", "%E6%8A%A5%E5%91%8A.pdf"},
		{"a#b?c.txt", "a%23b%3Fc.txt"},
		{"100%", "100%25"},
		{"trailing/", "trailing/"},
	}
	for _, c := range cases {
		if got := escapeKey(c.in); got != c.want {
			t.Errorf("escapeKey(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestObjectURL(t *testing.T) {
	// An explicit endpoint defaults to path-style (MinIO), an explicit
	// force_path_style=false means virtual-hosted-style (COS), and no endpoint
	// means the AWS official regional endpoint.
	noPathStyle := false
	cfg := &Config{
		Services: map[string]Service{
			"minio": {Endpoint: "http://localhost:9000", Region: "us-east-1"},
			"cos": {
				Endpoint:       "https://cos.ap-hongkong.myqcloud.com",
				Region:         "ap-hongkong",
				ForcePathStyle: &noPathStyle,
			},
			"aws": {Region: "eu-west-1"},
		},
		Buckets: []Bucket{
			{Bucket: "my-archive-bucket", Alias: "archive", Service: "minio"},
			{Bucket: "agent-publish-1253609954", Alias: "publish", Service: "cos"},
			{Bucket: "plain", Alias: "plainaws", Service: "aws"},
			{Bucket: "static", Alias: "site", Service: "cos", Domain: "https://static.example.com/"},
		},
	}
	if err := cfg.validate(); err != nil {
		t.Fatalf("validate: %v", err)
	}

	cases := []struct {
		addr, want string
	}{
		{"s3://archive/2026/report.pdf", "http://localhost:9000/my-archive-bucket/2026/report.pdf"},
		{"s3://publish/index.html", "https://agent-publish-1253609954.cos.ap-hongkong.myqcloud.com/index.html"},
		{"s3://plainaws/a.txt", "https://plain.s3.eu-west-1.amazonaws.com/a.txt"},
		{"s3://site/报告.pdf", "https://static.example.com/%E6%8A%A5%E5%91%8A.pdf"},
	}
	for _, c := range cases {
		b, key, err := cfg.ResolveAddr(c.addr)
		if err != nil {
			t.Errorf("ResolveAddr(%q): %v", c.addr, err)
			continue
		}
		got, err := cfg.ObjectURL(b, key)
		if err != nil {
			t.Errorf("ObjectURL(%q): %v", c.addr, err)
			continue
		}
		if got != c.want {
			t.Errorf("ObjectURL(%q) = %q, want %q", c.addr, got, c.want)
		}
	}
}

func TestObjectURLRejectsEmptyKey(t *testing.T) {
	cfg := testConfig()
	if err := cfg.validate(); err != nil {
		t.Fatal(err)
	}
	b, _ := cfg.LookupBucket("archive")
	if _, err := cfg.ObjectURL(b, ""); err == nil {
		t.Error("an empty key should be rejected")
	}
}
