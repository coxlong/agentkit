package main

import "testing"

func TestContentType(t *testing.T) {
	cases := []struct {
		path string
		want string
	}{
		// Formats the platform mime table misses (or lacks entirely on slim
		// container images); the fallback table must always resolve them.
		{"report.md", "text/markdown; charset=utf-8"},
		{"README.MD", "text/markdown; charset=utf-8"},
		{"notes.markdown", "text/markdown; charset=utf-8"},
		{"ci.yaml", "application/yaml"},
		{"ci.yml", "application/yaml"},
		{"app.toml", "application/toml"},
		// Formats the platform mime table is guaranteed to have, and an
		// unknown extension that should resolve to nothing.
		{"a.txt", "text/plain; charset=utf-8"},
		{"a.json", "application/json"},
		{"a.no-such-ext", ""},
	}
	for _, c := range cases {
		if got := contentType(c.path); got != c.want {
			t.Errorf("contentType(%q) = %q, want %q", c.path, got, c.want)
		}
	}
}
