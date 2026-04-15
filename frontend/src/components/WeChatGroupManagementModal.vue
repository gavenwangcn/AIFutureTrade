<template>
  <Modal
    :visible="visible"
    title="微信通知群管理"
    extraLarge
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="wechat-group-management-container">
      <!-- 查询条件区域 -->
      <div class="search-section">
        <div class="search-form">
          <div class="form-group">
            <label>群组名称</label>
            <input
              v-model="searchForm.groupName"
              type="text"
              class="form-input"
              placeholder="请输入群组名称"
              @keyup.enter="handleSearch"
            />
          </div>
          <div class="form-group">
            <label>启用状态</label>
            <select v-model="searchForm.isEnabled" class="form-input">
              <option value="">全部</option>
              <option value="true">启用</option>
              <option value="false">禁用</option>
            </select>
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
          <button class="btn-primary" type="button" @click="handleAdd">
            <i class="bi bi-plus-lg"></i>
            添加微信群
          </button>
        </div>
      </div>

      <!-- 微信群列表 -->
      <div class="wechat-group-list-section">
        <div v-if="loading" class="loading-container">
          <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary);"></i>
          <p style="margin-top: 12px; color: var(--text-2);">加载中...</p>
        </div>
        <div v-else class="wechat-group-table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>群组名称</th>
                <th>Webhook URL</th>
                <th>告警类型</th>
                <th>启用状态</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="group in wechatGroups" :key="group.id">
                <td><strong>{{ group.groupName }}</strong></td>
                <td class="text-truncate" :title="group.webhookUrl">
                  {{ truncateText(group.webhookUrl, 40) }}
                </td>
                <td class="text-truncate" :title="group.alertTypes">
                  {{ group.alertTypes || '全部' }}
                </td>
                <td>
                  <span :class="['badge', group.isEnabled ? 'badge-success' : 'badge-secondary']">
                    {{ group.isEnabled ? '启用' : '禁用' }}
                  </span>
                </td>
                <td>{{ formatDateTime(group.createdAt) }}</td>
                <td>
                  <button type="button" class="btn-icon" @click="handleView(group)" title="查看">
                    <i class="bi bi-eye"></i>
                  </button>
                  <button type="button" class="btn-icon" @click="handleEdit(group)" title="编辑">
                    <i class="bi bi-pencil"></i>
                  </button>
                  <button type="button" class="btn-icon" @click="handleTest(group)" title="测试发送">
                    <i class="bi bi-send"></i>
                  </button>
                  <button type="button" class="btn-icon btn-danger" @click="handleDelete(group)" title="删除">
                    <i class="bi bi-trash"></i>
                  </button>
                </td>
              </tr>
              <tr v-if="wechatGroups.length === 0">
                <td colspan="6" class="empty-state">暂无微信群配置</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="!loading && total > 0" class="pagination-section">
          <div class="pagination-info">
            共 {{ total }} 条记录，第 {{ currentPage }} / {{ totalPages }} 页
          </div>
          <div class="pagination-controls">
            <button
              type="button"
              class="btn-secondary"
              @click="handlePageChange(currentPage - 1)"
              :disabled="currentPage <= 1"
            >
              上一页
            </button>
            <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
            <button
              type="button"
              class="btn-secondary"
              @click="handlePageChange(currentPage + 1)"
              :disabled="currentPage >= totalPages"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑：与 StrategyManagementModal 一致，内联 overlay，避免嵌套子组件重复遮罩 -->
    <div v-if="showGroupForm" class="modal-overlay modal-overlay-nested" @click.self="closeGroupForm">
      <div class="modal-content strategy-form-modal">
        <div class="modal-header">
          <h3>{{ editingGroup ? '编辑微信群' : '添加微信群' }}</h3>
          <button type="button" class="btn-close" @click="closeGroupForm">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div v-if="formError" class="alert alert-error">{{ formError }}</div>

          <div class="form-group">
            <label>群组名称 <span class="required">*</span></label>
            <input
              v-model="groupForm.groupName"
              type="text"
              class="form-input"
              placeholder="请输入群组名称"
            />
          </div>

          <div class="form-group">
            <label>Webhook URL <span class="required">*</span></label>
            <input
              v-model="groupForm.webhookUrl"
              type="text"
              class="form-input"
              placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
            />
            <div class="form-hint">企业微信机器人的 Webhook 地址</div>
          </div>

          <div class="form-group">
            <label>告警类型</label>
            <div class="checkbox-group">
              <label class="checkbox-item">
                <input type="checkbox" value="TICKER_SYNC_TIMEOUT" v-model="selectedAlertTypes" />
                <span>Ticker同步超时</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" value="CONTAINER_RESTART" v-model="selectedAlertTypes" />
                <span>容器重启</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" value="SERVICE_ERROR" v-model="selectedAlertTypes" />
                <span>服务错误</span>
              </label>
              <label class="checkbox-item">
                <input type="checkbox" value="TRADE_ALERT" v-model="selectedAlertTypes" />
                <span>交易告警（含盯盘通知）</span>
              </label>
            </div>
            <div class="form-hint">不选择则接收所有类型的告警</div>
          </div>

          <div class="form-group">
            <label class="checkbox-item">
              <input type="checkbox" v-model="groupForm.isEnabled" />
              <span>启用此配置</span>
            </label>
          </div>

          <div class="form-group">
            <label>描述</label>
            <textarea
              v-model="groupForm.description"
              class="form-textarea"
              rows="3"
              placeholder="请输入描述信息(可选)"
            ></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="closeGroupForm">取消</button>
          <button type="button" class="btn-primary" @click="handleSaveGroup" :disabled="savingGroup">
            {{ savingGroup ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 查看详情 -->
    <div v-if="showViewModal" class="modal-overlay modal-overlay-nested" @click.self="closeViewModal">
      <div class="modal-content strategy-form-modal">
        <div class="modal-header">
          <h3>微信群详情</h3>
          <button type="button" class="btn-close" @click="closeViewModal">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="detail-item">
            <label>群组名称</label>
            <div class="detail-value">{{ viewingGroup?.groupName }}</div>
          </div>
          <div class="detail-item">
            <label>Webhook URL</label>
            <div class="detail-value">{{ viewingGroup?.webhookUrl }}</div>
          </div>
          <div class="detail-item">
            <label>告警类型</label>
            <div class="detail-value">{{ viewingGroup?.alertTypes || '全部' }}</div>
          </div>
          <div class="detail-item">
            <label>启用状态</label>
            <div class="detail-value">
              <span :class="['badge', viewingGroup?.isEnabled ? 'badge-success' : 'badge-secondary']">
                {{ viewingGroup?.isEnabled ? '启用' : '禁用' }}
              </span>
            </div>
          </div>
          <div class="detail-item">
            <label>描述</label>
            <div class="detail-value">{{ viewingGroup?.description || '无' }}</div>
          </div>
          <div class="detail-item">
            <label>创建时间</label>
            <div class="detail-value">{{ formatDateTime(viewingGroup?.createdAt) }}</div>
          </div>
          <div class="detail-item">
            <label>更新时间</label>
            <div class="detail-value">{{ formatDateTime(viewingGroup?.updatedAt) }}</div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="closeViewModal">关闭</button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import Modal from './Modal.vue'
import { tradeMonitorUrl } from '../config/tradeMonitorApi.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close'])

const loading = ref(false)
const wechatGroups = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

const searchForm = ref({
  groupName: '',
  isEnabled: ''
})

const showGroupForm = ref(false)
const editingGroup = ref(null)
const showViewModal = ref(false)
const viewingGroup = ref(null)

const groupForm = ref({
  groupName: '',
  webhookUrl: '',
  alertTypes: '',
  isEnabled: true,
  description: ''
})
const selectedAlertTypes = ref([])
const formError = ref('')
const savingGroup = ref(false)

/** 与后端 eventType 一致；兼容旧数据中的小写写法 */
const ALERT_TYPE_ALIASES = {
  ticker_sync_timeout: 'TICKER_SYNC_TIMEOUT',
  container_restart: 'CONTAINER_RESTART',
  service_error: 'SERVICE_ERROR',
  trade_alert: 'TRADE_ALERT'
}

function normalizeAlertTypeToken(t) {
  const s = (t || '').trim()
  return ALERT_TYPE_ALIASES[s] || s
}

let listAbortController = null

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

watch(selectedAlertTypes, (newTypes) => {
  groupForm.value.alertTypes = newTypes.join(',')
}, { deep: true })

function resetGroupFormFields() {
  groupForm.value = {
    groupName: '',
    webhookUrl: '',
    alertTypes: '',
    isEnabled: true,
    description: ''
  }
  selectedAlertTypes.value = []
  formError.value = ''
}

function fillGroupFormFromEditing() {
  const g = editingGroup.value
  if (!g) {
    resetGroupFormFields()
    return
  }
  groupForm.value = {
    groupName: g.groupName || '',
    webhookUrl: g.webhookUrl || '',
    alertTypes: g.alertTypes || '',
    isEnabled: g.isEnabled !== false,
    description: g.description || ''
  }
  selectedAlertTypes.value = g.alertTypes
    ? g.alertTypes.split(',').map((x) => normalizeAlertTypeToken(x)).filter(Boolean)
    : []
}

function closeGroupForm() {
  showGroupForm.value = false
  editingGroup.value = null
  resetGroupFormFields()
}

function closeViewModal() {
  showViewModal.value = false
  viewingGroup.value = null
}

/** 与 StrategyManagementModal.handleClose 一致：先收子层，再关主窗并通知 App */
function handleClose() {
  listAbortController?.abort()
  listAbortController = null
  closeGroupForm()
  closeViewModal()
  emit('update:visible', false)
  emit('close')
}

watch(
  () => props.visible,
  (open) => {
    if (open) {
      loadWeChatGroups()
    } else {
      listAbortController?.abort()
      listAbortController = null
      loading.value = false
      closeGroupForm()
      closeViewModal()
    }
  },
  { immediate: true }
)

async function loadWeChatGroups() {
  listAbortController?.abort()
  listAbortController = new AbortController()
  const signal = listAbortController.signal

  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      size: pageSize.value
    }

    if (searchForm.value.groupName) {
      params.groupName = searchForm.value.groupName
    }

    if (searchForm.value.isEnabled !== '') {
      params.isEnabled = searchForm.value.isEnabled === 'true'
    }

    const q = new URLSearchParams(params)
    const response = await fetch(tradeMonitorUrl(`/api/wechat-groups?${q}`), { signal })
    const data = await response.json()

    wechatGroups.value = data.records || []
    total.value = data.total || 0
  } catch (error) {
    if (error?.name === 'AbortError') {
      return
    }
    console.error('加载微信群配置失败:', error)
    alert('加载微信群配置失败')
  } finally {
    if (!signal.aborted) {
      loading.value = false
    }
  }
}

function handleSearch() {
  currentPage.value = 1
  loadWeChatGroups()
}

function handleReset() {
  searchForm.value = {
    groupName: '',
    isEnabled: ''
  }
  currentPage.value = 1
  loadWeChatGroups()
}

function handlePageChange(page) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    loadWeChatGroups()
  }
}

function handleAdd() {
  editingGroup.value = null
  resetGroupFormFields()
  showGroupForm.value = true
}

function handleEdit(group) {
  editingGroup.value = { ...group }
  fillGroupFormFromEditing()
  showGroupForm.value = true
}

function handleView(group) {
  viewingGroup.value = group
  showViewModal.value = true
}

async function handleTest(group) {
  if (!confirm(`确定要测试发送通知到 "${group.groupName}" 吗?`)) {
    return
  }

  try {
    const response = await fetch(tradeMonitorUrl(`/api/wechat-groups/${group.id}/test`), {
      method: 'POST'
    })
    const data = await response.json()

    if (data.success) {
      alert('测试发送成功')
    } else {
      alert('测试发送失败: ' + data.message)
    }
  } catch (error) {
    console.error('测试发送失败:', error)
    alert('测试发送失败')
  }
}

async function handleDelete(group) {
  if (!confirm(`确定要删除微信群 "${group.groupName}" 吗?`)) {
    return
  }

  try {
    const response = await fetch(tradeMonitorUrl(`/api/wechat-groups/${group.id}`), {
      method: 'DELETE'
    })
    const data = await response.json()

    if (data.success) {
      alert('删除成功')
      loadWeChatGroups()
    } else {
      alert('删除失败: ' + data.message)
    }
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败')
  }
}

function validateGroupForm() {
  if (!groupForm.value.groupName.trim()) {
    formError.value = '请输入群组名称'
    return false
  }

  if (!groupForm.value.webhookUrl.trim()) {
    formError.value = '请输入Webhook URL'
    return false
  }

  if (!groupForm.value.webhookUrl.startsWith('http')) {
    formError.value = 'Webhook URL格式不正确，必须以http开头'
    return false
  }

  formError.value = ''
  return true
}

async function handleSaveGroup() {
  if (!validateGroupForm()) {
    return
  }

  savingGroup.value = true
  formError.value = ''

  try {
    const url = editingGroup.value
      ? tradeMonitorUrl(`/api/wechat-groups/${editingGroup.value.id}`)
      : tradeMonitorUrl('/api/wechat-groups')

    const method = editingGroup.value ? 'PUT' : 'POST'

    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(groupForm.value)
    })

    if (!response.ok) {
      throw new Error('保存失败')
    }

    closeGroupForm()
    loadWeChatGroups()
  } catch (err) {
    console.error('保存失败:', err)
    formError.value = '保存失败: ' + (err.message || '未知错误')
  } finally {
    savingGroup.value = false
  }
}

function truncateText(text, maxLength) {
  if (!text) return ''
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}

function formatDateTime(dateTime) {
  if (!dateTime) return ''
  const date = new Date(dateTime)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}
</script>

<style scoped>
.wechat-group-management-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
  height: 100%;
}

.search-section {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  background: var(--bg-2);
  border-radius: var(--radius);
}

.search-form {
  display: flex;
  gap: 16px;
  flex: 1;
  align-items: flex-end;
}

.search-form .form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 150px;
}

.search-form .form-group label {
  font-size: 13px;
  color: var(--text-2);
  font-weight: 500;
}

.action-section {
  display: flex;
  gap: 8px;
}

.wechat-group-list-section {
  flex: 1;
  overflow: auto;
}

.wechat-group-table-container {
  overflow-x: auto;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.text-truncate {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badge-success {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.badge-secondary {
  background: var(--bg-2);
  color: var(--text-2);
}

.btn-icon {
  background: transparent;
  border: none;
  color: var(--text-2);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius);
  transition: all 0.2s;
}

.btn-icon:hover {
  background: var(--bg-2);
  color: var(--primary);
}

.btn-icon.btn-danger:hover {
  color: #dc3545;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-2);
  font-size: 14px;
}

.pagination-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  margin-top: 16px;
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
  padding: 0 12px;
  color: var(--text-2);
  font-size: 14px;
}

/* 与 StrategyManagementModal 子弹层一致，叠在主 Modal(z-index:1000) 之上 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-overlay-nested {
  z-index: 1100;
}

.strategy-form-modal {
  background: var(--bg-1);
  border-radius: var(--radius);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid var(--border-1);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.btn-close {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-2);
  padding: 4px;
  border-radius: var(--radius);
  transition: all 0.2s;
}

.btn-close:hover {
  background: var(--bg-2);
  color: var(--primary);
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid var(--border-1);
}

.detail-item {
  margin-bottom: 20px;
}

.detail-item:last-child {
  margin-bottom: 0;
}

.detail-item label {
  display: block;
  font-size: 13px;
  color: var(--text-2);
  font-weight: 500;
  margin-bottom: 6px;
}

.detail-value {
  font-size: 14px;
  color: var(--text-1);
  word-break: break-all;
}

.alert {
  padding: 12px 14px;
  border-radius: 10px;
  margin-bottom: 18px;
  font-size: 13px;
  border: 1px solid transparent;
}

.alert-error {
  background: rgba(245, 63, 63, 0.1);
  color: var(--danger);
  border-color: rgba(245, 63, 63, 0.3);
}

.form-group {
  margin-bottom: 20px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-group > label:not(.checkbox-item) {
  display: block;
  font-size: 14px;
  color: var(--text-1);
  font-weight: 500;
  margin-bottom: 8px;
}

.required {
  color: #dc3545;
}

.form-input {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius);
  font-size: 14px;
  background: var(--bg-1);
  color: var(--text-1);
}

.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.1);
}

.form-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  background: var(--bg-1);
  color: var(--text-1);
}

.form-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.1);
}

.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-2);
  font-style: italic;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-1);
}

.checkbox-item input[type='checkbox'] {
  cursor: pointer;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
