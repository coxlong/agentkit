---
name: agr
description: Operate Tencent Cloud Agent Runtime sandboxes with the agr CLI. Use when the user mentions agr, Agent Runtime, AGS, sandbox tools, browser or mobile sandboxes, or running code in a cloud sandbox.
---

# agr

`agr` is the Tencent Cloud Agent Runtime (AGS) CLI. Region and credentials come
from `~/.agr/config.toml`; `agr doctor` checks them.

A tool is a template; an instance is a running sandbox:

    agr tool create -n <unique-name> -t code-interpreter \
        --network-configuration '{"NetworkMode":"PUBLIC"}'
    agr instance create --tool-id <tool-id>        # 5m by default
    agr instance code run <id> -c "print(1)"       # or exec <id> -- ls -la
    agr instance delete <id> && agr tool delete <tool-id>

Types: `browser`, `code-interpreter`, `mobile`, `osworld`, `swebench`, `aio`,
`android-world`, `waa`, `custom`.

Rules:

- Names are unique per account and region; suffix them with a timestamp.
- Regions are isolated: a tool id lives only in its region, and the instance must
  match it. `--region` overrides the config default for that one command.
- Sandboxes bill while they run. Delete instance and tool the moment the task
  ends; prefer `--create-temp-instance` (self-cleaning) for one-shot work.
- Instances die after 5 minutes unless you pass `--timeout` sized to the job.
- Network mode is set on the tool, not the instance: `SANDBOX` (no egress),
  `PUBLIC`, `VPC` (needs `VpcConfig`).
- `mobile` exists only in `ap-guangzhou`. Other regions fail with
  `ResourceUnavailable.Provider` ("no available resources"), which means
  unsupported region, not capacity. It also needs a local `adb`: run
  `agr instance mobile connect <id>` and your adb commands in the same shell.
- `agr instance browser vnc <id>` prints VNC and CDP URLs; drive CDP with
  Playwright or Puppeteer.
- Run `agr <command> --help` rather than guessing flags.
