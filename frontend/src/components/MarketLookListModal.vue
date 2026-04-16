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
          <div class="form-group">
            <label>类型（执行状态）</label>
            <select v-model="searchForm.executionStatus" class="form-input">
              <option value="">全部</option>
              <option value="RUNNING">RUNNING</option>
              <option value="SENDING">SENDING</option>
              <option value="ENDED">ENDED</option>
            </select>
          </div>
          <div class="form-group flex-grow">
            <label>摘要</label>
            <input
              v-model="searchForm.detailSummary"
              type="text"
              class="form-input"
              placeholder="详情摘要关键字"
              @keyup.enter="handleSearch"
            />
          </div>
          <div class="form-group">
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
        <div class="action-section">
          <button class="btn-primary" type="button" @click="showAddMarketLookModal = true">
            <i class="bi bi-plus-lg"></i>
            添加盯盘
          </button>
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
                <td>
                  <button
                    type="button"
                    class="btn-icon btn-danger"
                    :disabled="deletingId === row.id"
                    title="删除"
                    @click="handleDelete(row)"
                  >
                    <i class="bi bi-trash"></i>
                  </button>
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

    <AddMarketLookModal
      :visible="showAddMarketLookModal"
      @update:visible="showAddMarketLookModal = $event"
      @saved="onAddSaved"
    />
  </Modal>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import Modal from './Modal.vue'
import AddMarketLookModal from './AddMarketLookModal.vue'
import { marketLookApi } from '../services/api.js'

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

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

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
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px;
  background: var(--bg-2);
  border-radius: var(--radius);
}

.search-form {
  display: flex;
  gap: 16px;
  flex: 1;
  flex-wrap: wrap;
  align-items: flex-end;
}

.search-form .form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 140px;
}

.search-form .form-group.flex-grow {
  flex: 1;
  min-width: 200px;
}

.search-form label {
  font-size: 13px;
  color: var(--text-2);
  font-weight: 500;
}

.action-section {
  display: flex;
  gap: 8px;
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
</style>
