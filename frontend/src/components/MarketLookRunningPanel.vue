<template>
  <div class="market-look-panel">
    <div class="market-look-header">
      <h3 class="market-look-title">盯盘详情</h3>
      <span class="market-look-sub">执行中（RUNNING）</span>
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

    <div v-if="loading && rows.length === 0" class="market-look-loading">
      <i class="bi bi-arrow-repeat spin"></i>
      <span>加载中…</span>
    </div>
    <div v-else-if="errorMsg" class="market-look-error">{{ errorMsg }}</div>
    <div v-else class="market-look-table-wrap">
      <table class="market-look-table">
        <thead>
          <tr>
            <th>合约</th>
            <th>策略</th>
            <th>开始时间</th>
            <th>执行进度</th>
            <th class="col-expand"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.id">
            <tr class="data-row" @click="toggleExpand(row.id)">
              <td><strong>{{ row.symbol }}</strong></td>
              <td class="cell-clip" :title="row.strategy_name || row.strategy_id">
                {{ row.strategy_name || row.strategy_id || '—' }}
              </td>
              <td class="cell-time">{{ formatStarted(row.started_at) }}</td>
              <td>
                <div class="progress-meta">
                  <span class="elapsed">{{ elapsedLabel(row) }}</span>
                </div>
                <div class="progress-track" :title="progressTitle(row)">
                  <div class="progress-fill" :style="{ width: progressPercent(row) + '%' }"></div>
                </div>
              </td>
              <td class="col-expand">
                <i class="bi" :class="expandedId === row.id ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
              </td>
            </tr>
            <tr v-if="expandedId === row.id" class="detail-row">
              <td colspan="5">
                <div class="detail-inner">
                  <div class="detail-meta">
                    <span><span class="meta-k">id</span> {{ row.id }}</span>
                    <span><span class="meta-k">strategy_id</span> {{ row.strategy_id }}</span>
                    <span><span class="meta-k">execution_status</span> {{ row.execution_status }}</span>
                    <span><span class="meta-k">started_at</span> {{ formatStarted(row.started_at) }}</span>
                    <span><span class="meta-k">ended_at</span> {{ formatEndedAt(row.ended_at) }}</span>
                  </div>
                  <div class="detail-label">signal_result</div>
                  <pre class="detail-pre">{{ formatSignal(row.signal_result) }}</pre>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="rows.length === 0">
            <td colspan="5" class="empty-cell">暂无执行中的盯盘任务</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { marketLookApi } from '../services/api.js'

/** 进度条参照时长：展示「自开始以来」相对该窗口的比例（非业务截止时刻） */
const REFERENCE_MS = 24 * 60 * 60 * 1000

const rows = ref([])
const loading = ref(false)
const errorMsg = ref('')
const expandedId = ref(null)
const nowTick = ref(Date.now())

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

function progressTitle(row) {
  return '相对 24h 参照窗口的占用比例；已执行时长见左侧文字'
}

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

/** 与后端 RUNNING 占位 ended_at（2099-12-31）一致 */
function isPlaceholderEndedAt(iso) {
  if (!iso) return true
  const d = new Date(iso)
  return Number.isFinite(d.getTime()) && d.getFullYear() >= 2099
}

function formatEndedAt(iso) {
  if (isPlaceholderEndedAt(iso)) return '—（未结束占位）'
  return formatStarted(iso)
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

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await marketLookApi.listRunning()
    rows.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error('[MarketLookRunningPanel]', e)
    errorMsg.value = e.message || '加载失败'
    rows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  // 与首页涨跌榜类似的定时拉取节奏：每 30 秒刷新列表
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
  min-height: 220px;
  min-width: 0;
  height: 100%;
}

.market-look-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
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

.market-look-loading,
.market-look-error {
  padding: 24px;
  text-align: center;
  color: var(--text-2);
  font-size: 14px;
}

.market-look-error {
  color: var(--danger, #dc3545);
}

.market-look-table-wrap {
  overflow: auto;
  flex: 1;
  max-height: 320px;
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
  background: rgba(51, 112, 255, 0.06);
}

.cell-clip {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-time {
  white-space: nowrap;
  color: var(--text-2);
}

.col-expand {
  width: 36px;
  text-align: center;
  color: var(--text-3);
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
  transition: width 0.3s ease;
}

.detail-row td {
  padding: 0;
  border-bottom: 1px solid var(--border-1, rgba(0, 0, 0, 0.06));
  background: rgba(0, 0, 0, 0.02);
}

.detail-inner {
  padding: 12px 14px;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  font-size: 11px;
  color: var(--text-2);
  margin-bottom: 10px;
  word-break: break-all;
}

.meta-k {
  color: var(--text-3);
  margin-right: 4px;
}

.detail-label {
  font-size: 11px;
  color: var(--text-3);
  margin-bottom: 6px;
}

.detail-pre {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 160px;
  overflow: auto;
  color: var(--text-1);
}

.empty-cell {
  text-align: center;
  color: var(--text-3);
  padding: 28px 12px !important;
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
