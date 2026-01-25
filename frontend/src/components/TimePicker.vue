<template>
  <div class="time-picker">
    <select v-model="hour" class="form-input time-select">
      <option value="">--</option>
      <option v-for="h in hours" :key="h" :value="String(h)">{{ pad2(h) }}</option>
    </select>
    <span class="time-sep">:</span>
    <select v-model="minute" class="form-input time-select" :disabled="!hasTime || hourIs24">
      <option v-for="m in minutes" :key="m" :value="String(m)">{{ pad2(m) }}</option>
    </select>
    <span class="time-sep">:</span>
    <select v-model="second" class="form-input time-select" :disabled="!hasTime || hourIs24">
      <option v-for="s in seconds" :key="s" :value="String(s)">{{ pad2(s) }}</option>
    </select>
    <button v-if="hasTime" class="btn-secondary time-clear" type="button" @click="clear">清空</button>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: [String, null],
    default: null
  }
})

const emit = defineEmits(['update:modelValue'])

const hours = Array.from({ length: 25 }, (_, i) => i) // 0..24（支持 24:00:00）
const minutes = Array.from({ length: 60 }, (_, i) => i)
const seconds = Array.from({ length: 60 }, (_, i) => i)

const hour = ref('')
const minute = ref('0')
const second = ref('0')

const hasTime = computed(() => hour.value !== '' && hour.value !== null && hour.value !== undefined)
const hourIs24 = computed(() => String(hour.value) === '24')

function pad2(n) {
  const x = Number(n)
  if (Number.isNaN(x)) return '00'
  return String(x).padStart(2, '0')
}

function normalizeFromParts(h, m, s) {
  if (h === '' || h === null || h === undefined) return null
  const hh = Number(h)
  const mm = Number(m)
  const ss = Number(s)
  if (!Number.isFinite(hh)) return null
  if (hh === 24) return '24:00:00'
  return `${pad2(hh)}:${pad2(mm)}:${pad2(ss)}`
}

function parseToParts(value) {
  if (value === null || value === undefined) return { h: '', m: '0', s: '0' }
  const str = String(value).trim()
  if (!str) return { h: '', m: '0', s: '0' }

  // 支持：HH / HH:mm / HH:mm:ss
  if (!str.includes(':')) {
    const h = String(Math.max(0, Math.min(24, Math.floor(Number(str)))))
    return { h: h === 'NaN' ? '' : h, m: '0', s: '0' }
  }

  const parts = str.split(':')
  const h = parts[0] ?? ''
  const m = parts[1] ?? '0'
  const s = parts[2] ?? '0'
  return { h: String(h).trim(), m: String(m).trim(), s: String(s).trim() }
}

let syncing = false

watch(
  () => props.modelValue,
  (val) => {
    syncing = true
    const p = parseToParts(val)
    hour.value = p.h
    minute.value = p.m || '0'
    second.value = p.s || '0'
    if (String(hour.value) === '24') {
      minute.value = '0'
      second.value = '0'
    }
    syncing = false
  },
  { immediate: true }
)

watch([hour, minute, second], () => {
  if (syncing) return
  if (String(hour.value) === '24') {
    if (minute.value !== '0') minute.value = '0'
    if (second.value !== '0') second.value = '0'
  }
  emit('update:modelValue', normalizeFromParts(hour.value, minute.value, second.value))
})

function clear() {
  hour.value = ''
  minute.value = '0'
  second.value = '0'
  emit('update:modelValue', null)
}
</script>

<style scoped>
.time-picker {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.time-select {
  width: 88px;
  padding: 8px 10px;
}

.time-sep {
  color: var(--text-2);
}

.time-clear {
  padding: 8px 10px;
}
</style>

