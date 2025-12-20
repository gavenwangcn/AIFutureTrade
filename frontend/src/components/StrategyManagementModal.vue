<template>
  <Modal
    :visible="visible"
    title="策略管理"
    extraLarge
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="strategy-management-container">
      <!-- 查询条件区域 -->
      <div class="search-section">
        <div class="search-form">
          <div class="form-group">
            <label>策略名称</label>
            <input 
              v-model="searchForm.name" 
              type="text" 
              class="form-input" 
              placeholder="请输入策略名称"
              @keyup.enter="handleSearch"
            />
          </div>
          <div class="form-group">
            <label>策略类型</label>
            <select v-model="searchForm.type" class="form-input">
              <option value="">全部</option>
              <option value="buy">买</option>
              <option value="sell">卖</option>
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
          <button class="btn-primary" @click="handleAddStrategy">
            <i class="bi bi-plus-lg"></i>
            添加策略
          </button>
        </div>
      </div>

      <!-- 策略列表 -->
      <div class="strategy-list-section">
        <div v-if="loading" class="loading-container">
          <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary-color);"></i>
          <p style="margin-top: 12px; color: var(--text-secondary);">加载中...</p>
        </div>
        <div v-else class="strategy-table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>策略名称</th>
                <th>策略类型</th>
                <th>策略内容</th>
                <th>策略代码</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="strategy in strategies" :key="strategy.id">
                <td><strong>{{ strategy.name }}</strong></td>
                <td>
                  <span :class="['badge', strategy.type === 'buy' ? 'badge-long' : 'badge-short']">
                    {{ strategy.type === 'buy' ? '买' : '卖' }}
                  </span>
                </td>
                <td class="text-truncate" :title="strategy.strategy_context">
                  {{ truncateText(strategy.strategy_context, 50) }}
                </td>
                <td class="text-truncate" :title="strategy.strategy_code">
                  {{ truncateText(strategy.strategy_code, 50) }}
                </td>
                <td>{{ formatDateTime(strategy.created_at) }}</td>
                <td>
                  <button class="btn-icon" @click="handleEdit(strategy)" title="编辑">
                    <i class="bi bi-pencil"></i>
                  </button>
                  <button class="btn-icon btn-danger" @click="handleDelete(strategy)" title="删除">
                    <i class="bi bi-trash"></i>
                  </button>
                </td>
              </tr>
              <tr v-if="strategies.length === 0">
                <td colspan="6" class="empty-state">暂无策略数据</td>
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

    <!-- 添加/编辑策略弹框 -->
    <div v-if="showStrategyForm" class="modal-overlay" @click.self="closeStrategyForm">
      <div class="modal-content strategy-form-modal">
        <div class="modal-header">
          <h3>{{ editingStrategy ? '编辑策略' : '添加策略' }}</h3>
          <button class="btn-close" @click="closeStrategyForm">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div v-if="formError" class="alert alert-error">{{ formError }}</div>
          <div class="form-group">
            <label>策略名称 <span class="required">*</span></label>
            <input 
              v-model="strategyForm.name" 
              type="text" 
              class="form-input" 
              placeholder="请输入策略名称"
            />
          </div>
          <div class="form-group">
            <label>策略类型 <span class="required">*</span></label>
            <select v-model="strategyForm.type" class="form-input">
              <option value="">请选择</option>
              <option value="buy">买</option>
              <option value="sell">卖</option>
            </select>
          </div>
          <div class="form-group">
            <label>策略内容</label>
            <textarea 
              v-model="strategyForm.strategy_context" 
              class="form-textarea" 
              rows="5"
              placeholder="请输入策略内容"
            ></textarea>
          </div>
          <div class="form-group">
            <label>策略代码</label>
            <textarea 
              v-model="strategyForm.strategy_code" 
              class="form-textarea" 
              rows="5"
              placeholder="请输入策略代码"
            ></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="closeStrategyForm">取消</button>
          <button class="btn-primary" @click="handleSaveStrategy" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import Modal from './Modal.vue'
import { strategyApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close'])

// 查询表单
const searchForm = ref({
  name: '',
  type: ''
})

// 策略列表
const strategies = ref([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

// 策略表单
const showStrategyForm = ref(false)
const editingStrategy = ref(null)
const strategyForm = ref({
  name: '',
  type: '',
  strategy_context: '',
  strategy_code: ''
})
const formError = ref('')
const saving = ref(false)

// 计算总页数
const totalPages = computed(() => {
  return Math.ceil(total.value / pageSize.value)
})

// 加载策略列表
const loadStrategies = async () => {
  loading.value = true
  try {
    const result = await strategyApi.getPage({
      pageNum: currentPage.value,
      pageSize: pageSize.value,
      name: searchForm.value.name || undefined,
      type: searchForm.value.type || undefined
    })
    strategies.value = result.data || []
    total.value = result.total || 0
  } catch (err) {
    console.error('[StrategyManagementModal] Error loading strategies:', err)
    alert('加载策略列表失败: ' + (err.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 查询
const handleSearch = () => {
  currentPage.value = 1
  loadStrategies()
}

// 重置
const handleReset = () => {
  searchForm.value = {
    name: '',
    type: ''
  }
  currentPage.value = 1
  loadStrategies()
}

// 分页
const handlePageChange = (page) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    loadStrategies()
  }
}

// 添加策略
const handleAddStrategy = () => {
  editingStrategy.value = null
  strategyForm.value = {
    name: '',
    type: '',
    strategy_context: '',
    strategy_code: ''
  }
  formError.value = ''
  showStrategyForm.value = true
}

// 编辑策略
const handleEdit = (strategy) => {
  editingStrategy.value = strategy
  strategyForm.value = {
    name: strategy.name || '',
    type: strategy.type || '',
    strategy_context: strategy.strategy_context || '',
    strategy_code: strategy.strategy_code || ''
  }
  formError.value = ''
  showStrategyForm.value = true
}

// 删除策略
const handleDelete = async (strategy) => {
  if (!confirm(`确定要删除策略"${strategy.name}"吗？`)) {
    return
  }
  
  loading.value = true
  try {
    await strategyApi.delete(strategy.id)
    alert('删除成功')
    await loadStrategies()
  } catch (err) {
    console.error('[StrategyManagementModal] Error deleting strategy:', err)
    alert('删除失败: ' + (err.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 保存策略
const handleSaveStrategy = async () => {
  formError.value = ''
  
  if (!strategyForm.value.name || !strategyForm.value.name.trim()) {
    formError.value = '请输入策略名称'
    return
  }
  
  if (!strategyForm.value.type) {
    formError.value = '请选择策略类型'
    return
  }
  
  saving.value = true
  try {
    if (editingStrategy.value) {
      // 更新
      await strategyApi.update(editingStrategy.value.id, {
        name: strategyForm.value.name.trim(),
        type: strategyForm.value.type,
        strategyContext: strategyForm.value.strategy_context || null,
        strategyCode: strategyForm.value.strategy_code || null
      })
      alert('更新成功')
    } else {
      // 新增
      await strategyApi.create({
        name: strategyForm.value.name.trim(),
        type: strategyForm.value.type,
        strategyContext: strategyForm.value.strategy_context || null,
        strategyCode: strategyForm.value.strategy_code || null
      })
      alert('添加成功')
    }
    closeStrategyForm()
    await loadStrategies()
  } catch (err) {
    console.error('[StrategyManagementModal] Error saving strategy:', err)
    formError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// 关闭策略表单
const closeStrategyForm = () => {
  showStrategyForm.value = false
  editingStrategy.value = null
  formError.value = ''
}

// 关闭模态框
const handleClose = () => {
  closeStrategyForm()
  emit('update:visible', false)
  emit('close')
}

// 文本截断
const truncateText = (text, maxLength) => {
  if (!text) return '-'
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}

// 格式化日期时间
const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  const date = new Date(dateTime)
  return date.toLocaleString('zh-CN')
}

// 监听 visible 变化，加载数据
watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadStrategies()
  }
})
</script>

<style scoped>
.strategy-management-container {
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

.strategy-list-section {
  flex: 1;
  overflow: auto;
}

.strategy-table-container {
  overflow-x: auto;
}

.text-truncate {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.required {
  color: #dc3545;
}

.form-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius);
  font-size: 14px;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  resize: vertical;
  background: var(--bg-1);
  color: var(--text-1);
}

.form-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.1);
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

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
</style>

