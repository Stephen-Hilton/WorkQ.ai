// Shared types — must stay in sync with apis/shared/models.py.

export type Status =
  | "queued for build"
  | "queued for planning"
  | "pending review"
  | "building"
  | "planning"
  | "complete"
  | "failed";

export const ALL_STATUSES: Status[] = [
  "queued for build",
  "queued for planning",
  "pending review",
  "building",
  "planning",
  "complete",
  "failed",
];

// Statuses the user can transition TO from the UI (Save and ...).
export const USER_SAVE_ACTIONS: Status[] = [
  "queued for build",
  "queued for planning",
  "pending review",
  "complete",
];

export interface TimelogEntry {
  status: string;
  ts: string; // ISO 8601 UTC
}

export interface Record {
  reqid: string;
  reqstatus: Status | string;
  reqarea: string;
  reqcreator: string;
  reqpr: string;
  request: string;
  response: string;
  timelog: TimelogEntry[];
}

export interface RuntimeConfig {
  api_url: string;
  cognito_user_pool_id: string;
  cognito_client_id: string;
  cognito_region: string;
  webapp_url: string;
  display_timezone: string;
  prompt_areas: string[]; // resolved area names from prompt_parts.yaml
}

declare global {
  // Vite-injected build-time constants. See vite.config.ts.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const __REQUESTQUEUE_API_URL__: string;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const __REQUESTQUEUE_COGNITO_USER_POOL_ID__: string;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const __REQUESTQUEUE_COGNITO_CLIENT_ID__: string;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const __REQUESTQUEUE_COGNITO_REGION__: string;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const __REQUESTQUEUE_WEBAPP_URL__: string;
}
