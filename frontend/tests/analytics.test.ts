import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import LibraryAnalytics from "../src/LibraryAnalytics.vue";
import {
  categoryPalette,
  formatLibraryBytes,
  libraryAnalytics,
  type CategoryAnalytics,
} from "../src/libraryAnalytics";

const TiB = 1024 ** 4;
const categories: CategoryAnalytics[] = [
  { category: "movies", count: 11, bytes: 0.5 * TiB, known_sizes: 11 },
  { category: "concerts", count: 0, bytes: 0, known_sizes: 0 },
  { category: "documentaries", count: 3, bytes: 0.25 * TiB, known_sizes: 3 },
  { category: "animations", count: 5, bytes: 0.125 * TiB, known_sizes: 5 },
  { category: "series", count: 37, bytes: 1.25 * TiB, known_sizes: 37 },
];
function render(rows = categories, extra = {}) {
  return mount(LibraryAnalytics, {
    props: { categories: rows, loading: false, error: "", ...extra },
  });
}
describe("Library overview visualization", () => {
  it("uses real count/byte totals consistently across donut, table and KPI", () => {
    const wrapper = render();
    const model = libraryAnalytics(categories);
    expect(wrapper.find(".donut-total").text()).toBe("56");
    expect(wrapper.find(".total-count").text()).toBe("56");
    expect(model.bytes).toBe(2.125 * TiB);
    expect(wrapper.find(".total-size").text()).toBe(
      formatLibraryBytes(model.bytes),
    );
    expect(wrapper.find(".kpi-value").text()).toBe(
      formatLibraryBytes(model.bytes),
    );
    expect(
      wrapper
        .findAll(".category-statistics tbody tr")
        .map((row) => row.attributes("data-category")),
    ).toEqual(categoryPalette.map((c) => c.category));
    const segments = wrapper.findAll(".donut-segment");
    expect(segments).toHaveLength(4);
    expect(wrapper.findAll(".donut-label")).toHaveLength(4);
    expect(
      segments.find(
        (segment) => segment.attributes("data-category") === "concerts",
      ),
    ).toBeUndefined();
    const series = segments.find(
      (segment) => segment.attributes("data-category") === "series",
    )!;
    expect(series.attributes("data-count")).toBe("37");
    expect(series.find("title").text()).toContain("66,1%");
    expect(
      model.slices.reduce((sum, slice) => sum + slice.share, 0),
    ).toBeCloseTo(1);
  });
  it("sorts storage by bytes, shares colors, and scales the binary axis dynamically", () => {
    const model = libraryAnalytics(categories),
      wrapper = render();
    expect(
      wrapper
        .findAll(".storage-row")
        .map((row) => row.attributes("data-category")),
    ).toEqual(["series", "movies", "documentaries", "animations", "concerts"]);
    expect(model.unitLabel).toBe("TiB");
    expect(model.axisMax).toBeGreaterThanOrEqual(1.25 * TiB);
    expect(model.ticks).toHaveLength(5);
    for (const row of model.rows) {
      const bar = wrapper.find(
        `.storage-row[data-category="${row.category}"] .storage-bar`,
      );
      expect(parseFloat((bar.element as HTMLElement).style.width)).toBeCloseTo(
        (row.bytes / model.axisMax) * 100,
      );
      const segment = wrapper.find(
        `.donut-segment[data-category="${row.category}"]`,
      );
      if (row.count) expect(segment.attributes("stroke")).toBe(row.color);
      expect(
        wrapper
          .find(`.storage-row[data-category="${row.category}"]`)
          .attributes("aria-label"),
      ).toContain(row.sizeLabel);
    }
    expect(
      libraryAnalytics([
        { category: "movies", count: 1, bytes: 2 * 1024 ** 3, known_sizes: 1 },
      ]).unitLabel,
    ).toBe("GiB");
    expect(formatLibraryBytes(1024 ** 3)).toBe("1 GiB");
    expect(formatLibraryBytes(1024 ** 4)).toBe("1 TiB");
  });
  it("shows an honest empty state with zero values and no invalid arcs/bars", () => {
    const wrapper = render([]);
    expect(wrapper.find('[role="status"]').text()).toContain(
      "Няма видеофайлове",
    );
    expect(wrapper.find(".donut-total").text()).toBe("0");
    expect(wrapper.find(".kpi-value").text()).toBe("0 B");
    expect(wrapper.findAll(".donut-segment")).toHaveLength(0);
    expect(
      wrapper
        .findAll(".storage-bar")
        .every((bar) => (bar.element as HTMLElement).style.width === "0%"),
    ).toBe(true);
    expect(wrapper.html()).not.toMatch(/NaN|Infinity/);
  });
  it("distinguishes partial and unknown sizes from proven zero storage", () => {
    const partial = render([
      { category: "movies", count: 10, bytes: 1024 ** 3, known_sizes: 6 },
    ]);
    expect(partial.find('[role="note"]').text()).toContain(
      "4 файла с неизвестен размер",
    );
    expect(partial.find(".total-size").text()).toBe("1 GiB");
    expect(partial.find(".kpi-caption").text()).toBe("Известен обем");
    const unknown = render([
      { category: "movies", count: 10, bytes: null, known_sizes: 0 },
    ]);
    expect(unknown.find(".total-size").text()).toBe("Неизвестен");
    expect(unknown.find(".kpi-value").text()).toBe("Неизвестен");
    expect(
      unknown
        .find('.category-statistics [data-category="movies"] .category-size')
        .text(),
    ).toBe("Неизвестен");
  });
  it("separates loading, failed requests and stale-but-known data", () => {
    const pending = render([], { loading: true });
    expect(pending.find('[role="status"]').text()).toContain("Зареждане");
    expect(pending.find(".kpi-value").exists()).toBe(false);
    const failed = render([], { error: "Връзката е прекъсната" });
    expect(failed.find('[role="alert"]').text()).toContain(
      "Връзката е прекъсната",
    );
    expect(failed.find(".donut-total").exists()).toBe(false);
    const stale = render(categories, { error: "Неуспешно обновяване" });
    expect(stale.find('[role="alert"]').text()).toContain(
      "последните успешно заредени данни",
    );
    expect(stale.find(".total-count").text()).toBe("56");
  });
  it("does not overlap labels for tiny adjacent categories or show zero labels", () => {
    const model = libraryAnalytics(
      categoryPalette.map((row, i) => ({
        category: row.category,
        count: i === 0 ? 10000 : 1,
        bytes: 1,
        known_sizes: 1,
      })),
    );
    for (const right of [false, true]) {
      const labels = model.slices
        .filter((s) => s.right === right)
        .sort((a, b) => a.y - b.y);
      for (let i = 1; i < labels.length; i++)
        expect(labels[i].y - labels[i - 1].y).toBeGreaterThanOrEqual(20);
    }
    expect(
      model.slices.slice(1).every((slice) => slice.percentage === "<0,1%"),
    ).toBe(true);
  });
  it("rejects malformed analytics instead of inventing a total", () => {
    const wrapper = render([
      { category: "movies", count: 1, bytes: -1, known_sizes: 1 },
    ]);
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
    expect(wrapper.find(".total-size").exists()).toBe(false);
  });
});
