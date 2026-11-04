export interface CategoryAnalytics {
  category: string;
  count: number;
  bytes: number | string | null;
  known_sizes: number;
}

export const categoryPalette = [
  { category: "series", label: "Сериали", color: "#6de1bc" },
  { category: "movies", label: "Филми", color: "#42bfb0" },
  { category: "animations", label: "Анимации", color: "#299e9c" },
  { category: "documentaries", label: "Документални", color: "#327e8c" },
  { category: "concerts", label: "Концерти", color: "#629aa8" },
] as const;

export function formatLibraryBytes(value: number | null): string {
  if (value === null) return "Неизвестен";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toLocaleString("bg-BG", { maximumFractionDigits: 2 })} ${units[unit]}`;
}

export function libraryAnalytics(input: CategoryAnalytics[]) {
  const seen = new Set<string>();
  for (const row of input) {
    if (
      !categoryPalette.some((c) => c.category === row.category) ||
      seen.has(row.category) ||
      !Number.isSafeInteger(row.count) ||
      row.count < 0 ||
      !Number.isSafeInteger(row.known_sizes) ||
      row.known_sizes < 0 ||
      row.known_sizes > row.count
    )
      throw new Error("INVALID_ANALYTICS");
    seen.add(row.category);
  }
  const rows = categoryPalette.map((category) => {
    const raw = input.find((r) => r.category === category.category);
    if (typeof raw?.bytes === "string" && !/^\d+$/.test(raw.bytes))
      throw new Error("INVALID_ANALYTICS");
    const count = raw?.count ?? 0;
    const size = raw?.bytes == null ? null : Number(raw.bytes);
    if (size !== null && (!Number.isSafeInteger(size) || size < 0))
      throw new Error("INVALID_ANALYTICS");
    const known = size === null ? 0 : (raw?.known_sizes ?? 0);
    return {
      ...category,
      count,
      bytes: size ?? 0,
      unknown: count - known,
      sizeLabel:
        count > 0 && known === 0 ? "Неизвестен" : formatLibraryBytes(size ?? 0),
    };
  });
  const count = rows.reduce((sum, row) => sum + row.count, 0);
  const bytes = rows.reduce((sum, row) => sum + row.bytes, 0);
  const unknown = rows.reduce((sum, row) => sum + row.unknown, 0);
  const hasKnownSize = rows.some((row) => row.count > row.unknown);
  const sizeLabel =
    count > 0 && !hasKnownSize ? "Неизвестен" : formatLibraryBytes(bytes);
  const ordered = [...rows].sort((a, b) => b.bytes - a.bytes);
  const maximum = Math.max(...rows.map((row) => row.bytes), 0);
  const unit =
    maximum >= 1024 ** 4
      ? 1024 ** 4
      : maximum >= 1024 ** 3
        ? 1024 ** 3
        : maximum >= 1024 ** 2
          ? 1024 ** 2
          : maximum >= 1024
            ? 1024
            : 1;
  const unitLabel =
    unit === 1024 ** 4
      ? "TiB"
      : unit === 1024 ** 3
        ? "GiB"
        : unit === 1024 ** 2
          ? "MiB"
          : unit === 1024
            ? "KiB"
            : "B";
  const rawStep = maximum / unit / 4;
  const power = rawStep > 0 ? 10 ** Math.floor(Math.log10(rawStep)) : 1;
  const step = Math.ceil(rawStep / power) * power || 1;
  const axisMax = step * 4 * unit;
  const ticks = Array.from({ length: 5 }, (_, i) => ({
    position: i * 25,
    label: (i * step).toLocaleString("bg-BG", { maximumFractionDigits: 2 }),
  }));

  let offset = 0;
  const slices = rows
    .filter((row) => row.count > 0)
    .map((row) => {
      const share = row.count / count;
      const angle = (offset + share / 2) * Math.PI * 2 - Math.PI / 2;
      const right = Math.cos(angle) >= 0;
      const slice = {
        ...row,
        share,
        offset,
        right,
        y: 120 + Math.sin(angle) * 104,
        x: 120 + Math.cos(angle) * 84,
        arcY: 120 + Math.sin(angle) * 84,
        percentage:
          share * 100 < 0.1
            ? "<0,1%"
            : `${(share * 100).toLocaleString("bg-BG", { maximumFractionDigits: 1 })}%`,
      };
      offset += share;
      return slice;
    });
  for (const right of [false, true]) {
    const labels = slices
      .filter((slice) => slice.right === right)
      .sort((a, b) => a.y - b.y);
    let y = 18;
    for (const label of labels) {
      label.y = Math.max(y, label.y);
      y = label.y + 20;
    }
    y = 222;
    for (const label of [...labels].reverse()) {
      label.y = Math.min(y, label.y);
      y = label.y - 20;
    }
  }
  return {
    rows,
    count,
    bytes,
    unknown,
    sizeLabel,
    ordered,
    axisMax,
    unitLabel,
    ticks,
    slices,
  };
}
