import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { config } from "@vue/test-utils";
import LibraryOperations from "../src/LibraryOperations.vue";
import LibraryOrganization from "../src/LibraryOrganization.vue";

function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
}
const media = {
  id: "asset-one",
  title: "Synthetic title",
  relative_path: "Movies/Synthetic.mkv",
  fingerprint: "a".repeat(64),
  category: "movies",
  availability: "AVAILABLE",
  revision: 1,
  data: {
    identity: {
      title: "Synthetic title",
      year: 2026,
      media_type: "movie",
      edition: "Theatrical",
    },
  },
  streams: [],
  file_size_bytes: 1234,
};
beforeEach(() => {
  config.global.stubs = { teleport: true };
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    top: 100,
    bottom: 130,
    left: 200,
    right: 230,
    width: 30,
    height: 30,
    x: 200,
    y: 100,
    toJSON: () => ({}),
  });
});
afterEach(() => {
  vi.restoreAllMocks();
});
describe("v1.1 Library", () => {
  it("uses the shortened toolbar labels without changing analysis or scan requests", async () => {
    const writes: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit) => {
        if (options.method === "POST") {
          writes.push(url);
          return response({ id: "scan-one" });
        }
        if (url.includes("/scans/"))
          return response({ id: "scan-one", state: "QUEUED", data: {} });
        return response(
          url.includes("analytics")
            ? { categories: [] }
            : { items: [media], total: 1 },
        );
      }),
    );
    const wrapper = mount(LibraryOperations);
    await flushPromises();
    expect(wrapper.find('.toolbar [aria-label="Нормализация"]').text()).toBe(
      "⚙ Нормализация",
    );
    expect(wrapper.find('.toolbar [aria-label="Обследване"]').text()).toBe(
      "⟳ Обследване",
    );
    await wrapper.find('.toolbar [aria-label="Нормализация"]').trigger("click");
    expect(writes).toHaveLength(0);
    expect(wrapper.find('[role="dialog"]').attributes("aria-label")).toBe(
      "Нормализация",
    );
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await flushPromises();
    await wrapper.find('.toolbar [aria-label="Обследване"]').trigger("click");
    await flushPromises();
    expect(writes).toEqual(["/api/v1/library/scans"]);
    wrapper.unmount();
  });
  it("keeps server page and selection across row menus and view changes", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push(url);
        if (url.includes("analytics"))
          return response({
            categories: [
              {
                category: "movies",
                count: 4119,
                bytes: 1234,
                known_sizes: 4119,
              },
            ],
          });
        return response({ items: [media], total: 4119 });
      }),
    );
    const wrapper = mount(LibraryOperations);
    await flushPromises();
    await wrapper
      .find('input[aria-label="Избери Synthetic title"]')
      .setValue(true);
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Следваща")!
      .trigger("click");
    await flushPromises();
    expect(calls.some((url) => url.includes("offset=25"))).toBe(true);
    await wrapper
      .find('button[aria-label="Действия за Synthetic title"]')
      .trigger("click");
    expect(wrapper.find(".action-pop").exists()).toBe(true);
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("Карти"))!
      .trigger("click");
    expect(
      wrapper.find('input[aria-label="Избери Synthetic title"]').element,
    ).toHaveProperty("checked", true);
    expect(wrapper.find(".pager").text()).toContain("26–50 от 4119");
    expect(wrapper.text()).not.toContain("Потвърди BG");
    wrapper.unmount();
  });
  it("sends title and stream filters to server and resets offset", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push(url);
        return response(
          url.includes("analytics")
            ? { categories: [] }
            : { items: [media], total: 4119 },
        );
      }),
    );
    const wrapper = mount(LibraryOperations);
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Следваща")!
      .trigger("click");
    await flushPromises();
    await wrapper
      .find('input[aria-label="Търси в библиотеката"]')
      .setValue("Beyond current page");
    await new Promise((resolve) => setTimeout(resolve, 250));
    await flushPromises();
    expect(calls.at(-1)).toContain("offset=0");
    expect(calls.at(-1)).toContain("search=Beyond+current+page");
    wrapper.unmount();
  });
  it("requires explicit physical delete confirmation and a ready exact plan", async () => {
    const mutations: { url: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit) => {
        if (options.method === "POST") {
          mutations.push({ url, body: JSON.parse(String(options.body)) });
          return response({ job_id: "job-one" });
        }
        if (url.includes("deletions/job-one"))
          return response({
            id: "job-one",
            state: "AwaitingApproval",
            data: { policy_revision: 0 },
            counts: { Planned: 1 },
            files: [
              {
                id: "f",
                state: "Planned",
                phase: 0,
                data: {
                  title: "Synthetic",
                  source: "Library/Synthetic.mkv",
                  files: [],
                },
              },
            ],
            plan: { revision: 1, sha256: "b".repeat(64) },
            history: [],
          });
        return response(
          url.includes("analytics")
            ? { categories: [] }
            : { items: [media], total: 1 },
        );
      }),
    );
    const wrapper = mount(LibraryOperations);
    await flushPromises();
    await wrapper
      .find('button[aria-label="Действия за Synthetic title"]')
      .trigger("click");
    await wrapper
      .find(".action-pop")
      .findAll("button")
      .find((b) => b.text() === "Изтриване")!
      .trigger("click");
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Анализирай")!
      .trigger("click");
    await flushPromises();
    const execute = wrapper
      .findAll("button")
      .find((b) => b.text() === "Потвърди изтриването")!;
    expect(execute.attributes("disabled")).toBeDefined();
    expect(mutations).toHaveLength(1);
    expect(mutations[0].body).toEqual({ asset_ids: ["asset-one"] });
    wrapper.unmount();
  });
});
describe("shared Library actions and delete safety", () => {
  function fixture(
    approve?: (url: string, options: RequestInit) => Promise<Response>,
    protectedAsset = false,
  ) {
    const mutations: { url: string; options: RequestInit }[] = [];
    const plan = {
      id: "delete-job",
      state: "AwaitingApproval",
      data: { policy_revision: 1 },
      counts: { Planned: 1 },
      files: [
        {
          id: "file",
          state: "Planned",
          phase: 0,
          data: { title: media.title, source: media.relative_path, files: [] },
        },
      ],
      plan: { revision: 7, sha256: "b".repeat(64) },
      history: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit) => {
        if (options.method === "POST") {
          mutations.push({ url, options });
          if (url.endsWith("/approve"))
            return approve
              ? approve(url, options)
              : response({ accepted: true });
          return response({ job_id: plan.id });
        }
        if (url.includes("/deletions/")) return response(plan);
        return response(
          url.includes("analytics")
            ? { categories: [] }
            : {
                items: [
                  {
                    ...media,
                    data: {
                      ...media.data,
                      ...(protectedAsset
                        ? { dependencies: ["protected-torrent"] }
                        : {}),
                    },
                  },
                ],
                total: 1,
              },
        );
      }),
    );
    return mutations;
  }
  async function openDelete(wrapper: ReturnType<typeof mount>) {
    await wrapper.find('button[aria-haspopup="menu"]').trigger("click");
    await flushPromises();
    await wrapper
      .findAll('[role="menuitem"]')
      .find((b) => b.text() === "Изтриване")!
      .trigger("click");
    await flushPromises();
  }
  it.each(["table", "cards"])(
    "exposes the same actions and dependency explanations in %s",
    async (view) => {
      const mutations = fixture(undefined, true);
      const wrapper = mount(LibraryOperations);
      await flushPromises();
      if (view === "cards")
        await wrapper
          .findAll("button")
          .find((b) => b.text().includes("Карти"))!
          .trigger("click");
      if (view === "table")
        expect(wrapper.findAll("th").at(-1)!.text()).toBe("Действия");
      await wrapper.find('button[aria-haspopup="menu"]').trigger("click");
      await flushPromises();
      const actions = wrapper.findAll('[role="menuitem"]');
      expect(actions).toHaveLength(5);
      expect(
        actions.map((b) => b.element.childNodes[0].textContent?.trim()),
      ).toEqual([
        "Нормализация",
        "Карантина",
        "Изтриване",
        "Субтитри / версии",
        "Идентификация / колекция",
      ]);
      for (const item of actions.slice(0, 3)) {
        expect(item.attributes("aria-disabled")).toBe("true");
        expect(item.attributes("title")).toContain("Torrent");
        await item.trigger("click");
      }
      expect(actions[3].attributes("aria-disabled")).toBe("false");
      expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
      expect(mutations).toHaveLength(0);
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      await flushPromises();
      expect(wrapper.find('[role="menu"]').exists()).toBe(false);
      await wrapper.find('button[aria-haspopup="menu"]').trigger("click");
      await flushPromises();
      document.dispatchEvent(new Event("pointerdown", { bubbles: true }));
      await flushPromises();
      expect(wrapper.find('[role="menu"]').exists()).toBe(false);
      wrapper.unmount();
    },
  );
  it.each(["Escape", "Cancel", "dismiss", "close"])(
    "never submits deletion on %s",
    async (dismiss) => {
      const mutations = fixture();
      const wrapper = mount(LibraryOperations);
      await flushPromises();
      await openDelete(wrapper);
      const dialog = wrapper.find('[role="dialog"]');
      expect(dialog.attributes("aria-label")).toBe("Потвърждение за изтриване");
      expect(dialog.text()).toContain(media.title);
      expect(dialog.text()).toContain(media.relative_path);
      const confirm = dialog
        .findAll("button")
        .find((b) => b.text() === "Потвърди изтриването")!;
      expect(confirm.attributes("disabled")).toBeDefined();
      expect(dialog.find('input[type="checkbox"]').exists()).toBe(true);
      if (dismiss === "Escape")
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      else if (dismiss === "Cancel")
        await dialog
          .findAll("button")
          .find((b) => b.text() === "Отказ")!
          .trigger("click");
      else if (dismiss === "dismiss")
        await wrapper.find(".compact-overlay").trigger("click");
      else await dialog.find('[aria-label="Затвори"]').trigger("click");
      await flushPromises();
      expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
      expect(mutations).toHaveLength(0);
      wrapper.unmount();
    },
  );
  it("cancels an acknowledged plan without requesting approval", async () => {
    const mutations = fixture();
    const wrapper = mount(LibraryOperations);
    await flushPromises();
    await openDelete(wrapper);
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Анализирай")!
      .trigger("click");
    await flushPromises();
    await wrapper.find('.compact-dialog input[type="checkbox"]').setValue(true);
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Отказ")!
      .trigger("click");
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(mutations.map((m) => m.url)).toEqual([
      "/api/v1/library/deletions/plans",
    ]);
    wrapper.unmount();
  });
  it.each(["success", "failure"])(
    "guards the exact plan and duplicate approval while showing server %s",
    async (outcome) => {
      let finish!: (value: Response) => void;
      const mutations = fixture(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      );
      const wrapper = mount(LibraryOperations);
      await flushPromises();
      await openDelete(wrapper);
      expect(mutations).toHaveLength(0);
      await wrapper
        .findAll("button")
        .find((b) => b.text() === "Анализирай")!
        .trigger("click");
      await flushPromises();
      const dialog = wrapper.find('[role="dialog"]');
      const confirm = dialog
        .findAll("button")
        .find((b) => b.text() === "Потвърди изтриването")!;
      expect(confirm.attributes("disabled")).toBeDefined();
      expect(mutations.map((m) => m.url)).toEqual([
        "/api/v1/library/deletions/plans",
      ]);
      await dialog.find('input[type="checkbox"]').setValue(true);
      expect(confirm.attributes("disabled")).toBeUndefined();
      confirm.element.dispatchEvent(new MouseEvent("click"));
      confirm.element.dispatchEvent(new MouseEvent("click"));
      await flushPromises();
      expect(mutations).toHaveLength(2);
      expect(JSON.parse(String(mutations[1].options.body))).toEqual({
        plan_revision: 7,
        plan_sha256: "b".repeat(64),
        confirmed: true,
      });
      expect(mutations[1].options.headers).toHaveProperty("Idempotency-Key");
      expect(confirm.attributes("disabled")).toBeDefined();
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      await flushPromises();
      expect(wrapper.find('[role="dialog"]').exists()).toBe(true);
      finish(
        outcome === "success"
          ? response({ accepted: true })
          : new Response(JSON.stringify({ code: "TORRENT_DEPENDENCY" }), {
              status: 409,
            }),
      );
      await flushPromises();
      if (outcome === "success") {
        expect(dialog.find('[role="status"]').text()).toContain(
          "Сървърът прие одобрението",
        );
        expect(confirm.attributes("disabled")).toBeDefined();
      } else
        expect(dialog.find('[role="alert"]').text()).toBe("TORRENT_DEPENDENCY");
      expect(mutations).toHaveLength(2);
      wrapper.unmount();
    },
  );
});
describe("v1.1 Organisation", () => {
  it("persists folder/token reorder as a revision and previews through API", async () => {
    const policy = {
      schema: 1,
      collections: true,
      categories: {
        movies: {
          root: "Movies",
          routes: {
            movie: {
              folders: ["{CollectionName}", "{Title} ({Year})"],
              filename: ["{Title}", " ({Year})"],
              subtitle: ["{VideoBase}", ".", "{SubtitleLang}"],
            },
          },
        },
      },
    };
    const writes: { url: string; body: Record<string, unknown> }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit) => {
        if (options.method === "POST") {
          const body = JSON.parse(String(options.body));
          writes.push({ url, body });
          return response(
            url.endsWith("preview")
              ? { path: "Movies/Title/Title.mkv", subtitle: "Title.bg.srt" }
              : { revision: 2 },
          );
        }
        return response({
          active: { revision: 1, data: structuredClone(policy) },
        });
      }),
    );
    const wrapper = mount(LibraryOrganization);
    await flushPromises();
    const folder = wrapper.findAll(".tree-node");
    await folder[1].trigger("dragstart");
    await folder[0].trigger("drop");
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Запази нова версия")!
      .trigger("click");
    await flushPromises();
    const save = writes.find((w) => w.url.endsWith("/policies"))!;
    expect(save.body.expected_revision).toBe(1);
    expect(
      (save.body.policy as typeof policy).categories.movies.routes.movie
        .folders[0],
    ).toBe("{Title} ({Year})");
    expect(writes.every((w) => w.url.includes("/library/policies"))).toBe(true);
    expect(wrapper.text()).toContain("Файлови операции: 0");
    wrapper.unmount();
  });
});
