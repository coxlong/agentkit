# agentkit

A collection of small CLI tools for agents (e.g. object storage operations) and
the skills that teach agents to drive them, in a single Go module with multiple
commands.

## Structure

```
cmd/<tool>/main.go       # each tool is an independent main package; the build output is a same-named binary
internal/...             # internal packages shared across tools (e.g. the object storage client), not exposed
skills/<name>/SKILL.md   # agent skills: a short command guide per tool; flags are left to --help
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

## Skills

- [gt-gitea](skills/gt-gitea/SKILL.md) — repositories, issues, pull requests, and
  releases through the `gt` CLI.
- [s3](skills/s3/SKILL.md) — object storage operations (buckets, ls/put/get/cat/rm,
  sync, url) through the `s3` CLI.
