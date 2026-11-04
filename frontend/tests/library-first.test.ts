import { mount, flushPromises, config } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import LibraryOperations from "../src/LibraryOperations.vue";

const media = {
  id: "review-asset",
  title: "Mystery",
  category: "movies",
  revision: 3,
  availability: "AVAILABLE",
  relative_path: "Movies/Mystery.mkv",
  streams: [],
  fingerprint: "a".repeat(64),
  data: {
    inspection: {
      state: "Unidentified",
      reason: "IDENTITY_UNAVAILABLE",
      parsed: { title: "Mystery", year: 2026, media_type: "movie" },
    },
  },
};
function response(data: unknown) {
  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it("shows persistent review evidence and scans the full library despite a category filter", async () => {
  config.global.stubs = { teleport: true };
  const writes: { url: string; body: unknown }[] = [];
  const reads: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit) => {
      if (options.method === "POST") {
        writes.push({ url, body: JSON.parse(String(options.body)) });
        return response({ id: "scan" });
      }
      reads.push(url);
      if (url.includes("analytics")) return response({ categories: [] });
      if (url.includes("/scans/"))
        return response({ id: "scan", state: "QUEUED", data: {} });
      return response({ items: [media], total: 1 });
    }),
  );
  const wrapper = mount(LibraryOperations);
  await flushPromises();
  await wrapper
    .findAll("button")
    .find((b) => b.text() === "За преглед")!
    .trigger("click");
  await flushPromises();
  expect(reads.some((url) => url.includes("review=true"))).toBe(true);
  expect(wrapper.find('[aria-label="Библиотека за преглед"]').text()).toContain(
    "IDENTITY_UNAVAILABLE",
  );
  await wrapper.findAll("select")[0]!.setValue("movies");
  await wrapper.find('[aria-label="Обследване"]').trigger("click");
  await flushPromises();
  expect(writes).toEqual([
    { url: "/api/v1/library/scans", body: { all: true } },
  ]);
  wrapper.unmount();
});

it("searches TMDb, saves a correction and re-analyzes only that asset", async () => {
  vi.useFakeTimers();
  config.global.stubs = { teleport: true };
  const writes: { url: string; body: Record<string, unknown> }[] = [];
  let searched = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit) => {
      if (options.method === "POST") {
        writes.push({
          url,
          body: options.body ? JSON.parse(String(options.body)) : {},
        });
        if (url.endsWith("identity-search")) searched = true;
        return response({ operation_id: "lookup", revision: 4 });
      }
      if (url.includes("analytics")) return response({ categories: [] });
      if (url.includes("/inspections/")) return response({ state: "DONE" });
      if (url.includes("identity-candidates"))
        return response({
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
        });
      return response({ items: [media], total: 1 });
    }),
  );
  const wrapper = mount(LibraryOperations);
  await flushPromises();
  await wrapper
    .findAll("button")
    .find((b) => b.text() === "За преглед")!
    .trigger("click");
  await flushPromises();
  await wrapper
    .findAll("button")
    .find((b) => b.text() === "Коригирай идентификацията")!
    .trigger("click");
  await flushPromises();
  const dialog = wrapper.find('[role="dialog"]');
  await dialog
    .findAll("button")
    .find((b) => b.text() === "Търси в TMDb")!
    .trigger("click");
  await flushPromises();
  await vi.advanceTimersByTimeAsync(4000);
  await flushPromises();
  await dialog
    .findAll("button")
    .find((b) => b.text().includes("English Film (2026)"))!
    .trigger("click");
  await dialog
    .findAll("label")
    .find((l) => l.text().startsWith("Категория"))!
    .find("select")
    .setValue("documentaries");
  await dialog
    .findAll("label")
    .find((l) => l.text() === "Отделно издание")!
    .find("input")
    .setValue(true);
  await dialog
    .findAll("button")
    .find((b) => b.text() === "Потвърди идентификацията")!
    .trigger("click");
  await flushPromises();
  const correction = writes.find((w) => w.url.endsWith("/identity"))!;
  expect(correction.body).toMatchObject({
    expected_revision: 3,
    category: "documentaries",
    identity: {
      provider_id: "42",
      title: "English Film",
      separate_edition: true,
    },
  });
  expect(writes.at(-1)?.url).toBe(
    "/api/v1/library/assets/review-asset/reanalyze",
  );
  expect(writes.some((w) => w.url.includes("/approve"))).toBe(false);
  wrapper.unmount();
});
