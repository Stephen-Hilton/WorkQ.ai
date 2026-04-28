# WorkQ.ai

A nearly-free, AWS-serverless, secure web queue for AI work requests. Submit and monitor on the go; a local server hands queued requests to headless `claude code`, opens a PR, and writes the result back.

- **Webapp** (S3 + CloudFront, Cognito auth): create/edit/clone/delete requests; live status; mobile-friendly.
- **API** (API Gateway + Lambda + DynamoDB): tiny REST CRUD, optimistic concurrency.
- **Local server** (Python): polls the API, runs `claude code` in a per-request `git worktree`, opens a PR, posts the result.

See [`prompts/reqv1.md`](prompts/reqv1.md) for the full spec.

---

## Quick start

### Prerequisites

On your **deploy machine** (typically your laptop):

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/) (`brew install uv`)
- Node 20+ and [`pnpm`](https://pnpm.io/) (`brew install pnpm`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) (`brew install aws-sam-cli`)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), configured (`aws configure`)
- [GitHub CLI](https://cli.github.com/) (`brew install gh`)
- An AWS account
- A GitHub repo you want claude to operate on (and a fine-grained PAT — see below)
- *Optional:* a custom domain + an ACM certificate in `us-east-1` covering both `work.<domain>` and `api.<domain>` (or a wildcard `*.<domain>`)

On your **local server** (laptop or otherwise):

- Same Python + `uv`
- `git`, `gh`, `claude` (Claude Code)
- One run of `scripts/bootstrap_local.sh` to fetch the service-user credentials (no AWS keys needed at runtime)

### One-time setup

```bash
git clone https://github.com/<you>/WorkQ.ai.git
cd WorkQ.ai
cp .env.example .env          # then edit .env (see env-var reference below)
make install                  # uv sync + pnpm install
make publish                  # sam deploy --guided + pnpm build + s3 sync + cloudfront invalidate
scripts/whitelist_user.sh -a yourname@yourdomain.com    # or -a @yourdomain.com
```

The first `make publish` runs `sam deploy --guided` which will prompt for stack name, region, and a few confirmations, then writes `samconfig.toml` so future `sam deploy` is non-interactive.

After publish, the deploy outputs (`webapp_url`, `api_url`, etc.) are written to `.workq.outputs.json`. Open `webapp_url` in a browser, sign up with the whitelisted email, log in.

### Set up the local server

On the box that will actually run `claude code`:

```bash
git clone https://github.com/<you>/WorkQ.ai.git
cd WorkQ.ai
cp .env.example .env          # set WORKQ_AWS_REGION + WORKQ_AWS_PROFILE temporarily for bootstrap
make install
scripts/bootstrap_local.sh    # one-time fetch of service-user password from Secrets Manager
                              # writes to ~/.config/workq/credentials
# AWS keys are no longer needed at runtime — you may remove them from .env now
make monitor                  # starts python -m local.monitor (long-running)
```

Use `make monitor-bg` to run it in the background and tail the log. Use a `systemd`/`launchd` unit on a real server.

---

## Env-var reference

All env vars are prefixed `WORKQ_`. See `.env.example` for the canonical list with comments. Highlights:

| Var | Used by | Notes |
|---|---|---|
| `WORKQ_AWS_REGION` | deploy | Must be `us-east-1` if you use a custom domain. |
| `WORKQ_AWS_PROFILE` | deploy / bootstrap | Optional — alternative to `AWS_ACCESS_KEY_ID`. Standard AWS credential chain applies. |
| `WORKQ_CUSTOM_DOMAIN` | deploy (optional) | E.g., `example.com`. If set, webapp = `https://work.<domain>`, API = `https://api.<domain>`. |
| `WORKQ_CUSTOM_DOMAIN_CERT_ARN` | deploy (required if custom domain) | ACM cert in `us-east-1` covering both subdomains. |
| `WORKQ_EMAIL_WHITELIST` | deploy (seed) | Comma-separated emails or `@domain` wildcards. Seeds SSM on first deploy. |
| `WORKQ_GITHUB_REPO_URL` | local | Repo claude will operate on. |
| `WORKQ_GITHUB_BRANCH` | local | Default base branch. Default `main`. |
| `WORKQ_GITHUB_TOKEN` | local | Fine-grained PAT — see scopes below. |
| `WORKQ_GITHUB_AUTO_MERGE` | local | `false` (default) or `true`. Auto-merges every PR. |
| `WORKQ_GITHUB_AUTO_MERGE_METHOD` | local | `squash` (default) / `merge` / `rebase`. |
| `WORKQ_POLLING_SECONDS` | local | Monitor poll interval. Default `30`. |
| `WORKQ_BUILD_TIMEOUT_SECONDS` | local | Max claude wall-clock. Default `2700` (45 min). |
| `WORKQ_DISPLAY_TIMEZONE` | webapp | Display-only TZ. Storage is always UTC. Default `UTC`. |
| `WORKQ_PROMPT_PARTS_PATH` | local | Default `./prompts/prompt_parts.yaml`. |

### GitHub PAT scopes

Minimum:

- `contents:write` (push branches)
- `pull_requests:write` (create PRs)

If `WORKQ_GITHUB_AUTO_MERGE=true`, you also need admin rights on the repo (the token must be allowed to use `gh pr merge --admin`, which bypasses branch protection).

---

## Architecture

```
                     Webapp users (browser)                           Local server (anywhere)
                              │                                                │
                  Cognito JWT │                                Cognito JWT     │
                              │                                  (service user)│
                              ▼                                                ▼
                   ┌──────────────────┐ same routes,        ┌────────────────────────────┐
                   │   API Gateway    │ same Cognito        │ local/monitor (long-lived) │
                   │ Cognito JWT auth │ authorizer for both │  - polls GET /status/queued│
                   └────────┬─────────┘                     │  - spawns local/build      │
                            │                               │  - stuck-build detector    │
                            ▼                               └─────────────┬──────────────┘
                   ┌──────────────────┐                                   │
                   │ API Lambda (py)  │                                   │ child subprocess
                   │  - CRUD ops      │                                   ▼
                   │  - JWT email →   │                     ┌────────────────────────────┐
                   │    reqcreator    │                     │ local/build (per-request)  │
                   │  - 409 on stale  │                     │  - claude code in worktree │
                   └────────┬─────────┘                     │  - git push, gh pr create  │
                            │                               │  - PUT response/status/pr  │
                            ▼                               └─────────────┬──────────────┘
                   ┌──────────────────┐                                   │
                   │ DynamoDB         │                                   ▼
                   │  PK = reqid v7   │                            ┌──────────────┐
                   │  no SK, no GSI   │                            │ GitHub repo  │
                   └──────────────────┘                            │  workq/<id>  │
                                                                   │  branches+PRs│
                  ┌────────────────────┐                           └──────────────┘
                  │ Cognito User Pool  │
                  │  human users +     │◀── pre-signup Lambda ── SSM whitelist
                  │  service-local-mon │
                  └────────────────────┘
                  ┌────────────────────┐    ┌──────────────────┐
                  │ S3 (private/OAC)   │◀── │ CloudFront        │
                  │  /static (bundle)  │    │  HTTPS, edge cache│
                  │  /config/*.yaml    │    └──────────────────┘
                  └────────────────────┘
```

Single Cognito authorizer for both clients. Local has zero AWS IAM credentials at runtime — only a Cognito service-user password. Builds run strictly serially across the local box. See [`prompts/reqv1.md`](prompts/reqv1.md) for full details.

---

## Operations

### Add / remove / list whitelisted users

```bash
scripts/whitelist_user.sh -a alice@example.com
scripts/whitelist_user.sh -a @example.com           # whole-domain wildcard
scripts/whitelist_user.sh -r alice@example.com
scripts/whitelist_user.sh -l
scripts/whitelist_user.sh -h
```

Edits `/workq/email_whitelist` in SSM Parameter Store. Takes effect immediately (no redeploy).

### Update `prompts/prompt_parts.yaml`

Edit the file in-repo, then:

```bash
make publish-prompts          # validates, uploads to S3, invalidates CloudFront
```

Webapp picks up the new `reqarea` selector values within ~60s (CloudFront cache TTL).

### Restart the monitor / build (after a code change to `local/`)

If you changed `local/monitor`, restart `make monitor`. If you changed `local/build`, no restart needed — the next request spawns a fresh subprocess.

### Tail logs

```bash
tail -f local/logs/monitor.log
tail -f local/logs/build.log
```

These contain *operational* telemetry only — they do **not** contain claude's per-request output. That goes to the `response` field on the DDB record (visible in the webapp).

---

## Local development

```bash
make dev                      # runs webapp Vite dev server on http://localhost:5173
make sam-sync                 # sam sync --watch — Lambda code changes deploy in ~5–10s
make validate                 # run validate_prompt_parts.py + lint + typecheck
```

The webapp dev server proxies API calls to the deployed API (no second backend to run). You'll need to be signed in via Cognito; the dev server uses the same Cognito as production.

---

## Failure modes & recovery

The system is designed to never leave a request silently stuck.

| What went wrong | What you'll see |
|---|---|
| Build exceeded 45 min | Status `failed`, `response` has last 100 lines + `# Recommended Next Step`. |
| `claude code` exited non-zero | Status `failed`, `response` has full output + exit code + recommended next step. |
| Claude succeeded but `git push` / `gh pr create` failed | Status `pending review`, `response` has the work product + manual recovery commands. |
| Auto-merge requested but `gh pr merge --admin` failed | Status `pending review`, `reqpr` set to PR URL, response notes the failure. |
| `local/build` crashed entirely (segfault, kernel OOM, server reboot) | After `WORKQ_BUILD_TIMEOUT_SECONDS + 60s`, monitor's stuck-build detector force-sets the record to `failed` with a "build appears to have died" response. |
| Two users save the same record concurrently | Second save returns 409; webapp shows a diff dialog. |

Every `failed`/`pending review` response includes a copy-pasteable `# Recommended Next Step` section. Read it, fix it, then either re-queue the request or `Save and Complete`.

---

## Layout

```
├── apis/             # Lambda code (Python). One file per route + shared/.
├── infra/            # SAM template.
├── local/            # Monitor + build (Python). Runs on a separate machine.
├── prompts/          # reqv1.md spec + prompt_parts.yaml.
├── scripts/          # publish, bootstrap_local, whitelist_user, validate_prompt_parts.
├── ui/webapp/        # React + Vite + TS + Tailwind + shadcn/ui.
├── Makefile          # deploy / publish / dev / monitor / validate.
└── .env.example      # canonical env var reference.
```

---

## License

See [LICENSE](LICENSE).
