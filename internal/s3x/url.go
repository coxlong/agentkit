package s3x

import (
	"fmt"
	"net/url"
	"strings"
)

// ObjectURL builds an object's public address. The bucket's custom domain wins
// when set; otherwise the address comes from the service endpoint. The result is
// not signed or verified — whether it answers is up to the ACL and the domain
// binding.
func (c *Config) ObjectURL(b *Bucket, key string) (string, error) {
	if key == "" {
		return "", fmt.Errorf("empty key; format: s3://<bucket>/<key>")
	}
	base, err := c.baseURL(b)
	if err != nil {
		return "", err
	}
	return base + "/" + escapeKey(key), nil
}

func (c *Config) baseURL(b *Bucket) (string, error) {
	if b.Domain != "" {
		return b.Domain, nil
	}

	svc, ok := c.Services[b.Service]
	if !ok {
		return "", fmt.Errorf("bucket %q references undefined service %q", b.Name(), b.Service)
	}

	if svc.Endpoint == "" {
		if svc.Region == "" {
			return "", fmt.Errorf("service %q is missing region", b.Service)
		}
		return fmt.Sprintf("https://%s.s3.%s.amazonaws.com", b.Bucket, svc.Region), nil
	}

	u, err := url.Parse(svc.Endpoint)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return "", fmt.Errorf("service %q has an invalid endpoint %q", b.Service, svc.Endpoint)
	}
	u.Path = strings.TrimSuffix(u.Path, "/")
	u.RawPath = ""
	u.RawQuery, u.Fragment = "", ""
	u.User = nil

	if svc.PathStyle() {
		return u.String() + "/" + b.Bucket, nil
	}
	u.Host = b.Bucket + "." + u.Host
	return u.String(), nil
}

// escapeKey encodes each segment, leaving "/" intact so key hierarchy survives.
func escapeKey(key string) string {
	segs := strings.Split(key, "/")
	for i, s := range segs {
		segs[i] = url.PathEscape(s)
	}
	return strings.Join(segs, "/")
}
