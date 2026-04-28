import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { RuntimeConfig } from "../types";
import { loadRuntimeConfig } from "./runtime";

const Ctx = createContext<RuntimeConfig | null>(null);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  useEffect(() => {
    loadRuntimeConfig().then(setConfig).catch(() => {
      // Fail-open: render with sensible defaults.
      setConfig({
        api_url: __WORKQ_API_URL__,
        cognito_user_pool_id: __WORKQ_COGNITO_USER_POOL_ID__,
        cognito_client_id: __WORKQ_COGNITO_CLIENT_ID__,
        cognito_region: __WORKQ_COGNITO_REGION__,
        webapp_url: __WORKQ_WEBAPP_URL__,
        display_timezone: "UTC",
        prompt_areas: ["General"],
      });
    });
  }, []);
  if (!config) {
    return <div className="flex h-screen items-center justify-center text-muted-foreground">Loading…</div>;
  }
  return <Ctx.Provider value={config}>{children}</Ctx.Provider>;
}

export function useConfig(): RuntimeConfig {
  const v = useContext(Ctx);
  if (!v) throw new Error("useConfig must be inside <ConfigProvider>");
  return v;
}
