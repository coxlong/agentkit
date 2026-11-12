# agentkit

A collection of small CLI tools for agents (e.g. object storage operations) and
the skills that teach agents to drive them, in a single Go module with multiple
commands.

## Structure

```
cmd/<tool>/main.go       # each tool is an independent main package; the build output is a same-named binary
internal/...             # internal packages shared across tools (e.g. the object storage client), not exposed
skills/<name>/SKILL.md   # agent skills: a short command guide per tool (or a method skill with reference/ and templates/); flags are left to --help
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
- [design-board](skills/design-board/SKILL.md) — design an app as one script-generated
  SVG design board: tokens, enforced scales, every state, stable element ids, shared
  sample data, static checks and headless render. Ships a Python board-kit and a small
  worked example.
- [design-parity-flutter](skills/design-parity-flutter/SKILL.md) — implement that board
  in Flutter and prove design↔app parity with scripts only: token/icon generation, a
  layout dump, an id-paired comparator with a baseline gate, mutation tests and a pixel
  fallback. Ships the Python tools and the Flutter test templates.
