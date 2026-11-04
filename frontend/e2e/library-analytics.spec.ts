import { test, expect } from "@playwright/test";

const TiB = 1024 ** 4;
const categories = [
  { category: "movies", count: 11, bytes: 0.5 * TiB, known_sizes: 11 },
  { category: "series", count: 37, bytes: 1.25 * TiB, known_sizes: 37 },
  { category: "animations", count: 5, bytes: 0.125 * TiB, known_sizes: 5 },
  { category: "documentaries", count: 3, bytes: 0.25 * TiB, known_sizes: 3 },
  { category: "concerts", count: 0, bytes: 0, known_sizes: 0 },
];
for (const width of [1600, 1024, 390, 320]) {
  test(`Library analytics values and responsive layout at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      await route.fulfill({
        json: path.endsWith("/analytics")
          ? { categories }
          : path.endsWith("/assets")
            ? { items: [], total: 0 }
            : path.endsWith("/health/ready")
              ? { database: true, worker: {}, write_enabled: false }
              : {},
      });
    });
    await page.goto("/#library");
    const overview = page.locator(".library-analytics");
    await expect(overview.locator(".donut-total")).toHaveText("56");
    await expect(overview.locator(".total-count")).toHaveText("56");
    await expect(overview.locator(".kpi-value")).toHaveText("2,13 TiB");
    await expect(overview.locator(".total-size")).toHaveText("2,13 TiB");
    await expect(overview.locator(".storage-label")).toHaveText([
      "Сериали",
      "Филми",
      "Документални",
      "Анимации",
      "Концерти",
    ]);
    await expect(overview.locator(".donut-label")).toHaveCount(4);
    const panels = overview.locator(".analytics-panel");
    const left = (await panels.nth(0).boundingBox())!,
      right = (await panels.nth(1).boundingBox())!;
    if (width >= 1600) expect(Math.abs(left.y - right.y)).toBeLessThan(1);
    else expect(right.y).toBeGreaterThanOrEqual(left.y + left.height);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    // Every value stays inside its panel; charts remain real width, not clipped.
    for (const selector of [
      ".category-statistics",
      ".storage-chart",
      ".storage-kpi",
    ]) {
      const box = (await overview.locator(selector).boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
    }
    const labels = await overview
      .locator(".donut-label text")
      .evaluateAll((nodes) =>
        nodes.map((node) => {
          const bounds = node.getBoundingClientRect();
          return {
            x: bounds.x,
            y: bounds.y,
            right: bounds.right,
            bottom: bounds.bottom,
          };
        }),
      );
    for (let i = 0; i < labels.length; i++)
      for (let j = i + 1; j < labels.length; j++) {
        const a = labels[i],
          b = labels[j];
        expect(
          a.right <= b.x ||
            b.right <= a.x ||
            a.bottom <= b.y ||
            b.bottom <= a.y,
        ).toBe(true);
      }
    await overview.screenshot({
      path: `../.test-artifacts/library-analytics-${width}.png`,
    });
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
}
