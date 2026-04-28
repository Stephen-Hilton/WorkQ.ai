# Web AI Build - RequestQueue Framework

An AWS-serverless (nearly free) secure web queue for AI work requests that run on a secondary server (on AWS, locally, GCP, Azure, wherever). Submit and monitor on the go; the "local" server hands queued requests to headless `claude code`, opens a PR, and writes the result back.

- **Webapp** (S3 + CloudFront, Cognito auth): create/edit/clone/delete requests; live status; mobile-friendly.
- **API** (API Gateway + Lambda + DynamoDB): tiny REST CRUD, optimistic concurrency.
- **Local server** (Python): polls the API, runs `claude code` in a per-request `git worktree`, opens a PR, posts the result.

See [`prompts/reqv1.md`](prompts/reqv1.md) for the full spec.

I use this for all of my AI projects, usually by merging it into my apps' admin control center, as it allows me to queue up runtime errors for review and/or auto-fix. I also allows me to submit work to the AI coding agent via my mobile device from the beach.  Sand helps me code. 

---
<br><br>

# Quick start

## Prerequisites and Setup

### Dev / Deploy Machine (laptop)

**Prereqs:**

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/) (`brew install uv`)
- Node 20+ and [`pnpm`](https://pnpm.io/) (`brew install pnpm`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) (`brew install aws-sam-cli`)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), configured (`aws configure`)
- [GitHub CLI](https://cli.github.com/) (`brew install gh`)
- An AWS account
- A GitHub repo you want claude to operate on (and a fine-grained PAT — see below)
- *Optional:* a custom domain + an ACM certificate in `us-east-1` covering both `work.<domain>` and `api.<domain>` (or a wildcard `*.<domain>`)

<br>

**One-Time Setup:**

```bash
git clone https://github.com/<you>/RequestQueue.ai.git
cd RequestQueue.ai
cp .env.example .env          # then edit .env (see env-var reference below)
make install                  # uv sync + pnpm install
make publish                  # sam deploy --guided + pnpm build + s3 sync + cloudfront invalidate
scripts/whitelist_user.sh -a yourname@yourdomain.com    # or -a @yourdomain.com
```

The first `make publish` runs `sam deploy --guided` which will prompt for stack name, region, and a few confirmations, then writes `samconfig.toml` so future `sam deploy` is non-interactive.

After publish, the deploy outputs (`webapp_url`, `api_url`, etc.) are written to `.requestqueue.outputs.json`. Open `webapp_url` in a browser, sign up with the whitelisted email, log in.

--- 
### "Local" Server

This is the server that will monitor for new queued work and run `claude code` as needed.  It's called "local" server by convention, but can be any server anywhere.

**Prereqs:**

- Same Python + `uv`
- `git`, `gh`, `claude` (Claude Code)
- One run of `scripts/bootstrap_local.sh` to fetch the service-user credentials (no AWS keys needed at runtime)

<br>

**One-Time Setup:**

```bash
git clone https://github.com/<you>/RequestQueue.ai.git
cd RequestQueue.ai
cp .env.example .env          # set REQUESTQUEUE_AWS_REGION + REQUESTQUEUE_AWS_PROFILE temporarily for bootstrap
make install
scripts/bootstrap_local.sh    # one-time fetch of service-user password from Secrets Manager
                              # writes to ~/.config/requestqueue/credentials
# AWS keys are no longer needed at runtime — you may remove them from .env now
make monitor                  # starts python -m local.monitor (long-running)
```

Use `make monitor-bg` to run it in the background and tail the log. Use a `systemd`/`launchd` unit on a real server.

---

### AWS Account

**Prereqs:**

- An AWS account (any tier — see "Cost expectation" below; this app stays in the free tier at typical volumes).
- Billing contact on file (AWS requires it even when nothing is being charged).
- Region: use **`us-east-1`** unless you have a specific reason otherwise. It's required if you plan to use a custom domain (CloudFront ACM certs must live in `us-east-1`).

<br>

**One-Time Setup:**

1. **Create a dedicated IAM user for deploys.** Don't use root. Console → IAM → Users → "Create user" → name it `requestqueue-deploy` (or similar). Skip console access; you only need programmatic access.

2. **Attach permissions.** Pick one of:
   - **Recommended for personal accounts:** attach the AWS-managed `AdministratorAccess` policy. SAM creates a wide variety of resources (Lambda, API Gateway, Cognito, DynamoDB, S3, CloudFront, IAM execution roles for the Lambdas), so a deploy user that can do anything is by far the simplest path.
   - **For shared / locked-down accounts:** see "Scoped-down permissions" below for a custom policy.

3. **Create an access key for that user.** User → Security credentials → "Create access key" → "Command Line Interface (CLI)" → save the Access Key ID + Secret Access Key.

4. **Configure the AWS CLI on your deploy machine.**
   ```bash
   aws configure --profile requestqueue
   # AWS Access Key ID:     <paste>
   # AWS Secret Access Key: <paste>
   # Default region name:   us-east-1
   # Default output format: json
   ```
   Then in `.env`, set `REQUESTQUEUE_AWS_PROFILE=requestqueue`. The deploy and bootstrap scripts will pick it up.

5. **(Optional) Custom domain.** If you set `REQUESTQUEUE_CUSTOM_DOMAIN=example.com`, you also need a single ACM certificate in `us-east-1` covering both `work.<domain>` and `api.<domain>` — easiest is a wildcard `*.<domain>`. Request it via ACM Console (in `us-east-1`), validate via DNS, and paste the cert ARN into `REQUESTQUEUE_CUSTOM_DOMAIN_CERT_ARN`. Then point your DNS at the CloudFront/API Gateway targets that show up in `.requestqueue.outputs.json` after `make publish`.

<br>

**Scoped-down permissions** (skip this if you're using `AdministratorAccess` on a personal account):

The deploy user needs to be able to create/update/delete resources across these services. Build a custom policy with these actions; resource ARNs can be scoped to `arn:aws:*:*:*:requestqueue-*` or similar where supported.

| Service | Actions |
|---|---|
| CloudFormation | `cloudformation:*` (SAM is built on CFN) |
| Lambda | `lambda:Create*`, `lambda:Update*`, `lambda:Delete*`, `lambda:Get*`, `lambda:List*`, `lambda:AddPermission`, `lambda:RemovePermission`, `lambda:TagResource`, `lambda:InvokeFunction` |
| API Gateway | `apigateway:*` |
| DynamoDB | `dynamodb:CreateTable`, `dynamodb:UpdateTable`, `dynamodb:DeleteTable`, `dynamodb:DescribeTable`, `dynamodb:DescribeContinuousBackups`, `dynamodb:UpdateContinuousBackups`, `dynamodb:TagResource` |
| Cognito | `cognito-idp:*` (user pool, client, domain, pre-signup trigger config; the custom resource also needs `cognito-idp:AdminCreateUser`/`AdminSetUserPassword`/`AdminGetUser`/`AdminDeleteUser` on the pool) |
| S3 | `s3:*` on `arn:aws:s3:::requestqueue-webapp-*` and the SAM-managed artifacts bucket (typically `aws-sam-cli-managed-default-*`) |
| CloudFront | `cloudfront:*` |
| IAM | `iam:CreateRole`, `iam:DeleteRole`, `iam:GetRole`, `iam:PassRole`, `iam:AttachRolePolicy`, `iam:DetachRolePolicy`, `iam:PutRolePolicy`, `iam:DeleteRolePolicy`, `iam:CreateServiceLinkedRole`, `iam:TagRole` (needed because SAM creates execution roles for each Lambda) |
| SSM Parameter Store | `ssm:GetParameter`, `ssm:GetParameters`, `ssm:PutParameter`, `ssm:DeleteParameter` on `arn:aws:ssm:*:*:parameter/requestqueue/*` |
| Secrets Manager | `secretsmanager:CreateSecret`, `secretsmanager:UpdateSecret`, `secretsmanager:DeleteSecret`, `secretsmanager:DescribeSecret`, `secretsmanager:GetSecretValue`, `secretsmanager:TagResource` on `arn:aws:secretsmanager:*:*:secret:/requestqueue/*` |
| CloudWatch Logs | `logs:CreateLogGroup`, `logs:DeleteLogGroup`, `logs:DescribeLogGroups`, `logs:PutRetentionPolicy`, `logs:TagResource` |
| ACM (only if custom domain) | `acm:DescribeCertificate` on the cert ARN |

After your first successful `make publish`, you can tighten further. **Ongoing operations** (whitelist edits via `whitelist_user.sh`, prompt updates via `make publish-prompts`, bootstrapping the local server) only need:

- `ssm:GetParameter` + `ssm:PutParameter` on `arn:aws:ssm:*:*:parameter/requestqueue/email_whitelist`
- `s3:PutObject` on `arn:aws:s3:::requestqueue-webapp-*/config/*`
- `cloudfront:CreateInvalidation` on the distribution ARN
- `cloudformation:DescribeStacks` (to fetch outputs)
- `secretsmanager:GetSecretValue` on the service-user secret (only needed once, to bootstrap a new local server)

You can leave the `requestqueue-deploy` user as-is and just rotate to a tighter user later, or have two separate users from the start (`requestqueue-deploy` for stack creation, `requestqueue-ops` for day-to-day).

<br>

**Cost expectation:**

At low volume (a few hundred requests, 30s polling), this app costs effectively **\~\$0.50–\$1.00 / month**:

| Service | Free tier | Typical use here | Cost |
|---|---|---|---|
| DynamoDB on-demand | n/a (pay per request) | ~thousands of read/writes/mo | < \$0.01 |
| Lambda | 1M requests/mo + 400k GB-s | well under | \$0 |
| API Gateway REST | 1M requests/mo for 12mo | well under | \$0 (or pennies after free tier) |
| S3 | 5 GB + 20k GETs | tiny bundle, low traffic | < \$0.05 |
| CloudFront | 1 TB egress for 12mo | low | \$0 |
| Cognito | 50k MAU forever | a handful of users | \$0 |
| **Secrets Manager** | none | 1 secret | **\$0.40** |
| SSM Parameter Store | unlimited standard params | 1 param | \$0 |
| CloudWatch Logs | 5 GB/mo | low | < \$0.05 |

Heavy use (frequent builds, many users, verbose logging) might push this into single-digit dollars/mo.

---

## Env-var reference

All env vars are prefixed `REQUESTQUEUE_`. See `.env.example` for the canonical list with comments. Highlights:

| Var | Used by | Notes |
|---|---|---|
| `REQUESTQUEUE_AWS_REGION` | deploy | Must be `us-east-1` if you use a custom domain. |
| `REQUESTQUEUE_AWS_PROFILE` | deploy / bootstrap | Optional — alternative to `AWS_ACCESS_KEY_ID`. Standard AWS credential chain applies. |
| `REQUESTQUEUE_CUSTOM_DOMAIN` | deploy (optional) | E.g., `example.com`. If set, webapp = `https://work.<domain>`, API = `https://api.<domain>`. |
| `REQUESTQUEUE_CUSTOM_DOMAIN_CERT_ARN` | deploy (required if custom domain) | ACM cert in `us-east-1` covering both subdomains. |
| `REQUESTQUEUE_EMAIL_WHITELIST` | deploy (seed) | Comma-separated emails or `@domain` wildcards. Seeds SSM on first deploy. |
| `REQUESTQUEUE_GITHUB_REPO_URL` | local | Repo claude will operate on. |
| `REQUESTQUEUE_GITHUB_BRANCH` | local | Default base branch. Default `main`. |
| `REQUESTQUEUE_GITHUB_TOKEN` | local | Fine-grained PAT — see scopes below. |
| `REQUESTQUEUE_GITHUB_AUTO_MERGE` | local | `false` (default) or `true`. Auto-merges every PR. |
| `REQUESTQUEUE_GITHUB_AUTO_MERGE_METHOD` | local | `squash` (default) / `merge` / `rebase`. |
| `REQUESTQUEUE_POLLING_SECONDS` | local | Monitor poll interval. Default `30`. |
| `REQUESTQUEUE_BUILD_TIMEOUT_SECONDS` | local | Max claude wall-clock. Default `2700` (45 min). |
| `REQUESTQUEUE_DISPLAY_TIMEZONE` | webapp | Display-only TZ. Storage is always UTC. Default `UTC`. |
| `REQUESTQUEUE_PROMPT_PARTS_PATH` | local | Default `./config/prompt_parts.yaml`. |

### GitHub PAT scopes

Minimum:

- `contents:write` (push branches)
- `pull_requests:write` (create PRs)

If `REQUESTQUEUE_GITHUB_AUTO_MERGE=true`, you also need admin rights on the repo (the token must be allowed to use `gh pr merge --admin`, which bypasses branch protection).<br>
This is primarily used for early dev or solo founders, where the product does not have active users that could be disrupted by a bad merge / deploy.  

If you have active users on your product, it's best practice to _NOT_ enable AUTO_MERGE.

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
                   │  PK = reqid v7   │                            ┌────────────────────┐
                   │  no SK, no GSI   │                            │ GitHub repo        │
                   └──────────────────┘                            │  requestqueue/<id> │
                                                                   │  branches+PRs      │
                  ┌────────────────────┐                           └────────────────────┘
                  │ Cognito User Pool  │
                  │  human users +     │◀── pre-signup Lambda ── SSM whitelist
                  │  service-local-mon │
                  └────────────────────┘
                  ┌────────────────────┐    ┌───────────────────┐
                  │ S3 (private/OAC)   │◀── │ CloudFront        │
                  │  /index.html + JS  │    │  HTTPS, edge cache│
                  │  /config/app.json  │    └───────────────────┘
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

Edits `/requestqueue/email_whitelist` in SSM Parameter Store. Takes effect immediately (no redeploy).

### Update `config/prompt_parts.yaml`

Edit the file in-repo, then:

```bash
make publish-prompts          # validates, derives app.json, uploads to S3, invalidates CloudFront
```

The full yaml stays local — only the area names reach the webapp (via `app.json`). See [`config/README.md`](config/README.md) for the rationale.

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
| `local/build` crashed entirely (segfault, kernel OOM, server reboot) | After `REQUESTQUEUE_BUILD_TIMEOUT_SECONDS + 60s`, monitor's stuck-build detector force-sets the record to `failed` with a "build appears to have died" response. |
| Two users save the same record concurrently | Second save returns 409; webapp shows a diff dialog. |

Every `failed`/`pending review` response includes a copy-pasteable `# Recommended Next Step` section. Read it, fix it, then either re-queue the request or `Save and Complete`.

---

## Layout

```
├── apis/             # Lambda code (Python). One file per route + shared/.
├── config/           # Runtime configuration (prompt_parts.yaml). Edit here.
├── infra/            # SAM template.
├── local/            # Monitor + build (Python). Runs on a separate machine.
├── prompts/          # Spec / version artifacts (reqv1.md). Not runtime config.
├── scripts/          # publish, bootstrap_local, whitelist_user, validate_prompt_parts.
├── ui/webapp/        # React + Vite + TS + Tailwind + shadcn/ui.
├── Makefile          # deploy / publish / dev / monitor / validate.
└── .env.example      # canonical env var reference.
```

---

## License

See [LICENSE](LICENSE).
