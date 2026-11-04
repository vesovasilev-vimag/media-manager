<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from "vue";
import {
  actionUnavailable,
  libraryActions,
  type LibraryAction,
} from "./libraryActions";
import type { Asset } from "./types";

const props = defineProps<{
  asset: Asset & { title: string; availability: string };
  busy: boolean;
  open: boolean;
}>();
const emit = defineEmits<{
  toggle: [];
  close: [];
  select: [action: LibraryAction];
}>();
const trigger = ref<HTMLButtonElement>();
const panel = ref<HTMLElement>();
const id = useId();
const position = ref({
  left: "0px",
  top: "0px",
  visibility: "hidden" as "hidden" | "visible",
});
const placement = ref("bottom-end");
const actions = computed(() =>
  libraryActions.map((action) => ({
    ...action,
    reason: actionUnavailable(action, props.asset, props.busy),
  })),
);
let observer: ResizeObserver | undefined;
let frame = 0;

function place() {
  if (!props.open || !trigger.value || !panel.value) return;
  const rect = trigger.value.getBoundingClientRect();
  const viewport = window.visualViewport;
  const left = viewport?.offsetLeft ?? 0,
    top = viewport?.offsetTop ?? 0;
  const right = left + (viewport?.width ?? window.innerWidth);
  const bottom = top + (viewport?.height ?? window.innerHeight);
  // Close when scrolling the trigger out of its clipping container.
  let ancestor = trigger.value.parentElement;
  let visibleTop = top,
    visibleBottom = bottom,
    visibleLeft = left,
    visibleRight = right;
  while (ancestor) {
    const style = getComputedStyle(ancestor);
    const bounds = ancestor.getBoundingClientRect();
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      visibleTop = Math.max(visibleTop, bounds.top);
      visibleBottom = Math.min(visibleBottom, bounds.bottom);
    }
    if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
      visibleLeft = Math.max(visibleLeft, bounds.left);
      visibleRight = Math.min(visibleRight, bounds.right);
    }
    ancestor = ancestor.parentElement;
  }
  if (
    rect.bottom <= visibleTop ||
    rect.top >= visibleBottom ||
    rect.right <= visibleLeft ||
    rect.left >= visibleRight
  ) {
    emit("close");
    return;
  }
  const gap = 8,
    edge = 8;
  const below = Math.max(0, bottom - edge - rect.bottom - gap);
  const above = Math.max(0, rect.top - top - edge - gap);
  const height = panel.value.scrollHeight;
  const flip = height > below && above > below;
  placement.value = flip ? "top-end" : "bottom-end";
  panel.value.style.maxHeight = `${flip ? above : below}px`;
  const size = panel.value.getBoundingClientRect();
  position.value = {
    left: `${Math.max(left + edge, Math.min(rect.right - size.width, right - edge - size.width))}px`,
    top: `${Math.max(top + edge, Math.min(flip ? rect.top - gap - size.height : rect.bottom + gap, bottom - edge - size.height))}px`,
    visibility: "visible",
  };
}
function schedule() {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(place);
}
function close(focus = false) {
  emit("close");
  if (focus) trigger.value?.focus();
}
function outside(event: PointerEvent) {
  const target = event.target as Node;
  if (!panel.value?.contains(target) && !trigger.value?.contains(target))
    close();
}
function keys(event: KeyboardEvent) {
  if (event.key === "Escape") {
    event.preventDefault();
    close(true);
  } else if (event.key === "Tab") close();
  else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const items = Array.from(
      panel.value?.querySelectorAll<HTMLButtonElement>("button") ?? [],
    );
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? items.length - 1
          : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) %
            items.length;
    items[next]?.focus();
  }
}
function select(action: (typeof actions.value)[number]) {
  if (action.reason) return;
  close(true);
  emit("select", action.id);
}
function cleanup() {
  observer?.disconnect();
  cancelAnimationFrame(frame);
  document.removeEventListener("pointerdown", outside, true);
  document.removeEventListener("keydown", keys);
  window.removeEventListener("scroll", schedule, true);
  window.removeEventListener("resize", schedule);
  window.visualViewport?.removeEventListener("resize", schedule);
  window.visualViewport?.removeEventListener("scroll", schedule);
}
watch(
  () => props.open,
  async (open, _previous, onCleanup) => {
    let cancelled = false;
    onCleanup(() => {
      cancelled = true;
      cleanup();
    });
    cleanup();
    if (!open) return;
    position.value.visibility = "hidden";
    await nextTick();
    if (!props.open || cancelled) return;
    place();
    panel.value?.querySelector<HTMLButtonElement>("button")?.focus();
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", keys);
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("scroll", schedule);
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(schedule);
      if (trigger.value) observer.observe(trigger.value);
      if (panel.value) observer.observe(panel.value);
      let ancestor = trigger.value?.parentElement;
      while (ancestor) {
        observer.observe(ancestor);
        ancestor = ancestor.parentElement;
      }
    }
  },
);
onBeforeUnmount(cleanup);
</script>
<template>
  <button
    ref="trigger"
    :aria-label="'Действия за ' + asset.title"
    aria-haspopup="menu"
    :aria-expanded="open"
    :aria-controls="open ? id : undefined"
    @click="emit('toggle')"
    @keydown.down.prevent="!open && emit('toggle')"
  >
    ⋯
  </button>
  <Teleport to="body">
    <div
      v-if="open"
      :id="id"
      ref="panel"
      class="action-pop"
      role="menu"
      :aria-label="'Действия за ' + asset.title"
      :style="position"
      :data-placement="placement"
    >
      <button
        v-for="action in actions"
        :key="action.id"
        role="menuitem"
        :class="{ danger: action.id === 'delete' }"
        :aria-disabled="!!action.reason"
        :aria-describedby="action.reason ? `${id}-${action.id}` : undefined"
        :title="action.reason"
        @click="select(action)"
      >
        {{ action.label
        }}<small v-if="action.reason" :id="`${id}-${action.id}`">{{
          action.reason
        }}</small>
      </button>
    </div>
  </Teleport>
</template>
<style scoped>
.action-pop {
  position: fixed;
  z-index: 90;
  width: min(230px, calc(100vw - 16px));
  overflow: auto;
  border: 1px solid #4b7972;
  background: #11262d;
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 14px 38px #0008;
}
.action-pop button {
  width: 100%;
  border: 0;
  text-align: left;
  font-size: 11px;
}
.action-pop small {
  display: block;
  font-size: 10px;
  color: #9fb5bd;
  margin-top: 4px;
}
.action-pop [aria-disabled="true"] {
  opacity: 0.65;
  cursor: not-allowed;
}
.danger {
  color: #ffb6b9;
  background: #35242a;
}
</style>
