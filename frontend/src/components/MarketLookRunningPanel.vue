<template>
  <div class="market-look-panel">
    <div class="market-look-toolbar">
      <div class="market-look-heading">
        <h3 class="market-look-title">盯盘详情</h3>
        <span class="market-look-sub">运行中（RUNNING）</span>
      </div>
      <span
        class="status-indicator small"
        :class="{
          updating: statusType === 'updating',
          success: statusType === 'success',
          error: statusType === 'error'
        }"
      >{{ statusText }}</span>
      <button
        type="button"
        class="btn-refresh"
        :disabled="loading"
        title="刷新"
        @click="load"
      >
        <i class="bi bi-arrow-repeat" :class="{ spin: loading }"></i>
      </button>
    </div>

    <div class="market-look-table-wrap">
      <table class="market-look-table">
        <thead>
          <tr>
            <th>数据ID</th>
            <th>策略ID</th>
            <th>策略名称</th>
            <th>合约</th>
            <th>开始时间</th>
            <th>结束时间</th>
            <th>执行进度</th>
            <th>详情摘要</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading && rows.length === 0" class="loading-row">
            <td colspan="8" class="loading-cell">
              <i class="bi bi-arrow-repeat spin"></i>
              <span>加载中…</span>
            </td>
          </tr>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="data-row"
            @click="openSignalModal(row)"
          >
            <td class="cell-mono cell-clip" :title="row.id">{{ row.id }}</td>
            <td class="cell-mono cell-clip" :title="row.strategy_id">{{ row.strategy_id || '—' }}</td>
            <td class="cell-clip" :title="row.strategy_name">{{ row.strategy_name || '—' }}</td>
            <td class="cell-symbol">{{ row.symbol || '—' }}</td>
            <td class="cell-time">{{ formatStarted(row.started_at ?? row.startedAt) }}</td>
            <td class="cell-time">{{ formatEndedAtDisplay(row.ended_at ?? row.endedAt) }}</td>
            <td class="col-progress">
              <div class="progress-meta">
                <span class="elapsed">{{ elapsedLabel(row) }}</span>
              </div>
              <div class="progress-track" :title="progressTitle">
                <div class="progress-fill" :style="{ width: progressPercent(row) + '%' }"></div>
              </div>
            </td>
            <td class="cell-detail" :title="detailSummaryRaw(row) || undefined">{{ detailSummaryDisplay(row) }}</td>
          </tr>
          <tr v-if="!loading && rows.length === 0">
            <td colspan="8" class="empty-cell">暂无运行中的盯盘任务</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Modal
      :visible="signalModalVisible"
      title="盯盘任务详情"
      :subtitle="signalModalSubtitle"
      :extra-large="true"
      @update:visible="signalModalVisible = $event"
      @close="closeSignalModal"
    >
      <div v-if="signalDetailRow" class="signal-modal-body">
        <section class="detail-section detail-section--strategy">
          <h4 class="section-label">策略内容</h4>
          <p v-if="strategyLoading" class="section-hint muted">正在加载策略…</p>
          <p v-else-if="strategyFetchError" class="section-hint error-text">{{ strategyFetchError }}</p>
          <template v-else-if="strategyDetail">
            <dl class="strategy-meta">
              <div v-if="strategyDisplayName" class="meta-row">
                <dt>名称</dt>
                <dd>{{ strategyDisplayName }}</dd>
              </div>
              <div v-if="strategyTypeLabel" class="meta-row">
                <dt>类型</dt>
                <dd>{{ strategyTypeLabel }}</dd>
              </div>
              <div v-if="strategyValidateSymbol" class="meta-row">
                <dt>校验合约</dt>
                <dd class="cell-mono">{{ strategyValidateSymbol }}</dd>
              </div>
            </dl>
            <div v-if="strategyContextText" class="strategy-block">
              <span class="block-label">策略说明 / 上下文</span>
              <pre class="strategy-pre">{{ strategyContextText }}</pre>
            </div>
            <div v-if="strategyCodeText" class="strategy-block">
              <span class="block-label">策略代码</span>
              <pre class="strategy-pre strategy-pre--code">{{ strategyCodeText }}</pre>
            </div>
            <p
              v-if="!strategyContextText && !strategyCodeText"
              class="section-hint muted"
            >
              该策略暂无说明与代码文本
            </p>
          </template>
          <p v-else class="section-hint muted">当前任务未关联策略 ID，无法加载策略内容</p>
        </section>

        <div class="detail-divider" role="separator" aria-hidden="true" />

        <section class="detail-section detail-section--signal">
          <h4 class="section-label">信号结果</h4>
          <pre class="signal-pre">{{
            formatSignal(signalDetailRow.signal_result ?? signalDetailRow.signalResult)
          }}</pre>
        </section>

        <div class="detail-divider" role="separator" aria-hidden="true" />

        <section class="detail-section detail-section--summary">
          <h4 class="section-label">详情摘要</h4>
          <p v-if="!detailSummaryRaw(signalDetailRow)" class="section-hint muted">暂无摘要</p>
          <pre v-else class="summary-pre">{{ detailSummaryRaw(signalDetailRow) }}</pre>
        </section>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { marketLookApi, strategyApi } from '../services/api.js'
import Modal from './Modal.vue'

/** 进度条：相对 24h 参照窗口的比例（RUNNING 无真实结束时刻时的可视化） */
const REFERENCE_MS = 24 * 60 * 60 * 1000

const rows = ref([])
const loading = ref(false)
const statusType = ref('default')
const statusText = ref('等待数据...')
const nowTick = ref(Date.now())

const signalModalVisible = ref(false)
const signalDetailRow = ref(null)
const strategyDetail = ref(null)
const strategyLoading = ref(false)
const strategyFetchError = ref('')

const signalModalSubtitle = computed(() => {
  const r = signalDetailRow.value
  if (!r) return ''
  const sym = r.symbol || '—'
  return `数据ID: ${r.id} · 合约: ${sym}`
})

const strategyDisplayName = computed(() => {
  const s = strategyDetail.value
  const r = signalDetailRow.value
  if (s?.name) return s.name
  if (s?.strategy_name) return s.strategy_name
  if (r?.strategy_name ?? r?.strategyName) return r.strategy_name ?? r.strategyName
  return ''
})

const strategyTypeLabel = computed(() => {
  const t = strategyDetail.value?.type
  if (!t) return ''
  const map = { buy: '买入', sell: '卖出', look: '盯盘' }
  return map[t] || t
})

const strategyValidateSymbol = computed(() => {
  const s = strategyDetail.value
  if (!s) return ''
  return s.validate_symbol ?? s.validateSymbol ?? ''
})

const strategyContextText = computed(() => {
  const s = strategyDetail.value
  if (!s) return ''
  const raw = s.strategy_context ?? s.strategyContext
  if (raw == null || String(raw).trim() === '') return ''
  return String(raw).trim()
})

const strategyCodeText = computed(() => {
  const s = strategyDetail.value
  if (!s) return ''
  const raw = s.strategy_code ?? s.strategyCode
  if (raw == null || String(raw).trim() === '') return ''
  return String(raw).trim()
})

let pollTimer = null
let tickTimer = null

function parseStartMs(startedAt) {
  if (!startedAt) return null
  const t = Date.parse(startedAt)
  return Number.isFinite(t) ? t : null
}

function progressPercent(row) {
  const start = parseStartMs(row.started_at ?? row.startedAt)
  if (start == null) return 0
  const elapsed = Math.max(0, nowTick.value - start)
  return Math.min(100, (elapsed / REFERENCE_MS) * 100)
}

const progressTitle = '相对 24h 参照窗口；下方为已执行时长'

function elapsedLabel(row) {
  const start = parseStartMs(row.started_at ?? row.startedAt)
  if (start == null) return '—'
  const ms = Math.max(0, nowTick.value - start)
  return formatDuration(ms)
}

function formatDuration(ms) {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const h = Math.floor(m / 60)
  const d = Math.floor(h / 24)
  if (d > 0) return `${d}天${h % 24}小时`
  if (h > 0) return `${h}小时${m % 60}分`
  if (m > 0) return `${m}分${s % 60}秒`
  return `${s}秒`
}

/** 摘要原文，无则空串 */
function detailSummaryRaw(row) {
  if (!row) return ''
  const v = row.detail_summary ?? row.detailSummary
  if (v == null || String(v).trim() === '') return ''
  return String(v).trim()
}

function detailSummaryDisplay(row) {
  const s = detailSummaryRaw(row)
  return s || '—'
}

function formatSignal(raw) {
  if (raw == null || raw === '') return '（空）'
  const s = String(raw).trim()
  try {
    const o = JSON.parse(s)
    return JSON.stringify(o, null, 2)
  } catch {
    return s
  }
}

async function openSignalModal(row) {
  signalDetailRow.value = row
  strategyDetail.value = null
  strategyFetchError.value = ''
  strategyLoading.value = true
  signalModalVisible.value = true
  try {
    const fresh = await marketLookApi.getById(row.id)
    if (fresh && fresh.id === row.id) {
      signalDetailRow.value = fresh
    }
  } catch (e) {
    console.warn('[MarketLookRunningPanel] getById fallback to row', e)
  }

  const r = signalDetailRow.value
  const sid = r ? String(r.strategy_id ?? r.strategyId ?? '').trim() : ''
  if (!sid) {
    strategyLoading.value = false
    return
  }
  try {
    strategyDetail.value = await strategyApi.getById(sid)
  } catch (e) {
    console.warn('[MarketLookRunningPanel] strategy getById', e)
    strategyFetchError.value = e?.message || '加载策略失败'
  } finally {
    strategyLoading.value = false
  }
}

function closeSignalModal() {
  signalModalVisible.value = false
  signalDetailRow.value = null
  strategyDetail.value = null
  strategyFetchError.value = ''
  strategyLoading.value = false
}

function formatStarted(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return String(iso)
  }
}

/** RUNNING 未结束时库内可能为 2099 占位 */
function isPlaceholderEndedAt(iso) {
  if (!iso) return true
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return false
  return d.getFullYear() >= 2099
}

function formatEndedAtDisplay(iso) {
  if (!iso) return '—'
  if (isPlaceholderEndedAt(iso)) return '未结束'
  return formatStarted(iso)
}

async function load() {
  loading.value = true
  statusType.value = 'updating'
  statusText.value = '正在更新...'
  try {
    const data = await marketLookApi.listRunning()
    rows.value = Array.isArray(data) ? data : []
    statusType.value = 'success'
    const t = new Date()
    statusText.value = `最后更新: ${t.toLocaleTimeString('zh-CN', { hour12: false })}`
  } catch (e) {
    console.error('[MarketLookRunningPanel]', e)
    rows.value = []
    statusType.value = 'error'
    statusText.value = '更新失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  pollTimer = window.setInterval(load, 30000)
  tickTimer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (tickTimer) clearInterval(tickTimer)
})

defineExpose({ load })
</script>

<style scoped>
.market-look-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.market-look-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.market-look-heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.market-look-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
}

.market-look-sub {
  font-size: 12px;
  color: var(--text-3);
}

.btn-refresh {
  margin-left: auto;
  border: none;
  background: var(--bg-2);
  color: var(--text-2);
  width: 32px;
  height: 32px;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-refresh:hover:not(:disabled) {
  color: var(--primary);
  background: rgba(51, 112, 255, 0.12);
}

.btn-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-row .loading-cell {
  text-align: center;
  padding: 20px !important;
  color: var(--text-2);
  font-size: 13px;
}

.loading-cell .spin {
  margin-right: 8px;
  vertical-align: middle;
}

.market-look-table-wrap {
  overflow: auto;
  max-height: min(420px, 60vh);
  border-radius: 12px;
  border: 1px solid var(--border-1, rgba(0, 0, 0, 0.08));
}

.market-look-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.market-look-table thead {
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  z-index: 1;
}

.market-look-table th,
.market-look-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border-1, rgba(0, 0, 0, 0.06));
  vertical-align: middle;
}

.market-look-table tbody tr:last-child td {
  border-bottom: none;
}

.market-look-table th {
  font-weight: 600;
  color: var(--text-2);
  font-size: 11px;
}

.data-row {
  cursor: pointer;
  transition: background 0.15s;
}

.data-row:hover {
  background: rgba(51, 112, 255, 0.08);
}

.cell-clip {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
}

.cell-symbol {
  font-weight: 500;
  color: var(--text-1);
  white-space: nowrap;
}

.cell-time {
  white-space: nowrap;
  color: var(--text-2);
}

.col-progress {
  min-width: 140px;
  max-width: 200px;
}

.progress-meta {
  margin-bottom: 4px;
}

.elapsed {
  font-size: 11px;
  color: var(--text-2);
}

.progress-track {
  height: 6px;
  border-radius: 999px;
  background: var(--bg-2, #e8eaf0);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #5b7cff, #3370ff);
  transition: width 0.35s ease;
}

.empty-cell {
  text-align: center;
  color: var(--text-3);
  padding: 20px 12px !important;
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.signal-modal-body {
  max-height: min(72vh, 680px);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.detail-section {
  min-width: 0;
}

.section-label {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
}

.section-hint {
  margin: 0;
  font-size: 12px;
}

.muted {
  color: var(--text-3);
}

.error-text {
  color: #c0392b;
  font-size: 12px;
}

.detail-divider {
  height: 1px;
  margin: 16px 0;
  background: var(--border-1, rgba(0, 0, 0, 0.12));
  flex-shrink: 0;
}

.strategy-meta {
  margin: 0 0 12px;
  font-size: 12px;
}

.meta-row {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 8px;
  margin-bottom: 6px;
  align-items: baseline;
}

.meta-row dt {
  margin: 0;
  color: var(--text-3);
  font-weight: 500;
}

.meta-row dd {
  margin: 0;
  color: var(--text-1);
}

.strategy-block {
  margin-bottom: 12px;
}

.strategy-block:last-child {
  margin-bottom: 0;
}

.block-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.strategy-pre {
  margin: 0;
  padding: 10px 12px;
  background: var(--bg-2, #f5f6fa);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  max-height: min(28vh, 280px);
  overflow: auto;
}

.strategy-pre--code {
  max-height: min(36vh, 360px);
}

.signal-pre {
  margin: 0;
  padding: 12px;
  background: var(--bg-2, #f5f6fa);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  max-height: min(36vh, 400px);
  overflow: auto;
}

.cell-detail {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-2);
  font-size: 11px;
}

.summary-pre {
  margin: 0;
  padding: 12px;
  background: var(--bg-2, #f5f6fa);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: min(28vh, 260px);
  overflow: auto;
}
</style>
