---
name: s3
description: Operate object storage (AWS S3, MinIO, R2, OSS, COS) with the s3 CLI from agentkit. Use when the user mentions S3, object storage, buckets, or uploading/downloading files to cloud storage.
---

# s3

`s3` is the agentkit object-storage CLI. It works with any S3-protocol
service; credentials and endpoints are operator config, invisible to you.

Common commands (always address objects as `s3://<bucket>/<key>`):

    s3 buckets                          # discover available buckets; run this first
    s3 ls s3://<bucket>/<prefix>        # non-recursive; --recursive to recurse
    s3 put <local file> s3://<bucket>/<key>
    s3 get s3://<bucket>/<key> <local path>
    s3 cat s3://<bucket>/<key>          # object content to stdout
    s3 rm s3://<bucket>/<key>           # --recursive deletes by prefix
    s3 sync <local dir> s3://<bucket>/<prefix>   # upload; reverse the args to download
    s3 url s3://<bucket>/<key>          # public URL to hand a human

Rules:

- Run `s3 buckets` before operating when you do not know which bucket to use;
  only configured buckets are usable and there is no default.
- A bucket with an alias is addressed only by that alias.
- `sync` treats the prefix as a folder and never deletes unless `--delete` is
  given; use `--dry-run` before a destructive sync.
- Confirm with the user before `rm --recursive` or `sync --delete`; both are
  irreversible.
- Run `s3 <command> --help` when unsure about flags; do not guess.
- Never try to pass credentials, endpoints, or regions — the tool accepts none.
  Adding a bucket is an operator task done via `s3 config`, not by you.
