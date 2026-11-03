import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import App from "../src/App.vue";
import { api, ApiError } from "../src/api";

afterEach(() => {
  vi.restoreAllMocks();
  location.hash = "";
});
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
describe("session and seven real API screens", () => {
  it("requires login after an expired session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ detail: "SESSION_REQUIRED" }, 401)),
    );
    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.text()).toContain("Вход в работното пространство");
    expect(wrapper.find("nav").exists()).toBe(false);
    wrapper.unmount();
  });
  it("renders all seven screens from API state with honest empty states", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.endsWith("/me")) return response({ role: "admin" });
      if (url.includes("/dashboard"))
        return response({
          counts: {},
          health: { database: true, write_enabled: false, worker: {} },
          recent: [],
        });
      if (url.includes("/settings")) return response({ sections: [] });
      if (url.includes("/library/analytics"))
        return response({ categories: [] });
      if (url.includes("/health/ready"))
        return response({ database: true, write_enabled: false, worker: {} });
      return response({ items: [] });
    });
    vi.stubGlobal("fetch", fetcher);
    const wrapper = mount(App);
    await flushPromises();
    const nav = wrapper.find("nav");
    expect(nav.findAll("button")).toHaveLength(7);
    for (const button of nav.findAll("button")) {
      await button.trigger("click");
      await flushPromises();
      expect(wrapper.find("h1").text()).toBe(button.text());
    }
    expect(wrapper.text()).toContain("Операции неактивни");
    expect(
      fetcher.mock.calls.some(([url]) => url.includes("/library/duplicates")),
    ).toBe(true);
    expect(fetcher.mock.calls.some(([url]) => url.includes("/subtitles"))).toBe(
      true,
    );
    wrapper.unmount();
  });
  it("sends CSRF and a stable supplied idempotency key without exposing session credentials", async () => {
    document.cookie = "vimag_csrf=synthetic-csrf";
    const fetcher = vi.fn().mockResolvedValue(response({ saved: true }));
    vi.stubGlobal("fetch", fetcher);
    await api(
      "/settings/automation",
      "PUT",
      { retry_budget: 3 },
      "synthetic-idempotency",
    );
    const headers = fetcher.mock.calls[0][1].headers;
    expect(headers["X-CSRF-Token"]).toBe("synthetic-csrf");
    expect(headers["Idempotency-Key"]).toBe("synthetic-idempotency");
    expect(headers.Authorization).toBeUndefined();
  });
  it("preserves structured denial codes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ code: "DEPENDENCY_BLOCKED" }, 423)),
    );
    await expect(
      api("/library/assets/fixture/quarantine-plan", "POST"),
    ).rejects.toEqual(new ApiError(423, "DEPENDENCY_BLOCKED"));
  });
});
