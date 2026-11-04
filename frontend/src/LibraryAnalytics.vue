<script setup lang="ts">
import { computed, useId } from "vue";
import { libraryAnalytics, type CategoryAnalytics } from "./libraryAnalytics";

const props = defineProps<{
  categories: CategoryAnalytics[];
  loading: boolean;
  error: string;
}>();
const id = useId();
const model = computed(() => {
  try {
    return libraryAnalytics(props.categories);
  } catch {
    return null;
  }
});
const unavailable = computed(
  () => !model.value || (!!props.error && !props.categories.length),
);
const circumference = 2 * Math.PI * 68;
const totalSize = computed(() => {
  const label = model.value?.sizeLabel ?? "";
  const split = label.lastIndexOf(" ");
  return {
    value: split > 0 ? label.slice(0, split) : label,
    unit: split > 0 ? label.slice(split + 1) : "",
  };
});
function description(row: NonNullable<typeof model.value>["rows"][number]) {
  return `${row.label}: ${row.count.toLocaleString("bg-BG")} видеофайла · ${row.sizeLabel}${row.unknown ? ` · ${row.unknown} с неизвестен размер` : ""}`;
}
</script>
<template>
  <div class="library-analytics" :aria-busy="loading">
    <p v-if="error || !model" role="alert" class="analytics-message warning">
      {{ error || "Данните за библиотеката не могат да бъдат визуализирани." }}
      <span v-if="categories.length && model"
        >Показани са последните успешно заредени данни.</span
      >
    </p>
    <p v-if="loading" role="status" class="analytics-message">
      Зареждане на статистиката…
    </p>
    <p
      v-else-if="!unavailable && model?.count === 0"
      role="status"
      class="analytics-message"
    >
      Няма видеофайлове в библиотеката. Стартирайте обследване, за да обновите
      каталога.
    </p>
    <p
      v-if="!loading && !unavailable && model?.unknown"
      class="analytics-message size-note"
      role="note"
    >
      Обемът включва само известните размери.
      {{ model.unknown.toLocaleString("bg-BG") }} файла с неизвестен размер не
      са включени.
    </p>
    <div class="overview-grid">
      <section class="analytics-panel" :aria-labelledby="`${id}-distribution`">
        <h2 :id="`${id}-distribution`">
          <span class="heading-symbol" aria-hidden="true">◔</span> РАЗПРЕДЕЛЕНИЕ
          ПО КАТЕГОРИИ
        </h2>
        <div
          v-if="loading || unavailable"
          class="chart-placeholder"
          :class="{ skeleton: loading }"
          aria-hidden="true"
        >
          <span>{{ loading ? "—" : "Няма достъпни данни" }}</span>
        </div>
        <div v-else-if="model" class="distribution-body">
          <svg
            class="category-donut"
            viewBox="0 0 240 240"
            role="img"
            :aria-label="`Разпределение на ${model.count.toLocaleString('bg-BG')} видеофайла по категории. ${model.slices.map((slice) => `${slice.label}: ${slice.percentage}`).join('; ')}`"
          >
            <circle
              cx="120"
              cy="120"
              r="68"
              fill="none"
              stroke="#203740"
              stroke-width="22"
            />
            <circle
              v-for="slice in model.slices"
              :key="slice.category"
              class="donut-segment"
              :data-category="slice.category"
              :data-count="slice.count"
              cx="120"
              cy="120"
              r="68"
              fill="none"
              :stroke="slice.color"
              stroke-width="22"
              :stroke-dasharray="`${slice.share * circumference} ${circumference}`"
              :stroke-dashoffset="-slice.offset * circumference"
              transform="rotate(-90 120 120)"
            >
              <title>{{ description(slice) }} · {{ slice.percentage }}</title>
            </circle>
            <g
              v-for="slice in model.slices"
              :key="`label-${slice.category}`"
              class="donut-label"
            >
              <polyline
                :points="`${slice.x},${slice.arcY} ${slice.right ? 201 : 39},${slice.y} ${slice.right ? 200 : 40},${slice.y}`"
                fill="none"
                :stroke="slice.color"
                stroke-width="1"
                opacity=".65"
              />
              <text
                :x="slice.right ? 233 : 7"
                :y="slice.y + 3"
                :text-anchor="slice.right ? 'end' : 'start'"
              >
                {{ slice.percentage }}
              </text>
            </g>
            <text
              class="donut-total"
              :style="{
                fontSize: `${Math.max(17, 30 - Math.max(0, model.count.toLocaleString('bg-BG').length - 5) * 2)}px`,
              }"
              x="120"
              y="120"
              text-anchor="middle"
            >
              {{ model.count.toLocaleString("bg-BG") }}
            </text>
            <text class="donut-caption" x="120" y="141" text-anchor="middle">
              ВИДЕОФАЙЛА
            </text>
          </svg>
          <table class="category-statistics">
            <caption class="visually-hidden">
              Категории, брой видеофайлове и известен обем
            </caption>
            <thead>
              <tr>
                <th scope="col">Категория</th>
                <th scope="col">Брой файлове</th>
                <th scope="col">Обем</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in model.rows"
                :key="row.category"
                :data-category="row.category"
              >
                <th scope="row">
                  <span
                    class="category-swatch"
                    :style="{ backgroundColor: row.color }"
                    aria-hidden="true"
                  />{{ row.label }}
                </th>
                <td class="category-count">
                  {{ row.count.toLocaleString("bg-BG") }}
                </td>
                <td class="category-size" :title="description(row)">
                  {{ row.sizeLabel
                  }}<span
                    v-if="row.unknown && row.unknown < row.count"
                    class="partial-mark"
                    aria-label="Непълен обем"
                    >*</span
                  >
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Общо</th>
                <td class="total-count">
                  {{ model.count.toLocaleString("bg-BG") }}
                </td>
                <td class="total-size">{{ model.sizeLabel }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
      <section
        class="analytics-panel storage-panel"
        :aria-labelledby="`${id}-storage`"
      >
        <h2 :id="`${id}-storage`">
          <span class="heading-symbol" aria-hidden="true">▥</span> ОБЕМ ПО
          КАТЕГОРИИ
        </h2>
        <div
          v-if="loading || unavailable"
          class="chart-placeholder"
          :class="{ skeleton: loading }"
          aria-hidden="true"
        >
          <span>{{ loading ? "—" : "Няма достъпни данни" }}</span>
        </div>
        <div v-else-if="model" class="storage-body">
          <div
            class="storage-chart"
            role="group"
            aria-label="Известен обем по категории, подреден низходящо"
          >
            <div
              v-for="row in model.ordered"
              :key="row.category"
              class="storage-row"
              role="img"
              :data-category="row.category"
              :data-bytes="row.bytes"
              :aria-label="description(row)"
            >
              <span class="storage-label">{{ row.label }}</span>
              <div class="bar-track" :title="description(row)">
                <div
                  class="storage-bar"
                  :style="{
                    width: `${(row.bytes / model.axisMax) * 100}%`,
                    backgroundColor: row.color,
                  }"
                />
              </div>
              <span class="storage-value"
                >{{ row.sizeLabel
                }}<span v-if="row.unknown && row.unknown < row.count"
                  >*</span
                ></span
              >
            </div>
            <div class="axis-row" aria-hidden="true">
              <div class="axis-ticks">
                <span
                  v-for="(tick, index) in model.ticks"
                  :key="index"
                  :style="{ left: `${tick.position}%` }"
                  >{{ tick.label }}</span
                >
              </div>
            </div>
            <p class="axis-caption">Обем ({{ model.unitLabel }})</p>
          </div>
          <div
            class="storage-kpi"
            role="group"
            aria-label="Общ обем на видеофайловете"
          >
            <span class="kpi-label">ОБЩ ОБЕМ</span
            ><strong class="kpi-value" :class="{ unknown: !totalSize.unit }"
              ><span>{{ totalSize.value }}</span
              ><span v-if="totalSize.unit" class="kpi-unit">{{
                " " + totalSize.unit
              }}</span></strong
            >
            <span class="kpi-caption">{{
              model.unknown ? "Известен обем" : "Видеофайлове"
            }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
<style scoped>
.library-analytics {
  container-type: inline-size;
  margin-bottom: 18px;
}
.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}
.analytics-panel {
  min-width: 0;
  background: linear-gradient(120deg, #11222c, #0e1b24);
  border: 1px solid #29454e;
  border-radius: 12px;
  padding: 18px;
}
h2 {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 18px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #c2d7dc;
}
.heading-symbol {
  color: #66dabe;
  font-size: 18px;
  line-height: 1;
}
.distribution-body {
  display: grid;
  grid-template-columns: minmax(165px, 0.85fr) minmax(0, 1.3fr);
  gap: 14px;
  align-items: center;
}
.category-donut {
  display: block;
  width: 100%;
  max-width: 245px;
  margin: auto;
  overflow: visible;
}
.donut-label text {
  font-size: 10px;
  fill: #bedbd6;
  font-weight: 600;
}
.donut-total {
  font-size: 30px;
  font-weight: 700;
  fill: #ecf8f5;
  font-variant-numeric: tabular-nums;
}
.donut-caption {
  font-size: 8px;
  fill: #89a8ad;
  letter-spacing: 0.8px;
}
.category-statistics {
  border-collapse: collapse;
  width: 100%;
  min-width: 0;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}
.category-statistics th,
.category-statistics td {
  padding: 9px 3px;
  border-bottom: 1px solid #27404a88;
  text-align: right;
}
.category-statistics th:first-child {
  text-align: left;
  font-weight: 500;
  white-space: nowrap;
}
.category-statistics thead th {
  color: #7f9fa8;
  font-size: 9px;
  font-weight: 500;
  padding-top: 0;
}
.category-statistics tbody th {
  color: #adc8cd;
}
.category-statistics tfoot th,
.category-statistics tfoot td {
  padding-top: 12px;
  border-bottom: 0;
  color: #83e6ca;
  font-weight: 700;
}
.category-count {
  color: #c6eeeb;
}
.category-size {
  color: #9bb8c0;
  white-space: nowrap;
}
.category-swatch {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 2px;
  margin-right: 6px;
}
.partial-mark {
  color: #d7cfa0;
}
.storage-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 112px;
  gap: 16px;
  align-items: stretch;
}
.storage-chart {
  min-width: 0;
  padding-top: 5px;
}
.storage-row {
  display: grid;
  grid-template-columns: 83px minmax(0, 1fr) 69px;
  gap: 8px;
  align-items: center;
  min-height: 33px;
  font-size: 10px;
}
.storage-label {
  color: #9ebbc3;
}
.storage-value {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: #aed6d5;
  font-size: 10px;
}
.bar-track {
  height: 24px;
  display: flex;
  align-items: center;
  background: repeating-linear-gradient(
    to right,
    #34515a55 0,
    #34515a55 1px,
    transparent 1px,
    transparent 25%
  );
  border-right: 1px solid #34515a55;
}
.storage-bar {
  height: 14px;
  border-radius: 0 3px 3px 0;
  min-width: 0;
}
.axis-row {
  margin: 5px 77px 0 91px;
  height: 15px;
  position: relative;
}
.axis-ticks span {
  position: absolute;
  transform: translateX(-50%);
  color: #698a95;
  font-size: 9px;
}
.axis-ticks span:first-child {
  transform: none;
}
.axis-ticks span:last-child {
  transform: translateX(-100%);
}
.axis-caption {
  margin: 7px 0 0;
  color: #688b95;
  font-size: 9px;
  text-align: center;
}
.storage-kpi {
  border-left: 1px solid #2b4a535c;
  padding-left: 15px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  min-width: 0;
}
.kpi-label {
  color: #a3bfc8;
  font-size: 9px;
  letter-spacing: 0.13em;
}
.kpi-value {
  color: #73e3be;
  font-weight: 600;
  font-size: clamp(21px, 2.2vw, 33px);
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.kpi-caption {
  color: #6e929e;
  font-size: 9px;
}
.kpi-value {
  display: flex;
  flex-direction: column;
  gap: 3px;
  white-space: nowrap;
  overflow-wrap: normal;
}
.kpi-unit {
  font-size: 15px;
  font-weight: 500;
}
.kpi-value.unknown {
  font-size: 14px;
}
.analytics-message {
  margin: 0 0 10px;
  color: #9ab8c1;
  font-size: 11px;
}
.size-note {
  color: #c9c399;
}
.chart-placeholder {
  height: 218px;
  display: grid;
  place-items: center;
  color: #6a8c96;
  border-radius: 6px;
}
.skeleton {
  background: #20363f55;
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@container (max-width: 1100px) {
  .overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .distribution-body {
    grid-template-columns: minmax(180px, 0.8fr) minmax(0, 1.3fr);
  }
}
@container (max-width: 540px) {
  .distribution-body {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .category-donut {
    width: 210px;
  }
  .analytics-panel {
    padding: 16px;
  }
  .storage-body {
    grid-template-columns: minmax(0, 1fr) 85px;
    gap: 10px;
  }
  .storage-row {
    grid-template-columns: 74px minmax(0, 1fr) 58px;
    gap: 5px;
    font-size: 9px;
  }
  .storage-value {
    font-size: 9px;
  }
  .storage-kpi {
    padding-left: 10px;
  }
  .kpi-value {
    font-size: 23px;
  }
  .axis-row {
    margin-left: 79px;
    margin-right: 63px;
  }
  .axis-ticks span:nth-child(even) {
    display: none;
  }
  h2 {
    font-size: 9px;
    letter-spacing: 0.07em;
  }
}
@container (max-width: 400px) {
  .storage-body {
    grid-template-columns: minmax(0, 1fr);
  }
  .storage-kpi {
    border-left: 0;
    border-top: 1px solid #2b4a535c;
    padding: 14px 0 0;
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }
  .kpi-value {
    flex-direction: row;
    align-items: baseline;
    gap: 4px;
    font-size: 27px;
  }
  .kpi-caption {
    display: none;
  }
}
</style>
