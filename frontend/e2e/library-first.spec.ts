import { test, expect } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`Library review and English proposal at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1100 });
    const mutations: { path: string; body: Record<string, unknown> }[] = [];
    let searched = false;
    const asset = {
      id: "review-fixture",
      title: "Mystery",
      relative_path: "Movies/Mystery.mkv",
      category: "movies",
      availability: "AVAILABLE",
      revision: 1,
      fingerprint: "a".repeat(64),
      streams: [],
      data: {
        inspection: {
          state: "Unidentified",
          reason: "IDENTITY_UNAVAILABLE",
          parsed: { title: "Mystery", year: 2026, media_type: "movie" },
        },
      },
    };
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request(),
        url = new URL(request.url());
      let data: unknown = {};
      if (request.method() === "POST") {
        mutations.push({
          path: url.pathname,
          body: request.postDataJSON() ?? {},
        });
        if (url.pathname.endsWith("identity-search")) searched = true;
        data = url.pathname.endsWith("/plans")
          ? { job_id: "preview" }
          : { operation_id: "search", revision: 2 };
      } else if (url.pathname.endsWith("/assets"))
        data = { items: [asset], total: 1 };
      else if (url.pathname.endsWith("/analytics")) data = { categories: [] };
      else if (url.pathname.includes("/inspections/")) data = { state: "DONE" };
      else if (url.pathname.endsWith("identity-candidates"))
        data = {
          items: searched
            ? [
                {
                  id: "42",
                  title: "English Film",
                  year: 2026,
                  media_type: "movie",
                },
              ]
            : [],
        };
      else if (url.pathname.includes("/normalizations/preview"))
        data = {
          id: "preview",
          state: "AwaitingApproval",
          data: { policy_revision: 0 },
          counts: { Planned: 1 },
          files: [
            {
              id: "file",
              asset_id: asset.id,
              phase: 0,
              state: "Planned",
              review_state: "Ready",
              data: {
                title: "English Film",
                source: asset.relative_path,
                target:
                  "Library/Movies/English Film (2026)/English Film (2026).mkv",
                metadata_changes: {
                  title: { current: "Mystery", proposed: "English Film" },
                },
                files: [],
              },
            },
          ],
          plan: { revision: 1, sha256: "b".repeat(64) },
          history: [],
        };
      else if (url.pathname.endsWith("/health/ready"))
        data = { database: true, write_enabled: false, worker: {} };
      await route.fulfill({ json: data });
    });
    await page.goto("/#library");
    await page
      .locator(".toolbar")
      .getByRole("button", { name: "За преглед", exact: true })
      .click();
    const queue = page.getByRole("region", { name: "Библиотека за преглед" });
    await expect(queue).toContainText("IDENTITY_UNAVAILABLE");
    await queue
      .getByRole("button", { name: "Коригирай идентификацията" })
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("TMDb търсене").fill("English Film");
    await dialog
      .getByRole("button", { name: "Търси в TMDb", exact: true })
      .click();
    await dialog
      .getByRole("button", { name: /English Film \(2026\)/ })
      .click({ timeout: 12000 });
    await dialog
      .getByRole("combobox", { name: "Категория", exact: true })
      .selectOption("documentaries");
    await dialog.getByLabel("Отделно издание", { exact: true }).check();
    await dialog
      .getByRole("button", { name: "Потвърди идентификацията", exact: true })
      .click();
    await expect(dialog).toHaveCount(0);
    expect(
      mutations.find((m) => m.path.endsWith("/identity"))?.body,
    ).toMatchObject({
      category: "documentaries",
      identity: {
        provider_id: "42",
        title: "English Film",
        separate_edition: true,
      },
    });
    expect(mutations.at(-1)?.path).toBe(
      "/api/v1/library/assets/review-fixture/reanalyze",
    );
    await queue
      .getByRole("button", { name: "Обнови предложението", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toContainText("English Film (2026)");
    await page.getByLabel("Филтър на предложенията").selectOption("Ready");
    expect(mutations.some((m) => m.path.endsWith("/approve"))).toBe(false);
    await expect(page.locator("body")).not.toContainText("DEPENDENCY_BLOCKED");
    await page.screenshot({
      path: `../.test-artifacts/library-first-${width}.png`,
      fullPage: true,
    });
  });
}
