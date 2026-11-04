<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
const props = withDefaults(
  defineProps<{ title: string; error?: string; dismissible?: boolean }>(),
  { dismissible: true, error: undefined },
);
const emit = defineEmits<{ close: [] }>();
const panel = ref<HTMLElement>();
let prior: HTMLElement | null = null;
function keydown(e: KeyboardEvent) {
  if (e.key === "Escape" && props.dismissible) emit("close");
  if (e.key !== "Tab") return;
  const nodes = panel.value?.querySelectorAll<HTMLElement>(
    'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
  );
  if (!nodes?.length) {
    e.preventDefault();
    return;
  }
  const first = nodes[0],
    last = nodes[nodes.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  }
  if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}
onMounted(() => {
  prior = document.activeElement as HTMLElement;
  panel.value?.focus();
  document.addEventListener("keydown", keydown);
});
onUnmounted(() => {
  document.removeEventListener("keydown", keydown);
  prior?.focus();
});
</script>
<template>
  <div class="compact-overlay" @click.self="dismissible && emit('close')">
    <section
      ref="panel"
      class="compact-dialog"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      tabindex="-1"
    >
      <div class="dialog-heading">
        <h2>{{ title }}</h2>
        <button
          aria-label="Затвори"
          :disabled="!dismissible"
          @click="emit('close')"
        >
          ×
        </button>
      </div>
      <p v-if="error" role="alert" class="warning">{{ error }}</p>
      <slot />
    </section>
  </div>
</template>
<style scoped>
.compact-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: #030c11d9;
  display: grid;
  place-items: center;
  padding: 18px;
  backdrop-filter: blur(4px);
}
.compact-dialog {
  width: min(780px, 100%);
  max-height: 90vh;
  overflow: auto;
  background: #12232b;
  border: 1px solid #456b69;
  border-radius: 16px;
  padding: 22px;
  box-shadow: 0 22px 80px #000a;
  outline: none;
}
.dialog-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.dialog-heading h2 {
  font-size: 19px;
  margin: 0;
}
</style>
