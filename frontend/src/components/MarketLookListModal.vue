<template>
  <Modal
    :visible="visible"
    title="盯盘任务列表"
    extraLarge
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="market-look-list-container">
      <div class="search-section">
        <div class="search-form">
          <div class="form-group form-group--status">
            <label>类型（执行状态）</label>
            <select v-model="searchForm.executionStatus" class="form-input">
              <option value="">全部</option>
              <option value="RUNNING">RUNNING</option>
              <option value="SENDING">SENDING</option>
              <option value="ENDED">ENDED</option>
            </select>
          </div>
          <div class="form-group form-group--summary">
            <label>摘要</label>
            <input
              v-model="searchForm.detailSummary"
              type="text"
              class="form-input"
              placeholder="详情摘要关键字"
              @keyup.enter="handleSearch"
            />
          </div>
          <div class="form-group form-group--search-btns">
            <label class="form-label-placeholder" aria-hidden="true">&nbsp;</label>
            <div class="btn-row">
              <button class="btn-primary" type="button" @click="handleSearch" :disabled="loading">
                <i class="bi bi-search"></i>
                查询
              </button>
              <button class="btn-secondary" type="button" @click="handleReset">
                <i class="bi bi-arrow-counterclockwise"></i>
                重置
              </button>
            </div>
          </div>
          <div class="form-group form-group--add">
            <label class="form-label-placeholder" aria-hidden="true">&nbsp;</label>
            <button class="btn-primary" type="button" @click="showAddMarketLookModal = true">
              <i class="bi bi-plus-lg"></i>
              添加盯盘
            </button>
          </div>
        </div>
      </div>

      <div class="list-section">
        <div v-if="loading" class="loading-container">
          <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color)"></i>
          <p style="margin-top: 12px; color: var(--text-secondary)">加载中...</p>
        </div>
        <div v-else class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>执行状态</th>
                <th>合约</th>
                <th>策略名称</th>
                <th>详情摘要</th>
                <th>开始时间</th>
                <th>结束时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.id">
                <td>
                  <span class="exec-pill" :class="statusClass(row)">{{ row.execution_status || row.executionStatus || '—' }}</span>
                </td>
                <td>{{ row.symbol || '—' }}</td>
                <td class="text-truncate" :title="row.strategy_name || row.strategyName">{{ row.strategy_name || row.strategyName || '—' }}</td>
                <td class="text-truncate" :title="detailSummary(row)">{{ truncate(detailSummary(row), 48) }}</td>
                <td>{{ formatDt(row.started_at ?? row.startedAt) }}</td>
                <td>{{ formatEnded(row) }}</td>
                <td class="cell-actions">
                  <div class="action-btns">
                    <button
                      type="button"
                      class="btn-detail"
                      title="查看详情"
                      @click="openTaskDetail(row)"
                    >
                      查看详情
                    </button>
                    <button
                      type="button"
                      class="btn-icon btn-danger"
                      :disabled="deletingId === row.id"
                      title="删除"
                      @click="handleDelete(row)"
                    >
                      <i class="bi bi-trash"></i>
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="rows.length === 0">
                <td colspan="7" class="empty-state">暂无盯盘任务</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="!loading && total > 0" class="pagination-section">
          <div class="pagination-info">共 {{ total }} 条，第 {{ currentPage }} / {{ totalPages }} 页</div>
          <div class="pagination-controls">
            <button class="btn-secondary" type="button" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
            <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
            <button class="btn-secondary" type="button" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
          </div>
        </div>
      </div>
    </div>
  </Modal>

  <AddMarketLookModal
    :visible="showAddMarketLookModal"
    @update:visible="showAddMarketLookModal = $event"
    @saved="onAddSaved"
  />

  <Modal
      :visible="detailModalVisible"
      title="盯盘任务详情"
      :subtitle="detailModalSubtitle"
      :extra-large="true"
      width="50vw"
      height="50vh"
      @update:visible="detailModalVisible = $event"
      @close="closeTaskDetail"
    >
      <div v-if="detailLoading" class="detail-loading">
        <i class="bi bi-arrow-repeat spin"></i>
        <span>加载中…</span>
      </div>
      <p v-else-if="detailFetchError" class="detail-error">{{ detailFetchError }}</p>
      <div v-else-if="signalDetailRow" class="signal-modal-body">
        <section class="detail-section detail-section--strategy">
          <h4 class="section-label">关联策略</h4>
          <dl class="strategy-meta strategy-meta--task">
            <div class="meta-row">
              <dt>策略名称</dt>
              <dd>{{ taskStrategyNameDisplay }}</dd>
            </div>
          </dl>
          <p class="section-hint muted strategy-code-hint">
            此处仅展示任务关联的策略摘要；完整 Python 策略代码请在「策略管理」中打开对应策略查看。
          </p>
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
            <p v-if="!strategyContextText" class="section-hint muted">该策略暂无文字说明（仍可在策略管理中查看代码）</p>
          </template>
          <p v-else class="section-hint muted">当前任务未关联策略 ID，无法加载策略信息</p>
        </section>

        <div class="detail-divider" role="separator" aria-hidden="true" />

        <section class="detail-section detail-section--signal">
          <h4 class="section-label">运行结果 run_log</h4>
          <pre class="signal-pre">{{ formatSignal(signalDetailRow.signal_result ?? signalDetailRow.signalResult) }}</pre>
        </section>

        <div class="detail-divider" role="separator" aria-hidden="true" />

        <section class="detail-section detail-section--snapshots">
          <h4 class="section-label">通知快照 trade_notify（extra_json）</h4>
          <p v-if="!tradeNotifies.length" class="section-hint muted">暂无通知快照</p>
          <div v-for="n in tradeNotifies" :key="n.id" class="notify-card">
            <div class="notify-card-head">
              <span class="notify-id">#{{ n.id }}</span>
              <span class="notify-time">{{ formatNotifyTime(n.created_at ?? n.createdAt) }}</span>
            </div>
            <div v-if="n.title" class="notify-title">{{ n.title }}</div>
            <pre v-if="n.message" class="notify-msg">{{ n.message }}</pre>
            <div class="notify-extra-label">数据快照 extra_json</div>
            <pre class="notify-extra-pre">{{ formatExtraJson(n.extra_json ?? n.extraJson) }}</pre>
          </div>
        </section>

        <div class="detail-divider" role="separator" aria-hidden="true" />

        <section class="detail-section detail-section--summary">
          <h4 class="section-label">详情摘要</h4>
          <p v-if="!detailSummaryRaw(signalDetailRow)" class="section-hint muted">暂无摘要</p>
          <pre v-else class="summary-pre">{{ detailSummaryRaw(signalDetailRow) }}</pre>
        </section>
      </div>
  </Modal>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import Modal from './Modal.vue'
import AddMarketLookModal from './AddMarketLookModal.vue'
import { marketLookApi, strategyApi } from '../services/api.js'

const PLACEHOLDER_END = '2099-12-31'

const props = defineProps({
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['update:visible', 'close', 'task-saved'])

const searchForm = ref({
  executionStatus: '',
  detailSummary: ''
})

const rows = ref([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const deletingId = ref(null)
const showAddMarketLookModal = ref(false)

const detailModalVisible = ref(false)
const detailLoading = ref(false)
const detailFetchError = ref('')
const signalDetailRow = ref(null)
const tradeNotifies = ref([])
const strategyDetail = ref(null)
const strategyLoading = ref(false)
const strategyFetchError = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const detailModalSubtitle = computed(() => {
  const r = signalDetailRow.value
  if (!r) return ''
  const sym = r.symbol || '—'
  return `数据ID: ${r.id} · 合约: ${sym}`
})

const taskStrategyNameDisplay = computed(() => {
  const r = signalDetailRow.value
  if (!r) return '—'
  const n = (r.strategy_name ?? r.strategyName ?? '').trim()
  return n || '—'
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

function detailSummary(row) {
  return row.detail_summary ?? row.detailSummary ?? ''
}

function truncate(s, n) {
  if (!s) return '—'
  return s.length <= n ? s : s.slice(0, n) + '…'
}

function formatDt(v) {
  if (v == null || v === '') return '—'
  const s = String(v).replace(' ', 'T')
  const d = new Date(s)
  if (!Number.isFinite(d.getTime())) return String(v)
  return d.toLocaleString('zh-CN', { hour12: false })
}

function formatEnded(row) {
  const raw = row.ended_at ?? row.endedAt
  if (raw == null || raw === '') return '—'
  const s = String(raw)
  if (s.includes(PLACEHOLDER_END)) return '—'
  return formatDt(raw)
}

function statusClass(row) {
  const st = row.execution_status || row.executionStatus || ''
  if (st === 'RUNNING') return 'st-running'
  if (st === 'SENDING') return 'st-sending'
  if (st === 'ENDED') return 'st-ended'
  return ''
}

function detailSummaryRaw(row) {
  if (!row) return ''
  const v = row.detail_summary ?? row.detailSummary
  if (v == null || String(v).trim() === '') return ''
  return String(v).trim()
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

function formatExtraJson(raw) {
  if (raw == null || raw === '') return '（空）'
  const s = String(raw).trim()
  try {
    const o = JSON.parse(s)
    return JSON.stringify(o, null, 2)
  } catch {
    return s
  }
}

function formatNotifyTime(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(String(iso).replace(' ', 'T'))
    if (!Number.isFinite(d.getTime())) return String(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return String(iso)
  }
}

async function openTaskDetail(row) {
  if (!row?.id) return
  detailModalVisible.value = true
  detailLoading.value = true
  detailFetchError.value = ''
  signalDetailRow.value = null
  tradeNotifies.value = []
  strategyDetail.value = null
  strategyFetchError.value = ''
  strategyLoading.value = true
  try {
    const data = await marketLookApi.getTaskDetail(row.id)
    const ml = data?.marketLook ?? data?.market_look
    if (!ml?.id) {
      detailFetchError.value = '未获取到任务数据'
      return
    }
    signalDetailRow.value = ml
    tradeNotifies.value = Array.isArray(data?.tradeNotifies) ? data.tradeNotifies : data?.trade_notifies || []

    const sid = String(ml.strategy_id ?? ml.strategyId ?? '').trim()
    if (!sid) {
      strategyLoading.value = false
      return
    }
    try {
      strategyDetail.value = await strategyApi.getById(sid)
    } catch (e) {
      console.warn('[MarketLookListModal] strategy getById', e)
      strategyFetchError.value = e?.message || '加载策略失败'
    } finally {
      strategyLoading.value = false
    }
  } catch (e) {
    console.error('[MarketLookListModal] getTaskDetail', e)
    detailFetchError.value = e?.message || '加载详情失败'
    strategyLoading.value = false
  } finally {
    detailLoading.value = false
  }
}

function closeTaskDetail() {
  detailModalVisible.value = false
  signalDetailRow.value = null
  tradeNotifies.value = []
  strategyDetail.value = null
  strategyFetchError.value = ''
  detailFetchError.value = ''
}

async function loadList() {
  loading.value = true
  try {
    const params = {
      pageNum: currentPage.value,
      pageSize: pageSize.value
    }
    if (searchForm.value.executionStatus) {
      params.execution_status = searchForm.value.executionStatus
    }
    if (searchForm.value.detailSummary && searchForm.value.detailSummary.trim()) {
      params.detail_summary = searchForm.value.detailSummary.trim()
    }
    const result = await marketLookApi.page(params)
    rows.value = result.data || []
    total.value = Number(result.total) || 0
  } catch (e) {
    console.error('[MarketLookListModal]', e)
    alert('加载失败: ' + (e.message || '未知错误'))
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  currentPage.value = 1
  loadList()
}

function handleReset() {
  searchForm.value = { executionStatus: '', detailSummary: '' }
  currentPage.value = 1
  loadList()
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  currentPage.value = p
  loadList()
}

async function handleDelete(row) {
  if (!row?.id) return
  if (!window.confirm('确定删除该盯盘任务？删除后不可恢复。')) return
  deletingId.value = row.id
  try {
    const res = await marketLookApi.delete(row.id)
    if (res?.success && res?.verifiedAbsent) {
      if (signalDetailRow.value?.id === row.id) {
        closeTaskDetail()
      }
      emit('task-saved')
      await loadList()
    } else {
      alert(res?.message || res?.error || '删除失败')
    }
  } catch (e) {
    alert(e?.message || '删除失败')
  } finally {
    deletingId.value = null
  }
}

function onAddSaved() {
  showAddMarketLookModal.value = false
  emit('task-saved')
  loadList()
}

function handleClose() {
  emit('update:visible', false)
  emit('close')
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      loadList()
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.market-look-list-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 320px;
}

.search-section {
  padding: 16px;
  background: var(--bg-2);
  border-radius: var(--radius);
}

.search-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px 16px;
}

.search-form .form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group--status {
  flex: 0 0 auto;
  min-width: 160px;
  max-width: 200px;
}

/* 摘要关键字：固定窄宽度，避免在 extraLarge 弹窗里被拉成整行 */
.form-group--summary {
  flex: 0 0 auto;
  width: 200px;
  max-width: min(200px, calc(100vw - 120px));
}

.form-group--summary .form-input {
  width: 100%;
  max-width: 200px;
  min-width: 0;
  box-sizing: border-box;
}

.form-group--search-btns .btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.form-group--add {
  flex: 0 0 auto;
  margin-left: auto;
}

.form-label-placeholder {
  visibility: hidden;
  font-size: 13px;
  line-height: 1.2;
  min-height: 1.2em;
  user-select: none;
}

.search-form label:not(.form-label-placeholder) {
  font-size: 13px;
  color: var(--text-2);
  font-weight: 500;
}

.list-section {
  flex: 1;
  overflow: auto;
}

.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th,
.data-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-1);
  text-align: left;
}

.data-table th {
  background: var(--bg-2);
  font-weight: 600;
}

.text-truncate {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-state {
  text-align: center;
  color: var(--text-3);
  padding: 32px !important;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
}

.pagination-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  margin-top: 8px;
  border-top: 1px solid var(--border-1);
}

.pagination-info {
  color: var(--text-2);
  font-size: 14px;
}

.pagination-controls {
  display: flex;
  gap: 12px;
  align-items: center;
}

.page-info {
  color: var(--text-2);
  font-size: 14px;
}

.exec-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.exec-pill.st-running {
  background: rgba(46, 204, 113, 0.2);
  color: #27ae60;
}

.exec-pill.st-sending {
  background: rgba(52, 152, 219, 0.2);
  color: #2980b9;
}

.exec-pill.st-ended {
  background: rgba(149, 165, 166, 0.25);
  color: #7f8c8d;
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.cell-actions {
  white-space: nowrap;
  vertical-align: middle;
}

.action-btns {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.btn-detail {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid rgba(51, 112, 255, 0.45);
  background: rgba(51, 112, 255, 0.08);
  color: var(--primary-color, #3370ff);
  cursor: pointer;
}

.btn-detail:hover {
  background: rgba(51, 112, 255, 0.14);
}

.detail-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-secondary);
}

.detail-error {
  color: #c0392b;
  padding: 16px;
  margin: 0;
}

.signal-modal-body {
  max-height: min(46vh, 640px);
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
  color: var(--text-1, inherit);
}

.section-hint {
  margin: 0;
  font-size: 12px;
}

.muted {
  color: var(--text-3, #888);
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

.strategy-meta--task {
  margin-top: -4px;
  margin-bottom: 10px;
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
  color: var(--text-3, #888);
  font-weight: 500;
}

.meta-row dd {
  margin: 0;
  color: var(--text-1, inherit);
}

.strategy-block {
  margin-bottom: 12px;
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

.strategy-code-hint {
  margin: 0 0 10px;
  line-height: 1.45;
  font-size: 12px;
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

.cell-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.notify-card {
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--border-1, rgba(0, 0, 0, 0.1));
  border-radius: 8px;
  background: var(--bg-2, #fafbfc);
}

.notify-card:last-child {
  margin-bottom: 0;
}

.notify-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-2);
}

.notify-id {
  font-family: ui-monospace, Menlo, monospace;
  font-weight: 600;
}

.notify-time {
  color: var(--text-3);
}

.notify-title {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 13px;
}

.notify-msg {
  margin: 0 0 10px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 6px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow: auto;
}

.notify-extra-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 6px;
}

.notify-extra-pre {
  margin: 0;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--border-1, rgba(0, 0, 0, 0.08));
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  max-height: min(32vh, 360px);
  overflow: auto;
}
</style>
