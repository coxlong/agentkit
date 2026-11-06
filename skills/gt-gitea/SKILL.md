---
name: gt-gitea
description: Operate Gitea repositories, issues, pull requests, and releases with the gt CLI. Use when the user mentions Gitea, gt, repositories, PRs, issues, or releases.
---

# gt-gitea

`gt` is the official Gitea CLI.

Common commands (`-R` selects the repository; omit it inside a clone):

    gt repo list
    gt repo view <owner>/<name>
    gt repo clone <owner>/<name>
    gt repo create <name> --private
    gt issue list -R <owner>/<name>
    gt pr list -R <owner>/<name>
    gt release list -R <owner>/<name>

Run `gt <command> --help` when unsure about flags; do not guess.
Confirm before deleting a repository, force-pushing, or closing someone else's PR.
