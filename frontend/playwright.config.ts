import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    baseURL: "http://localhost:8088",
    viewport: { width: 1440, height: 1000 },
  },
  reporter: [
    ["list"],
    ["junit", { outputFile: "../.test-artifacts/browser.xml" }],
  ],
  outputDir: "../.test-artifacts/browser",
});
