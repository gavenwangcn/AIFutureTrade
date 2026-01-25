<template>
  <div class="time-picker">
    <input
      class="time-input"
      type="time"
      step="1"
      :disabled="disabled"
      :value="draft"
      placeholder="HH:MM:SS"
      @input="onInput"
    />

    <button
      v-if="modelValue"
      type="button"
      class="time-btn subtle"
      :disabled="disabled"
      @click="clear"
      title="清空"
    >
      清空
    </button>

    <span v-if="showInvalid" class="time-error">时间格式应为 HH:MM:SS</span>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: [String, null],
    default: null
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

const draft = ref(props.modelValue ?? '')

watch(
  () => props.modelValue,
  (v) => {
    draft.value = v ?? ''
  }
)

const showInvalid = computed(() => {
  const v = draft.value
  if (v === null || v === undefined || v === '') return false
  return !isValidTimeString(String(v))
})

function onInput(e) {
  const raw = e?.target?.value ?? ''
  const normalized = normalize(raw)
  draft.value = normalized

  if (!normalized) {
    emit('update:modelValue', null)
    return
  }

  if (isValidTimeString(normalized)) {
    emit('update:modelValue', normalized || null)
  }
}

function clear() {
  emit('update:modelValue', null)
}

function normalize(value) {
  if (value === null || value === undefined) return ''
  const v = String(value).trim()
  if (!v) return ''
  // 允许 HH:MM -> HH:MM:SS
  if (/^\d{2}:\d{2}$/.test(v)) return `${v}:00`
  return v
}

function isValidTimeString(value) {
  const v = normalize(value)
  // 00:00:00 ~ 23:59:59
  return /^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(v)
}
</script>

<style scoped>
.time-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.time-input {
  padding: 8px 10px;
  border: 1px solid var(--border-color, #e5e6eb);
  border-radius: 6px;
  background: var(--bg-secondary, #fff);
  color: var(--text-primary, #1f2329);
  font-size: 14px;
  line-height: 1;
  min-width: 140px;
}

.time-btn {
  padding: 7px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-color, #e5e6eb);
  background: var(--bg-secondary, #fff);
  color: var(--text-primary, #1f2329);
  font-size: 13px;
  cursor: pointer;
}

.time-btn:hover:enabled {
  border-color: var(--primary-color, #3370ff);
}

.time-btn.subtle {
  color: var(--text-secondary, #86909c);
}

.time-btn:disabled,
.time-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.time-error {
  color: #f56c6c;
  font-size: 12px;
}
</style>
