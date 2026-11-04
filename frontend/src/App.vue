<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  LayoutDashboard,
  Layers,
  Library,
  Columns2,
  ArrowLeftRight,
  Captions,
  Settings,
  ShieldCheck,
  RefreshCw,
  LogOut,
  ArrowUpRight,
  Search,
  Menu,
} from "lucide-vue-next";
import { api, ApiError } from "./api";
import LibraryOperations from "./LibraryOperations.vue";
import LibraryOrganization from "./LibraryOrganization.vue";
import type {
  Asset,
  Audit,
  Evidence,
  Health,
  Identity,
  Job,
  Operation,
  Plan,
  Item,
} from "./types";

const routes = [
  { id: "dashboard", label: "Табло", icon: LayoutDashboard },
  { id: "jobs", label: "Задачи за импорт", icon: Layers },
  { id: "library", label: "Библиотека", icon: Library },
  { id: "comparison", label: "Сравнение на версии", icon: Columns2 },
  { id: "queue", label: "Опашка за преместване", icon: ArrowLeftRight },
  { id: "subtitles", label: "Български субтитри", icon: Captions },
  { id: "settings", label: "Настройки", icon: Settings },
];
const steps = [
  "Изтегляне",
  "Идентификация",
  "Сравнение",
  "Организация",
  "Субтитри",
  "Jellyfin",
  "Seeding",
];
const categories = {
  movies: "Филми",
  series: "Сериали",
  animations: "Анимация",
  documentaries: "Документални",
  concerts: "Концерти",
};
const authenticated = ref(false),
  checking = ref(true),
  enrolling = ref(false),
  busy = ref(false),
  error = ref(""),
  notice = ref("");
const username = ref(""),
  password = ref(""),
  setupToken = ref(""),
  sidebar = ref(false);
const collapsed = ref(
  localStorage.getItem("vimag-sidebar-collapsed") === "true",
);
const narrow = ref(window.innerWidth <= 900);
function viewportChanged() {
  narrow.value = window.innerWidth <= 900;
  if (!narrow.value) sidebar.value = false;
}
function toggleSidebar() {
  if (narrow.value) {
    sidebar.value = !sidebar.value;
    return;
  }
  collapsed.value = !collapsed.value;
  localStorage.setItem("vimag-sidebar-collapsed", String(collapsed.value));
}
const route = ref(location.hash.slice(1) || "dashboard"),
  jobs = ref<Job[]>([]),
  selected = ref<Job>(),
  plan = ref<Plan>(),
  health = ref<Health>();
const assets = ref<Asset[]>([]),
  operations = ref<Operation[]>([]),
  decisions = ref<Evidence[]>([]),
  subtitles = ref<Evidence[]>([]),
  audit = ref<Audit[]>([]);
const search = ref(""),
  category = ref(""),
  state = ref(""),
  offset = ref(0),
  activeStep = ref(0),
  tab = ref("overview");
const reviewItem = ref(""),
  reviewTitle = ref(""),
  reviewYear = ref(2026),
  reviewType = ref("movie"),
  reviewProvider = ref(""),
  reviewEdition = ref("Theatrical"),
  reviewSeason = ref(1),
  reviewEpisodes = ref("1"),
  reviewArtist = ref(""),
  reviewReason = ref(""),
  reviewDecision = ref("KeepBoth"),
  materialImprovement = ref(false);
const approvalChecked = ref(false),
  pendingQuarantine = ref<Plan>();
const subtitleReview = ref<Evidence>(),
  subtitleText = ref(""),
  subtitleOffset = ref(0),
  subtitleScale = ref(1),
  subtitleConfirmed = ref(false);
async function verifyBg(item: Item, key: string, action: "verify" | "revoke") {
  await attempt(async () => {
    await api("/media/bg-evidence", "POST", {
      item_id: item.id,
      fingerprint: item.data.fingerprint,
      stream_key: key,
      action,
      reason: "Ръчно stream-bound потвърждение от администратора",
    });
    notice.value =
      "Доказателството е записано; промяната на името изисква безопасен план.";
    await refresh();
  });
}
function openSubtitle(sub: Evidence) {
  subtitleReview.value = sub;
  subtitleText.value =
    typeof sub.data.content === "string" ? sub.data.content : "";
  subtitleConfirmed.value = false;
}
async function downloadSubtitle(sub: Evidence) {
  await attempt(async () => {
    await api(`/subtitles/${sub.id}/download`, "POST");
    notice.value =
      "Кандидатът се изтегля за проверка на текста и синхронизацията.";
    await refresh();
  });
}
async function syncSubtitle() {
  await attempt(async () => {
    const result = await api<{ content: string }>(
      "/subtitles/sync-proposal",
      "POST",
      {
        content: subtitleText.value,
        offset: subtitleOffset.value,
        scale: subtitleScale.value,
      },
    );
    subtitleText.value = result.content;
    subtitleConfirmed.value = false;
    notice.value = "Това е предложение. Проверете timing преди използване.";
  });
}
async function attachSubtitle() {
  await attempt(async () => {
    const sub = subtitleReview.value;
    if (!sub || !subtitleConfirmed.value) return;
    if (sub.asset_id) {
      await api(`/library/assets/${sub.asset_id}/subtitles/accept`, "POST", {
        asset_revision: sub.asset_revision,
        fingerprint: sub.context?.fingerprint,
        edition: sub.context?.identity?.edition ?? "Unknown",
        content: subtitleText.value,
        duration: Number(sub.context?.probe?.format?.duration),
        language: "bg",
        kind: "normal",
        complete: true,
        timing_confirmed: true,
        source_quality: "reviewed",
        provider: String(sub.data.provider ?? "manual"),
        release: String(sub.data.id ?? sub.id),
      });
      subtitleReview.value = undefined;
      notice.value =
        "Кандидатът е приет. Приложете го чрез план за нормализация в Библиотека.";
      await refresh();
      return;
    }
    await api("/subtitles/verify", "POST", {
      item_id: sub.item_id,
      fingerprint: sub.context?.fingerprint,
      edition: sub.context?.identity?.edition,
      content: subtitleText.value,
      timing_confirmed: true,
      reason: "Ръчно потвърдено съответствие с точния видеофайл",
    });
    subtitleReview.value = undefined;
    notice.value = "Провереният кандидат е в опашката за безопасно прикачване.";
    await refresh();
  });
}
const settingsTab = ref("connections"),
  pollSeconds = ref(20),
  retries = ref(3),
  minFree = ref(100),
  settingSections = ref<
    { key: string; value: Record<string, unknown>; revision: number }[]
  >([]);
const normalizingAsset = ref<Asset>();
const title = computed(() =>
  route.value.startsWith("job/")
    ? "Детайли на задача"
    : (routes.find((r) => r.id === route.value)?.label ?? "Табло"),
);
const counts = ref<Record<string, number>>({});
const total = computed(() =>
  Object.values(counts.value).reduce((a, b) => a + b, 0),
);
let timer: ReturnType<typeof setInterval> | undefined;

function formatDate(value: string) {
  return new Intl.DateTimeFormat("bg-BG", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}
function label(job: Job) {
  return String(
    job.data.title ??
      job.media_items?.[0]?.data.identity?.title ??
      job.id.slice(0, 8),
  );
}
function statusClass(value: string) {
  return value.includes("Completed") || value === "VERIFIED"
    ? "success"
    : /Review|Approval|Pending|Blocked|Recovery|Required|Conflict|Unavailable/.test(
          value,
        )
      ? "warn"
      : "info";
}
function navigate(value: string) {
  location.hash = value;
  route.value = value;
  sidebar.value = false;
  error.value = "";
  void refresh();
}
function handleHash() {
  route.value = location.hash.slice(1) || "dashboard";
  void refresh();
}
async function attempt(action: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    await action();
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) authenticated.value = false;
    error.value = e instanceof Error ? e.message : "Грешка при заявката";
  } finally {
    busy.value = false;
  }
}
async function login() {
  await attempt(async () => {
    if (enrolling.value)
      await api("/auth/setup", "POST", {
        username: username.value,
        password: password.value,
        setup_token: setupToken.value,
      });
    await api("/auth/login", "POST", {
      username: username.value,
      password: password.value,
    });
    password.value = "";
    setupToken.value = "";
    authenticated.value = true;
    await refresh();
  });
}
async function logout() {
  await attempt(async () => {
    await api("/auth/logout", "POST");
    authenticated.value = false;
    selected.value = undefined;
    jobs.value = [];
    assets.value = [];
  });
}
async function refresh() {
  if (!authenticated.value) return;
  try {
    if (route.value === "dashboard" || route.value === "jobs") {
      const result = await api<{ items: Job[] }>(
        "/jobs?" +
          new URLSearchParams({
            search: search.value,
            category: category.value,
            state: state.value,
            offset: String(offset.value),
          }),
      );
      jobs.value = result.items;
      const dashboard = await api<{
        counts: Record<string, number>;
        health: Health;
        recent: Audit[];
      }>("/dashboard");
      counts.value = dashboard.counts;
      health.value = dashboard.health;
      audit.value = dashboard.recent;
    } else if (route.value.startsWith("job/")) {
      selected.value = await api<Job>("/jobs/" + route.value.slice(4));
      try {
        plan.value = await api<Plan>("/jobs/" + route.value.slice(4) + "/plan");
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 404) throw e;
        plan.value = undefined;
      }
    } else if (route.value === "library") {
      health.value = await api<Health>("/health/ready");
    } else if (route.value === "comparison")
      decisions.value = (
        await api<{ items: Evidence[] }>("/library/duplicates")
      ).items;
    else if (route.value === "queue")
      operations.value = (
        await api<{ items: Operation[] }>("/transfers")
      ).items;
    else if (route.value === "subtitles")
      subtitles.value = (await api<{ items: Evidence[] }>("/subtitles")).items;
    else if (route.value === "settings") {
      const result = await api<{ sections: typeof settingSections.value }>(
        "/settings",
      );
      settingSections.value = result.sections;
      health.value = await api<Health>("/health/ready");
      audit.value = (await api<{ items: Audit[] }>("/audit")).items;
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) authenticated.value = false;
    error.value = e instanceof Error ? e.message : "Връзката е прекъсната";
  }
}
async function control(action: string) {
  await attempt(async () => {
    if (!selected.value) return;
    await api(`/jobs/${selected.value.id}/${action}`, "POST");
    notice.value = "Заявката е записана. Worker проверява текущото състояние.";
    await refresh();
  });
}
async function approve() {
  await attempt(async () => {
    if (!plan.value || !selected.value || !approvalChecked.value) return;
    await api(`/jobs/${selected.value.id}/approve`, "POST", {
      plan_revision: plan.value.revision,
      plan_sha256: plan.value.sha256,
      reason: reviewReason.value || "Планът е прегледан",
    });
    approvalChecked.value = false;
    await refresh();
  });
}
function editItem(id: string) {
  const item = selected.value?.media_items?.find((i) => i.id === id);
  if (!item) return;
  reviewItem.value = id;
  materialImprovement.value = false;
  const i = item.data.identity;
  reviewTitle.value = i?.title ?? "";
  reviewYear.value = i?.year ?? 2026;
  reviewProvider.value = i?.provider_id ?? "";
  reviewType.value = i?.media_type ?? "movie";
  reviewEdition.value = i?.edition ?? "Theatrical";
  reviewSeason.value = i?.season ?? 1;
  reviewEpisodes.value = i?.episodes?.join(",") ?? "1";
  reviewReason.value = "";
}
async function saveReview() {
  await attempt(async () => {
    if (!selected.value && !normalizingAsset.value) return;
    const identity: Identity = {
      title: reviewTitle.value,
      year: reviewYear.value,
      media_type: reviewType.value,
      provider_id: reviewProvider.value || null,
      edition: reviewEdition.value,
      artist: reviewArtist.value || undefined,
    };
    if (reviewType.value === "show") {
      identity.season = reviewSeason.value;
      identity.episodes = reviewEpisodes.value.split(",").map(Number);
    }
    if (normalizingAsset.value) {
      pendingQuarantine.value = await api<Plan>(
        `/library/assets/${normalizingAsset.value.id}/normalization-plan`,
        "POST",
        { identity, quality_label: "Original", reason: reviewReason.value },
      );
      normalizingAsset.value = undefined;
      reviewItem.value = "";
      approvalChecked.value = false;
      return;
    }
    if (!selected.value) return;
    await api(`/jobs/${selected.value.id}/review`, "POST", {
      expected_revision: selected.value.revision,
      item_id: reviewItem.value,
      identity,
      quality_decision: reviewDecision.value,
      material_improvement_verified: materialImprovement.value,
      reason: reviewReason.value,
    });
    reviewItem.value = "";
    await refresh();
  });
}
async function approveQuarantine() {
  await attempt(async () => {
    const q = pendingQuarantine.value;
    if (!q || !approvalChecked.value) return;
    await api(
      `/library/${q.data.action === "NORMALIZE" ? "normalization-plans" : "quarantine-plans"}/${q.id}/approve`,
      "POST",
      {
        plan_revision: q.revision,
        plan_sha256: q.sha256,
        reason: reviewReason.value || "Прегледан обратим план",
      },
    );
    pendingQuarantine.value = undefined;
    notice.value = "Планът е одобрен; live dependency проверката предстои.";
    await refresh();
  });
}
async function approveSidecar(conflict: {
  relative_path: string;
  observed_sha256: string;
}) {
  await attempt(async () => {
    if (!selected.value || !plan.value || !approvalChecked.value) return;
    await api(`/jobs/${selected.value.id}/sidecars/approve`, "POST", {
      plan_revision: plan.value.revision,
      plan_sha256: plan.value.sha256,
      relative_path: conflict.relative_path,
      observed_sha256: conflict.observed_sha256,
      reason: "Изрично одобрена замяна на показаната ревизия с backup",
    });
    approvalChecked.value = false;
    await refresh();
  });
}
async function saveSettings() {
  await attempt(async () => {
    await api("/settings/automation", "PUT", {
      poll_seconds: pollSeconds.value,
      retry_budget: retries.value,
    });
    await api("/settings/storage", "PUT", { min_free_gib: minFree.value });
    notice.value = "Настройките са записани.";
    await refresh();
  });
}
onMounted(async () => {
  window.addEventListener("resize", viewportChanged);
  window.addEventListener("hashchange", handleHash);
  try {
    await api("/me");
    authenticated.value = true;
    await refresh();
  } catch {
    authenticated.value = false;
  } finally {
    checking.value = false;
  }
  timer = setInterval(() => {
    if (!busy.value && !reviewItem.value) void refresh();
  }, 5000);
});
onUnmounted(() => {
  window.removeEventListener("resize", viewportChanged);
  window.removeEventListener("hashchange", handleHash);
  if (timer) clearInterval(timer);
});
</script>

<template>
  <div v-if="checking" class="login-shell">
    <p role="status">Проверка на сесията…</p>
  </div>
  <div v-else-if="!authenticated" class="login-shell">
    <form class="login panel" @submit.prevent="login">
      <div class="brand">
        <span class="logo">VM</span
        ><span>ViMag <small>MEDIA MANAGER</small></span>
      </div>
      <h1>
        {{
          enrolling ? "Първоначална настройка" : "Вход в работното пространство"
        }}
      </h1>
      <p class="muted">Частна медийна библиотека · Един администратор</p>
      <label
        >Потребител<input
          v-model="username"
          required
          autocomplete="username"
          maxlength="80"
      /></label>
      <label
        >Парола<input
          v-model="password"
          type="password"
          required
          :minlength="enrolling ? 14 : 1"
          maxlength="256"
          :autocomplete="enrolling ? 'new-password' : 'current-password'"
      /></label>
      <label v-if="enrolling"
        >Еднократен setup token<input
          v-model="setupToken"
          type="password"
          required
          autocomplete="off"
      /></label>
      <p v-if="error" role="alert" class="warning">{{ error }}</p>
      <button class="primary" :disabled="busy">
        {{ busy ? "Проверка…" : enrolling ? "Създай администратор" : "Вход" }}
      </button>
      <button type="button" class="ghost" @click="enrolling = !enrolling">
        {{ enrolling ? "Обратно към вход" : "Първо стартиране" }}
      </button>
    </form>
  </div>
  <div v-else class="app-shell" :class="{ collapsed }">
    <aside :class="['sidebar', { open: sidebar }]">
      <div class="brand">
        <span class="logo">VM</span
        ><span>ViMag <small>MEDIA MANAGER</small></span>
      </div>
      <span class="eyebrow">РАБОТНО ПРОСТРАНСТВО</span>
      <nav aria-label="Основна навигация">
        <button
          v-for="r in routes"
          :key="r.id"
          :class="{ active: route === r.id }"
          :title="collapsed ? r.label : undefined"
          :aria-label="r.label"
          :aria-current="route === r.id ? 'page' : undefined"
          @click="navigate(r.id)"
        >
          <component :is="r.icon" :size="18" /><span>{{ r.label }}</span>
        </button>
      </nav>
      <div class="side-bottom panel">
        <ShieldCheck :size="20" /><strong>{{
          health?.write_enabled && health?.production_authorized
            ? "Операции активни"
            : "Операции неактивни"
        }}</strong>
        <p>Legacy torrents са защитени.</p>
        <span class="badge">1.1.0</span>
      </div>
    </aside>
    <div class="workspace">
      <header>
        <div class="row">
          <button
            class="icon"
            aria-label="Прибери или разгъни навигацията"
            :aria-expanded="narrow ? sidebar : !collapsed"
            @click="toggleSidebar()"
          >
            <Menu :size="18" /></button
          ><span class="muted">Работно пространство</span><span>/</span
          ><strong>{{ title }}</strong>
        </div>
        <div class="row">
          <span
            class="badge"
            :class="
              health?.write_enabled && health?.production_authorized
                ? 'success'
                : 'warn'
            "
            >{{
              health?.write_enabled && health?.production_authorized
                ? "Операции активни"
                : "Операции неактивни"
            }}</span
          ><button
            class="icon"
            aria-label="Обнови"
            :disabled="busy"
            @click="refresh"
          >
            <RefreshCw :size="17" /></button
          ><button class="icon" aria-label="Изход" @click="logout">
            <LogOut :size="17" />
          </button>
        </div>
      </header>
      <main>
        <div class="page-heading">
          <div>
            <div class="eyebrow">VIMAG / МЕДИЙНИ ОПЕРАЦИИ</div>
            <h1>{{ title }}</h1>
            <p class="muted">
              {{
                route === "dashboard"
                  ? "Импорт, безопасно преместване и проверено публикуване."
                  : "Данни и доказателства от устойчивия журнал."
              }}
            </p>
          </div>
        </div>
        <p v-if="error" role="alert" class="warning">{{ error }}</p>
        <p v-if="notice" role="status" class="notice">{{ notice }}</p>
        <template v-if="route === 'dashboard'">
          <div class="kpis">
            <button
              v-for="k in [
                { label: 'Всички задачи', count: total, state: '' },
                {
                  label: 'Изчакващи',
                  count: counts.Queued ?? 0,
                  state: 'Queued',
                },
                {
                  label: 'За преглед',
                  count: counts.NeedsReview ?? 0,
                  state: 'NeedsReview',
                },
                {
                  label: 'Завършени',
                  count:
                    (counts.Completed ?? 0) +
                    (counts.CompletedWithWarnings ?? 0),
                  state: 'Completed',
                },
              ]"
              :key="k.label"
              class="panel kpi"
              @click="
                state = k.state;
                navigate('jobs');
              "
            >
              <span class="muted">{{ k.label }}</span
              ><strong>{{ k.count }}</strong
              ><span class="tiny"
                >Устойчиво състояние на задачите <ArrowUpRight :size="13"
              /></span>
            </button>
          </div>
          <div class="split">
            <section class="panel feature">
              <div class="eyebrow">ТЕКУЩО СЪСТОЯНИЕ</div>
              <h2>{{ health?.worker.state ?? "Изчаква Worker" }}</h2>
              <p class="muted">
                Преместване, integrity, mapping и seeding се проверяват
                независимо.
              </p>
              <div class="row">
                <span class="badge success">Защита на BG аудио</span
                ><span class="badge">Без автоматично изтриване</span>
              </div>
            </section>
            <section class="panel pad">
              <h2>Инфраструктура</h2>
              <dl>
                <dt>PostgreSQL</dt>
                <dd>{{ health?.database ? "Достъпен" : "Непроверен" }}</dd>
                <dt>Worker heartbeat</dt>
                <dd>
                  {{
                    typeof health?.worker.time === "string"
                      ? formatDate(health.worker.time)
                      : "Няма данни"
                  }}
                </dd>
                <dt>qBittorrent</dt>
                <dd>{{ health?.worker.qbt ?? "Непроверен" }}</dd>
                <dt>NAS</dt>
                <dd>
                  {{ health?.worker.nas ? "Проверен mount" : "Непроверен" }}
                </dd>
              </dl>
            </section>
          </div>
        </template>
        <section v-if="route === 'dashboard' || route === 'jobs'" class="panel">
          <div class="panel-head">
            <h2>Задачи за импорт</h2>
            <span class="badge">{{ jobs.length }} показани</span>
          </div>
          <form
            class="filters"
            @submit.prevent="
              offset = 0;
              refresh();
            "
          >
            <Search :size="16" /><input
              v-model="search"
              aria-label="Търси задачи"
              placeholder="Заглавие…"
            /><select
              v-model="category"
              aria-label="Категория"
              @change="
                offset = 0;
                refresh();
              "
            >
              <option value="">Всички категории</option>
              <option v-for="(name, key) in categories" :key="key" :value="key">
                {{ name }}
              </option></select
            ><select
              v-model="state"
              aria-label="Статус"
              @change="
                offset = 0;
                refresh();
              "
            >
              <option value="">Всички състояния</option>
              <option
                v-for="s in [
                  'Queued',
                  'Inspecting',
                  'NeedsReview',
                  'AwaitingApproval',
                  'Moving',
                  'PublishPending',
                  'RecoveryRequired',
                  'Completed',
                  'CompletedWithWarnings',
                ]"
                :key="s"
              >
                {{ s }}
              </option></select
            ><button>Търси</button>
          </form>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Заглавие / задача</th>
                  <th>Категория</th>
                  <th>Стъпка</th>
                  <th>Статус</th>
                  <th>Обхват</th>
                  <th>Създадена</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="job in jobs" :key="job.id">
                  <td>
                    <strong>{{ label(job) }}</strong
                    ><small class="mono">{{ job.id.slice(0, 8) }}</small>
                  </td>
                  <td>{{ job.snapshot?.category }}</td>
                  <td>{{ job.step }} / 7 · {{ steps[job.step - 1] }}</td>
                  <td>
                    <span class="badge" :class="statusClass(job.state)">{{
                      job.state
                    }}</span>
                  </td>
                  <td>{{ job.scope }}</td>
                  <td>{{ formatDate(job.created_at) }}</td>
                  <td>
                    <button @click="navigate('job/' + job.id)">
                      Преглед <ArrowUpRight :size="13" />
                    </button>
                  </td>
                </tr>
                <tr v-if="!jobs.length">
                  <td colspan="7" class="empty">
                    Няма задачи, съответстващи на филтрите. Новите допустими
                    torrents се откриват от Worker.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="panel-foot">
            <button
              :disabled="offset === 0"
              @click="
                offset = Math.max(0, offset - 50);
                refresh();
              "
            >
              Назад</button
            ><span
              >{{ jobs.length ? offset + 1 : 0 }}–{{
                offset + jobs.length
              }}</span
            ><button
              :disabled="jobs.length < 50"
              @click="
                offset += 50;
                refresh();
              "
            >
              Напред
            </button>
          </div>
        </section>
        <template v-if="route.startsWith('job/') && selected">
          <div class="row controls">
            <span class="badge" :class="statusClass(selected.state)">{{
              selected.state
            }}</span
            ><span class="mono muted">{{ selected.id }}</span
            ><button :disabled="busy" @click="control('pause')">Пауза</button
            ><button :disabled="busy" @click="control('resume')">
              Продължи</button
            ><button :disabled="busy" @click="control('retry')">
              Провери и повтори
            </button>
          </div>
          <div class="steps">
            <button
              v-for="(s, i) in steps"
              :key="s"
              :class="{
                current: selected.step === i + 1,
                done: selected.step > i + 1,
              }"
              @click="activeStep = i + 1"
            >
              <small>СТЪПКА 0{{ i + 1 }}</small
              ><strong>{{ s }}</strong
              ><span>{{
                selected.step > i + 1
                  ? "Проверена"
                  : selected.step === i + 1
                    ? selected.state
                    : "Предстои"
              }}</span>
            </button>
          </div>
          <div class="tabs">
            <button
              v-for="t in [
                { id: 'overview', label: 'Обобщение' },
                { id: 'streams', label: 'Файлове и потоци' },
                { id: 'technical', label: 'План и операции' },
                { id: 'activity', label: 'История' },
              ]"
              :key="t.id"
              :class="{ active: tab === t.id }"
              @click="tab = t.id"
            >
              {{ t.label }}
            </button>
          </div>
          <div v-if="tab === 'overview' || tab === 'streams'" class="cards">
            <article
              v-for="item in selected.media_items"
              :key="item.id"
              class="panel pad"
            >
              <h2>{{ item.data.identity?.title ?? item.data.source_name }}</h2>
              <div class="row">
                <span class="badge">{{ item.data.bg }}</span
                ><span class="badge">{{ item.data.quality_label }}</span
                ><span class="badge">{{ item.data.subtitle }}</span>
              </div>
              <dl>
                <dt>Identity</dt>
                <dd>{{ item.data.identity ?? "Изисква преглед" }}</dd>
                <dt>NAS integrity</dt>
                <dd>{{ item.data.integrity ? "Проверена" : "Непроверена" }}</dd>
                <dt>Jellyfin</dt>
                <dd>
                  {{ item.data.published ? "Разпознат" : "Изчаква проверка" }}
                </dd>
                <dt>Оригинално име</dt>
                <dd>{{ item.data.source_name }}</dd>
              </dl>
              <details>
                <summary>Технически доказателства</summary>
                <pre>{{ JSON.stringify(item.data, null, 2) }}</pre>
              </details>
              <div
                v-for="stream in (item.data.stream_keys as {
                  index: number;
                  key: string;
                }[]) ?? []"
                :key="stream.key"
                class="row controls"
              >
                <span class="muted">Аудиопоток {{ stream.index }}</span
                ><button
                  :disabled="busy"
                  @click="verifyBg(item, stream.key, 'verify')"
                >
                  Потвърди BG</button
                ><button
                  :disabled="busy"
                  @click="verifyBg(item, stream.key, 'revoke')"
                >
                  Отмени BG доказателство
                </button>
              </div>
              <button class="primary" @click="editItem(item.id)">
                Преглед на идентификацията и версията
              </button>
            </article>
          </div>
          <section v-if="tab === 'technical'" class="panel pad">
            <article
              v-for="conflict in selected.data.sidecar_conflicts as Record<
                string,
                {
                  relative_path: string;
                  observed_sha256: string;
                  old_preview: string;
                  new_preview: string;
                }
              >"
              :key="conflict.relative_path"
              class="operation"
            >
              <h2>Sidecar конфликт · {{ conflict.relative_path }}</h2>
              <div class="compare-grid">
                <pre>{{ conflict.old_preview }}</pre>
                <pre>{{ conflict.new_preview }}</pre>
              </div>
              <label class="check"
                ><input v-model="approvalChecked" type="checkbox" />Одобрявам
                тази точна промяна с backup.</label
              ><button
                :disabled="busy || !approvalChecked"
                @click="approveSidecar(conflict)"
              >
                Одобри замяната на sidecar
              </button>
            </article>
            <h2>Неизменяем план · ревизия {{ plan?.revision ?? "—" }}</h2>
            <pre>{{
              JSON.stringify(
                plan?.data ?? { state: "Няма подготвен план" },
                null,
                2,
              )
            }}</pre>
            <p class="mono">{{ plan?.sha256 }}</p>
            <label class="check"
              ><input v-model="approvalChecked" type="checkbox" />Прегледах
              точните пътища, версия и зависимости.</label
            ><button
              class="primary"
              :disabled="!plan || !approvalChecked || busy"
              @click="approve"
            >
              Одобри тази ревизия
            </button>
            <article
              v-for="op in selected.operations"
              :key="op.id"
              class="operation"
            >
              <strong>{{ op.kind }}</strong
              ><span class="badge" :class="statusClass(op.status)">{{
                op.status
              }}</span>
              <pre>{{ JSON.stringify(op, null, 2) }}</pre>
            </article>
          </section>
          <section v-if="tab === 'activity'" class="panel pad">
            <h2>История на задачата</h2>
            <div
              v-for="event in selected.timeline"
              :key="event.id"
              class="timeline-item"
            >
              <strong>{{ event.kind }}</strong
              ><small
                >{{ formatDate(event.created_at) }} · {{ event.actor }}</small
              >
            </div>
            <p v-if="!selected.timeline?.length" class="empty">
              Няма записани събития.
            </p>
          </section>
        </template>
        <LibraryOperations v-if="route === 'library'" />
        <template v-if="route === 'comparison'"
          ><div class="notice">
            <ShieldCheck :size="18" />Българският дублаж се пази. Препоръката не
            разрешава изтриване или quarantine.
          </div>
          <article
            v-for="decision in decisions"
            :key="decision.id"
            class="panel pad"
          >
            <h2>{{ decision.data.decision }}</h2>
            <div class="row">
              <span
                v-for="reason in decision.data.reason_codes as string[]"
                :key="reason"
                class="badge"
                >{{ reason }}</span
              >
            </div>
            <div class="compare-grid">
              <section
                v-for="(name, index) in ['Съществуваща версия', 'Нова версия']"
                :key="name"
              >
                <h3>{{ name }}</h3>
                <dl>
                  <template
                    v-for="(value, factor) in decision.data.factors as Record<
                      string,
                      unknown[]
                    >"
                    :key="factor"
                    ><dt>{{ factor }}</dt>
                    <dd>
                      {{ value[index] ?? "Няма доказателства" }}
                    </dd></template
                  >
                </dl>
              </section>
            </div>
            <p class="muted">
              Решението се записва в прегледа на съответната задача.
            </p>
          </article>
          <p v-if="!decisions.length" class="panel empty">
            Няма потвърдени сравнения на версии.
          </p></template
        >
        <template v-if="route === 'queue'"
          ><div class="notice">
            Прогресът е неизвестен, когато qBt предоставя само moving state.
            Requested ≠ Verified.
          </div>
          <article v-for="op in operations" :key="op.id" class="panel pad">
            <div class="row">
              <h2>{{ op.kind }}</h2>
              <span class="badge" :class="statusClass(op.status)">{{
                op.status
              }}</span
              ><button v-if="op.job_id" @click="navigate('job/' + op.job_id)">
                Задача <ArrowUpRight :size="14" />
              </button>
            </div>
            <div class="compare-grid">
              <div>
                <h3>Заявено</h3>
                <pre>{{ JSON.stringify(op.intent, null, 2) }}</pre>
              </div>
              <div>
                <h3>Наблюдавано / проверено</h3>
                <pre>{{
                  JSON.stringify(
                    op.observed ?? { state: "Няма потвърждение" },
                    null,
                    2,
                  )
                }}</pre>
              </div>
            </div>
          </article>
          <p v-if="!operations.length" class="panel empty">
            Няма файлови или torrent операции в журнала.
          </p></template
        >
        <template v-if="route === 'subtitles'"
          ><div class="notice">
            Съответствието с edition и времето се проверява преди използване.
            Оригиналните субтитри се пазят.
          </div>
          <article v-for="sub in subtitles" :key="sub.id" class="panel pad">
            <div class="row">
              <h2>
                {{
                  sub.data.provider ?? sub.data.source ?? "Резултат от търсене"
                }}
              </h2>
              <span
                class="badge"
                :class="statusClass(String(sub.data.status))"
                >{{ sub.data.status }}</span
              >
            </div>
            <pre>{{ JSON.stringify(sub.data, null, 2) }}</pre>
            <p class="muted">
              Точният видео fingerprint и timing evidence са задължителни.
            </p>
            <button
              v-if="sub.item_id && sub.context?.identity"
              :disabled="busy"
              @click="openSubtitle(sub)"
            >
              Избери / провери SRT и timing
            </button>
            <button
              v-if="sub.data.provider === 'OpenSubtitles' && !sub.data.content"
              :disabled="busy"
              @click="downloadSubtitle(sub)"
            >
              Изтегли кандидат за проверка
            </button>
          </article>
          <p v-if="!subtitles.length" class="panel empty">
            Няма кандидати за субтитри. Те се търсят след безопасното
            преместване.
          </p></template
        >
        <template v-if="route === 'settings'"
          ><div class="settings-layout">
            <nav class="panel settings-nav" aria-label="Раздели настройки">
              <button
                v-for="s in [
                  { id: 'connections', label: 'Връзки' },
                  { id: 'storage', label: 'Хранилище' },
                  { id: 'naming', label: 'Имена и категории' },
                  { id: 'quality', label: 'Качество и езици' },
                  { id: 'automation', label: 'Автоматизация' },
                  { id: 'system', label: 'Система и recovery' },
                ]"
                :key="s.id"
                :class="{ active: settingsTab === s.id }"
                @click="settingsTab = s.id"
              >
                {{ s.label }}
              </button>
            </nav>
            <section class="panel pad">
              <template v-if="settingsTab === 'connections'"
                ><h2>Връзки и здраве</h2>
                <dl>
                  <dt>PostgreSQL</dt>
                  <dd>{{ health?.database ? "Готов" : "Непроверен" }}</dd>
                  <dt>Worker</dt>
                  <dd>{{ health?.worker.state ?? "Неизвестно" }}</dd>
                  <dt>qBt</dt>
                  <dd>{{ health?.worker.qbt ?? "Непроверен" }}</dd>
                  <dt>Jellyfin</dt>
                  <dd>{{ health?.worker.jellyfin ?? "Непроверен" }}</dd>
                  <dt>Worker heartbeat (секунди)</dt>
                  <dd>
                    {{ health?.worker.heartbeat_age_seconds ?? "Непроверен" }}
                  </dd>
                  <dt>Последна грешка</dt>
                  <dd>{{ health?.worker.error_code ?? "Няма" }}</dd>
                </dl>
                <button @click="refresh">Провери състоянието</button>
                <p class="muted">
                  Ключовете се предоставят като Worker secret файлове.
                </p></template
              >
              <LibraryOrganization v-else-if="settingsTab === 'naming'" />
              <template v-else-if="settingsTab === 'quality'"
                ><h2>Bulgarian-first</h2>
                <ul>
                  <li>Пази открития BG дублаж.</li>
                  <li>
                    Съществено по-добро non-BG видео: Keep Both след
                    доказателства.
                  </li>
                  <li>
                    Resolution и размер сами по себе си не доказват качество.
                  </li>
                  <li>Различните editions остават отделни версии.</li>
                  <li>
                    Физическо изтриване само с отделен потвърден план и
                    dependency проверки.
                  </li>
                </ul></template
              ><template v-else-if="settingsTab === 'system'"
                ><h2>Диагностика и audit</h2>
                <pre>{{ JSON.stringify(health, null, 2) }}</pre>
                <div
                  v-for="event in audit"
                  :key="event.id"
                  class="timeline-item"
                >
                  <strong>{{ event.kind }}</strong
                  ><small>{{ formatDate(event.created_at) }}</small>
                </div></template
              >
              <form v-else @submit.prevent="saveSettings">
                <h2>
                  {{
                    settingsTab === "storage" ? "Хранилище" : "Автоматизация"
                  }}
                </h2>
                <label
                  >Polling интервал (секунди)<input
                    v-model.number="pollSeconds"
                    type="number"
                    min="15"
                    max="300" /></label
                ><label
                  >Безопасни retry опити<input
                    v-model.number="retries"
                    type="number"
                    min="1"
                    max="5" /></label
                ><label
                  >Минимален NAS резерв (GiB)<input
                    v-model.number="minFree"
                    type="number"
                    min="10"
                    max="10000" /></label
                ><button class="primary" :disabled="busy">
                  Запази настройките
                </button>
                <details>
                  <summary>Текущи записани стойности</summary>
                  <pre>{{ JSON.stringify(settingSections, null, 2) }}</pre>
                </details>
              </form>
            </section>
          </div></template
        >
      </main>
    </div>
    <div v-if="subtitleReview" class="modal-backdrop">
      <form
        class="modal panel"
        role="dialog"
        aria-modal="true"
        aria-label="Проверка на субтитри"
        @submit.prevent="attachSubtitle"
      >
        <h2>
          Проверка на субтитри · {{ subtitleReview.context?.identity?.title }}
        </h2>
        <p class="mono">{{ subtitleReview.context?.fingerprint }}</p>
        <label
          >Оригинално SRT съдържание<textarea
            v-model="subtitleText"
            required
            maxlength="1048576"
            rows="12"
          />
        </label>
        <div class="form-grid">
          <label
            >Offset (s)<input
              v-model.number="subtitleOffset"
              type="number"
              min="-300"
              max="300"
              step="0.01" /></label
          ><label
            >Timing scale<input
              v-model.number="subtitleScale"
              type="number"
              min="0.9"
              max="1.1"
              step="0.0001"
          /></label>
        </div>
        <button
          type="button"
          :disabled="busy || !subtitleText"
          @click="syncSubtitle"
        >
          Създай sync предложение</button
        ><label class="check"
          ><input v-model="subtitleConfirmed" type="checkbox" />Проверих точния
          edition и timing спрямо това видео.</label
        >
        <p v-if="error" role="alert" class="warning">{{ error }}</p>
        <div class="row">
          <button type="button" @click="subtitleReview = undefined">
            Отказ</button
          ><button class="primary" :disabled="busy || !subtitleConfirmed">
            Запиши проверения кандидат
          </button>
        </div>
      </form>
    </div>
    <div
      v-if="reviewItem"
      class="modal-backdrop"
      @keydown.esc="reviewItem = ''"
    >
      <form
        class="modal panel"
        role="dialog"
        aria-modal="true"
        aria-label="Преглед на медия"
        @submit.prevent="saveReview"
      >
        <h2>Потвърди съдържанието</h2>
        <div class="form-grid">
          <label
            >Канонично заглавие<input v-model="reviewTitle" required /></label
          ><label
            >Година<input
              v-model.number="reviewYear"
              type="number"
              min="1880"
              max="2200"
              required /></label
          ><label
            >Тип<select v-model="reviewType">
              <option value="movie">Филм</option>
              <option value="show">Сериал</option>
              <option value="concert">Концерт</option>
            </select></label
          ><label
            >TMDb ID (може да липсва)<input
              v-model="reviewProvider"
              pattern="[0-9]*" /></label
          ><label>Edition<input v-model="reviewEdition" required /></label
          ><label v-if="reviewType === 'concert'"
            >Изпълнител<input v-model="reviewArtist" required /></label
          ><template v-if="reviewType === 'show'"
            ><label
              >Сезон<input
                v-model.number="reviewSeason"
                type="number"
                min="0"
                required /></label
            ><label
              >Епизоди (1,2)<input
                v-model="reviewEpisodes"
                required /></label></template
          ><label
            >Решение<select v-model="reviewDecision">
              <option>KeepBoth</option>
              <option>KeepBGPreferred</option>
              <option>PreferBetterBG</option>
              <option>NeedsReview</option>
              <option>Skip</option>
            </select></label
          >
        </div>
        <label class="check"
          ><input v-model="materialImprovement" type="checkbox" />Проверих
          съществено подобрение на качеството; описах доказателствата
          по-долу.</label
        >
        <label
          >Доказателства и причина<textarea
            v-model="reviewReason"
            required
            minlength="1"
            maxlength="1000"
          />
        </label>
        <p v-if="error" role="alert" class="warning">{{ error }}</p>
        <div class="row">
          <button type="button" @click="reviewItem = ''">Отказ</button
          ><button class="primary" :disabled="busy">
            Запиши и създай нов план
          </button>
        </div>
      </form>
    </div>
    <div v-if="pendingQuarantine" class="modal-backdrop">
      <section
        class="modal panel"
        role="dialog"
        aria-modal="true"
        aria-label="Quarantine approval"
      >
        <h2>
          {{
            pendingQuarantine.data.action === "NORMALIZE"
              ? "План за нормализация"
              : "Обратима карантина"
          }}
        </h2>
        <pre>{{ JSON.stringify(pendingQuarantine.data, null, 2) }}</pre>
        <p class="warning">
          Approval не отменя проверката за активни torrent зависимости.
        </p>
        <label class="check"
          ><input v-model="approvalChecked" type="checkbox" />Одобрявам точния
          план и fingerprint.</label
        >
        <div class="row">
          <button @click="pendingQuarantine = undefined">Отказ</button
          ><button
            class="primary"
            :disabled="!approvalChecked || busy"
            @click="approveQuarantine"
          >
            Одобри
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
