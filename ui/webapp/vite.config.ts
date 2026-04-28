import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";

// Bake deploy outputs into the bundle at build time. See README + spec.
function loadDeployOutputs(): Record<string, string> {
  const candidates = [
    path.resolve(__dirname, "../../.workq.outputs.json"),
    path.resolve(__dirname, "../../infra/.workq.outputs.json"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      try {
        const raw = JSON.parse(fs.readFileSync(p, "utf8")) as Record<string, string>;
        // Accept both snake_case (preferred, written by publish.sh) and the
        // raw CFN PascalCase keys.
        const normalized: Record<string, string> = { ...raw };
        const aliases: Record<string, string> = {
          WebappUrl: "webapp_url",
          ApiUrl: "api_url",
          CognitoUserPoolId: "cognito_user_pool_id",
          CognitoClientId: "cognito_client_id",
          CognitoDomain: "cognito_domain",
          CognitoRegion: "cognito_region",
          S3WebappBucket: "s3_webapp_bucket",
          CloudfrontDistributionId: "cloudfront_distribution_id",
        };
        for (const [pascal, snake] of Object.entries(aliases)) {
          if (raw[pascal] !== undefined && normalized[snake] === undefined) {
            normalized[snake] = raw[pascal];
          }
        }
        return normalized;
      } catch (e) {
        console.warn(`vite: failed to parse ${p}:`, e);
      }
    }
  }
  console.warn("vite: .workq.outputs.json not found — using empty defaults (dev only).");
  return {};
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, "../.."), "WORKQ_");
  const outputs = loadDeployOutputs();

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: { port: 5173, host: true },
    define: {
      __WORKQ_API_URL__: JSON.stringify(outputs.api_url ?? env.WORKQ_API_URL ?? ""),
      __WORKQ_COGNITO_USER_POOL_ID__: JSON.stringify(outputs.cognito_user_pool_id ?? ""),
      __WORKQ_COGNITO_CLIENT_ID__: JSON.stringify(outputs.cognito_client_id ?? ""),
      __WORKQ_COGNITO_REGION__: JSON.stringify(env.WORKQ_AWS_REGION ?? "us-east-1"),
      __WORKQ_WEBAPP_URL__: JSON.stringify(outputs.webapp_url ?? ""),
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
      sourcemap: true,
    },
  };
});
