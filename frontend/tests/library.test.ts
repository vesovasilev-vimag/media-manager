import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
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
afterEach(() => {
  vi.restoreAllMocks();
});
describe("v1.1 Library", () => {
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
      .find((b) => b.text() === "Изтрий потвърдените файлове")!;
    expect(execute.attributes("disabled")).toBeDefined();
    expect(mutations).toHaveLength(1);
    expect(mutations[0].body).toEqual({ asset_ids: ["asset-one"] });
    wrapper.unmount();
  });
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
