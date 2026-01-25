<template>
  <div class="time-picker">
    <input
      class="time-input"
      type="time"
      step="1"
      :disabled="disabled"
      :value="inputValue"
      :placeholder="is24 ? '已设置 24:00:00' : 'HH:MM:SS'"
      @input="onInput"
    />

    <button
      type="button"
      class="time-btn"
      :class="{ active: is24 }"
      :disabled="disabled"
      @click="set24"
      title="设置为 24:00:00"
    >
      24:00:00
    </button>

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

    <span v-if="showInvalid" class="time-error">时间格式应为 HH:MM:SS 或 24:00:00</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

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

const is24 = computed(() => normalize(props.modelValue) === '24:00:00')

const inputValue = computed(() => {
  const v = normalize(props.modelValue)
  // HTML <input type="time"> 不支持 24:00:00，遇到该值时保持输入框为空，用 placeholder 提示即可
  if (v === '24:00:00') return ''
  if (!v) return ''
  // time input 一般接受 HH:MM 或 HH:MM:SS；这里给 HH:MM:SS
  return v
})

const showInvalid = computed(() => {
  const v = props.modelValue
  if (v === null || v === undefined || v === '') return false
  return !isValidTimeString(String(v))
})

function onInput(e) {
  const raw = e?.target?.value ?? ''
  const normalized = normalize(raw)
  emit('update:modelValue', normalized || null)
}

function set24() {
  emit('update:modelValue', '24:00:00')
}

function clear() {
  emit('update:modelValue', null)
}

function normalize(value) {
  if (value === null || value === undefined) return ''
  const v = String(value).trim()
  if (!v) return ''
  if (v === '24:00' || v === '24:00:00') return '24:00:00'
  // 允许 HH:MM -> HH:MM:SS
  if (/^\d{2}:\d{2}$/.test(v)) return `${v}:00`
  return v
}

function isValidTimeString(value) {
  const v = normalize(value)
  if (v === '24:00:00') return true
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

.time-btn.active {
  border-color: var(--primary-color, #3370ff);
  color: var(--primary-color, #3370ff);
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
