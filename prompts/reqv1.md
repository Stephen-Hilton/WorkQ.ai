# WorkQ.ai — Requirements (v1)

> This document is the authoritative spec. It was originally a high-level brief, then refined through 24 design decisions (recorded inline below as **DECISION** notes and summarized in the **Decisions log** at the bottom). The implementation must match this document.

## Goal

A simple, secure web app running on AWS that allows authorized users to create and monitor "work requests", which are then built or planned by a headless `claude code` running on a separate local server.

## Architecture components

### AWS (deployed via SAM)

- **Cognito** — security / authentication for both human users (webapp) and the local server (service user). Single user pool, single app client, single API Gateway authorizer.
- **API Gateway + Lambda** — REST CRUD over the work-request DDB table. Cognito JWT auth on every route. *(DECISION 9: a single Cognito authorizer serves both webapp and local; no IAM SigV4, no separate `/builder/*` route prefix.)*
- **DynamoDB** — single table for work requests. *(DECISION 1: PK = `reqid` only; no sort key, no GSI. `GET /status/<status>` is a `Scan` with a filter expression. Volume is expected to be small — a few hundred records — so scan cost is negligible.)*
- **S3 + CloudFront (OAC)** — webapp static hosting. *(DECISION 7: CloudFront fronts a private S3 bucket via OAC for HTTPS and edge caching.)*
- **SSM Parameter Store** — `/workq/email_whitelist`, the canonical email whitelist for sign-up.
- **Secrets Manager** — `/workq/service-local-monitor/password`, the password for the Cognito service user used by the local server.
- *(DECISION 2: There is no SQS queue. The local monitor pure-polls the API every `polling_seconds`.)*

### Local server (anywhere — laptop, EC2, or otherwise)

Two long-running processes, started independently:

- **`local/monitor`** — long-lived; polls the API for queued requests and dispatches them. Also detects stuck builds. *(DECISION 11: monitor is orchestration only; it never modifies DDB directly.)*
- **`local/build`** — short-lived per-request subprocess spawned by the monitor (`Popen` + `wait()`, not daemonized). Runs the full lifecycle of one request: status updates, prompt assembly, headless `claude code` invocation, result writeback, optional git push + PR creation.

*(DECISION 10: builds run strictly serially across the machine — one claude session at a time.)*
*(DECISION 9: runtime has zero AWS IAM credentials — only a Cognito service-user password bootstrapped once via `scripts/bootstrap_local.sh`.)*

### Configuration

Two config layers:

- **Deploy inputs (`.env`, hand-edited, gitignored):**
  - `WORKQ_AWS_REGION` — must be `us-east-1` if using a custom domain (CloudFront cert constraint).
  - `WORKQ_AWS_ACCESS_KEY_ID` / `WORKQ_AWS_SECRET_ACCESS_KEY` — used only for `sam deploy` and `scripts/bootstrap_local.sh`. Not needed at local-server runtime.
  - `WORKQ_CUSTOM_DOMAIN` (optional) — e.g., `example.com`. If set, webapp deploys to `work.<domain>` and API to `api.<domain>`.
  - `WORKQ_CUSTOM_DOMAIN_CERT_ARN` (optional, required if `WORKQ_CUSTOM_DOMAIN` is set) — single ACM cert in `us-east-1` covering both subdomains (wildcard or SAN).
  - `WORKQ_EMAIL_WHITELIST` — comma-separated emails or `@domain` entries; seeds the SSM whitelist on first deploy.
  - `WORKQ_GITHUB_REPO_URL` — the repo claude will operate on.
  - `WORKQ_GITHUB_BRANCH` — default `main`.
  - `WORKQ_GITHUB_TOKEN` — fine-grained PAT with `contents:write` and `pull_requests:write` (plus admin if auto-merge enabled).
  - `WORKQ_GITHUB_AUTO_MERGE` — `false` by default. If `true`, every PR is auto-merged via `gh pr merge --admin` immediately after creation. *(DECISION 12.)*
  - `WORKQ_GITHUB_AUTO_MERGE_METHOD` — `squash` (default) | `merge` | `rebase`.
  - `WORKQ_POLLING_SECONDS` — monitor poll interval; default 30.
  - `WORKQ_BUILD_TIMEOUT_SECONDS` — max claude wall-clock; default 2700 (45 min). *(DECISION 9b.)*
  - `WORKQ_DISPLAY_TIMEZONE` — display-only TZ for timelog. UTC is always used for storage. Default `UTC`. Use abbreviations from <https://en.wikipedia.org/wiki/List_of_time_zone_abbreviations>.
  - `WORKQ_PROMPT_PARTS_PATH` — path on disk; default `./prompts/prompt_parts.yaml`.

- **Deploy outputs (`.workq.outputs.json`, auto-written by `sam deploy`, gitignored):**
  - `webapp_url`, `api_url`, `cognito_user_pool_id`, `cognito_client_id`, `cognito_domain`, `s3_webapp_bucket`, `cloudfront_distribution_id`. Webapp `pnpm build` reads this to bake values into the bundle. *(DECISION 7, 23.)*

### `prompt_parts.yaml`

Per-project prompt customization. Source of truth lives at `prompts/prompt_parts.yaml` in this repo *(DECISION 24)*; `scripts/publish.sh` uploads it to `s3://<webapp-bucket>/config/prompt_parts.yaml` so the webapp can read it at runtime, and `local/build` reads it from disk.

Shape *(DECISION 3 — map-of-objects, not lists; spec's original example was malformed YAML)*:

```yaml
all:
  pre: |
    You are a headless planning and coding engine, with no interactivity with the user.
    You cannot ask questions. Whatever your final response is will be returned as the
    "Response" back to the user, and the session will end.
  post: |
    Always structure your response as markdown, with this structure:
    # <Generated title for the request>
    Restate your understanding of the request in bullet-list form, and what actions
    you performed at a high level to satisfy the request.

    ---
    If you have a critical question that must be answered before this can be considered
    complete, end your response with the exact line `<!-- workq:status=pending_review -->`.
    If you tried but could not satisfy the request, end with `<!-- workq:status=failed -->`.
    Otherwise, omit the fence and the system will mark the request complete.

status:
  build:
    pre: |
      Make code changes specified below. Once complete, test, deploy to AWS using the
      credentials in the local Config file, then test the deployed change.
    post: |
      ## Details
      Outline what changes were made. Include any concerns or questions you may have
      had, and what assumptions you made.
      Include notes on any deployment success/failure/challenges.
      Include testing results, both local pre-deploy and post-deploy.

  planning:
    pre: |
      Enter planning mode, and build a plan for the code changes specified below.
      Once complete, write the complete plan to your Response, update the request to
      "pending review" and end.
    post: |
      ## Plan
      Outline your entire plan, including any supporting markdown grids, mermaid or
      ascii architecture diagrams, etc.

      ## Questions
      This is a Q&A for the user to fill in. The user will answer in-line below using
      the `> quote` markdown line prefix.
      - question 1:
      - question 2:

areas:
  webapp:
    pre: "Change pertains primarily to the UI files in `/ui/webapp/*`"
    post: |
      ## Playwright Tests
      For webapp visible or behavior changes, use Playwright to perform UAT, and
      place results here.
  APIs:
    pre: "Change pertains primarily to API files, found in `/apis/*`"
    post: ""
  local_monitor:
    pre: "Change pertains only to the local monitor files, found in `/local/monitor/*`"
    post: "!!IMPORTANT: Once all testing is complete and code is pushed, restart the local_monitor process and confirm it working."
  local_build:
    pre: "Change pertains only to the local build files, found in `/local/build/*`"
    post: "!!IMPORTANT: be sure to add a new TEST Request to confirm the update worked. This must be submitted as a new Request API, and monitor expected outcome (since this 'build' process will still be running on the old code)."
```

**Notes on the shape:**

- `all.pre/post`, `status.<key>.pre/post`, `areas.<key>.pre/post` — every entry has both `pre` and `post`; either may be empty string.
- `status` keys are short (`build`, `planning`) and refer to the *action being performed*, not the queue state. `local/build` maps DDB statuses `"queued for build" → "build"` and `"queued for planning" → "planning"`. *(DECISION 3.)*
- `areas` keys are arbitrary, defined per project. `"General"` is auto-injected with empty `pre/post` if not present in yaml. *(DECISION 22.)*
- `prompt_parts.yaml` content (text inside `pre`/`post`) is markdown — code snippets, mermaid, etc. are fine. YAML block-scalar (`|`) handles escaping.

### Prompt assembly

Per request, `local/build` constructs:

```
<all.pre>
<status.<mapped>.pre>
<areas.<reqarea>.pre>

<request text, plus existing response prepended as "# Previous AI Responses" if non-empty>

<all.post>
<status.<mapped>.post>
<areas.<reqarea>.post>
```

*(DECISION 3: the spec's original example ended with `<area.[area].pre>` — that was a typo for `.post`.)*

## DDB data elements

Each record:

- **`reqid`** — PK. uuid v7 (time-ordered). Server-generated only; clients cannot supply. *(DECISION 17.)*
- **`reqstatus`** — one of (constrained by webapp UI, but DDB stores any string):
  - `queued for build` — local monitor will pick up next poll.
  - `queued for planning` — local monitor will pick up next poll.
  - `pending review` — needs human attention; local ignores.
  - `building` — local build in progress.
  - `planning` — local plan in progress.
  - `complete` — done.
  - `failed` — local build attempted but produced nothing usable. *(DECISION 14: new status added.)*
- **`reqarea`** — one of the keys in `prompt_parts.areas`. Defaults to `General`.
- **`reqcreator`** — derived from the JWT `email` claim on POST. **Immutable** after creation; PUT silently strips this field. Webapp users → their own email; service user → `service-local-monitor@workq.internal`. *(DECISION 19.)*
- **`reqpr`** *(renamed from `reqcommit` per DECISION 13)* — URL of the GitHub PR created by `local/build` for this request, e.g. `https://github.com/.../pull/39`. Empty for planning-only or zero-commit requests.
- **`request`** — main user request text (markdown). On Clone, source `response` is appended under a `## Previous AI Response` heading so context is preserved permanently in the new record. *(DECISION 18.)*
- **`response`** — main AI response text (markdown). Includes claude's full output. On re-submission of the same record (e.g., after `pending review`), local/build appends the existing response to the prompt under `# Previous AI Responses`, then prepends new output to `response`.
- **`timelog`** — list of objects: `[{"status": "<status>", "ts": "<iso8601-utc>"}, ...]`. Append-only. Webapp converts UTC → `WORKQ_DISPLAY_TIMEZONE` for display. The list length doubles as the version vector for optimistic concurrency on PUT. *(DECISIONS 16, 21.)*

## APIs

REST CRUD on a single resource. Cognito JWT auth on every route. *(DECISION 4.)*

| Method | Path | Behavior |
|---|---|---|
| GET | `/id/<uuid>` | Single record by `reqid`. 404 if missing. |
| GET | `/status/all` | All records (DDB Scan). |
| GET | `/status/queued` | Both `queued for build` and `queued for planning` in one response. |
| GET | `/status/<status>` | Single status (URL-encode spaces, e.g. `pending%20review`). |
| POST | `/id` | Create. Server generates `reqid` (uuid v7), sets `reqcreator` from JWT. Body: any of `reqarea`, `reqstatus`, `request`, `response`. Initializes `timelog` with one entry. |
| PUT | `/id/<uuid>` | Update. Body: any subset of mutable fields plus `expected_timelog_len` (length of `timelog` when the client loaded the record). Lambda enforces optimistic concurrency via `ConditionExpression: size(timelog) = :expected_len` → returns **409 Conflict** with current record on mismatch. Strips `reqcreator` from body. Appends a new `timelog` entry on every successful update. |
| DELETE | `/id/<uuid>` | Delete by `reqid`. |

## Workflow

### User opens webapp

1. User opens the webapp URL.
2. User signs up with their email. Pre-signup Lambda checks SSM whitelist (`/workq/email_whitelist`); rejects if no match. Wildcard `@domain.com` entries match anyone in that domain. *(DECISION 8.)*
3. After approval, user signs in. Cognito issues JWT.
4. Webapp loads runtime config:
   - Cognito IDs / `api_url` from baked-in build constants.
   - `prompt_parts.yaml` and `app.json` (timezone) fetched from S3 via CloudFront. *(DECISION 23.)*
5. Webapp renders.

### Webapp UI

- **Top bar:**
  - Summary count of all requests, by `reqstatus` (plus a "total" tally).
  - "New Request" and "Refresh Data" buttons. Auto-refresh every 20 seconds. *(DECISION 21.)*
- **Body:**
  - Accordion control listing all requests (collapsed by default).
  - Each header shows: `reqstatus`, `reqarea`, first line of `request` (as a title proxy), first `timelog` entry's timestamp (in `WORKQ_DISPLAY_TIMEZONE`), and an Actions context menu.
  - **Actions menu:**
    - Status changes: "Queue for Build", "Queue for Planning", "Mark for Review", "Complete".
    - "Clone this Request" — creates new record per DECISION 18 semantics; refreshes the page.
    - "Delete" — confirms, then deletes; refreshes.
  - Expanding a row shows all DDB fields:
    - `reqid` and `reqcreator` immutable, displayed as a small horizontal strip across the top.
    - `reqstatus` and `reqarea` as selectors.
    - `request` and `response` as multi-line markdown editors with syntax highlighting (`@uiw/react-md-editor`). *(DECISION 20.)*
    - `reqpr` as a clickable link.
    - `timelog` at the bottom (read-only), all timestamps in `WORKQ_DISPLAY_TIMEZONE`.
    - Save button at the bottom labeled `Save and <action>` — same action options as the Actions menu.
  - **Auto-refresh pause:** if a row is expanded *and* dirty, the 20s refresh timer pauses with a banner "Auto-refresh paused while editing. Save or cancel to resume." Resumes on Save (success) or Cancel. *(DECISION 21.)*
  - **Conflict (409) on save:** webapp shows a "this record changed while you were editing" diff dialog with options to merge or discard. Optimistic-concurrency check is `size(timelog)` on the server side. *(DECISION 21.)*

### New request flow

1. User clicks "New Request".
2. A mobile-friendly lightbox appears with all DDB fields editable (except `reqid` and `reqcreator`).
3. User fills in `request` text, optionally selects `reqarea` (defaults to `General`).
4. User clicks `Save and Queue for Build` (or Planning, or Mark for Review (default), or Complete).
5. Webapp `POST /id`s the record; refreshes the page on success.

### Local monitor + build cycle

1. `local/monitor` wakes up every `WORKQ_POLLING_SECONDS`.
2. Calls `GET /status/queued`; sorts results by `reqid` (uuid v7 = create-order).
3. Also calls `GET /status/all` and scans for stuck records: any in `building` or `planning` whose latest `timelog.ts` is older than `WORKQ_BUILD_TIMEOUT_SECONDS + 60s`. Force-sets those to `failed` with a "Build appears to have died" response, including a `# Recommended Next Step` section. *(DECISION 15.)*
4. For each queued record, top to bottom:
   1. `Popen("python -m local.build <reqid>")` and `wait()` for it (strict serial). *(DECISION 10.)*
   2. `local/build`:
      - Updates DDB `reqstatus` to `building` or `planning`.
      - Creates a `git worktree` from the bare clone at `local/workspace/.git-bare/`. *(DECISION 12.)*
      - Assembles the prompt from `prompt_parts.yaml` + record fields.
      - Spawns `claude code -p --dangerously-skip-permissions` with the prompt; captures stdout in memory.
      - Wall-clock timeout: `WORKQ_BUILD_TIMEOUT_SECONDS` (default 45 min). On timeout: kill, status=`failed`, response includes last 100 lines of output.
      - For `build` requests:
        - If claude made commits: `git push origin workq/<reqid>`, `gh pr create`, capture PR URL into `reqpr`. If `WORKQ_GITHUB_AUTO_MERGE=true`: also `gh pr merge --<method> --delete-branch --admin`.
        - If claude made no commits: leave `reqpr` empty, status=`pending review`, response explains.
      - For `planning` requests: no commit/push/PR.
      - Parses last 500 bytes of stdout for `<!-- workq:status=<value> -->` fence. Whitelist: `pending_review`, `complete`, `failed`. *(DECISION 14.)*
      - Sets final status (or per fence override or per failure mapping).
      - **All failure responses include a `# Recommended Next Step` section** with copy-pasteable commands (e.g., manual `gh pr create`, `git -C ... merge --squash`). *(DECISION 15.)*
      - Removes the worktree. Exits.
5. After draining the queue, monitor sleeps for `WORKQ_POLLING_SECONDS`.

### User monitors and acts

- User watches the webapp (auto-refresh every 20s).
- For `pending review` items, user expands, edits `request`/`response`, clicks `Save and Queue for...`.
- For `failed` items, user reviews the `# Recommended Next Step`, fixes, then re-queues or marks complete or deletes.
- "Clone this Request" duplicates with prior context baked into the new `request` text.

## Authentication and security

- **Webapp users:** Cognito sign-up gated by SSM whitelist (`@domain` wildcards supported). JWT with 24h access + 30d refresh. Bearer token on every API call.
- **Local server:** authenticates as Cognito service user `service-local-monitor`. Password fetched once via `scripts/bootstrap_local.sh` to `~/.config/workq/credentials`. Runtime has zero AWS IAM credentials. *(DECISION 9.)*
- **Token refresh:** every API call checks `expires_in`; if <300s, refreshes via the refresh token before the call. Falls back to password login on refresh failure. Refresh always between API calls, never during one — API Gateway 30s timeout makes in-flight expiry impossible.
- **Email whitelist management:** `scripts/whitelist_user.sh -a/-r/-l/-h <email_or_@domain>`.
- **Pre-signup Lambda:** auto-confirms whitelisted users; rejects others.

## Deploy / operate

- **First deploy (developer's machine):**
  1. `cp .env.example .env` and fill in.
  2. `make publish` (runs `sam deploy`, `pnpm build`, `aws s3 sync`, runtime config upload, CloudFront invalidation).
  3. `scripts/whitelist_user.sh -a yourname@yourdomain.com`.
- **Local server setup (one-time, on the box that runs claude):**
  1. `scripts/bootstrap_local.sh` (uses dev creds to fetch service-user password from Secrets Manager).
  2. `python -m local.monitor` (or `make monitor`) — long-running.
- **Updating prompts/config without code changes:**
  - Edit `prompts/prompt_parts.yaml` → `aws s3 cp prompts/prompt_parts.yaml s3://<bucket>/config/` + `aws cloudfront create-invalidation`.
  - Edit SSM whitelist via `scripts/whitelist_user.sh`.

---

## Decisions log

The 24 decisions made when refining this spec. Each is referenced inline above as `(DECISION N)`.

1. **DDB schema** — `reqid` PK only; no SK, no GSI. `Scan + filter` for status queries. Volume too small to justify a GSI.
2. **No queue.** local_monitor pure-polls.
3. **`prompt_parts.yaml` shape** — map-of-objects (`all`, `status`, `areas`); short `status` keys (`build`/`planning`) with mapping; assembly ends with `area.post`.
4. **API paths** — `/id/...` and `/status/...`; explicit `/status/all`, `/status/queued`, `/status/<exact>`.
5. **Tech stack** — Python 3.12 (apis + local) via `uv`; React + Vite + TS + Tailwind + shadcn/ui + `@uiw/react-md-editor` via pnpm.
6. **IaC** — AWS SAM. `sam sync --watch` for ~5–10s dev iteration.
7. **CloudFront + optional unified custom domain.** `WORKQ_CUSTOM_DOMAIN=example.com` → `work.<d>` + `api.<d>` with one ACM cert. Inputs in `.env`, outputs in `.workq.outputs.json`.
8. **Cognito whitelist via SSM Parameter Store.** Wildcards `@domain.com`. Helper `scripts/whitelist_user.sh -a/-r/-l/-h`.
9. **Cognito for both webapp and local.** Service user with password in Secrets Manager. `bootstrap_local.sh` for one-time fetch. Token TTL 24h/30d. Build timeout 45 min.
10. **Strict serial builds.** One claude session at a time.
11. **Two-process design.** monitor orchestrates; build is a child subprocess. `local/logs/` is operational telemetry only — claude's output goes to `response`.
12. **`git worktree`-per-build.** Branch `workq/<reqid>`; always create PR; optional auto-merge with `--admin`.
13. **`reqcommit` renamed to `reqpr`.** Stores PR URL.
14. **Status fence** `<!-- workq:status=<value> -->` (whitelist: `pending_review`, `complete`, `failed`). New `failed` status added.
15. **Failure handling.** Uniform mapping; every failure response has a `# Recommended Next Step`; stuck-build detector in monitor.
16. **`timelog` is list of objects.** UTC stored; displayed in `WORKQ_DISPLAY_TIMEZONE`.
17. **uuid v7 server-side only.**
18. **Clone semantics.** `request` = source.request + (source.response as `## Previous AI Response` if non-empty); fresh response/timelog/reqpr; status=`pending review`; reqcreator=current user. Webapp-side via GET+POST.
19. **`reqcreator`** from JWT email; immutable.
20. **Webapp libs.** `@uiw/react-md-editor`, `shadcn/ui`, `lucide-react`.
21. **Auto-refresh + edit safety.** 20s hardcoded; pause-while-editing banner; optimistic concurrency via `size(timelog)`; 409 on stale.
22. **`General` reqarea auto-injected** with empty pre/post.
23. **Webapp config: hybrid.** Build-time bake + runtime fetch.
24. **`prompt_parts.yaml` source of truth = repo.** Published to S3. CI validation via `scripts/validate_prompt_parts.py`.
