// Loads runtime config that lives on S3 (uploaded by scripts/publish.sh).
// Build-time constants are baked in via vite.config.ts; runtime config is
// the editable bits — display timezone and the list of `reqarea` names that
// the user can pick from. Both are derived from config/prompt_parts.yaml +
// REQUESTQUEUE_DISPLAY_TIMEZONE by scripts/derive_app_config.py at deploy time.
//
// The full prompt_parts.yaml is NEVER published — pre/post text stays
// server-side. See config/README.md.

import type { RuntimeConfig } from "../types";

const WEBAPP_BASE = (() => {
  if (typeof window !== "undefined") {
    return `${window.location.origin}`;
  }
  return __REQUESTQUEUE_WEBAPP_URL__;
})();

interface AppJson {
  display_timezone?: string;
  prompt_areas?: string[];
}

async function fetchAppJson(): Promise<AppJson> {
  try {
    const resp = await fetch(`${WEBAPP_BASE}/config/app.json`, { cache: "no-cache" });
    if (!resp.ok) return {};
    return (await resp.json()) as AppJson;
  } catch {
    return {};
  }
}

let cached: RuntimeConfig | null = null;

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  if (cached) return cached;
  const app = await fetchAppJson();
  const areas = (app.prompt_areas && app.prompt_areas.length > 0)
    ? app.prompt_areas.slice()
    : ["General"];
  if (!areas.includes("General")) areas.unshift("General");
  cached = {
    api_url: __REQUESTQUEUE_API_URL__,
    cognito_user_pool_id: __REQUESTQUEUE_COGNITO_USER_POOL_ID__,
    cognito_client_id: __REQUESTQUEUE_COGNITO_CLIENT_ID__,
    cognito_region: __REQUESTQUEUE_COGNITO_REGION__,
    webapp_url: __REQUESTQUEUE_WEBAPP_URL__,
    display_timezone: app.display_timezone || "UTC",
    prompt_areas: areas,
  };
  return cached;
}
