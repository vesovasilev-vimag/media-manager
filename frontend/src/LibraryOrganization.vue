<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { api } from "./api";
type Rule = { folders: string[]; filename: string[]; subtitle: string[] };
interface Policy {
  schema: number;
  collections: boolean;
  categories: Record<string, { root: string; routes: Record<string, Rule> }>;
}
const policy = ref<Policy>(),
  saved = ref<Policy>(),
  revision = ref(0),
  category = ref("movies"),
  mediaType = ref("movie"),
  tab = ref("structure"),
  target = ref<"filename" | "subtitle">("filename"),
  error = ref(""),
  notice = ref(""),
  busy = ref(false),
  preview = ref<{ path: string; subtitle: string }>(),
  literal = ref(" - ");
const names: Record<string, string> = {
  movies: "Филми",
  series: "Сериали",
  animations: "Анимации",
  documentaries: "Документални",
  concerts: "Концерти",
};
const tokens = [
  "{Title}",
  "{Year}",
  "{SeriesTitle}",
  "{Season:02}",
  "{Episode:02}",
  "{EpisodeTitle}",
  "{Resolution}",
  "{BG}",
  "{Edition}",
  "{VideoCodec}",
  "{AudioCodec}",
  "{Artist}",
  "{Event}",
  "{CollectionName}",
  "{VideoBase}",
  "{SubtitleLang}",
];
const rule = computed(
  () => policy.value?.categories[category.value]?.routes[mediaType.value],
);
const dirty = computed(
  () => JSON.stringify(policy.value) !== JSON.stringify(saved.value),
);
const sample = ref({
  title: "Sample Title",
  year: 2026,
  artist: "Sample Artist",
  edition: "Theatrical",
  season: 1,
  episode: 1,
  collection_override: "",
});
let drag:
    | { kind: "folder" | "token" | "palette"; index?: number; value?: string }
    | undefined,
  previewSequence = 0;
async function livePreview() {
  if (!policy.value) return;
  const seq = ++previewSequence;
  try {
    const result = await api<{ path: string; subtitle: string }>(
      "/library/policies/preview",
      "POST",
      {
        policy: policy.value,
        category: category.value,
        identity: {
          ...sample.value,
          media_type: mediaType.value,
          confirmed: true,
          title_language: "en-US",
          english_title_verified: true,
          collection_override_language: "en-US",
          episode_title: "Sample Episode",
          episode_title_language: "en-US",
          episodes: [sample.value.episode],
        },
        data: { bg: "BG_TAGGED", quality_label: "1080p" },
        path: "preview.mkv",
      },
    );
    if (seq === previewSequence) {
      preview.value = result;
      error.value = "";
    }
  } catch (e) {
    if (seq === previewSequence) {
      error.value = String(e);
      preview.value = undefined;
    }
  }
}
function move(items: string[], from: number, to: number) {
  if (to < 0 || to >= items.length) return;
  items.splice(to, 0, items.splice(from, 1)[0]);
}
function drop(kind: "folder" | "token", to: number) {
  if (!rule.value || !drag) return;
  const list =
    kind === "folder" ? rule.value.folders : rule.value[target.value];
  if (drag.kind === "palette" && kind === "token")
    list.splice(to, 0, drag.value!);
  else if (drag.kind === kind)
    move(list, drag.index!, Math.min(to, list.length - 1));
  drag = undefined;
}
function chooseCategory() {
  mediaType.value = Object.keys(
    policy.value!.categories[category.value].routes,
  )[0];
}
async function save() {
  if (!policy.value) return;
  busy.value = true;
  try {
    const result = await api<{ revision: number }>(
      "/library/policies",
      "POST",
      { expected_revision: revision.value, policy: policy.value },
    );
    revision.value = result.revision;
    saved.value = JSON.parse(JSON.stringify(policy.value));
    notice.value = `Записана политика v${revision.value}. Файлови операции: 0.`;
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}
watch([policy, category, mediaType, sample], () => void livePreview(), {
  deep: true,
});
onMounted(async () => {
  try {
    const result = await api<{ active: { revision: number; data: Policy } }>(
      "/library/policies",
    );
    policy.value = result.active.data;
    saved.value = structuredClone(result.active.data);
    revision.value = result.active.revision;
  } catch (e) {
    error.value = String(e);
  }
});
</script>
<template>
  <section class="organization">
    <div class="row organization-head">
      <div>
        <h2>Организация на библиотеката</h2>
        <p class="muted">
          Нова версия на йерархията и имената. Прилагането е чрез отделно
          одобрена нормализация.
        </p>
      </div>
      <span class="badge">v{{ revision }} {{ dirty ? "· Чернова" : "" }}</span
      ><button
        class="primary"
        :disabled="busy || !dirty || !!error"
        @click="save"
      >
        Запази нова версия
      </button>
    </div>
    <p v-if="error" role="alert" class="warning">{{ error }}</p>
    <p v-if="notice" role="status" class="notice">{{ notice }}</p>
    <template v-if="policy && rule"
      ><div class="tabs">
        <button
          v-for="t in [
            { id: 'structure', name: 'Структура' },
            { id: 'naming', name: 'Naming Convention' },
            { id: 'versions', name: 'Преглед и версии' },
          ]"
          :key="t.id"
          :aria-pressed="tab === t.id"
          @click="tab = t.id"
        >
          {{ t.name }}
        </button>
      </div>
      <div class="organization-layout">
        <div class="panel pad editor">
          <div class="row">
            <label
              >Категория<select v-model="category" @change="chooseCategory">
                <option v-for="(name, key) in names" :key="key" :value="key">
                  {{ name }}
                </option>
              </select></label
            ><label
              >Тип<select v-model="mediaType">
                <option
                  v-for="t in Object.keys(policy.categories[category].routes)"
                  :key="t"
                >
                  {{ t }}
                </option>
              </select></label
            >
          </div>
          <template v-if="tab === 'structure'"
            ><h3>Library /</h3>
            <label
              >Корен на категорията<input
                v-model="policy.categories[category].root"
            /></label>
            <div class="tree">
              <div
                v-for="(folder, i) in rule.folders"
                :key="i"
                class="tree-node"
                draggable="true"
                :style="{ marginLeft: Math.min(i, 4) * 12 + 'px' }"
                @dragstart="drag = { kind: 'folder', index: i }"
                @dragover.prevent
                @drop.prevent="drop('folder', i)"
              >
                <span aria-hidden="true">⋮⋮ ▰</span
                ><input
                  v-model="rule.folders[i]"
                  :aria-label="'Директория ниво ' + (i + 1)"
                /><button
                  :disabled="i === 0"
                  :aria-label="'Премести ниво ' + (i + 1) + ' нагоре'"
                  @click="move(rule.folders, i, i - 1)"
                >
                  ↑</button
                ><button
                  :disabled="i === rule.folders.length - 1"
                  :aria-label="'Премести ниво ' + (i + 1) + ' надолу'"
                  @click="move(rule.folders, i, i + 1)"
                >
                  ↓</button
                ><button
                  :aria-label="'Премахни ниво ' + (i + 1)"
                  @click="rule.folders.splice(i, 1)"
                >
                  ×
                </button>
              </div>
            </div>
            <button @click="rule.folders.push('Нова папка')">
              ＋ Добави ниво</button
            ><label class="check"
              ><input v-model="policy.collections" type="checkbox" />TMDb
              колекции · условно ниво {CollectionName}</label
            >
            <p class="muted">
              Липсваща колекция пропуска нивото. Идентификаторите на петте
              qBittorrent категории остават постоянни.
            </p></template
          >
          <template v-if="tab === 'naming'"
            ><div class="row">
              <button
                :aria-pressed="target === 'filename'"
                @click="target = 'filename'"
              >
                Видео файл</button
              ><button
                :aria-pressed="target === 'subtitle'"
                @click="target = 'subtitle'"
              >
                Субтитри
              </button>
            </div>
            <h3>Атрибути</h3>
            <div class="palette">
              <button
                v-for="token in tokens"
                :key="token"
                draggable="true"
                @dragstart="drag = { kind: 'palette', value: token }"
                @click="rule[target].push(token)"
              >
                {{ token }}
              </button>
            </div>
            <h3>Текуща конвенция</h3>
            <div
              class="token-zone"
              aria-label="Naming tokens"
              @dragover.prevent
              @drop.self.prevent="drop('token', rule[target].length)"
            >
              <div
                v-for="(token, i) in rule[target]"
                :key="i"
                class="token"
                draggable="true"
                @dragstart.stop="drag = { kind: 'token', index: i }"
                @dragover.prevent
                @drop.stop.prevent="drop('token', i)"
              >
                <span>{{ token }}</span
                ><button
                  :aria-label="'Атрибут ' + (i + 1) + ' наляво'"
                  :disabled="i === 0"
                  @click="move(rule[target], i, i - 1)"
                >
                  ←</button
                ><button
                  :aria-label="'Атрибут ' + (i + 1) + ' надясно'"
                  :disabled="i === rule[target].length - 1"
                  @click="move(rule[target], i, i + 1)"
                >
                  →</button
                ><button
                  :aria-label="'Премахни атрибут ' + (i + 1)"
                  @click="rule[target].splice(i, 1)"
                >
                  ×
                </button>
              </div>
            </div>
            <div class="row">
              <input
                v-model="literal"
                aria-label="Текст или разделител"
                maxlength="40"
              /><button @click="rule[target].push(literal)">
                Добави текст
              </button>
            </div></template
          >
          <template v-if="tab === 'versions'"
            ><p>
              Текуща v{{ revision }} →
              {{ dirty ? "Нова версия" : "Без промени" }}
            </p>
            <div v-for="(conf, cat) in policy.categories" :key="cat">
              <h3>{{ names[cat] }}</h3>
              <p v-for="(r, t) in conf.routes" :key="t" class="path-preview">
                {{ conf.root }} / {{ r.folders.join(" / ") }} /
                {{ r.filename.join("") }}
              </p>
            </div>
            <button @click="policy = JSON.parse(JSON.stringify(saved))">
              Върни запазената версия
            </button></template
          >
        </div>
        <aside class="panel pad preview">
          <h3>Жив преглед · примерни метаданни</h3>
          <label>Заглавие<input v-model="sample.title" /></label
          ><label
            >Година<input v-model.number="sample.year" type="number" /></label
          ><label
            >Ръчна колекция<input
              v-model="sample.collection_override"
              placeholder="Пропусни при липса"
          /></label>
          <div v-if="mediaType === 'show'" class="row">
            <label
              >Сезон<input
                v-model.number="sample.season"
                type="number" /></label
            ><label
              >Епизод<input v-model.number="sample.episode" type="number"
            /></label>
          </div>
          <label v-if="mediaType === 'concert'"
            >Артист<input v-model="sample.artist"
          /></label>
          <p class="path-preview">
            {{ preview?.path ?? "Невалиден или непълен шаблон" }}
          </p>
          <p class="path-preview">{{ preview?.subtitle }}</p>
          <p class="notice">
            Записването създава неизменяема версия. Промени по NAS: 0.
          </p>
        </aside>
      </div>
    </template>
  </section>
</template>
<style scoped>
.organization-head {
  justify-content: space-between;
  flex-wrap: wrap;
}
.organization-head p {
  font-size: 12px;
}
.organization h2 {
  font-size: 18px;
}
.organization h3 {
  font-size: 13px;
}
.organization-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(270px, 1fr);
  gap: 16px;
}
.organization label {
  display: block;
  font-size: 11px;
  margin: 12px 0;
}
.organization label input,
.organization label select {
  width: 100%;
  margin-top: 7px;
}
.organization label.check {
  display: flex;
}
.organization label.check input {
  width: auto;
}
.organization .row {
  flex-wrap: wrap;
}
.editor {
  min-width: 0;
}
.tree {
  border-left: 1px dashed #395a5b;
  padding-left: 12px;
  margin: 16px 0;
}
.tree-node {
  display: flex;
  gap: 5px;
  background: #17303a;
  border: 1px solid #32515b;
  border-radius: 9px;
  padding: 8px;
  margin-bottom: 10px;
  align-items: center;
}
.tree-node input {
  min-width: 50px;
  width: 100%;
}
.tree-node button {
  padding: 5px 8px;
}
.palette,
.token-zone {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.palette button,
.token {
  font-size: 11px;
  background: #1b3844;
  color: #b8dde8;
  border: 1px solid #406577;
  border-radius: 8px;
  padding: 8px;
  cursor: grab;
}
.token {
  display: flex;
  align-items: center;
  gap: 3px;
}
.token button {
  font-size: 10px;
  padding: 2px 5px;
}
.token-zone {
  padding: 12px;
  border: 1px dashed #47736d;
  border-radius: 10px;
  min-height: 80px;
  margin: 12px 0;
}
.path-preview {
  font:
    12px/1.7 Consolas,
    monospace;
  color: #a4ffe2;
  background: #0c1b23;
  padding: 12px;
  border: 1px solid #2b4a51;
  border-radius: 8px;
  overflow-wrap: anywhere;
}
.preview {
  align-self: start;
}
.tabs {
  display: flex;
  gap: 8px;
  margin: 18px 0;
  flex-wrap: wrap;
}
@media (max-width: 1000px) {
  .organization-layout {
    grid-template-columns: 1fr;
  }
}
</style>
