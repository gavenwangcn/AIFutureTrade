<template>
  <div v-if="visible" class="modal-overlay" @click.self="handleClose">
    <div class="modal-content add-market-look-modal">
      <div class="modal-header">
        <h3>添加盯盘</h3>
        <button class="btn-close" type="button" @click="handleClose">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="modal-body">
        <div v-if="error" class="alert alert-error">{{ error }}</div>

        <div class="form-group">
          <label>合约名称 (symbol) <span class="required">*</span></label>
          <input
            v-model="form.symbol"
            type="text"
            class="form-input"
            placeholder="例如 BTC、ETH"
            autocomplete="off"
          />
        </div>

        <div class="form-group">
          <label>详情摘要 <span class="required">*</span></label>
          <textarea
            v-model="form.detailSummary"
            class="form-textarea"
            rows="3"
            placeholder="任务说明或监控要点"
          />
        </div>

        <div class="form-group">
          <label>策略类型</label>
          <select v-model="strategyTypeFilter" class="form-input" @change="onStrategyTypeChange">
            <option value="look">盯盘</option>
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
          <div class="form-hint">仅「盯盘」类型可保存为盯盘任务；其它类型仅供查看策略库</div>
        </div>

        <div class="form-group">
          <label>策略 <span class="required">*</span></label>
          <select v-model="form.strategyId" class="form-input" @change="onStrategyPick">
            <option value="">请选择策略</option>
            <option v-for="s in filteredStrategies" :key="s.id" :value="s.id">
              {{ s.name || s.id }}（{{ typeLabel(s.type) }}）
            </option>
          </select>
        </div>

        <div v-if="selectedStrategy && strategyTypeFilter === 'look'" class="strategy-preview">
          <div class="preview-row"><span class="k">策略名称</span><span class="v">{{ selectedStrategy.name || '—' }}</span></div>
          <div v-if="validateSym" class="preview-row"><span class="k">校验合约</span><span class="v mono">{{ validateSym }}</span></div>
        </div>

        <div class="form-group">
          <label>开始时间 <span class="required">*</span></label>
          <input v-model="form.startedAt" type="datetime-local" class="form-input" step="1" />
        </div>

        <div class="form-group">
          <label>结束时间 <span class="required">*</span></label>
          <input v-model="form.endedAt" type="datetime-local" class="form-input" step="1" />
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn-secondary" @click="handleClose">取消</button>
        <button type="button" class="btn-primary" :disabled="saving || !canSave" @click="handleSave">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { marketLookApi, strategyApi } from '../services/api.js'

const props = defineProps({
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['update:visible', 'saved'])

const error = ref('')
const saving = ref(false)
const strategies = ref([])
const strategyTypeFilter = ref('look')

const form = ref({
  symbol: '',
  detailSummary: '',
  strategyId: '',
  strategyName: '',
  startedAt: '',
  endedAt: ''
})

function typeLabel(t) {
  const m = { buy: '买入', sell: '卖出', look: '盯盘' }
  return m[t] || t || '—'
}

const filteredStrategies = computed(() => {
  const t = strategyTypeFilter.value
  return (strategies.value || []).filter((s) => (s.type || '').toLowerCase() === t)
})

const selectedStrategy = computed(() => {
  const id = String(form.value.strategyId || '').trim()
  if (!id) return null
  return strategies.value.find((s) => s.id === id) || null
})

const validateSym = computed(() => {
  const s = selectedStrategy.value
  if (!s) return ''
  return s.validate_symbol ?? s.validateSymbol ?? ''
})

const canSave = computed(() => {
  if (!String(form.value.symbol || '').trim()) return false
  if (!String(form.value.detailSummary || '').trim()) return false
  if (!String(form.value.strategyId || '').trim()) return false
  if (strategyTypeFilter.value !== 'look') return false
  if (!String(form.value.startedAt || '').trim()) return false
  if (!String(form.value.endedAt || '').trim()) return false
  return true
})

function defaultDatetimeLocal(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function resetDefaults() {
  const now = new Date()
  const end = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  form.value = {
    symbol: '',
    detailSummary: '',
    strategyId: '',
    strategyName: '',
    startedAt: defaultDatetimeLocal(now),
    endedAt: defaultDatetimeLocal(end)
  }
  strategyTypeFilter.value = 'look'
  error.value = ''
}

function onStrategyTypeChange() {
  form.value.strategyId = ''
  form.value.strategyName = ''
}

function onStrategyPick() {
  const s = selectedStrategy.value
  form.value.strategyName = s ? (s.name || '') : ''
}

function localDatetimeToPayload(str) {
  if (!str || !String(str).trim()) return null
  let s = String(str).trim()
  if (s.length === 16) s = `${s}:00`
  return s.replace(' ', 'T')
}

async function loadStrategies() {
  try {
    const list = await strategyApi.getAll()
    strategies.value = Array.isArray(list) ? list : []
  } catch (e) {
    console.warn('[AddMarketLookModal] load strategies', e)
    strategies.value = []
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      resetDefaults()
      loadStrategies()
    }
  }
)

function handleClose() {
  emit('update:visible', false)
}

async function handleSave() {
  error.value = ''
  if (!canSave.value) {
    error.value = '请填写合约名称、详情摘要，并选择盯盘策略；开始/结束时间必填，且策略类型须为盯盘。'
    return
  }
  const started = localDatetimeToPayload(form.value.startedAt)
  const ended = localDatetimeToPayload(form.value.endedAt)
  const startMs = new Date(started).getTime()
  const endMs = new Date(ended).getTime()
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) {
    error.value = '开始或结束时间格式无效'
    return
  }
  if (endMs <= startMs) {
    error.value = '结束时间必须晚于开始时间'
    return
  }
  saving.value = true
  try {
    const body = {
      symbol: String(form.value.symbol).trim(),
      detail_summary: String(form.value.detailSummary).trim(),
      strategy_id: String(form.value.strategyId).trim(),
      strategy_name: String(form.value.strategyName || selectedStrategy.value?.name || '').trim() || undefined,
      execution_status: 'RUNNING',
      started_at: started,
      ended_at: ended
    }
    await marketLookApi.create(body)
    emit('saved')
    emit('update:visible', false)
  } catch (e) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.add-market-look-modal {
  max-width: 520px;
  width: 92vw;
}

.required {
  color: #c0392b;
}

.strategy-preview {
  margin: 0 0 14px;
  padding: 10px 12px;
  background: var(--bg-2, #f5f6fa);
  border-radius: 8px;
  font-size: 12px;
}

.preview-row {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
}

.preview-row:last-child {
  margin-bottom: 0;
}

.preview-row .k {
  color: var(--text-3, #888);
  flex-shrink: 0;
  width: 72px;
}

.preview-row .v {
  color: var(--text-1);
  word-break: break-word;
}

.preview-row .v.mono {
  font-family: ui-monospace, monospace;
}

.alert-error {
  padding: 8px 12px;
  background: rgba(192, 57, 43, 0.08);
  border-radius: 8px;
  color: #a93226;
  font-size: 13px;
  margin-bottom: 12px;
}
</style>
