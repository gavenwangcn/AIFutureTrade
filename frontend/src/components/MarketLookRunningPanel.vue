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
            <th>执行进度</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading && rows.length === 0" class="loading-row">
            <td colspan="6" class="loading-cell">
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
            <td class="cell-time">{{ formatStarted(row.started_at) }}</td>
            <td class="col-progress">
              <div class="progress-meta">
                <span class="elapsed">{{ elapsedLabel(row) }}</span>
              </div>
              <div class="progress-track" :title="progressTitle">
                <div class="progress-fill" :style="{ width: progressPercent(row) + '%' }"></div>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && rows.length === 0">
            <td colspan="6" class="empty-cell">暂无运行中的盯盘任务</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Modal
      :visible="signalModalVisible"
      title="signal_result"
      :subtitle="signalModalSubtitle"
      large
      @update:visible="signalModalVisible = $event"
      @close="closeSignalModal"
    >
      <div v-if="signalDetailRow" class="signal-modal-body">
        <pre class="signal-pre">{{
          formatSignal(signalDetailRow.signal_result ?? signalDetailRow.signalResult)
        }}</pre>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { marketLookApi } from '../services/api.js'
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

const signalModalSubtitle = computed(() => {
  const r = signalDetailRow.value
  if (!r) return ''
  const sym = r.symbol || '—'
  return `数据ID: ${r.id} · 合约: ${sym}`
})

let pollTimer = null
let tickTimer = null

function parseStartMs(startedAt) {
  if (!startedAt) return null
  const t = Date.parse(startedAt)
  return Number.isFinite(t) ? t : null
}

function progressPercent(row) {
  const start = parseStartMs(row.started_at)
  if (start == null) return 0
  const elapsed = Math.max(0, nowTick.value - start)
  return Math.min(100, (elapsed / REFERENCE_MS) * 100)
}

const progressTitle = '相对 24h 参照窗口；下方为已执行时长'

function elapsedLabel(row) {
  const start = parseStartMs(row.started_at)
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
  signalModalVisible.value = true
  try {
    const fresh = await marketLookApi.getById(row.id)
    if (fresh && fresh.id === row.id) {
      signalDetailRow.value = fresh
    }
  } catch (e) {
    console.warn('[MarketLookRunningPanel] getById fallback to row', e)
  }
}

function closeSignalModal() {
  signalModalVisible.value = false
  signalDetailRow.value = null
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
  max-height: min(70vh, 640px);
  overflow: auto;
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
}
</style>
