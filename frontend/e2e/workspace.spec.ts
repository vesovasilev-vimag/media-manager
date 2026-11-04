import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";

test("enrollment, protected navigation and seven real screens at desktop/mobile", async ({
  page,
  request,
}) => {
  const privateFile = resolve("../.tools/e2e-auth.json");
  let credentials: { username: string; password: string };
  if (existsSync(privateFile))
    credentials = JSON.parse(readFileSync(privateFile, "utf8"));
  else {
    credentials = {
      username: "synthetic-ui-admin",
      password: randomBytes(32).toString("base64url"),
    };
    const setup = await request.post("/api/v1/auth/setup", {
      headers: { Origin: "http://localhost:8088" },
      data: {
        ...credentials,
        setup_token: readFileSync(
          "../deploy/secrets/setup_token",
          "utf8",
        ).trim(),
      },
    });
    expect(setup.status()).toBe(201);
    mkdirSync(resolve("../.tools"), { recursive: true });
    writeFileSync(privateFile, JSON.stringify(credentials), { mode: 0o600 });
  }
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Вход в работното пространство" }),
  ).toBeVisible();
  await page
    .getByLabel("Потребител", { exact: true })
    .fill(credentials.username);
  await page.getByLabel("Парола", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Вход", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Табло", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../.test-artifacts/dashboard-desktop.png",
    fullPage: true,
  });
  for (const name of [
    "Задачи за импорт",
    "Библиотека",
    "Сравнение на версии",
    "Опашка за преместване",
    "Български субтитри",
    "Настройки",
    "Табло",
  ]) {
    await page
      .getByRole("navigation", { name: "Основна навигация" })
      .getByRole("button", { name, exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name, exact: true, level: 1 }),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".sidebar")).toHaveCSS(
    "transform",
    "matrix(1, 0, 0, 1, -242, 0)",
  );
  await page.screenshot({
    path: "../.test-artifacts/dashboard-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", {
      name: "Прибери или разгъни навигацията",
      exact: true,
    })
    .click();
  await page
    .getByRole("navigation", { name: "Основна навигация" })
    .getByRole("button", { name: "Библиотека", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Библиотека", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
  await page.getByRole("button", { name: "Изход", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Вход в работното пространство" }),
  ).toBeVisible();
});

test("v1.1 server pagination, compact plans, policy revisions and persistent collapse", async ({
  page,
}) => {
  const credentials = JSON.parse(
    readFileSync(resolve("../.tools/e2e-auth.json"), "utf8"),
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByLabel("Потребител", { exact: true })
    .fill(credentials.username);
  await page.getByLabel("Парола", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Вход", exact: true }).click();
  await page
    .getByRole("navigation", { name: "Основна навигация" })
    .getByRole("button", { name: "Библиотека", exact: true })
    .click();
  await page.getByRole("button", { name: "Обследване", exact: true }).click();
  await expect(
    page.locator(".library-operations .notice").first(),
  ).toContainText("COMPLETED", { timeout: 60000 });
  await expect(page.locator(".results tbody tr")).toHaveCount(25);
  await page.getByLabel("На страница").selectOption("12");
  await expect(page.locator(".results tbody tr")).toHaveCount(12);
  await page.getByRole("button", { name: "Следваща", exact: true }).click();
  await expect(page.locator(".pager")).toContainText("13–24");
  const checkbox = page.locator("tbody input[type=checkbox]").first();
  await checkbox.check();
  await page
    .getByRole("button", { name: /Действия за/ })
    .first()
    .click();
  await expect(page.locator(".action-pop")).toBeVisible();
  await page.getByRole("button", { name: "Карти", exact: false }).click();
  await expect(page.locator(".pager")).toContainText("13–24");
  await expect(
    page.locator(".compact-card input[type=checkbox]").first(),
  ).toBeChecked();
  await page.getByLabel("Търси в библиотеката").fill("BrowserFixture 29");
  await expect(page.locator(".compact-card")).toHaveCount(1);
  await expect(page.locator(".pager")).toContainText("1–1 от 1");
  await page
    .getByRole("button", { name: /Действия за/ })
    .first()
    .click();
  await page
    .locator(".action-pop")
    .getByRole("menuitem", { name: "Изтриване", exact: true })
    .click();
  await page.getByRole("button", { name: "Анализирай", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "Потвърждение за изтриване",
  });
  await expect(dialog).toContainText("AwaitingApproval", { timeout: 30000 });
  await expect(
    dialog.getByRole("button", { name: "Потвърди изтриването" }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../.test-artifacts/library-v11-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  const before = (
    await (await page.request.get("/api/v1/library/assets?limit=200")).json()
  ).items.map((a: { id: string; relative_path: string }) => [
    a.id,
    a.relative_path,
  ]);
  await page
    .getByRole("navigation", { name: "Основна навигация" })
    .getByRole("button", { name: "Настройки", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Имена и категории", exact: true })
    .click();
  const categoryRoot = page.getByLabel("Корен на категорията");
  await categoryRoot.fill(
    (await categoryRoot.inputValue()) === "Browser Movies"
      ? "Browser Movies Repeat"
      : "Browser Movies",
  );
  await page
    .getByRole("button", { name: "Запази нова версия", exact: true })
    .click();
  await expect(page.locator(".organization")).toContainText(
    "Файлови операции: 0",
  );
  const after = (
    await (await page.request.get("/api/v1/library/assets?limit=200")).json()
  ).items.map((a: { id: string; relative_path: string }) => [
    a.id,
    a.relative_path,
  ]);
  expect(after).toEqual(before);
  await page
    .getByRole("button", { name: "Naming Convention", exact: true })
    .click();
  const tokens = page.locator(".token-zone > .token");
  await tokens.nth(6).dragTo(tokens.nth(7));
  await page
    .getByRole("button", { name: "Запази нова версия", exact: true })
    .click();
  await expect(page.locator(".organization")).toContainText(
    "Файлови операции: 0",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../.test-artifacts/settings-v11-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("button", {
      name: "Прибери или разгъни навигацията",
      exact: true,
    })
    .click();
  await expect(page.locator(".app-shell")).toHaveClass(/collapsed/);
  await page.reload();
  await expect(page.locator(".app-shell")).toHaveClass(/collapsed/);
  await expect(
    page
      .getByRole("navigation", { name: "Основна навигация" })
      .getByRole("button", { name: "Библиотека", exact: true }),
  ).toHaveAttribute("title", "Библиотека");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#library");
  await expect(page.locator(".sidebar")).toHaveCSS(
    "transform",
    "matrix(1, 0, 0, 1, -242, 0)",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../.test-artifacts/library-v11-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
