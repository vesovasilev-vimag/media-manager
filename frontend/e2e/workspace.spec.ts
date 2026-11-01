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
  await expect(page.locator('.sidebar')).toHaveCSS('transform','matrix(1, 0, 0, 1, -242, 0)');
  await page.screenshot({
    path: "../.test-artifacts/dashboard-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Навигация", exact: true }).click();
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
