---
name: requestqueue-install
description: Interactive install wizard for RequestQueue. Walks through prereqs, AWS + GitHub setup, .env values, deploy, and first-user whitelist. Idempotent across restarts.
---

# /requestqueue-install — Install Wizard

You are guiding the user step-by-step through a full RequestQueue installation. The user invoked this skill expecting a **wizard experience** — patient, explanatory, one decision at a time. Do **not** batch operations or skip ahead.

The canonical README is at `README.md`; this wizard is its executable form. When in doubt about *what* a step does, the README is the source of truth. When the README and this skill disagree, surface it via the "Report an issue" path below.

## CRITICAL RULES — READ FIRST

1. **Use `AskUserQuestion` for every user-facing decision.** Never just print and proceed. Every choice point goes through `AskUserQuestion`.

2. **Every `AskUserQuestion` MUST include a `Report an issue` option** with a brief description like "Something is unclear or broken — let me describe it." When the user picks this option:
   - Use `AskUserQuestion` again with `multiSelect: false` to capture a free-text description (use one of the question's options to ask "Type your description below as the next message" — or accept their next message as the issue).
   - **STOP the wizard immediately**. Do not continue to the next step.
   - Investigate the issue (read the relevant scripts, README sections, SAM template, etc.).
   - Implement the fix (could be a README correction, a script bug fix, a clarification in this skill itself, an idempotency hole, anything).
   - Run the relevant verification (tests, syntax check, lint).
   - Commit + push the fix with a clear message referencing the user's report.
   - Tell the user: "Issue addressed and pushed. The wizard is **idempotent** — re-run `/requestqueue-install` to start over from Phase 0; already-done steps will detect themselves and skip."

3. **Every phase must be idempotent.** Before doing work, *detect whether it's already done* and skip with a clear "already done — moving on" message. Re-running the wizard from a fully-installed state should reach the end without making any changes.

4. **Never silently swallow errors.** If a command fails, surface the failure to the user, ask whether to retry / debug / report-issue.

5. **Communicate before each phase.** Tell the user what's about to happen and why. Pause for input. Then run.

6. **Don't skip the "Report an issue" option to save tokens.** It is the entire point of this wizard's first run — discovering install bugs.

7. **Interactive commands cannot be run from this side.** Claude Code's `Bash` tool does not connect user stdin to spawned processes, and the user-typed `! <cmd>` prefix has the same limitation — both will hit `EOF when reading a line` (or block forever) on any command that reads from a TTY. This includes `aws configure`, `aws configure sso`, `gh auth login`, `sam deploy --guided`, and any other command that prompts the user mid-run. Never instruct the user to use `! aws configure` — it does not work.

   **Two ways around this — pick the lighter one first:**

   - **(a) Helper script that resolves secrets locally.** Write a script that takes the secret from a *local source* the user already has — a downloaded credentials CSV, the system clipboard via `$(pbpaste)` / `$(wl-paste)` / `$(xclip)`, or a file the user prepared. Shell expansion happens *inside the `!` subprocess after Claude has captured the bash-input as literal text*, so the secret value never appears in the transcript. The script must use commands that don't echo the secret (e.g. `aws configure set` is silent; raw `cat $secret_file` would leak). Output should be limited to non-secret verification (`aws sts get-caller-identity` JSON is fine — account/ARN are not secrets). See `scripts/aws_setup_config.sh` for the canonical pattern (CSV mode + clipboard mode + format validation). This is the **preferred** path because it runs inline in the wizard with no context-switching.
   - **(b) Separate terminal as last resort.** If no script-driven path is feasible (e.g. the upstream CLI's only auth flow is browser-redirect-and-paste-back-into-stdin), instruct the user to open a separate terminal window, `cd` into the repo, run the interactive command there, then return and confirm via `AskUserQuestion`. Verify state from this side with a non-interactive read-only command (`aws sts get-caller-identity`, `gh auth status`, etc.).

## STANDARD ASKUSERQUESTION PATTERN

Every question follows this shape:

```
Question: "<the actual question>"
Options:
  - <real option 1, e.g., "Yes, proceed">
  - <real option 2, e.g., "No, skip this step">
  - "Report an issue: type your description on the next prompt"  ← always last
```

When the user picks the "Report an issue" option, immediately follow up with a free-form prompt:

```
Question: "Describe the issue or point of confusion. Be as specific as possible — what step are you on, what did you expect, what happened?"
Options:
  - "Cancel — I picked Report by mistake"
  - "I'll type my description in the next message"
```

Then accept their next message as the issue description and proceed with the fix-then-restart flow described above.

---

# Phase 0 — Sanity & welcome

Before anything else:

1. Verify cwd is the repo root by checking that `.env.example`, `README.md`, and `Makefile` all exist. If not, tell the user to `cd` into the cloned repo and re-run.

2. Detect OS via `uname -s`:
   - `Darwin` → macOS, use `brew`.
   - `Linux` (and `/proc/sys/kernel/osrelease` contains "microsoft" or "WSL") → WSL2 inside Windows, use `apt` (or whatever the distro provides).
   - `Linux` (other) → native Linux, use `apt` / `dnf` / `pacman` as appropriate.
   - Anything else → tell the user the wizard supports macOS, Linux, and WSL2 only; on native Windows they need WSL2 first (see README "On Windows? Use WSL2."). Stop.

3. Run `git status --porcelain` and `git rev-parse --abbrev-ref HEAD`. If there are uncommitted changes or they're on a non-`main` branch, mention it but don't block — they may be developing.

4. Print a friendly welcome:

   > Welcome to RequestQueue install. This wizard has 8 phases:
   > 1. Detect & install prereqs (uv, pnpm, aws, sam, gh, jq, openssl)
   > 2. AWS account + IAM user + access key
   > 3. GitHub authentication + fine-grained PAT
   > 4. Walk through .env values
   > 5. Generate the Cognito service-user password
   > 6. Install Python + JS dependencies
   > 7. Deploy to AWS (`make publish`)
   > 8. Whitelist your email + verify
   >
   > Each step detects already-done state and skips automatically, so it's safe to interrupt and re-run.

5. `AskUserQuestion`: "Ready to begin?" Options: "Yes, start", "Tell me more about what each phase does first", "Report an issue".

---

# Phase 1 — Prereqs

For each tool in this list, run `command -v <tool>` and record installed/missing:

| Tool | Detect command | macOS install | Linux/WSL install | Why needed |
|---|---|---|---|---|
| Python 3.12+ | `python3 --version` (must be ≥3.12) | `brew install python@3.12` | `apt install python3.12` | API + local code |
| `uv` | `uv --version` | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Python package mgr |
| Node 20+ | `node --version` (must be ≥20) | `brew install node` | `apt install nodejs` (or `nvm install 20`) | Webapp build |
| `pnpm` | `pnpm --version` | `brew install pnpm` | `npm install -g pnpm` | Webapp deps (npm fallback OK) |
| `aws` | `aws --version` | `brew install awscli` | `apt install awscli` | AWS CLI |
| `sam` | `sam --version` | `brew install aws-sam-cli` | follow [SAM install docs](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) | SAM deploys |
| `gh` | `gh --version` | `brew install gh` | `apt install gh` | GitHub auth + PRs |
| `jq` | `jq --version` | `brew install jq` | `apt install jq` | publish.sh, whitelist_user.sh |
| `openssl` | `openssl version` | usually pre-installed | usually pre-installed | refresh_creds.sh password gen |
| `git` | `git --version` | usually pre-installed | `apt install git` | Repo ops |

Print the detection table to the user. For each missing tool:

- `AskUserQuestion`: "Tool `<name>` is missing. Install via `<install command>`?"
  - "Yes, install now" → run the install command via `Bash`. After install, re-detect; if still missing, ask the user to install manually and confirm when done.
  - "No, I'll install it manually — I'll confirm when done" → wait, then re-detect.
  - "Skip this tool" → only allow if it's truly optional (none of the above are; refuse and re-ask).
  - "Report an issue: ..."

If `brew` itself is missing on macOS: `AskUserQuestion`: "Homebrew is required and not installed. Install Homebrew? It will run the official one-liner from brew.sh." → if yes, run `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`.

After all tools are present, print a green success and move to Phase 2.

---

# Phase 2 — AWS account + IAM user

**Detection (idempotency):**

1. Read `REQUESTQUEUE_AWS_PROFILE` from `.env` if it exists (default `requestqueue`).
2. Run `aws sts get-caller-identity --profile $REQUESTQUEUE_AWS_PROFILE 2>&1`.
3. If it returns an Account/UserId without error: tell the user "AWS profile `<name>` is configured (account `<account>`, user `<arn>`). Skipping IAM setup." → confirm with a simple `AskUserQuestion` ("Use this profile?" / "Use a different profile" / "Report an issue") and move on.

**Otherwise (not yet configured):**

Walk the user through the README "AWS Account / One-Time Setup" steps:

1. `AskUserQuestion`: "Do you have an AWS account?"
   - "Yes" → continue.
   - "No, I need to create one" → print `https://console.aws.amazon.com/` and explain they'll need to come back. Suggest they finish account creation, then re-run `/requestqueue-install` (it'll skip everything else they've already done).
   - "Report an issue: ..."

2. Walk through creating the deploy IAM user. Print the URL `https://console.aws.amazon.com/iam/home#/users` and instruct them to:
   - Click "Create user", name it `requestqueue-deploy`.
   - Skip console access (programmatic only).
   - Permissions: "Attach policies directly" → `AdministratorAccess`. (For locked-down accounts, point to README's scoped-down policy table.)
   - After creation, go to **Security credentials → Create access key → "Command Line Interface (CLI)"** use case.
   - On the success page, **click "Download .csv file"** — this saves both the Access Key ID and Secret to `~/Downloads/AccessKey-AKIA<id>.csv`. This is the cleanest path for the next step. (If they dismiss this prompt, they can still continue via the clipboard fallback below.)
   - `AskUserQuestion`: "Did you download the .csv file?" Options: "Yes, downloaded the CSV", "No — I have the keys but not the CSV (use clipboard mode)", "Not yet — give me a minute", "Report an issue".

3. Configure the AWS CLI profile using `scripts/aws_setup_config.sh`. **Keys never pass through Claude** — the script reads them from a CSV file or the system clipboard locally, calls `aws configure set` (which doesn't echo values), and prints only the non-secret `aws sts get-caller-identity` JSON to confirm.

   **Mode A — CSV (recommended, single command):**

   If the user has the downloaded CSV:

   > Run (replace the path with where you saved the CSV):
   > ```
   > ! ./scripts/aws_setup_config.sh --csv ~/Downloads/AccessKey-<id>.csv requestqueue us-east-1
   > ```

   On success the script prints `aws sts get-caller-identity` JSON (account ID + ARN) and a "✓ Profile … is configured" line. After verifying, suggest the user `rm` the CSV (the script's last line shows the exact command).

   **Mode B — Clipboard (fallback, two commands):**

   If they don't have the CSV (e.g. dismissed the download prompt):

   > Copy the **Access Key ID** to your clipboard, then run:
   > ```
   > ! ./scripts/aws_setup_config.sh --clip-id requestqueue
   > ```
   > Then copy the **Secret Access Key** to your clipboard, then run:
   > ```
   > ! ./scripts/aws_setup_config.sh --clip-secret requestqueue us-east-1
   > ```

   Shell expansion of `pbpaste` / `wl-paste` / `xclip` happens *inside* the script after Claude has already captured the bash-input as literal `--clip-id` / `--clip-secret` args, so the secret value never appears in the conversation. The script validates format (Access Key ID must be `[A-Z0-9]{16,128}`; Secret must be ≥20 chars) before calling `aws configure set`.

   `AskUserQuestion` after either mode: "Did the script print '✓ Profile … is configured and authenticates successfully'?" Options: "Yes, configured", "Failed — let's debug", "I want to try the other mode (CSV ↔ clipboard)", "Report an issue".

   **Last-resort fallback (separate terminal):** if both modes fail (clipboard tool missing on Linux, CSV parsing error, etc.), instruct the user to open a separate terminal and run `aws configure --profile requestqueue` interactively. Verify back here with `aws sts get-caller-identity --profile requestqueue`.

4. Write/update `REQUESTQUEUE_AWS_PROFILE` and `REQUESTQUEUE_AWS_REGION` in `.env` (use the same .env-merge pattern that `refresh_creds.sh` uses — strip-then-append, never overwrite the whole file).

5. `AskUserQuestion`: "Optional: do you want to set up a custom domain (`work.<yourdomain>` + `api.<yourdomain>`)?" Options:
   - "Skip for now (use AWS-default URLs)" → don't set CUSTOM_DOMAIN.
   - "Yes, walk me through it" → ask for domain, ask for ACM cert ARN (with instructions to provision it in `us-east-1` covering both subdomains; recommend wildcard). Write to .env.
   - "Report an issue: ..."

---

# Phase 3 — GitHub auth + PAT

**Detection (idempotency):**

1. Run `gh auth status 2>&1`.
2. If logged in: tell the user "GitHub CLI is authenticated as `<username>`." Skip `gh auth login`.
3. Otherwise: **`gh auth login` is interactive — it cannot be run from this side** (see CRITICAL RULES item 7). Instruct the user:

   > Open a separate terminal window and run:
   > ```
   > gh auth login
   > ```
   > Choose: **GitHub.com** → **HTTPS** → **Yes (authenticate Git)** → **Login with a web browser**. Copy the one-time code, paste it in the browser, approve. When done, return here.

   Then `AskUserQuestion`: "Done — signed in?" Options: "Yes, signed in", "Report an issue". On yes, verify with `gh auth status`.

**Fine-grained PAT** (separate from gh auth login — used by `local/build` for git push):

1. Read current `REQUESTQUEUE_GITHUB_TOKEN` from `.env`. If non-empty: skip with confirmation.
2. Otherwise:
   - Print the URL `https://github.com/settings/personal-access-tokens/new`.
   - Explain required scopes: `Contents: Read and write` and `Pull requests: Read and write`. If they plan to enable `WORKQ_GITHUB_AUTO_MERGE`, also `Administration: Read and write` on the target repo.
   - `AskUserQuestion`: "Set token expiration:" with options "30 days", "90 days", "1 year", "No expiration (least secure)", "Report an issue". Tell them what you suggest based on their preference.
   - `AskUserQuestion` for the token value (the answer is the token itself).
   - Validate by running `gh api user --hostname github.com -H "Authorization: Bearer $TOKEN"` (or similar) — if it fails, ask them to recheck and re-enter.
   - Write `REQUESTQUEUE_GITHUB_TOKEN=<value>` to `.env`.

---

# Phase 4 — Walk through `.env`

Read existing `.env`. For each variable below, do the following dance:

- If already set with a non-empty value, `AskUserQuestion`: "`<VAR>` is set to `<value>`. Keep this?" Options: "Keep", "Change it", "Report an issue".
- If empty or unset, `AskUserQuestion` for the value with the default pre-suggested.

Variables to walk (in this order — match the README's importance ordering):

| Var | Default | Notes |
|---|---|---|
| `REQUESTQUEUE_STACK_NAME` | `requestqueue` | Lowercase + hyphens. Must be unique per AWS account. |
| `REQUESTQUEUE_EMAIL_WHITELIST` | (no default — ask) | Their email or `@domain` wildcard. Comma-separated for multiple. |
| `REQUESTQUEUE_GITHUB_REPO_URL` | (no default) | Repo claude will operate on. Format: `https://github.com/<owner>/<repo>.git`. Validate with `gh repo view <url>` to confirm access. |
| `REQUESTQUEUE_GITHUB_BRANCH` | `main` | Target base branch. |
| `REQUESTQUEUE_GITHUB_AUTO_MERGE` | `false` | Explain the trade-off (speed vs. review). Default `false`. |
| `REQUESTQUEUE_GITHUB_AUTO_MERGE_METHOD` | `squash` | Only ask if AUTO_MERGE is true. |
| `REQUESTQUEUE_DISPLAY_TIMEZONE` | `UTC` | Suggest a timezone abbrev (e.g., PST, EST) based on user's locale if detectable; otherwise UTC. |

**Don't ask about technical defaults** unless the user wants to: `REQUESTQUEUE_POLLING_SECONDS=30`, `REQUESTQUEUE_BUILD_TIMEOUT_SECONDS=2700`, `REQUESTQUEUE_PROMPT_PARTS_PATH=./config/prompt_parts.yaml`. Set them to defaults silently if not present. If they're already set, leave alone.

**Idempotent merge:** when writing values to `.env`, strip the existing line for that variable first, then append the new line. Never blow away the whole file.

After this phase, `.env` should be fully populated except for `REQUESTQUEUE_SERVICE_USER_*` (set in Phase 5).

---

# Phase 5 — Generate Cognito service-user password

**Detection (idempotency):**

1. Read `REQUESTQUEUE_SERVICE_USER_PASSWORD` from `.env`.
2. If set with a value of length ≥ 16: `AskUserQuestion`: "Service-user password is already set in .env. Skip regeneration?" Options: "Yes, skip" (default), "Regenerate (rotates the password — backs up .env first)", "Report an issue".

**Otherwise (not set):**

1. Tell the user: "About to run `scripts/refresh_creds.sh`. This generates a 40-char password, backs up your current `.env` to `backups/env/.env_<ts>`, and writes `REQUESTQUEUE_SERVICE_USER_EMAIL` + `REQUESTQUEUE_SERVICE_USER_PASSWORD` into `.env`. No AWS calls."
2. `AskUserQuestion`: "Run it now?" Options: "Yes", "Show me the script first", "Report an issue".
3. Run `scripts/refresh_creds.sh` via `Bash`.
4. Verify by re-reading `.env` and confirming the two variables are now set.

---

# Phase 6 — `make install`

**Detection (idempotency):**

1. Check whether `apis/.venv/`, `local/.venv/`, and `ui/webapp/node_modules/` all exist.
2. If yes: `AskUserQuestion`: "Dependencies appear to be installed. Re-sync anyway? (Safe — `uv sync` and `pnpm install` are idempotent.)" Options: "Yes, re-sync", "Skip — they're current", "Report an issue".

**Run:**

`Bash`: `make install` (this runs `uv sync` in `apis/`, `uv sync` in `local/`, and `pnpm install` in `ui/webapp/`). Show output. Watch for errors — if any, surface them and ask whether to debug, retry, or report.

---

# Phase 7 — `make publish`

This is the big step: SAM deploy + webapp build + S3 sync + CloudFront invalidation. Takes 5–10 minutes on first deploy.

**Detection (idempotency):**

1. Read `.requestqueue.outputs.json` if it exists.
2. If it has a `webapp_url` and a `cognito_user_pool_id`: tell the user "A previous deploy exists (stack `<name>`, webapp `<url>`). Re-running `make publish` is safe and will produce a no-op CloudFormation changeset if nothing changed." Then `AskUserQuestion`: "Re-run anyway? (Recommended after `.env` changes; needed if you ran `refresh_creds.sh`.)" Options: "Yes, re-run (~1–2 min for empty changeset)", "Skip — already deployed", "Report an issue".

**First-run vs. re-run detection:**

Check for `samconfig.toml` at the repo root.
- **Absent** → first deploy → `sam deploy --guided` will prompt interactively → user must run in a separate terminal (see CRITICAL RULES item 7).
- **Present** → SAM has saved its config → `make publish` runs non-interactively → can run via `Bash` here.

**Run (first deploy — `samconfig.toml` absent):**

1. Brief the user: "First-deploy runs `sam deploy --guided`, which will ask several questions:
   - **Stack Name** → enter the `REQUESTQUEUE_STACK_NAME` value from `.env` (usually `requestqueue`)
   - **AWS Region** → enter the `REQUESTQUEUE_AWS_REGION` value (e.g. `us-east-1`)
   - **Confirm changes before deploy** → `N` (CI-style)
   - **Allow SAM CLI IAM role creation** → `Y`
   - **Disable rollback** → `N`
   - **Save arguments to configuration file** → `Y` (this writes `samconfig.toml` so future runs are non-interactive)
   - **SAM configuration file** → accept default (`samconfig.toml`)
   - **SAM configuration environment** → accept default (`default`)
   "
2. `AskUserQuestion`: "Ready to deploy?" Options: "Yes, walk me through opening a separate terminal", "Show me what `make publish` does first", "Report an issue".
3. Instruct the user:

   > Open a separate terminal window, `cd` into this repo, and run:
   > ```
   > make publish
   > ```
   > Answer the SAM prompts as listed above. The full deploy takes 5–10 minutes (CloudFormation create + webapp build + S3 sync + CloudFront invalidation). When you see `Successfully created/updated stack`, return here.

   `AskUserQuestion`: "Done — deploy succeeded?" Options: "Yes, succeeded", "It failed (let's debug)", "Still running — check back in a minute", "Report an issue".

**Run (re-deploy — `samconfig.toml` present):**

1. `make publish` is non-interactive on subsequent runs. Run it directly via `Bash` here. Show progress.

**On success (either path):**

Read `.requestqueue.outputs.json` and print:
- `webapp_url` (the URL the user will sign up at)
- `api_url`
- `cognito_user_pool_id`

**On failure:** capture the error, surface it, ask "Debug / retry / report-issue?".

---

# Phase 8 — Whitelist email + verify

**Detection (idempotency):**

1. Get the current SSM whitelist by running `bash scripts/whitelist_user.sh -l`.
2. `AskUserQuestion`: "What email do you want to log in as in the webapp?" — accept their answer.
3. If the email is already in the whitelist (or covered by a `@domain` wildcard), tell them and skip the add. Otherwise:
4. Run `Bash`: `bash scripts/whitelist_user.sh -a <email>`. The script is idempotent (no-ops if already present).

**Verification:**

Print the webapp URL from `.requestqueue.outputs.json` and instruct:

> 1. Open `<webapp_url>` in your browser.
> 2. Click "Sign up" and enter the whitelisted email + a password (≥12 chars, with uppercase, lowercase, and a digit).
> 3. After sign-up, log in. You should see an empty "no requests yet" state.
>
> Note: the pre-signup Lambda auto-confirms whitelisted users — you should NOT receive a verification email.

`AskUserQuestion`: "Did the webapp load and let you sign up?" Options: "Yes, working", "No, something failed (let's debug)", "Report an issue".

If "no", help debug — check CloudFront cache, Cognito user pool, SSM whitelist param, etc.

---

# Phase 9 — Local server (optional)

`AskUserQuestion`: "Where will the local-server (the box that runs `make monitor` and invokes claude code) live?"

Options:
- "Same machine as the deploy (this one)"
- "A different machine (a VPS, a Pi, EC2, my partner's laptop, etc.)"
- "I'll set it up later — wizard done"
- "Report an issue: ..."

**Same machine:**

1. `AskUserQuestion`: "Start the monitor now in foreground (logs to stdout) or background?" Options: "Foreground (`make monitor`)", "Background (`make monitor-bg`)", "Skip — I'll start it later", "Report an issue".
2. Run the chosen command. If foreground, the wizard ends here.

**Different machine:**

1. Tell the user the next steps to do on the local server:
   ```
   git clone <this repo> && cd <repo>
   cp .env.example .env
   # Edit .env and paste in:
   #   REQUESTQUEUE_GITHUB_REPO_URL, _BRANCH, _TOKEN
   #   REQUESTQUEUE_DISPLAY_TIMEZONE
   #   REQUESTQUEUE_AWS_REGION (region only, no AWS keys needed)
   #   REQUESTQUEUE_SERVICE_USER_EMAIL=<value from this machine's .env>
   #   REQUESTQUEUE_SERVICE_USER_PASSWORD=<value from this machine's .env>
   make install
   make monitor       # or make monitor-bg
   ```
2. Print the actual values of `REQUESTQUEUE_SERVICE_USER_EMAIL` and `REQUESTQUEUE_SERVICE_USER_PASSWORD` from this machine's `.env` so the user can copy them.
3. `AskUserQuestion`: "Done? Or skip — you'll set the local server up later." Options: "Done — local server is running", "I'll set it up later", "Report an issue".

---

# Wrap-up

Print a final success summary:

```
RequestQueue is installed.

Webapp:    <webapp_url>
API:       <api_url>
Stack:     <stack_name>
Profile:   <aws_profile>
Whitelisted email: <email>

Next:
  - Open the webapp and create a "queued for planning" request to test the pipeline.
  - When you want to rotate the service-user password: scripts/refresh_creds.sh && make publish
  - When you want to whitelist more users: scripts/whitelist_user.sh -a <email_or_@domain>
  - Logs: tail -f local/logs/monitor.log local/logs/build.log
```

Tell the user the wizard ran cleanly and they're done.

---

# Implementation hints for Claude (you)

- Read `.env`, `.env.example`, `.requestqueue.outputs.json`, and `config/prompt_parts.yaml` to understand current state.
- For `.env` edits: always read the file, modify in memory, write atomically via `.env.tmp` + `mv`. Match the strip-then-append idempotent pattern used in `scripts/refresh_creds.sh`.
- Don't echo full secret values back to the user except where they explicitly need to copy them (e.g., service-user password to a different machine). Truncate access keys / tokens to first 4 + last 4 chars when echoing back.
- After "Report an issue" → fix → push, end your turn with a clear "Run `/requestqueue-install` again to restart" — do **not** automatically re-invoke the skill.
- The `Report an issue` flow exists specifically to discover bugs in this wizard, scripts, README, and SAM template. **Take user reports seriously.** A "this is confusing" report is just as actionable as a "this command failed" report — clarify the docs, don't just acknowledge.
