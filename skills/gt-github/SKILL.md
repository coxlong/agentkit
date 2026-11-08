---
name: gt-github
description: Operate GitHub repositories, issues, pull requests, Actions, and releases with the gh CLI. Use when the user mentions GitHub, gh, repositories, PRs, issues, Actions, or releases.
---

# gt-github

`gh` is the official GitHub CLI. `-R [HOST/]OWNER/REPO` selects the repository;
omit it inside a clone. This is GitHub, not Gitea — Gitea work belongs to `gt`.

Repositories:

    gh repo view --json name,defaultBranchRef,visibility
    gh repo list --limit 50
    gh repo clone <owner>/<name>
    gh repo create <name> --private --source . --push
    gh repo fork --clone
    gh repo sync

Issues and pull requests:

    gh issue list --state open --limit 20
    gh issue view <n> --comments
    gh issue create --title <t> --body <b>
    gh issue comment <n> --body <b>
    gh pr list --state open
    gh pr view <n> --json state,mergeable,reviewDecision
    gh pr diff <n>
    gh pr checkout <n>
    gh pr create --fill --draft
    gh pr review <n> --approve --body <b>
    gh pr merge <n> --squash --delete-branch
    gh pr checks <n> --watch

Actions:

    gh run list --limit 20
    gh run view <id> --log-failed
    gh run watch <id>
    gh run rerun <id> --failed
    gh workflow list

Releases, search, and the escape hatch:

    gh release list
    gh release create <tag> --generate-notes
    gh search prs <query> --repo <owner>/<name>
    gh api repos/<owner>/<name>/...        # anything the commands above miss

Rules:

- Read structured data with `--json <fields> --jq <expr>`; never parse table
  output, which is formatted for humans and changes between versions.
- Auth is already configured for this host. Do not run `gh auth login` — it is
  interactive and hangs without a TTY. If a scope is missing, `gh auth refresh
  -s <scope>` and tell the user a browser step is waiting for them.
- Confirm before `repo delete`, `release delete`, `run delete`, `pr merge
  --admin`, force-pushing, or closing someone else's PR or issue.
- `--fill` takes the title and body from commits; pass `--title`/`--body` when
  they matter. Link an issue with `Fixes #<n>` in the PR body.
- Do not guess flags: run `gh <command> --help`. Never print `gh auth token` or
  put a token in a command line.
- `gh` prints the created or updated object's URL; report that URL rather than
  reconstructing one.
