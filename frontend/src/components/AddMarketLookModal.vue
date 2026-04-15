<template>
  <Modal
    :visible="visible"
    title="添加盯盘"
    width="520px"
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
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
      <input
        type="text"
        class="form-input form-input-readonly"
        value="盯盘"
        readonly
        tabindex="-1"
        aria-readonly="true"
      />
      <div class="form-hint">盯盘任务仅支持「盯盘」类型策略</div>
    </div>

    <div class="form-group strategy-combo-wrap">
      <label>策略 <span class="required">*</span></label>
      <div class="strategy-combo">
        <input
          v-model="strategySearchQuery"
          type="text"
          class="form-input"
          placeholder="输入名称、ID 或校验合约搜索，点击列表选择"
          autocomplete="off"
          @focus="strategyDropdownOpen = true"
          @input="onStrategySearchInput"
        />
        <ul
          v-show="strategyDropdownOpen && strategyOptionsFiltered.length > 0"
          class="strategy-dropdown"
          role="listbox"
        >
          <li
            v-for="s in strategyOptionsFiltered"
            :key="s.id"
            role="option"
            class="strategy-option"
            @mousedown.prevent="selectStrategy(s)"
          >
            <span class="opt-name">{{ s.name || s.id }}</span>
            <span class="opt-id">{{ s.id }}</span>
          </li>
        </ul>
        <div
          v-show="strategyDropdownOpen && strategyOptionsFiltered.length === 0 && strategySearchQuery.trim() !== ''"
          class="strategy-dropdown empty"
        >
          无匹配盯盘策略
        </div>
      </div>
    </div>

    <div v-if="selectedStrategy" class="strategy-preview">
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

    <template #footer>
      <button type="button" class="btn-secondary" @click="handleClose">取消</button>
      <button type="button" class="btn-primary" :disabled="saving || !canSave" @click="handleSave">
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import Modal from './Modal.vue'
import { marketLookApi, strategyApi } from '../services/api.js'

const props = defineProps({
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['update:visible', 'close', 'saved'])

const error = ref('')
const saving = ref(false)
const strategies = ref([])
const strategySearchQuery = ref('')
const strategyDropdownOpen = ref(false)

const form = ref({
  symbol: '',
  detailSummary: '',
  strategyId: '',
  strategyName: '',
  startedAt: '',
  endedAt: ''
})

/** 仅盯盘类型策略 */
const lookStrategies = computed(() =>
  (strategies.value || []).filter((s) => (s.type || '').toLowerCase() === 'look')
)

const strategyOptionsFiltered = computed(() => {
  const q = strategySearchQuery.value.trim().toLowerCase()
  const list = lookStrategies.value
  if (!q) return list
  return list.filter((s) => {
    const name = String(s.name || '').toLowerCase()
    const id = String(s.id || '').toLowerCase()
    const vs = String(s.validate_symbol || s.validateSymbol || '').toLowerCase()
    return name.includes(q) || id.includes(q) || vs.includes(q)
  })
})

const selectedStrategy = computed(() => {
  const id = String(form.value.strategyId || '').trim()
  if (!id) return null
  return lookStrategies.value.find((s) => s.id === id) || null
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
  if (!String(form.value.startedAt || '').trim()) return false
  if (!String(form.value.endedAt || '').trim()) return false
  return true
})

function selectedStrategyLabel() {
  const s = selectedStrategy.value
  if (!s) return ''
  return String(s.name || s.id || '').trim()
}

function onStrategySearchInput() {
  strategyDropdownOpen.value = true
  const sel = selectedStrategy.value
  if (!sel) return
  const label = selectedStrategyLabel()
  const q = strategySearchQuery.value.trim()
  if (label && q !== label) {
    form.value.strategyId = ''
    form.value.strategyName = ''
  }
}

function selectStrategy(s) {
  form.value.strategyId = s.id
  form.value.strategyName = s.name || ''
  strategySearchQuery.value = String(s.name || s.id || '')
  strategyDropdownOpen.value = false
}

function onDocumentPointerDown(e) {
  const el = e.target
  if (el && typeof el.closest === 'function' && el.closest('.strategy-combo')) return
  strategyDropdownOpen.value = false
}

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
  strategySearchQuery.value = ''
  strategyDropdownOpen.value = false
  error.value = ''
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
      document.addEventListener('pointerdown', onDocumentPointerDown, true)
    } else {
      document.removeEventListener('pointerdown', onDocumentPointerDown, true)
    }
  }
)

onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
})

function handleClose() {
  strategyDropdownOpen.value = false
  emit('update:visible', false)
  emit('close')
}

async function handleSave() {
  error.value = ''
  if (!canSave.value) {
    error.value = '请填写合约名称、详情摘要，并选择盯盘策略；开始与结束时间必填。'
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
    emit('close')
  } catch (e) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.required {
  color: #c0392b;
}

.form-input-readonly {
  background: var(--bg-2, #f5f6fa);
  color: var(--text-2, #555);
  cursor: default;
}

.strategy-combo-wrap {
  position: relative;
  z-index: 1;
}

.strategy-combo {
  position: relative;
}

.strategy-dropdown {
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  margin: 4px 0 0;
  padding: 4px 0;
  list-style: none;
  max-height: 220px;
  overflow-y: auto;
  background: var(--bg-1, #fff);
  border: 1px solid var(--border-1, #e0e0e0);
  border-radius: 8px;
  box-shadow: var(--shadow-2, 0 4px 12px rgba(0, 0, 0, 0.08));
  z-index: 20;
}

.strategy-dropdown.empty {
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-3, #888);
}

.strategy-option {
  padding: 8px 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}

.strategy-option:hover {
  background: rgba(51, 112, 255, 0.08);
}

.opt-name {
  color: var(--text-1);
  font-weight: 500;
}

.opt-id {
  font-size: 11px;
  color: var(--text-3);
  font-family: ui-monospace, monospace;
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
