import { defineConfig, devices } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// Read backend .env to get BROWSERLESS_WS_URL
let wsEndpoint: string | undefined = undefined;
try {
  const envPath = path.resolve(__dirname, "../../../backend/.env");
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, "utf-8");
    const match = envContent.match(/^BROWSERLESS_WS_URL\s*=\s*(.+)$/m);
    if (match) {
      wsEndpoint = match[1].trim().replace(/['"]/g, "");
    }
  }
} catch (e) {
  // Ignore
}

export default defineConfig({
  testDir: "./",
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:19006",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    connectOptions: wsEndpoint ? { wsEndpoint } : undefined,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: process.env.BASE_URL
    ? undefined
    : {
        command: "npm run web",
        cwd: "../../../web",
        url: "http://localhost:19006",
        reuseExistingServer: true,
        timeout: 120000,
      },
});
