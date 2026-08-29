# agentkit

A collection of small CLI tools for agents (e.g. object storage operations), a
single Go module with multiple commands.

## Structure

```
cmd/<tool>/main.go   # each tool is an independent main package; the build output is a same-named binary
internal/...         # internal packages shared across tools (e.g. the object storage client), not exposed
```

## Development

```bash
make build   # compile every tool under cmd/ into bin/
make test
make vet
```

Add a tool: create `cmd/<tool>/main.go` and define the command with cobra. Put
shared logic in `internal/`.

## Tools

- [s3](docs/s3.md) — object storage operations for agents. See the doc for
  commands, config format, and the secret storage scheme.
