import {cloudflareTest} from "@cloudflare/vitest-plugin";
import {defineConfig} from "vitest/config";

export default defineConfig({
  plugins: [cloudflareTest({
    wrangler: {configPath: "./wrangler.jsonc"},
    miniflare: {bindings: {
      BACKEND_URL: "https://brain-test.run.app",
      GATEWAY_SHARED_SECRET: "test-secret-with-at-least-32-characters",
      ACCESS_TEAM_DOMAIN: "brain-test.cloudflareaccess.com",
      ACCESS_AUD: "brain-test-audience",
      ALLOWED_EMAILS: "member@example.com,admin@example.com",
      ADMIN_EMAILS: "admin@example.com",
    }},
  })],
  test: {include: ["tests/**/*.test.ts"]},
});
