# RequestQueue — runtime configuration

This directory holds files you edit at runtime to configure your RequestQueue deployment. They are **not** source code, **not** version artifacts, and **not** auto-generated. They live in version control so changes go through PR review like any other code change.

## Files

### `prompt_parts.yaml`

Per-project prompt customization for the headless `claude code` invocation. Defines:

- **`all.pre/post`** — prepended/appended to *every* prompt (status-fence instructions, response format, etc.).
- **`status.<key>.pre/post`** — added when the request is being acted on as that action. Keys: `build`, `planning`. The DDB → action mapping is `"queued for build" → "build"`, `"queued for planning" → "planning"`.
- **`areas.<key>.pre/post`** — added based on the record's `reqarea`. Keys are arbitrary; users pick them in the webapp dropdown. `General` is auto-injected with empty pre/post if absent.

### Who reads this file

- **`local/build/`** reads it from disk (path: `REQUESTQUEUE_PROMPT_PARTS_PATH`, default `./config/prompt_parts.yaml`) to assemble the prompt for each build.
- **The webapp** does **not** read this file directly. At deploy time, `scripts/publish.sh` extracts the list of area keys and bakes them into `app.json` (uploaded to S3). The webapp fetches `app.json` to populate the `reqarea` dropdown.

This split keeps the prompt content (which may contain sensitive build instructions, internal file paths, etc.) entirely server-side. The webapp never sees the `pre`/`post` text — only the area names users can pick from.

## Editing flow

1. Edit `config/prompt_parts.yaml` here in the repo.
2. Run `make validate` (or `python3 scripts/validate_prompt_parts.py`) to confirm the schema is valid.
3. `make publish-prompts` — uploads the derived `app.json` to S3 and invalidates CloudFront. The full yaml stays local (used by `local/build` only).
4. Restart `local/monitor` if needed (it picks up the new file at next build).
