// Loads runtime config that lives on S3 (uploaded by scripts/publish.sh).
// Build-time constants are baked in via vite.config.ts; runtime config is
// the editable bits: prompt_parts.yaml (areas) and app.json (timezone).

import yaml from "js-yaml";
import type { RuntimeConfig } from "../types";

const WEBAPP_BASE = (() => {
  // CloudFront serves both the webapp and /config/* from the same origin.
  if (typeof window !== "undefined") {
    return `${window.location.origin}`;
  }
  return __WORKQ_WEBAPP_URL__;
})();

interface PromptPartsYaml {
  areas?: Record<string, unknown>;
}

interface AppJson {
  display_timezone?: string;
}

async function fetchPromptAreas(): Promise<string[]> {
  try {
    const resp = await fetch(`${WEBAPP_BASE}/config/prompt_parts.yaml`, { cache: "no-cache" });
    if (!resp.ok) return ["General"];
    const text = await resp.text();
    const parsed = yaml.load(text) as PromptPartsYaml | null;
    const areas = parsed?.areas ? Object.keys(parsed.areas) : [];
    if (!areas.includes("General")) areas.unshift("General");
    return areas;
  } catch {
    return ["General"];
  }
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
  const [areas, app] = await Promise.all([fetchPromptAreas(), fetchAppJson()]);
  cached = {
    api_url: __WORKQ_API_URL__,
    cognito_user_pool_id: __WORKQ_COGNITO_USER_POOL_ID__,
    cognito_client_id: __WORKQ_COGNITO_CLIENT_ID__,
    cognito_region: __WORKQ_COGNITO_REGION__,
    webapp_url: __WORKQ_WEBAPP_URL__,
    display_timezone: app.display_timezone || "UTC",
    prompt_areas: areas,
  };
  return cached;
}
