package main

import (
	"encoding/json"
	"io"
)

// emitJSON writes a structured result to the given writer so the agent can
// parse it.
func emitJSON(w io.Writer, v any) error {
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}
