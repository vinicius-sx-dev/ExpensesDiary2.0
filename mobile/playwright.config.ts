import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/ui",
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:8081", headless: true, launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } },
  webServer: {
    command: "python3 -m http.server 8081 --directory dist --bind 127.0.0.1",
    url: "http://127.0.0.1:8081",
    reuseExistingServer: !process.env.CI,
  },
});
