<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { api } from "./api";
import CompactDialog from "./CompactDialog.vue";
import LibraryActionMenu from "./LibraryActionMenu.vue";
import LibraryAnalytics from "./LibraryAnalytics.vue";
import type { LibraryAction } from "./libraryActions";
import type { Asset, Plan } from "./types";

interface Track {
  index: number;
  type: string;
  codec?: string;
  profile?: string;
  language: string;
  channels?: number;
  bitrate?: number;
  width?: number;
  height?: number;
}
interface Media extends Asset {
  title: string;
  category: string;
  video_quality?: string;
  file_size_bytes?: number;
  availability: string;
  revision: number;
  streams: Track[] | null;
}
interface FileRecord {
  id: string;
  state: string;
  phase: number;
  data: {
    title: string;
    source: string;
    target?: string;
    error_code?: string;
    files?: { source: string; target?: string; size: number }[];
    warnings?: string[];
    preserved_sidecars?: string[];
    sidecar_proposals?: { target: string; kind: string }[];
  };
}
interface Maintenance {
  id: string;
  state: string;
  data: { policy_revision: number; phase?: string };
  counts: Record<string, number>;
  files: FileRecord[];
  plan?: Plan;
  history: { kind: string; created_at: string }[];
}
const categories: Record<string, string> = {
  movies: "Филми",
  series: "Сериали",
  animations: "Анимации",
  documentaries: "Документални",
  concerts: "Концерти",
};
const criteria = ref({
  search: "",
  category: "",
  video_quality: "",
  audio_codec: "",
  audio_language: "",
  subtitle_language: "",
  sort: "title",
  order: "asc",
});
const limit = ref(25),
  offset = ref(0),
  view = ref("table"),
  rows = ref<Media[]>([]),
  total = ref(0),
  loading = ref(false),
  busy = ref(false),
  error = ref("");
const selected = ref<string[]>([]),
  menu = ref<string>(),
  analytics = ref<
    { category: string; count: number; bytes: number; known_sizes: number }[]
  >([]);
const knownMedia = new Map<string, Media>();
const analyticsLoading = ref(true),
  analyticsError = ref("");
let operationGeneration = 0;
const deleteTargets = ref<
  { id: string; title: string; relative_path: string }[]
>([]);
const approvalPending = ref(false),
  approvalAccepted = ref(false);
const deleteReady = computed(
  () =>
    !!operation.value?.plan &&
    operation.value.state === "AwaitingApproval" &&
    !!operation.value.counts.Planned,
);
const deleteStatus = computed(() => {
  if (!operation.value) return "";
  if (["Completed", "CompletedWithWarnings"].includes(operation.value.state))
    return "Сървърът потвърди приключването на операцията. Прегледайте резултатите за всеки файл.";
  if (
    ["NeedsReview", "Failed", "RecoveryRequired"].includes(
      operation.value.state,
    )
  )
    return "Операцията не е потвърдена като успешна. Прегледайте съобщенията за файловете.";
  return approvalAccepted.value
    ? "Сървърът прие одобрението. Изчакайте потвърждение за изпълнението."
    : "";
});
const scan = ref<{
  id: string;
  state: string;
  data: Record<string, unknown>;
}>();
const action = ref(""),
  scope = ref("all"),
  scopeCategory = ref("movies"),
  operation = ref<Maintenance>(),
  confirmed = ref(false),
  history = ref(false);
const quarantine = ref<
  { id: string; state: string; data: { source: string; bulk?: boolean } }[]
>([]);
const restoreSelection = ref<string[]>([]),
  restoreJob = ref<{
    id: string;
    state: string;
    data: { error_code?: string };
    maintenance_files?: {
      id: string;
      state: string;
      data: { title?: string; error_code?: string };
    }[];
  }>();
async function refreshHistory() {
  quarantine.value = (
    await api<{ items: typeof quarantine.value }>("/library/quarantine")
  ).items;
  if (restoreJob.value)
    restoreJob.value = await api(`/jobs/${restoreJob.value.id}`);
}
async function restoreSelected() {
  await attempt(async () => {
    const result = await api<{ job_id: string }>(
      "/library/quarantines/restores",
      "POST",
      { manifest_ids: restoreSelection.value, confirmed: true },
    );
    restoreJob.value = await api(`/jobs/${result.job_id}`);
    restoreSelection.value = [];
  });
}
async function retryRestore() {
  await attempt(async () => {
    await api(
      `/library/quarantine/restores/${restoreJob.value!.id}/retry`,
      "POST",
    );
    await refreshHistory();
  });
}
const subtitleAsset = ref<Media>(),
  subtitleVersions = ref<
    {
      generation: number;
      data: { primary: string; history: { path: string }[] };
    }[]
  >([]);
const subtitleContent = ref(""),
  subtitleTiming = ref(false),
  subtitleProvider = ref("manual"),
  subtitleRelease = ref("");
const identityAsset = ref<Media>();
const manualEnglish = ref(false);
const identityCandidates = ref<
  { id: string; title: string; year: number; media_type: string }[]
>([]);
function chooseIdentityCandidate(
  candidate: (typeof identityCandidates.value)[number],
) {
  identityForm.value = {
    ...identityForm.value,
    title: candidate.title,
    year: candidate.year,
    media_type: candidate.media_type,
    provider_id: candidate.id,
  };
}
const identityForm = ref({
  title: "",
  year: "" as number | "",
  media_type: "movie",
  provider_id: "",
  edition: "Theatrical",
  season: 1,
  episode: 1,
  artist: "",
  collection_override: "",
});
function editIdentity(row: Media) {
  manualEnglish.value = false;
  identityAsset.value = row;
  menu.value = undefined;
  const i = row.data.identity;
  identityForm.value = {
    title: i?.title ?? row.title,
    year: i?.year ?? "",
    media_type: i?.media_type ?? (row.category === "series" ? "show" : "movie"),
    provider_id: i?.provider_id ?? "",
    edition: i?.edition ?? "Theatrical",
    season: i?.season ?? 1,
    episode: i?.episodes?.[0] ?? 1,
    artist: i?.artist ?? "",
    collection_override: String(i?.collection_override ?? ""),
  };
  identityCandidates.value = [];
  void attempt(async () => {
    identityCandidates.value = (
      await api<{ items: typeof identityCandidates.value }>(
        `/library/assets/${row.id}/identity-candidates`,
      )
    ).items;
  });
}
async function saveIdentity() {
  await attempt(async () => {
    const value = identityForm.value;
    await api(`/library/assets/${identityAsset.value!.id}/identity`, "POST", {
      expected_revision: identityAsset.value!.revision,
      identity: {
        ...Object.fromEntries(
          Object.entries(value).filter(([key]) => key !== "episode"),
        ),
        provider_id: value.provider_id || null,
        episodes: value.media_type === "show" ? [value.episode] : [],
        confirmed: true,
        ...(manualEnglish.value
          ? {
              title_language: "en-US",
              english_title_verified: true,
              collection_override_language: value.collection_override
                ? "en-US"
                : undefined,
            }
          : {}),
      },
    });
    identityAsset.value = undefined;
    await load();
  });
}
async function selectMatching() {
  await attempt(async () => {
    const ids: string[] = [];
    for (let start = 0; start < Math.min(total.value, 10000); start += 200) {
      const params = new URLSearchParams({
        limit: "200",
        offset: String(start),
      });
      for (const [k, v] of Object.entries(criteria.value))
        if (v) params.set(k, v);
      const page = await api<{ items: Media[] }>("/library/assets?" + params);
      page.items.forEach((row) => knownMedia.set(row.id, row));
      ids.push(...page.items.map((r) => r.id));
    }
    selected.value = [...new Set(ids)];
  });
}
const fileOffset = ref(0);
const operationRoutes: Record<string, string> = {
  normalize: "normalizations",
  quarantine: "quarantines",
  delete: "deletions",
};
const pageSelected = computed(
  () =>
    rows.value.length > 0 &&
    rows.value.every((r) => selected.value.includes(r.id)),
);
const allCount = computed(() =>
  analytics.value.reduce((n, c) => n + c.count, 0),
);
let poll: ReturnType<typeof setInterval> | undefined,
  debounce: ReturnType<typeof setTimeout> | undefined,
  generation = 0;
function bytes(n?: number) {
  if (n == null) return "Неизвестен";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let i = 0;
  while (n >= 1024 && i < 4) {
    n /= 1024;
    i++;
  }
  return `${n.toLocaleString("bg-BG", { maximumFractionDigits: 2 })} ${units[i]}`;
}
function tracks(row: Media, type: string) {
  return row.streams?.filter((t) => t.type === type) ?? [];
}
async function attempt(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Грешка";
  } finally {
    busy.value = false;
  }
}
async function load() {
  const current = ++generation;
  loading.value = true;
  try {
    const params = new URLSearchParams({
      limit: String(limit.value),
      offset: String(offset.value),
    });
    for (const [k, v] of Object.entries(criteria.value))
      if (v) params.set(k, v);
    const result = await api<{ items: Media[]; total: number }>(
      "/library/assets?" + params,
    );
    if (current === generation) {
      rows.value = result.items;
      result.items.forEach((row) => knownMedia.set(row.id, row));
      total.value = result.total;
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    if (current === generation) loading.value = false;
  }
}
async function aggregate() {
  try {
    const result = await api<{
      categories: typeof analytics.value;
      last_scan?: NonNullable<typeof scan.value>[];
    }>("/library/analytics");
    if (!Array.isArray(result.categories)) throw new Error("INVALID_ANALYTICS");
    analytics.value = result.categories;
    if (result.last_scan?.length) scan.value = result.last_scan[0];
    analyticsError.value = "";
  } catch {
    analyticsError.value =
      "Статистиката за библиотеката не може да бъде обновена.";
  } finally {
    analyticsLoading.value = false;
  }
}
function toggle(id: string) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((x) => x !== id)
    : [...selected.value, id];
}
function togglePage() {
  const ids = rows.value.map((r) => r.id);
  selected.value = pageSelected.value
    ? selected.value.filter((id) => !ids.includes(id))
    : [...new Set([...selected.value, ...ids])];
}
function start(which: string, ids?: string[]) {
  if (approvalPending.value) return;
  operationGeneration++;
  action.value = which;
  operation.value = undefined;
  confirmed.value = false;
  approvalAccepted.value = false;
  error.value = "";
  menu.value = undefined;
  fileOffset.value = 0;
  if (ids) selected.value = ids;
  deleteTargets.value =
    which === "delete"
      ? selected.value.map((id) => {
          const row = knownMedia.get(id);
          return {
            id,
            title: row?.title ?? id,
            relative_path:
              row?.relative_path ?? "Пътят ще бъде потвърден в точния план.",
          };
        })
      : [];
  scope.value = selected.value.length ? "selected" : "all";
}
function assetAction(which: LibraryAction, row: Media) {
  if (which === "identity") editIdentity(row);
  else if (which === "subtitles") void showSubtitles(row);
  else start(which, [row.id]);
}
function closeOperation() {
  if (approvalPending.value) return;
  operationGeneration++;
  action.value = "";
  operation.value = undefined;
  confirmed.value = false;
}
async function analyze() {
  if (busy.value) return;
  const current = operationGeneration;
  const route = operationRoutes[action.value];
  await attempt(async () => {
    const body =
      scope.value === "selected" || action.value !== "normalize"
        ? { asset_ids: selected.value }
        : scope.value === "category"
          ? { category: scopeCategory.value }
          : { all: true };
    const result = await api<{ job_id: string }>(
      `/library/${route}/plans`,
      "POST",
      body,
    );
    if (current !== operationGeneration) return;
    const value = await api<Maintenance>(`/library/${route}/${result.job_id}`);
    if (current === operationGeneration) operation.value = value;
  });
}
async function updateOperation() {
  if (!operation.value) return;
  const current = operationGeneration;
  const value = await api<Maintenance>(
    `/library/${operationRoutes[action.value]}/${operation.value.id}?offset=${fileOffset.value}`,
  );
  if (current === operationGeneration) operation.value = value;
}
async function approve() {
  const current = operation.value;
  const p = current?.plan;
  if (
    busy.value ||
    approvalPending.value ||
    approvalAccepted.value ||
    !p ||
    !confirmed.value ||
    current.state !== "AwaitingApproval" ||
    !current.counts.Planned
  )
    return;
  approvalPending.value = true;
  try {
    await attempt(async () => {
      await api(
        `/library/${operationRoutes[action.value]}/${current.id}/approve`,
        "POST",
        { plan_revision: p.revision, plan_sha256: p.sha256, confirmed: true },
      );
      approvalAccepted.value = true;
      confirmed.value = false;
      await updateOperation();
    });
  } finally {
    approvalPending.value = false;
  }
}
async function control(command: string) {
  await attempt(async () => {
    await api(
      `/library/${operationRoutes[action.value]}/${operation.value!.id}/${command}`,
      "POST",
    );
    await updateOperation();
  });
}
async function startScan() {
  await attempt(async () => {
    const result = await api<{ id: string }>(
      "/library/scans",
      "POST",
      criteria.value.category
        ? { category: criteria.value.category }
        : { all: true },
    );
    scan.value = await api(`/library/scans/${result.id}`);
  });
}
async function showHistory() {
  history.value = true;
  await attempt(async () => {
    quarantine.value = (
      await api<{ items: typeof quarantine.value }>("/library/quarantine")
    ).items;
  });
}
async function restore(id: string) {
  await attempt(async () => {
    const result = await api<{ job_id: string }>(
      `/library/quarantine/${id}/restore`,
      "POST",
    );
    restoreJob.value = await api(`/jobs/${result.job_id}`);
    await load();
    await aggregate();
  });
}
async function showSubtitles(row: Media) {
  subtitleAsset.value = row;
  menu.value = undefined;
  subtitleContent.value = "";
  subtitleTiming.value = false;
  subtitleRelease.value = row.relative_path;
  await attempt(async () => {
    subtitleVersions.value = (
      await api<{ items: typeof subtitleVersions.value }>(
        `/library/assets/${row.id}/subtitles/versions`,
      )
    ).items;
  });
}
async function acceptSubtitle() {
  await attempt(async () => {
    const row = subtitleAsset.value!;
    await api(`/library/assets/${row.id}/subtitles/accept`, "POST", {
      asset_revision: row.revision,
      fingerprint: row.fingerprint,
      content: subtitleContent.value,
      edition: row.data.identity?.edition ?? "Unknown",
      duration: Number(row.data.probe?.format?.duration),
      language: "bg",
      kind: "normal",
      complete: true,
      timing_confirmed: subtitleTiming.value,
      source_quality: "reviewed",
      provider: subtitleProvider.value,
      release: subtitleRelease.value,
    });
    subtitleAsset.value = undefined;
    start("normalize", [row.id]);
  });
}
async function restoreSubtitle(n: number) {
  await attempt(async () => {
    await api(
      `/library/assets/${subtitleAsset.value!.id}/subtitles/versions/${n}/restore`,
      "POST",
    );
  });
}
watch(
  criteria,
  () => {
    offset.value = 0;
    clearTimeout(debounce);
    debounce = setTimeout(() => void load(), 200);
  },
  { deep: true },
);
watch(limit, () => {
  offset.value = 0;
  void load();
});
watch(offset, () => void load());
watch(
  [view, offset, limit, criteria],
  () => {
    menu.value = undefined;
  },
  { deep: true },
);
watch(fileOffset, () => void updateOperation());
onMounted(() => {
  void attempt(async () => {
    await Promise.all([load(), aggregate()]);
  });
  poll = setInterval(() => {
    if (!busy.value)
      void attempt(async () => {
        if (operation.value) await updateOperation();
        if (history.value) await refreshHistory();
        if (scan.value && ["QUEUED", "RUNNING"].includes(scan.value.state))
          scan.value = await api(`/library/scans/${scan.value.id}`);
        await load();
        await aggregate();
      });
  }, 4000);
});
onUnmounted(() => {
  clearInterval(poll);
  clearTimeout(debounce);
});
</script>
<template>
  <div class="library-operations">
    <div class="row toolbar">
      <span class="muted"
        >{{ allCount.toLocaleString("bg-BG") }} видеофайла</span
      ><button
        class="primary"
        aria-label="Нормализация"
        @click="start('normalize')"
      >
        ⚙ Нормализация</button
      ><button :disabled="busy" aria-label="Обследване" @click="startScan">
        ⟳ Обследване</button
      ><button @click="showHistory">Карантина</button>
    </div>
    <p
      v-if="error && !action && !history && !subtitleAsset && !identityAsset"
      role="alert"
      class="warning"
    >
      {{ error }}
    </p>
    <div v-if="scan" class="notice" role="status">
      Обследване · {{ scan.state }} · {{ scan.data.processed ?? 0 }} обработени
      · нови {{ scan.data.new ?? 0 }} · променени {{ scan.data.changed ?? 0 }} ·
      непроменени {{ scan.data.unchanged ?? 0 }} · липсващи
      {{ scan.data.missing ?? 0 }} · грешки {{ scan.data.failed ?? 0 }}
    </div>
    <details
      v-if="scan && Array.isArray(scan.data.errors) && scan.data.errors.length"
    >
      <summary>Грешки при обследването</summary>
      <p
        v-for="(entry, i) in scan.data.errors as {
          category?: string;
          path?: string;
          code: string;
        }[]"
        :key="i"
      >
        {{ entry.category }} · {{ entry.path }} · {{ entry.code }}
      </p>
    </details>
    <LibraryAnalytics
      :categories="analytics"
      :loading="analyticsLoading"
      :error="analyticsError"
    />
    <div class="panel library-filters">
      <label
        >Търсене по заглавие<input
          v-model="criteria.search"
          placeholder="Заглавие или път…"
          aria-label="Търси в библиотеката"
      /></label>
      <label
        >Категория<select v-model="criteria.category">
          <option value="">Всички категории</option>
          <option v-for="(name, key) in categories" :key="key" :value="key">
            {{ name }}
          </option>
        </select></label
      >
      <label
        >Видео качество<select v-model="criteria.video_quality">
          <option value="">Всички качества</option>
          <option
            v-for="q in ['SD', 'HD', 'Full HD', '2K', '4K', '8K']"
            :key="q"
          >
            {{ q }}
          </option>
        </select></label
      >
      <label
        >Аудио формат<select v-model="criteria.audio_codec">
          <option value="">Всички формати</option>
          <option
            v-for="c in ['aac', 'ac3', 'eac3', 'dts', 'truehd', 'opus', 'flac']"
            :key="c"
          >
            {{ c }}
          </option>
        </select></label
      >
      <label
        >Език аудио<select v-model="criteria.audio_language">
          <option value="">Всички езици</option>
          <option
            v-for="l in ['bg', 'en', 'de', 'fr', 'es', 'ja', 'unknown', 'none']"
            :key="l"
          >
            {{ l }}
          </option>
        </select></label
      >
      <label
        >Език субтитри<select v-model="criteria.subtitle_language">
          <option value="">Всички езици</option>
          <option
            v-for="l in ['bg', 'en', 'de', 'fr', 'unknown', 'none']"
            :key="l"
          >
            {{ l }}
          </option>
        </select></label
      >
    </div>
    <div v-if="selected.length" class="selection-bar row">
      <strong>{{ selected.length }} избрани</strong
      ><button :disabled="busy" @click="selectMatching">
        Избери всички филтрирани</button
      ><button @click="start('normalize')">Нормализация</button
      ><button @click="start('quarantine')">Карантина</button
      ><button class="danger" @click="start('delete')">Изтриване</button
      ><button @click="selected = []">Изчисти</button>
    </div>
    <section class="panel results">
      <div class="row result-head">
        <strong>{{ total }} резултата</strong
        ><label
          >Подреждане<select v-model="criteria.sort">
            <option value="title">Заглавие</option>
            <option value="category">Категория</option>
            <option value="size">Размер</option>
            <option value="quality">Качество</option>
          </select></label
        ><button
          :aria-label="
            criteria.order === 'asc' ? 'Низходящ ред' : 'Възходящ ред'
          "
          @click="criteria.order = criteria.order === 'asc' ? 'desc' : 'asc'"
        >
          {{ criteria.order === "asc" ? "↑" : "↓" }}</button
        ><button :aria-pressed="view === 'table'" @click="view = 'table'">
          ☷ Таблица</button
        ><button :aria-pressed="view === 'cards'" @click="view = 'cards'">
          ▦ Карти
        </button>
      </div>
      <p v-if="loading" role="status" class="muted pad">Зареждане…</p>
      <div :class="view === 'cards' ? 'compact-cards' : 'table-scroll'">
        <table v-if="view === 'table' && rows.length">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  aria-label="Избери текущата страница"
                  :checked="pageSelected"
                  @change="togglePage"
                />
              </th>
              <th>Заглавие / файл</th>
              <th>Категория</th>
              <th>Видео</th>
              <th>Аудиопътеки</th>
              <th>Субтитри</th>
              <th>Размер</th>
              <th>Статус</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>
                <input
                  type="checkbox"
                  :aria-label="'Избери ' + row.title"
                  :checked="selected.includes(row.id)"
                  @change="toggle(row.id)"
                />
              </td>
              <td>
                <strong>{{ row.title }}</strong
                ><small class="file-path" :title="row.relative_path">{{
                  row.relative_path
                }}</small>
              </td>
              <td>{{ categories[row.category] ?? "Неизвестна" }}</td>
              <td>
                <span class="badge">{{
                  row.video_quality ?? "Неизвестно"
                }}</span>
              </td>
              <td>
                <details>
                  <summary>
                    ♫
                    {{
                      row.streams === null
                        ? "Неизвестни"
                        : tracks(row, "audio").length + " потока"
                    }}
                  </summary>
                  <p v-for="t in tracks(row, 'audio')" :key="t.index">
                    {{ t.language }} · {{ t.codec ?? "неизвестен" }} ·
                    {{ t.channels ?? "?" }} ch ·
                    {{
                      t.bitrate
                        ? Math.round(t.bitrate / 1000) + " kb/s"
                        : "битрейт неизвестен"
                    }}
                    <small v-if="t.language === 'bg'"
                      >Открит BG · автоматично приет</small
                    >
                  </p>
                </details>
              </td>
              <td>
                <details>
                  <summary>
                    ▤
                    {{
                      row.streams === null
                        ? "Неизвестни"
                        : tracks(row, "subtitle").length + " вградени"
                    }}
                  </summary>
                  <p v-for="t in tracks(row, 'subtitle')" :key="t.index">
                    {{ t.language }} · {{ t.profile ?? t.codec }}
                  </p>
                  <p
                    v-for="s in (row.data.external_subtitles as {
                      path: string;
                      language: string;
                    }[]) ?? []"
                    :key="s.path"
                  >
                    {{ s.language }} · външни
                  </p>
                </details>
              </td>
              <td>{{ bytes(row.file_size_bytes) }}</td>
              <td>
                <span
                  :title="
                    row.data.dependencies?.length
                      ? 'Torrent зависимост блокира операции'
                      : ''
                  "
                  >{{
                    row.data.dependencies?.length
                      ? "⛓ Torrent"
                      : row.availability
                  }}</span
                >
              </td>
              <td>
                <LibraryActionMenu
                  :asset="row"
                  :busy="busy"
                  :open="menu === row.id"
                  @toggle="menu = menu === row.id ? undefined : row.id"
                  @close="menu = undefined"
                  @select="assetAction($event, row)"
                />
              </td>
            </tr>
          </tbody>
        </table>
        <article
          v-for="row in view === 'cards' ? rows : []"
          :key="row.id"
          class="compact-card"
        >
          <div class="card-top">
            <input
              type="checkbox"
              :aria-label="'Избери ' + row.title"
              :checked="selected.includes(row.id)"
              @change="toggle(row.id)"
            /><span class="badge">{{ categories[row.category] }}</span
            ><LibraryActionMenu
              :asset="row"
              :busy="busy"
              :open="menu === row.id"
              @toggle="menu = menu === row.id ? undefined : row.id"
              @close="menu = undefined"
              @select="assetAction($event, row)"
            />
          </div>
          <h2>{{ row.title }}</h2>
          <p class="file-path">{{ row.relative_path }}</p>
          <div class="row">
            <span class="badge">{{ row.video_quality ?? "Неизвестно" }}</span
            ><span>{{ bytes(row.file_size_bytes) }}</span
            ><span>{{ row.availability }}</span>
          </div>
          <details>
            <summary>♫ Аудио · {{ tracks(row, "audio").length }}</summary>
            <p v-for="t in tracks(row, 'audio')" :key="t.index">
              {{ t.language }} · {{ t.profile ?? t.codec }} ·
              {{ t.channels ?? "?" }} ch ·
              {{ t.bitrate ?? "?" }}
            </p>
          </details>
          <details>
            <summary>▤ Субтитри</summary>
            <p v-for="t in tracks(row, 'subtitle')" :key="t.index">
              {{ t.language }} · {{ t.profile ?? t.codec }}
            </p>
            <p
              v-for="s in (row.data.external_subtitles as {
                path: string;
                language: string;
              }[]) ?? []"
              :key="s.path"
            >
              {{ s.language }} · външни
            </p>
          </details>
        </article>
      </div>
      <p v-if="!rows.length && !loading" class="empty">
        Няма намерени записи. Променете филтрите или стартирайте read-only
        обследване.
      </p>
      <div class="row pager">
        <span
          >{{ total ? offset + 1 : 0 }}–{{ Math.min(offset + limit, total) }} от
          {{ total }}</span
        ><button
          :disabled="offset === 0"
          @click="offset = Math.max(0, offset - limit)"
        >
          Предишна</button
        ><button :disabled="offset + limit >= total" @click="offset += limit">
          Следваща</button
        ><label
          >На страница<select v-model.number="limit">
            <option v-for="n in [12, 25, 50, 100]" :key="n">{{ n }}</option>
          </select></label
        >
      </div>
    </section>
    <CompactDialog
      v-if="action"
      :error="error"
      :title="
        action === 'normalize'
          ? 'Нормализация'
          : action === 'delete'
            ? 'Потвърждение за изтриване'
            : 'Карантина'
      "
      :dismissible="!approvalPending"
      @close="closeOperation"
    >
      <template v-if="action === 'delete'">
        <p>
          Заявявате изтриване на избраните видеофайлове и доказано
          принадлежащите им файлове от библиотеката. Това действие не може да се
          отмени от ViMag. Карантината и torrent зависимостите остават защитени.
        </p>
        <div v-for="target in deleteTargets" :key="target.id" class="plan-row">
          <strong>{{ target.title }}</strong
          ><span class="delete-path">{{ target.relative_path }}</span>
        </div>
        <p>
          Първо анализирайте точния план. Само допустимите файлове в одобрения
          план могат да бъдат обработени от сървъра.
        </p>
        <p v-if="deleteStatus" role="status">{{ deleteStatus }}</p>
      </template>
      <template v-if="!operation"
        ><p>Анализ → точен план → едно одобрение → автоматично изпълнение.</p>
        <label v-if="action === 'normalize'"
          >Обхват<select v-model="scope">
            <option value="all">Цяла библиотека</option>
            <option value="category">Категория</option>
            <option value="selected" :disabled="!selected.length">
              Избрани ({{ selected.length }})
            </option>
          </select></label
        ><select v-if="scope === 'category'" v-model="scopeCategory">
          <option v-for="(n, k) in categories" :key="k" :value="k">
            {{ n }}
          </option>
        </select>
        <p v-if="action !== 'normalize'">
          {{ selected.length }} избрани видеофайла и доказано принадлежащите им
          sidecars. Torrent зависимостите блокират съответния файл.
        </p>
        <button class="primary" :disabled="busy" @click="analyze">
          Анализирай
        </button></template
      >
      <template v-else
        ><button
          v-if="!operation.plan && operation.state !== 'Analyzing'"
          :disabled="busy"
          @click="control('retry')"
        >
          Повтори анализа
        </button>
        <div class="row">
          <span class="badge">{{ operation.state }}</span
          ><span>Политика v{{ operation.data.policy_revision }}</span
          ><span>{{ operation.data.phase }}</span>
        </div>
        <p>
          {{
            Object.entries(operation.counts)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ")
          }}
        </p>
        <div class="phase-list">
          <span
            v-for="(p, i) in [
              'Идентификация',
              'Йерархия / naming',
              'BG субтитри',
              'Jellyfin проверка',
            ]"
            :key="p"
            >0{{ i + 1 }} · {{ p }}</span
          >
        </div>
        <div v-for="f in operation.files" :key="f.id" class="plan-row">
          <strong>{{ f.data.title }}</strong
          ><span>{{ f.state }} · фаза {{ f.phase }}</span
          ><small
            >{{ f.data.source }} →
            {{
              f.data.target ??
              (action === "delete" ? "Физическо премахване" : "—")
            }}</small
          ><small v-for="entry in f.data.files" :key="entry.source"
            >{{ entry.source }} → {{ entry.target ?? "Премахване" }} ·
            {{ bytes(entry.size) }}</small
          >
          <p v-if="f.data.error_code" class="warning">
            {{ f.data.error_code }}
          </p>
          <small
            v-for="proposal in f.data.sidecar_proposals"
            :key="proposal.target"
            >{{ proposal.kind }} → {{ proposal.target }}</small
          >
          <small v-if="f.data.preserved_sidecars?.length"
            >Запазени shared / непотвърдени sidecars:
            {{ f.data.preserved_sidecars.join(", ") }}</small
          >
          <small v-if="f.data.warnings?.length">{{
            f.data.warnings.join(" · ")
          }}</small>
        </div>
        <div class="row">
          <button
            :disabled="fileOffset === 0"
            @click="fileOffset = Math.max(0, fileOffset - 100)"
          >
            Предишни файлове</button
          ><button
            :disabled="operation.files.length < 100"
            @click="fileOffset += 100"
          >
            Следващи файлове
          </button>
        </div>
        <template
          v-if="operation.state === 'AwaitingApproval' && action !== 'delete'"
          ><label class="check"
            ><input v-model="confirmed" type="checkbox" />{{
              action === "delete"
                ? "Потвърждавам физическо и окончателно изтриване на точните допустими файлове."
                : "Прегледах точния план и одобрявам изпълнението."
            }}</label
          ><button
            :disabled="!confirmed || busy || !operation.counts.Planned"
            :class="action === 'delete' ? 'danger' : 'primary'"
            @click="approve"
          >
            {{
              action === "delete"
                ? "Изтрий потвърдените файлове"
                : "Одобри плана"
            }}
          </button></template
        >
        <div
          v-else-if="operation.plan && operation.state !== 'AwaitingApproval'"
          class="row"
        >
          <button :disabled="busy" @click="control('pause')">Пауза</button
          ><button :disabled="busy" @click="control('resume')">Продължи</button
          ><button :disabled="busy" @click="control('cancel')">
            Отмени остатъка</button
          ><button :disabled="busy" @click="control('retry')">
            Повтори неуспешните
          </button>
        </div>
        <details>
          <summary>История и възстановяване</summary>
          <p v-for="(e, i) in operation.history" :key="i">
            {{ e.kind }} · {{ e.created_at }}
          </p>
        </details></template
      >
      <div v-if="action === 'delete'">
        <label class="check"
          ><input
            v-model="confirmed"
            type="checkbox"
            :disabled="
              !deleteReady || busy || approvalPending || approvalAccepted
            "
          />
          Разбирам, че потвърждавам окончателно изтриване само на допустимите
          файлове от точния план.</label
        >
        <div class="row">
          <button :disabled="approvalPending" @click="closeOperation">
            Отказ
          </button>
          <button
            class="danger"
            :disabled="
              !confirmed ||
              !deleteReady ||
              busy ||
              approvalPending ||
              approvalAccepted
            "
            @click="approve"
          >
            {{ approvalPending ? "Изпращане…" : "Потвърди изтриването" }}
          </button>
        </div>
      </div>
    </CompactDialog>
    <CompactDialog
      v-if="history"
      :error="error"
      title="Карантина · възстановяване"
      @close="history = false"
      ><p>
        Няма автоматично изчистване. Възстановява се оригиналният път;
        конфликтите изискват преглед.
      </p>
      <div v-for="q in quarantine" :key="q.id" class="plan-row">
        <label class="check"
          ><input
            v-model="restoreSelection"
            type="checkbox"
            :value="q.id"
            :disabled="q.state !== 'QUARANTINED' || !q.data.bulk"
          />{{
            q.data.bulk
              ? "Избери за възстановяване"
              : "RC1 manifest · индивидуално възстановяване"
          }}</label
        >
        <span>{{ q.data.source }} · {{ q.state }}</span
        ><button
          :disabled="q.state !== 'QUARANTINED' || busy"
          @click="restore(q.id)"
        >
          Възстанови оригинала
        </button>
      </div>
      <button
        :disabled="busy || !restoreSelection.length"
        @click="restoreSelected"
      >
        Възстанови избраните към оригиналните пътища ({{
          restoreSelection.length
        }})
      </button>
      <section v-if="restoreJob">
        <p>{{ restoreJob.state }} · {{ restoreJob.data.error_code }}</p>
        <p v-for="f in restoreJob.maintenance_files" :key="f.id">
          {{ f.data.title }} · {{ f.state }} · {{ f.data.error_code }}
        </p>
        <button
          v-if="!['Queued', 'MaintenanceVerified'].includes(restoreJob.state)"
          :disabled="busy"
          @click="retryRestore"
        >
          Повтори неуспешното възстановяване
        </button>
      </section></CompactDialog
    >
    <CompactDialog
      v-if="subtitleAsset"
      :error="error"
      title="BG субтитри · подобряване и версии"
      @close="subtitleAsset = undefined"
      ><p>
        {{ subtitleAsset.title }} · кандидатът се прилага чрез отделно одобрен
        план за нормализация.
      </p>
      <label>Provider<input v-model="subtitleProvider" /></label
      ><label>Release / издание<input v-model="subtitleRelease" /></label
      ><label
        >Проверен UTF-8 SRT<textarea
          v-model="subtitleContent"
          rows="7"
        /></label
      ><label class="check"
        ><input v-model="subtitleTiming" type="checkbox" />Проверих точния cut,
        FPS, продължителност, пълнота и синхрон с това видео.</label
      ><button
        :disabled="busy || !subtitleTiming || !subtitleContent"
        @click="acceptSubtitle"
      >
        Приеми и подготви нормализация
      </button>
      <h3>История извън Jellyfin Library</h3>
      <div v-for="v in subtitleVersions" :key="v.generation" class="plan-row">
        <span
          >Поколение {{ v.generation }} · {{ v.data.history.length }} запазени
          варианта</span
        ><button :disabled="busy" @click="restoreSubtitle(v.generation)">
          Възстанови този основен вариант
        </button>
      </div></CompactDialog
    >
    <CompactDialog
      v-if="identityAsset"
      :error="error"
      title="Идентификация и колекция"
      @close="identityAsset = undefined"
      ><p>{{ identityAsset.relative_path }}</p>
      <div v-if="identityCandidates.length">
        <p>Кандидати от TMDb · изберете и потвърдете точната идентичност</p>
        <button
          v-for="candidate in identityCandidates"
          :key="candidate.id"
          @click="chooseIdentityCandidate(candidate)"
        >
          {{ candidate.title }} ({{ candidate.year }}) ·
          {{ candidate.media_type }} · TMDb {{ candidate.id }}
        </button>
      </div>
      <label>Заглавие<input v-model="identityForm.title" /></label
      ><label
        >Година<input
          v-model.number="identityForm.year"
          type="number"
          min="1880"
          max="2200" /></label
      ><label
        >Тип<select v-model="identityForm.media_type">
          <option value="movie">Филм</option>
          <option value="show">Сериал</option>
          <option value="concert">Концерт</option>
        </select></label
      ><label
        >TMDb ID<input
          v-model="identityForm.provider_id"
          inputmode="numeric" /></label
      ><label>Издание<input v-model="identityForm.edition" /></label
      ><label
        >Ръчна колекция<input v-model="identityForm.collection_override"
      /></label>
      <div v-if="identityForm.media_type === 'show'" class="row">
        <label
          >Сезон<input
            v-model.number="identityForm.season"
            type="number" /></label
        ><label
          >Епизод<input v-model.number="identityForm.episode" type="number"
        /></label>
      </div>
      <label v-if="identityForm.media_type === 'concert'"
        >Артист<input v-model="identityForm.artist"
      /></label>
      <p class="notice">
        Потвърждава метаданни. Промяната на файловете изисква нов план за
        нормализация.
      </p>
      <label class="check"
        ><input v-model="manualEnglish" type="checkbox" /> Потвърждавам, че
        ръчно въведените заглавие и колекция са на английски. Другите заглавия
        изискват преглед преди нормализация.</label
      >
      <button
        class="primary"
        :disabled="busy || !identityForm.title"
        @click="saveIdentity"
      >
        Потвърди идентификацията
      </button></CompactDialog
    >
  </div>
</template>
<style scoped>
.toolbar {
  justify-content: flex-end;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.toolbar .muted {
  margin-right: auto;
}
.library-filters {
  display: grid;
  grid-template-columns: 2fr repeat(5, 1fr);
  gap: 10px;
  padding: 16px;
  margin-bottom: 14px;
}
.library-filters label,
.pager label {
  font-size: 10px;
  color: #9fb5bd;
}
.library-filters input,
.library-filters select {
  margin-top: 7px;
  width: 100%;
}
.selection-bar {
  padding: 10px 16px;
  background: #174039;
  border: 1px solid #438f79;
  border-radius: 10px;
  margin: 12px 0;
  flex-wrap: wrap;
}
.results {
  overflow: visible;
}
.result-head {
  padding: 14px;
  flex-wrap: wrap;
}
.result-head strong {
  margin-right: auto;
}
.result-head label {
  font-size: 11px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.table-scroll {
  overflow: auto;
  min-height: 200px;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 1020px;
  font-size: 11px;
}
td,
th {
  padding: 12px 9px;
  border-bottom: 1px solid #263d47;
  text-align: left;
}
td {
  position: relative;
  vertical-align: middle;
}
td strong {
  font-size: 12px;
}
.file-path {
  display: block;
  font-size: 10px;
  color: #92a8b2;
  max-width: 290px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 5px;
}
summary {
  cursor: pointer;
  font-size: 11px;
}
details p {
  font-size: 11px;
  max-width: 250px;
}
details small {
  display: block;
  color: #83dfc4;
}
.delete-path {
  overflow-wrap: anywhere;
  font-size: 11px;
}
.danger {
  color: #ffb6b9;
  border-color: #855252;
  background: #35242a;
}
.compact-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  padding: 16px;
}
.compact-card {
  position: relative;
  padding: 15px;
  border: 1px solid #314754;
  border-radius: 10px;
  background: #11222b;
  min-width: 0;
}
.compact-card h2 {
  font-size: 14px;
}
.compact-card details {
  margin-top: 12px;
}
.card-top {
  display: flex;
  gap: 12px;
  align-items: center;
}
.card-top :deep(button[aria-haspopup]) {
  margin-left: auto;
}
.pager {
  padding: 14px;
  flex-wrap: wrap;
  justify-content: space-between;
}
.plan-row {
  border-bottom: 1px solid #2a444c;
  padding: 12px 0;
  display: grid;
  gap: 5px;
  font-size: 12px;
}
.plan-row small {
  color: #9cb5bc;
  overflow-wrap: anywhere;
}
.phase-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 10px;
  color: #8fe5cd;
  margin: 15px 0;
}
.library-operations :deep(textarea) {
  width: 100%;
  resize: vertical;
}
.library-operations :deep(.compact-dialog label) {
  display: block;
  margin: 12px 0;
}
.library-operations input[type="checkbox"] {
  accent-color: #57e3c2;
}
@media (max-width: 1400px) {
  .library-filters {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (max-width: 900px) {
  .compact-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .library-filters {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 600px) {
  .compact-cards {
    grid-template-columns: 1fr;
  }
  .library-filters {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
