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

   **When you DO and DON'T need `!` mode for secrets:**

   The point of `!` is to keep secret *text* out of the conversation transcript when that text would otherwise appear in the bash-input or bash-stdout. Three cases:

   - **You DON'T need `!` — Claude runs it via `Bash`.** Whenever the secret is *not in the command-line text* and the script *doesn't echo* it. Example: `./scripts/aws_setup_config.sh --csv ./foo.csv` reads keys from a file and calls silent `aws configure set`. The Bash tool runs the same script in the same local shell; the keys never enter Claude's context either way. Same for clipboard mode — `pbpaste` resolves locally inside the script. **This is the default**: prefer running the script via Claude's `Bash` tool. Don't make the user type `!` commands they don't need to type.
   - **You DO need `!` — user runs it.** Whenever the secret is in the command-line text itself (e.g. `aws configure set aws_access_key_id AKIA<real key>` typed inline by the user, or `$(pbpaste)` used directly in the user-typed command and the user wants the literal substitution to happen client-side). The `!` form preserves the literal pre-expansion text in the transcript while shell expansion happens locally.
   - **Neither works — separate terminal as last resort.** If the upstream CLI's only auth flow is interactive-prompt-on-stdin (e.g. `aws configure`, `gh auth login`'s "paste this code in browser then back into stdin" flow, `sam deploy --guided`), instruct the user to open a separate terminal window, `cd` into the repo, run the interactive command there, then return and confirm via `AskUserQuestion`. Verify state from this side with a non-interactive read-only command (`aws sts get-caller-identity`, `gh auth status`, etc.).

   See `scripts/aws_setup_config.sh` for the canonical "secret stays out of the command line" pattern (CSV mode + clipboard mode + format validation + non-secret-only output).

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

2. **Determine starting point — does the user already have a key CSV?**

   Most users will need the IAM walkthrough. **Don't assume they've done it** — ask first.

   `AskUserQuestion`: "Have you already created a deploy IAM user in AWS and downloaded the access-keys CSV file?"
   - "Yes — I have the CSV file" → skip walkthrough, jump to step 3.
   - "No — walk me through creating the user, key, and CSV" → print the **IAM walkthrough below**, then come back to step 3.
   - "I have access keys but no CSV file" → tell them they have two options: (a) deactivate the existing key in the AWS console and create a new one with "Download .csv file" (5 sec, cleanest), or (b) skip CSV entirely and use clipboard mode in step 3 (paste the keys from wherever they're stored). Then ask which they want.
   - "Report an issue".

   **IAM walkthrough** (only printed when the user picks "walk me through"):

   Print this verbatim:

   > ## Create the deploy IAM user (5–10 minutes in the AWS console)
   >
   > **What we're doing:** creating a dedicated IAM user named `requestqueue-deploy` with permission to deploy this app's CloudFormation stack. This user is for *deploys only*. The local-server side of RequestQueue runs with no AWS keys at all (it authenticates as a Cognito user instead).
   >
   > **Why a dedicated user?** SAM creates a wide variety of resources (Lambda, API Gateway, Cognito, DynamoDB, S3, CloudFront, IAM execution roles for the Lambdas), so the simplest path is `AdministratorAccess` on a deploy-only user. Don't use root for this — root keys have no blast-radius limit and shouldn't sit on your laptop. For shared/locked-down accounts, README "Scoped-down permissions" has a custom policy that works in lieu of `AdministratorAccess`.
   >
   > **Steps in the AWS console:**
   >
   > 1. Open **https://console.aws.amazon.com/iam/home#/users** in your browser.
   > 2. Click **Create user**.
   > 3. **User name:** `requestqueue-deploy` (any name is fine; if you change it, that's a memo for yourself — the wizard doesn't depend on the name).
   > 4. **DO NOT** check "Provide user access to the AWS Management Console" — programmatic access only.
   > 5. Click **Next**.
   > 6. **Permissions options:** select **"Attach policies directly"**.
   > 7. In the search box type `AdministratorAccess`, check the box next to that policy.
   > 8. Click **Next**, review, click **Create user**.
   > 9. Click into the newly-created `requestqueue-deploy` user → **Security credentials** tab.
   > 10. Scroll to **Access keys** → click **Create access key**.
   > 11. **Use case:** select **"Command Line Interface (CLI)"**. Check the confirmation checkbox at the bottom. Click **Next**.
   > 12. (Optional) **Description tag:** anything memorable, e.g. `requestqueue-deploy-cli`.
   > 13. Click **Create access key**.
   > 14. **CRITICAL — on the success page, click "Download .csv file".** This saves both the Access Key ID and Secret to a CSV. AWS will not show the secret again after you leave this page; if you skip the download, you'll have to deactivate the key and create a new one (no big deal, just a few extra clicks).
   > 15. Save the CSV somewhere you'll remember. Common locations: `~/Downloads/` (default for most browsers), `~/Desktop/`, or this repo's root directory. The wizard will auto-find it in any of those locations in the next step.
   >
   > **Region:** this wizard assumes `us-east-1`. CloudFront ACM certs (used for custom domains, optional) MUST live in `us-east-1`, so unless you have a strong reason for another region, leave it. Region is set in `.env` as `REQUESTQUEUE_AWS_REGION`.

   `AskUserQuestion`: "Done — IAM user is created and the access-keys CSV is downloaded?" Options: "Yes, CSV is downloaded", "Hit a snag — let me describe", "Report an issue".

3. **Configure the AWS CLI profile** using `scripts/aws_setup_config.sh`.

   **Why we do it this way (tell the user this verbatim before running):**

   > Your AWS keys give full access to your AWS account, so we never want them transmitted off your machine — not to me (Claude), not to any LLM, not over any network. The wizard solves this by running a **local script** (`scripts/aws_setup_config.sh`) that reads your keys directly from the CSV file (or your system clipboard), then calls `aws configure set` to write them into `~/.aws/credentials`. The keys flow CSV-on-disk → local AWS CLI → `~/.aws/credentials` — they never appear in this chat. I'll run the script for you using my Bash tool, which executes locally on your machine (no different from running it yourself). The only output you'll see in the conversation is the verification: your AWS account ID and IAM user ARN, returned by `aws sts get-caller-identity`. Those are not secrets.

   **Step 3a — Find the CSV.**

   Run a `find` over the common save locations to discover candidate CSV files:

   ```bash
   find ~/Downloads ~/Desktop "$PWD" -maxdepth 2 -type f \( -iname '*accessKey*.csv' -o -iname '*credentials*.csv' \) 2>/dev/null
   ```

   Then branch based on the count:

   - **0 matches:** `AskUserQuestion`: "I couldn't find a CSV in ~/Downloads, ~/Desktop, or the repo root. Type the path manually?" Options: "I'll type the path next", "Use clipboard mode instead", "Re-run the IAM walkthrough", "Report an issue". On "type the path", accept their next message as the path. Tell them path conventions: absolute paths start with `/` (e.g. `/Users/you/Downloads/foo.csv`), relative paths start with `./` and are relative to the **repo root** (e.g. `./requestqueue-deploy_accessKeys.csv`).

   - **1 match:** present it as the suggested option in `AskUserQuestion`. Options: "Use this file: `<path>`" (recommended), "Use a different file (I'll type the path)", "Switch to clipboard mode", "Report an issue".

   - **2+ matches:** `AskUserQuestion` with up to 3 of the matches as separate options (most-recent first by mtime), plus "None of these — I'll type the path", "Switch to clipboard mode", "Report an issue".

   Validate the chosen path with `[ -f "$path" ]` before proceeding. If the file doesn't exist, re-ask.

   **Step 3b — Run the script (Claude runs it via `Bash`, not the user).**

   The script reads keys from a local file, calls silent `aws configure set`, and outputs only `aws sts get-caller-identity` JSON (account + ARN — non-secret). Since the secret value is never in the command-line text, **Claude runs this directly via the `Bash` tool** — don't make the user type a `!` invocation. The Bash tool runs in the user's local shell, so the keys stay on the user's machine the same way they would for `!`.

   Tell the user briefly what's about to happen (e.g. "Running `./scripts/aws_setup_config.sh --csv <path> requestqueue us-east-1` now — output will be the `aws sts get-caller-identity` JSON for verification"), then call:

   ```
   ./scripts/aws_setup_config.sh --csv <chosen path> requestqueue us-east-1
   ```

   **Args:** `requestqueue` is the AWS profile name (matches `REQUESTQUEUE_AWS_PROFILE` in `.env`). `us-east-1` is the region (matches `REQUESTQUEUE_AWS_REGION`). Both have these as defaults if omitted.

   On success the script prints `aws sts get-caller-identity` JSON + a `✓ Profile … is configured and authenticates successfully` line. Confirm to the user the configuration succeeded, name the AWS account ID and IAM-user ARN you saw, then `AskUserQuestion`: "Delete the CSV now? (Recommended — keys are in `~/.aws/credentials`, the CSV is no longer needed.)" Options: "Yes, delete it", "Keep it for now", "Report an issue". On "yes", run `rm <path>` via Bash.

   On failure, surface the error to the user and `AskUserQuestion`: "Debug, retry, switch to clipboard mode, or report an issue?"

   **Step 3c — Clipboard mode (alternative path, if user chose it).**

   Same principle: secret is read by the script from the local clipboard, never appears in the command line, never appears in script output. Claude runs both commands via `Bash` — the user just confirms the clipboard state between them.

   First, `AskUserQuestion`: "Copy your **Access Key ID** to clipboard and confirm when ready" Options: "Ready — clipboard has the Access Key ID", "Switch back to CSV mode", "Report an issue".

   On confirm, Claude runs via `Bash`:
   ```
   ./scripts/aws_setup_config.sh --clip-id requestqueue
   ```

   The script reads the clipboard via `pbpaste` (macOS) / `wl-paste` / `xclip` (Linux), validates format (Access Key ID must be 16-128 uppercase alphanumeric), and calls silent `aws configure set`. Output to Claude is just a length-only confirmation (no key value).

   Then `AskUserQuestion`: "Now copy your **Secret Access Key** to clipboard and confirm when ready" Options: "Ready — clipboard has the Secret", "Cancel and try CSV mode", "Report an issue".

   On confirm, Claude runs via `Bash`:
   ```
   ./scripts/aws_setup_config.sh --clip-secret requestqueue us-east-1
   ```

   The script validates the secret format (≥20 chars), calls silent `aws configure set` for the secret + region + output, then runs `aws sts get-caller-identity` to verify. Output to Claude is the JSON + success line. The clipboard contents never appear in the conversation because (a) the script doesn't echo them and (b) `pbpaste` is invoked inside the script, not in the user-typed command.

   **Last-resort fallback (separate terminal):** if neither mode works (clipboard tool missing on a Linux system, CSV parsing error on an unusual format, etc.), instruct the user to open a separate terminal and run `aws configure --profile requestqueue` interactively. Verify back here with `aws sts get-caller-identity --profile requestqueue`.

4. Write/update `REQUESTQUEUE_AWS_PROFILE` and `REQUESTQUEUE_AWS_REGION` in `.env` (use the same .env-merge pattern that `refresh_creds.sh` uses — strip-then-append, never overwrite the whole file).

5. **Optional custom domain — Claude provisions the ACM cert automatically.**

   `AskUserQuestion`: "Use AWS-default URLs (CloudFront / API Gateway hostnames) or set up a custom domain (`work.<yours>` + `api.<yours>`)?" Options:
   - "Skip — use AWS-default URLs (Recommended for first install)" → no `.env` changes for `CUSTOM_DOMAIN*`; move on.
   - "Set up custom domain" → continue with steps a–h below.
   - "Report an issue".

   The user has `AdministratorAccess` on the deploy IAM profile, so **Claude provisions the ACM certificate via the AWS CLI** — don't make the user navigate to ACM in the console. The user's only manual step (and only if their DNS isn't in Route 53) is adding a CNAME record in their DNS provider's UI.

   **a. Get the URL(s).** `AskUserQuestion`: "What URLs? You can answer in any of these forms:" with example options like "Just the base domain (e.g. `paydaay.com`) → I'll use the default `work.<base>` + `api.<base>` layout", "Base domain + custom subdomains (I'll ask)", "Both URLs explicitly (e.g. `workq.hilton.zone` + `api.workq.hilton.zone`) — paste them and I'll derive the rest", plus "Report an issue". User picks auto-Other to type freely.

   **Parse what they typed** to derive three values: `CUSTOM_DOMAIN` (the registered/Route-53-able zone), `WEBAPP_SUBDOMAIN` (subdomain prefix for the webapp), `API_SUBDOMAIN` (subdomain prefix for the API). Examples:
   - User types `paydaay.com` → CUSTOM_DOMAIN=`paydaay.com`, WEBAPP_SUBDOMAIN=`work` (default), API_SUBDOMAIN=`api` (default).
   - User types `workq.hilton.zone` and `api.workq.hilton.zone` → CUSTOM_DOMAIN=`hilton.zone`, WEBAPP_SUBDOMAIN=`workq`, API_SUBDOMAIN=`api.workq`. (Find the longest common DNS suffix that matches a Route 53 hosted zone they own; the leftover labels are the subdomains.)
   - User types `https://app.example.com` and `https://api.example.com` → strip protocol, CUSTOM_DOMAIN=`example.com`, WEBAPP_SUBDOMAIN=`app`, API_SUBDOMAIN=`api`.

   Confirm the parse back to the user in one line ("Parsed: CUSTOM_DOMAIN=hilton.zone, WEBAPP_SUBDOMAIN=workq, API_SUBDOMAIN=api.workq → webapp at workq.hilton.zone, API at api.workq.hilton.zone — correct?") and only proceed if it matches.

   **b. Detect Route 53 state.** Route 53 has TWO independent services — query both, since a registered domain does NOT automatically have a hosted zone:

      ```bash
      # Hosted zone (DNS records). Global service.
      ZONE_ID=$(aws route53 list-hosted-zones --profile requestqueue \
        --query "HostedZones[?Name=='<base>.'].Id" --output text)

      # Registered domain (Registrar). Lives only in us-east-1.
      REGISTERED=$(aws route53domains list-domains --profile requestqueue \
        --region us-east-1 \
        --query "Domains[?DomainName=='<base>'].DomainName" --output text)
      ```

      Three cases:

      - **Hosted zone exists** (`ZONE_ID` non-empty) → Claude can fully automate DNS validation by UPSERTing CNAMEs into the existing zone (step e). Best case.

      - **Registered but no hosted zone** (`ZONE_ID` empty, `REGISTERED` non-empty) → very common gotcha when a user transfers a domain into Route 53: the registrar holds the registration but no DNS hosting is set up. **Offer to create a hosted zone.** `AskUserQuestion`: "`<base>` is registered in your Route 53 account but has no hosted zone. Create a hosted zone now? I'll also update the domain's nameservers to point at it (so DNS resolves through Route 53), which lets me automate everything else." Options: "Yes, create the hosted zone (Recommended)", "No — I manage DNS elsewhere; I'll add validation CNAMEs manually", "Report an issue".

         On "Yes":
         ```bash
         # Create the hosted zone
         aws route53 create-hosted-zone \
           --name "<base>" \
           --caller-reference "requestqueue-install-$(date +%s)" \
           --profile requestqueue
         # Capture HostedZone.Id and DelegationSet.NameServers (4 of them)

         # Point the registered domain at the new zone's NS records
         aws route53domains update-domain-nameservers \
           --domain-name "<base>" \
           --nameservers Name=ns-XXX.awsdns-XX.com Name=... Name=... Name=... \
           --region us-east-1 --profile requestqueue
         ```
         Tell the user: "Created hosted zone `<id>` and pointed `<base>`'s registrar nameservers at it. NS propagation typically completes in 1–60 minutes — ACM validation will work once propagation reaches the resolvers ACM uses (usually within 5 min). Continuing." Then proceed as if `ZONE_ID` was non-empty.

      - **Not registered with us at all** (`ZONE_ID` empty, `REGISTERED` empty) → the user manages DNS at a third-party provider (Cloudflare, Namecheap, GoDaddy, etc.). Surface validation CNAMEs after the cert request and ask the user to add them manually (step e fallback path).

   **c. Request the certificate.** Use specific names for the webapp + API hosts (not a wildcard) — wildcards in ACM cover only one DNS label, so multi-label subdomains like `api.workq.hilton.zone` need explicit SANs:
      ```
      aws acm request-certificate \
        --domain-name "<webapp_subdomain>.<base>" \
        --subject-alternative-names "<api_subdomain>.<base>" \
        --validation-method DNS \
        --region us-east-1 \
        --profile requestqueue \
        --tags Key=Name,Value=requestqueue-<base>
      ```
      For the default `work`/`api` layout you can use a wildcard (`--domain-name "*.<base>" --subject-alternative-names "<base>"`) instead — fewer validation CNAMEs. Decide based on how many DNS labels the subdomains have. Capture the returned `CertificateArn`.

   **d. Fetch the validation CNAMEs.** ACM populates these asynchronously. Poll with a brief delay:
      ```
      sleep 5
      aws acm describe-certificate --certificate-arn <arn> \
        --region us-east-1 --profile requestqueue \
        --query 'Certificate.DomainValidationOptions[*].ResourceRecord' --output json
      ```
      You'll get one or more `{Name, Type, Value}` records. Retry every 5s up to 60s if the field is empty.

   **e. Validate.**
      - **If Route 53 hosted zone exists:** write a `change-batch.json` with `UPSERT` actions for each validation CNAME and submit:
        ```
        aws route53 change-resource-record-sets \
          --hosted-zone-id <zone-id> \
          --change-batch file:///tmp/r53-validation.json \
          --profile requestqueue
        ```
        Tell the user: "Added validation CNAME(s) to Route 53 zone `<zone-id>`. ACM typically validates within 1–5 minutes."
      - **If no Route 53 zone:** print the CNAME records (Name + Value) clearly. `AskUserQuestion`: "Add the CNAME(s) above to your DNS provider, then confirm — done?" Options: "Done — added the CNAMEs", "Report an issue".

   **f. Wait for `ISSUED`.** Poll status every 15s, surfacing a one-line update to the user every ~60s:
      ```
      aws acm describe-certificate --certificate-arn <arn> \
        --region us-east-1 --profile requestqueue \
        --query 'Certificate.Status' --output text
      ```
      Until status is `ISSUED` (typical: 1–5 min Route 53 / 5–30 min third-party DNS). On `FAILED`, surface the reason from `FailureReason` and `AskUserQuestion` retry/skip/report.

   **g. Write to `.env`** (idempotent strip-then-append). Always write `CUSTOM_DOMAIN` + `CUSTOM_DOMAIN_CERT_ARN`. Only write the subdomain overrides if they differ from the defaults `work` / `api`:
      ```
      REQUESTQUEUE_CUSTOM_DOMAIN=<base>
      REQUESTQUEUE_CUSTOM_DOMAIN_CERT_ARN=<arn>
      # only if non-default:
      REQUESTQUEUE_WEBAPP_SUBDOMAIN=<webapp_subdomain>
      REQUESTQUEUE_API_SUBDOMAIN=<api_subdomain>
      ```

   **h. Heads-up to user:** "Custom domain `<domain>` is provisioned. After Phase 7 deploy, you'll need DNS records for `work.<domain>` (CloudFront) and `api.<domain>` (API Gateway) — these come from `.requestqueue.outputs.json`. If you're in Route 53, I'll add them automatically post-deploy. Otherwise you'll add them manually."

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

**Fine-grained PAT** (`REQUESTQUEUE_GITHUB_TOKEN` — **optional**, used by `local/build` for git push + `gh pr create`):

This token is **not needed** when the machine running `make monitor` has already run `gh auth login` — `local/build/git_ops.py` only forces `GITHUB_TOKEN`/`GH_TOKEN` env-var override when the .env value is non-empty; otherwise git/gh subprocesses inherit the parent environment and gh's keyring auth takes effect.

**Decision tree:**

1. Read current `REQUESTQUEUE_GITHUB_TOKEN` from `.env`. If non-empty: skip — already configured.
2. If empty AND `gh auth status` succeeded in the previous step (Phase 3 step 1) AND the user plans to run `make monitor` on **this same machine**: **skip the PAT entirely**. Tell the user: "PAT is optional — your local `gh auth login` keyring will be used. Leaving REQUESTQUEUE_GITHUB_TOKEN empty." Move on.
3. If empty AND the user plans cross-machine local-server (e.g. monitor runs on a Pi, VPS, or different laptop): walk through PAT creation since the remote machine won't have access to this machine's keyring:
   - Print the URL `https://github.com/settings/personal-access-tokens/new`.
   - Explain required scopes: `Contents: Read and write` and `Pull requests: Read and write` on the target repo. If they plan to enable `REQUESTQUEUE_GITHUB_AUTO_MERGE`, also `Administration: Read and write`.
   - `AskUserQuestion`: "Set token expiration:" with options "30 days", "90 days", "1 year", "No expiration (least secure)", "Report an issue".
   - **Don't ask for the token value via AskUserQuestion** (that puts the secret in the conversation transcript). Instead use the same clipboard pattern as Phase 2 step 3c: have the user copy the token to their clipboard, then run a script that reads from clipboard, validates with `gh api user`, and writes to `.env`. (If no such script exists yet, write one — `scripts/set_github_token.sh` is the natural shape, mirroring `aws_setup_config.sh --clip-secret`.)

The decision between (2) and (3) depends on the answer to Phase 9's "where will the local-server live?" question. **Defer the PAT decision until Phase 9** — it's the right time to know whether (2) or (3) applies. Tell the user during Phase 3: "PAT decision deferred to Phase 9 (local-server location). For now, leaving REQUESTQUEUE_GITHUB_TOKEN empty — gh keyring auth will work for same-machine setups; we'll capture a PAT later if you go cross-machine."

---

# Phase 4 — Walk through `.env`

Read existing `.env`. For each variable below, do the following dance — **one variable at a time**, JIT. Don't bundle multiple variables into one `AskUserQuestion`; each gets its own ask, the user answers, you write to `.env`, then move to the next.

For each variable:

- **Detect `.env.example` placeholders** as if unset. Specifically: `@example.com` for `EMAIL_WHITELIST`, `https://github.com/yourorg/yourrepo.git` for `GITHUB_REPO_URL`, `your-domain.com` for `CUSTOM_DOMAIN`, etc. Treat these the same as missing values — don't ask the user to "keep" a placeholder.
- **If already set with a real (non-placeholder) value**, `AskUserQuestion`: "`<VAR>` is set to `<value>`. Keep this?" Options: "Keep", "Change it", "Report an issue". (Skip the ask entirely for technical defaults the user is unlikely to care about — see "Don't ask about technical defaults" below.)
- **If empty, unset, or placeholder**, `AskUserQuestion` for the value with concrete suggestions. Use 2–3 specific options (e.g. for `EMAIL_WHITELIST`: "Use my email: dev@paydaay.com", "Use @paydaay.com domain wildcard", "Report an issue") + the framework's auto-`Other`. The user picks auto-Other to type their own value inline; the typed string becomes the answer.

**Never include "Other" as one of your own options.** The framework auto-adds it for free-text typing. Adding your own "Other" defeats this — it'll be treated as a fixed label and the user can't type a value.

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

- **Keep the wizard flowing — don't pause between phases.** When a phase or step finishes successfully, briefly tell the user what just finished and what's next, then **continue immediately** to the next step. Don't `AskUserQuestion` for "shall I continue?" or "did that work?" when the answer is already visible (exit code 0 + expected success line in output). Only pause for: (a) genuine user input that's needed to proceed (an answer, a credential paste, a path, a yes/no for an irreversible action like `rm`), (b) the user picking "Report an issue", (c) actual failure states. The wizard has 9 phases and many sub-steps; if you stop after each one to ask permission, the user loses track of progress and may think the install finished prematurely. Trust the idempotency — phases detect their own state, so a re-run from any point is safe; that's why you don't need permission to keep going.

- **Always tell the user where they are in the overall progress.** When transitioning between phases (or after a long step like Phase 7 deploy), use a concise one-line indicator: "✓ Phase 2 done (AWS profile configured) → Phase 3: GitHub auth (next)". This anchors the user against the 9-phase outline so they know how much remains.

- **`AskUserQuestion` auto-`Other`: never add your own "Other" option.** The framework automatically adds an "Other" choice that lets the user type a free-text answer inline; the typed string becomes the answer. If you add your own option labeled "Other (I'll type it)" or similar, the framework treats it as a fixed label — the user picks it, you get the *label* back as the answer, and they have no way to type their actual value. Always provide 1–3 concrete suggested values + "Report an issue" as your options, and trust the framework to add Other for free-text. Use this for any field where the user might want to type a custom value: emails, domains, URLs, paths, timezones, etc.

- **JIT, one question at a time — don't bundle.** Each free-text value gets its own `AskUserQuestion` at the moment we need it. Capture the answer, act on it (write to `.env`, run a command, request a cert), then ask the next question. **Never** ask the user to "type these N values in your next message as a multi-line block" — that's the wizard regressing into a printed README. The whole point of the wizard's conversational shape is that each answer can immediately drive the next prompt (e.g. user types domain → Claude detects Route 53 → next question is automatically tailored based on what was found). Bundling collapses that loop into a static form.

- **Use the AWS access you have.** Once Phase 2 is done, Claude has AdministratorAccess on the deploy IAM profile. Wherever a wizard step would otherwise require the user to navigate to the AWS console, do it via `aws` CLI instead. Examples: provisioning ACM certs (Phase 2 step 5), adding Route 53 validation/routing records, looking up CloudFront distribution IDs, fetching CloudFormation outputs. Only fall back to "click around the console" when there's no programmatic equivalent (e.g. AWS account creation itself, root-user MFA). The user opted into the wizard precisely so they don't have to do AWS console clicking they don't need to do.
