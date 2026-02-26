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
            <button class="btn-primary" @click="handleSearch" :disabled="loading">
              <i class="bi bi-search"></i>
              查询
            </button>
            <button class="btn-secondary" @click="handleReset">
              <i class="bi bi-arrow-counterclockwise"></i>
              重置
            </button>
          </div>
        </div>
        <div class="action-section">
          <button class="btn-primary" @click="handleAdd">
            <i class="bi bi-plus-lg"></i>
            添加微信群
          </button>
        </div>
      </div>

      <!-- 微信群列表 -->
      <div class="wechat-group-list-section">
        <div v-if="loading" class="loading-container">
          <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color);"></i>
          <p style="margin-top: 12px; color: var(--text-secondary);">加载中...</p>
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
                  <button class="btn-icon" @click="handleView(group)" title="查看">
                    <i class="bi bi-eye"></i>
                  </button>
                  <button class="btn-icon" @click="handleEdit(group)" title="编辑">
                    <i class="bi bi-pencil"></i>
                  </button>
                  <button class="btn-icon" @click="handleTest(group)" title="测试发送">
                    <i class="bi bi-send"></i>
                  </button>
                  <button class="btn-icon btn-danger" @click="handleDelete(group)" title="删除">
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

        <!-- 分页 -->
        <div v-if="!loading && total > 0" class="pagination-section">
          <div class="pagination-info">
            共 {{ total }} 条记录，第 {{ currentPage }} / {{ totalPages }} 页
          </div>
          <div class="pagination-controls">
            <button
              class="btn-secondary"
              @click="handlePageChange(currentPage - 1)"
              :disabled="currentPage <= 1"
            >
              上一页
            </button>
            <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
            <button
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

    <!-- 添加/编辑微信群弹框 -->
    <AddWeChatGroupModal
      v-if="showGroupForm"
      :visible="showGroupForm"
      :group="editingGroup"
      @update:visible="showGroupForm = $event"
      @saved="handleGroupSaved"
    />

    <!-- 查看详情弹框 -->
    <div v-if="showViewModal" class="modal-overlay" @click.self="closeViewModal">
      <div class="modal-content view-modal">
        <div class="modal-header">
          <h3>微信群详情</h3>
          <button class="btn-close" @click="closeViewModal">
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
          <button class="btn-secondary" @click="closeViewModal">关闭</button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import Modal from './Modal.vue'
import AddWeChatGroupModal from './AddWeChatGroupModal.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible'])

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

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

onMounted(() => {
  if (props.visible) {
    loadWeChatGroups()
  }
})

async function loadWeChatGroups() {
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

    const response = await fetch(`http://localhost:5005/api/wechat-groups?${new URLSearchParams(params)}`)
    const data = await response.json()

    wechatGroups.value = data.records || []
    total.value = data.total || 0
  } catch (error) {
    console.error('加载微信群配置失败:', error)
    alert('加载微信群配置失败')
  } finally {
    loading.value = false
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
  if (page < 1 || page > totalPages.value) return
  currentPage.value = page
  loadWeChatGroups()
}

function handleAdd() {
  editingGroup.value = null
  showGroupForm.value = true
}

function handleEdit(group) {
  editingGroup.value = { ...group }
  showGroupForm.value = true
}

function handleView(group) {
  viewingGroup.value = group
  showViewModal.value = true
}

function closeViewModal() {
  showViewModal.value = false
  viewingGroup.value = null
}

async function handleTest(group) {
  if (!confirm(`确定要测试发送通知到 "${group.groupName}" 吗?`)) {
    return
  }

  try {
    const response = await fetch(`http://localhost:5005/api/wechat-groups/${group.id}/test`, {
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
    const response = await fetch(`http://localhost:5005/api/wechat-groups/${group.id}`, {
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

function handleGroupSaved() {
  showGroupForm.value = false
  editingGroup.value = null
  loadWeChatGroups()
}

function handleClose() {
  emit('update:visible', false)
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
  gap: 20px;
}

.search-section {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  padding: 20px;
  background: var(--card-bg);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.search-form {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  flex: 1;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.form-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--input-bg);
  color: var(--text-primary);
  font-size: 14px;
  min-width: 180px;
}

.action-section {
  display: flex;
  gap: 10px;
}

.btn-primary, .btn-secondary {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-secondary {
  background: var(--secondary-bg);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--hover-bg);
}

.btn-primary:disabled, .btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wechat-group-list-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--card-bg);
  border-radius: 8px;
  overflow: hidden;
}

.data-table thead {
  background: var(--secondary-bg);
}

.data-table th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-color);
}

.data-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  font-size: 14px;
}

.data-table tbody tr:hover {
  background: var(--hover-bg);
}

.text-truncate {
  max-width: 300px;
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
  background: var(--secondary-bg);
  color: var(--text-secondary);
}

.btn-icon {
  padding: 6px 8px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-icon:hover {
  background: var(--hover-bg);
  color: var(--primary-color);
}

.btn-icon.btn-danger:hover {
  color: #ef4444;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-secondary);
}

.pagination-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--card-bg);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.pagination-info {
  font-size: 14px;
  color: var(--text-secondary);
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-info {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

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
  z-index: 2000;
}

.modal-content {
  background: var(--card-bg);
  border-radius: 12px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
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
  color: var(--text-secondary);
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-close:hover {
  background: var(--hover-bg);
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
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
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: 6px;
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
  word-break: break-all;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
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



