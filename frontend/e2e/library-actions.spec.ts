import { test, expect, type Page } from "@playwright/test";

const media = Array.from({ length: 30 }, (_, i) => ({
  id: `action-fixture-${i}`,
  title: `Action fixture ${i}`,
  relative_path: `Movies/Action fixture ${i}.mkv`,
  category: "movies",
  availability: "AVAILABLE",
  fingerprint: "a".repeat(64),
  revision: 1,
  file_size_bytes: 1234,
  streams: [],
  data: {},
}));
const labels = [
  "Нормализация",
  "Карантина",
  "Изтриване",
  "Субтитри / версии",
  "Идентификация / колекция",
];

async function library(page: Page) {
  // Browser-only fixtures; no destructive request reaches even the synthetic Worker.
  const mutations: { path: string; body: unknown }[] = [];
  let approved = false;
  let releaseApproval: (() => void) | undefined;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    let data: unknown = {};
    if (request.method() === "POST") {
      mutations.push({ path: url.pathname, body: request.postDataJSON() });
      if (url.pathname.endsWith("/approve")) {
        await new Promise<void>((resolve) => {
          releaseApproval = resolve;
        });
        approved = true;
        data = { accepted: true };
      } else data = { job_id: "delete-fixture" };
    } else if (url.pathname.includes("/deletions/delete-fixture"))
      data = {
        id: "delete-fixture",
        state: approved ? "Completed" : "AwaitingApproval",
        data: { policy_revision: 1 },
        counts: approved ? { Completed: 1 } : { Planned: 1 },
        files: [
          {
            id: "file",
            state: approved ? "Completed" : "Planned",
            phase: 0,
            data: {
              title: media[0].title,
              source: media[0].relative_path,
              files: [],
            },
          },
        ],
        plan: { revision: 7, sha256: "b".repeat(64) },
        history: [],
      };
    else if (url.pathname.endsWith("/assets")) {
      const filtered = media.filter((m) =>
        m.title.includes(url.searchParams.get("search") ?? ""),
      );
      const offset = Number(url.searchParams.get("offset") ?? 0);
      data = {
        items: filtered.slice(
          offset,
          offset + Number(url.searchParams.get("limit") ?? 25),
        ),
        total: filtered.length,
      };
    } else if (url.pathname.endsWith("/analytics")) data = { categories: [] };
    else if (url.pathname.endsWith("/health/ready"))
      data = { database: true, write_enabled: false, worker: {} };
    await route.fulfill({ json: data });
  });
  await page.goto("/#library");
  await expect(page.locator("tbody tr")).toHaveCount(25);
  return { mutations, release: () => releaseApproval?.() };
}

async function anchored(page: Page, top: boolean) {
  const trigger = page.getByRole("button", {
    name: "Действия за Action fixture 0",
    exact: true,
  });
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(menu).toHaveAttribute(
    "data-placement",
    top ? "top-end" : "bottom-end",
  );
  await expect
    .poll(async () => {
      const a = (await trigger.boundingBox())!,
        b = (await menu.boundingBox())!;
      return Math.abs((top ? a.y - b.y - b.height : b.y - a.y - a.height) - 8);
    })
    .toBeLessThan(1);
  const box = (await menu.boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.x).toBeGreaterThanOrEqual(7);
  expect(box.y).toBeGreaterThanOrEqual(7);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width - 7);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height - 7);
}

for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 390, height: 844 },
]) {
  test(`Library menus anchor, flip and preserve state at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const { mutations } = await library(page);
    const trigger = page.getByRole("button", {
      name: "Действия за Action fixture 0",
      exact: true,
    });
    await page.getByLabel("Избери Action fixture 0", { exact: true }).check();
    await trigger.click();
    await expect(page.getByRole("menuitem")).toHaveText(labels);
    await page.keyboard.press("End");
    await expect(
      page.getByRole("menuitem", {
        name: "Идентификация / колекция",
        exact: true,
      }),
    ).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(
      page.getByRole("menuitem", { name: "Нормализация", exact: true }),
    ).toBeFocused();
    // Horizontal table scrolling must not clip the portalled menu.
    await expect(page.getByRole("menu")).toBeVisible();
    await anchored(page, false);
    await page.locator(".table-scroll").evaluate((el) => {
      el.style.maxHeight = "180px";
      el.scrollTop = 10;
    });
    await anchored(page, false);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu")).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await page.locator(".table-scroll").evaluate((el) => {
      el.style.maxHeight = "";
      el.scrollTop = 0;
    });
    await page.getByRole("button", { name: "Карти" }).click();
    await expect(
      page.getByLabel("Избери Action fixture 0", { exact: true }),
    ).toBeChecked();
    await trigger.scrollIntoViewIfNeeded();
    // Leave enough document space to place the same trigger near either viewport edge.
    await page.evaluate(() => {
      const spacer = document.createElement("div");
      spacer.style.height = "100vh";
      document.body.prepend(spacer.cloneNode());
      document.body.appendChild(spacer);
    });
    await trigger.evaluate((el) =>
      window.scrollBy(0, el.getBoundingClientRect().top - 180),
    );
    await trigger.click();
    await expect(page.getByRole("menuitem")).toHaveText(labels);
    await anchored(page, false);
    await page.setViewportSize({
      width: viewport.width - 40,
      height: viewport.height,
    });
    await anchored(page, false);
    await page.setViewportSize(viewport);
    await anchored(page, false);
    await page.screenshot({
      path: `../.test-artifacts/library-actions-${viewport.width}.png`,
    });
    await page.evaluate(() => window.scrollBy(0, 20));
    await anchored(page, false);
    await page.keyboard.press("Escape");
    await trigger.evaluate((el) =>
      window.scrollBy(
        0,
        el.getBoundingClientRect().bottom - (innerHeight - 20),
      ),
    );
    await trigger.click();
    await anchored(page, true);
    await page
      .getByRole("menuitem", { name: "Нормализация", exact: true })
      .click();
    await expect(page.getByRole("menu")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await trigger.click();
    await page.locator(".compact-card h2").first().click();
    await expect(page.getByRole("menu")).toHaveCount(0);
    await page.getByRole("button", { name: "Следваща", exact: true }).click();
    await expect(page.locator(".pager")).toContainText("26–30 от 30");
    await page.getByLabel("Търси в библиотеката").fill("Action fixture 29");
    await expect(page.locator(".compact-card")).toHaveCount(1);
    await expect(page.locator(".pager")).toContainText("1–1 от 1");
    expect(mutations).toHaveLength(0);
  });
}

test("delete dialog cancels safely and approves an acknowledged exact plan only once", async ({
  page,
}) => {
  const fixture = await library(page);
  const trigger = page.getByRole("button", {
    name: "Действия за Action fixture 0",
    exact: true,
  });
  const dialog = page.getByRole("dialog", {
    name: "Потвърждение за изтриване",
  });
  async function open() {
    await trigger.click();
    await page
      .getByRole("menuitem", { name: "Изтриване", exact: true })
      .click();
    await expect(dialog).toBeVisible();
  }
  for (const dismiss of ["Escape", "Отказ", "backdrop"]) {
    await open();
    await expect(dialog).toContainText(media[0].title);
    await expect(dialog).toContainText(media[0].relative_path);
    await expect(
      dialog.getByRole("button", { name: "Потвърди изтриването" }),
    ).toBeDisabled();
    if (dismiss === "Escape") await page.keyboard.press("Escape");
    else if (dismiss === "backdrop")
      await page
        .locator(".compact-overlay")
        .click({ position: { x: 2, y: 2 } });
    else
      await dialog.getByRole("button", { name: "Отказ", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(fixture.mutations).toHaveLength(0);
  }
  await open();
  await dialog.getByRole("button", { name: "Анализирай", exact: true }).click();
  await expect(dialog).toContainText("AwaitingApproval");
  const confirm = dialog.getByRole("button", { name: "Потвърди изтриването" });
  await expect(confirm).toBeDisabled();
  await dialog.getByRole("checkbox").check();
  await confirm.evaluate((el) => {
    (el as HTMLButtonElement).click();
    (el as HTMLButtonElement).click();
  });
  await expect(
    dialog.getByRole("button", { name: "Изпращане…" }),
  ).toBeDisabled();
  await expect
    .poll(
      () => fixture.mutations.filter((m) => m.path.endsWith("/approve")).length,
    )
    .toBe(1);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  fixture.release();
  await expect(dialog.getByRole("status")).toContainText(
    "Сървърът потвърди приключването",
  );
  expect(fixture.mutations.map((m) => m.path)).toEqual([
    "/api/v1/library/deletions/plans",
    "/api/v1/library/deletions/delete-fixture/approve",
  ]);
  expect(fixture.mutations[1].body).toEqual({
    plan_revision: 7,
    plan_sha256: "b".repeat(64),
    confirmed: true,
  });
});
