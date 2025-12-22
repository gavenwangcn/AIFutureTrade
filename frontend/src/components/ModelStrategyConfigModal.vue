<template>
  <Modal
    :visible="visible"
    :title="`策略配置 - ${modelName}`"
    extraLarge
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="strategy-config-container">
      <!-- 搜索区域 -->
      <div class="search-section">
        <div class="search-form">
          <div class="form-group">
            <input 
              v-model="searchForm.name" 
              type="text" 
              class="form-input" 
              placeholder="策略名称"
              @keyup.enter="handleSearch"
            />
          </div>
          <div class="form-group">
            <select v-model="searchForm.type" class="form-input">
              <option value="">全部类型</option>
              <option value="buy">买</option>
              <option value="sell">卖</option>
            </select>
          </div>
          <div class="form-group">
            <button class="btn-primary" @click="handleSearch" :disabled="loading">
              <i class="bi bi-search"></i>
              搜索
            </button>
          </div>
        </div>
      </div>

      <!-- 左右布局 -->
      <div class="strategy-config-layout">
        <!-- 左侧：所有策略列表 -->
        <div class="strategy-list-panel left-panel">
          <div class="panel-header">
            <h4>所有策略</h4>
          </div>
          <div v-if="loading" class="loading-container">
            <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary);"></i>
            <p style="margin-top: 12px; color: var(--text-2);">加载中...</p>
          </div>
          <div v-else class="strategy-list">
            <div
              v-for="strategy in filteredAllStrategies"
              :key="strategy.id"
              :class="['strategy-item', { selected: selectedLeftStrategyId === strategy.id }]"
              @click="selectLeftStrategy(strategy.id)"
            >
              <div class="strategy-item-left">
                <div class="strategy-name">{{ strategy.name }}</div>
                <div class="strategy-meta">
                  <span :class="['badge', strategy.type === 'buy' ? 'badge-long' : 'badge-short']">
                    {{ strategy.type === 'buy' ? '买' : '卖' }}
                  </span>
                  <span class="strategy-time">{{ formatDateTime(strategy.created_at) }}</span>
                </div>
              </div>
            </div>
            <div v-if="filteredAllStrategies.length === 0" class="empty-state">
              暂无策略数据
            </div>
          </div>
          <!-- 分页控件 -->
          <div v-if="!loading && totalPages > 1" class="pagination-section">
            <div class="pagination-info">
              共 {{ total }} 条记录，第 {{ currentPage }} / {{ totalPages }} 页
            </div>
            <div class="pagination-controls">
              <button 
                class="btn-secondary btn-small" 
                @click="handlePageChange(currentPage - 1)"
                :disabled="currentPage <= 1"
              >
                上一页
              </button>
              <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
              <button 
                class="btn-secondary btn-small" 
                @click="handlePageChange(currentPage + 1)"
                :disabled="currentPage >= totalPages"
              >
                下一页
              </button>
            </div>
          </div>
        </div>

        <!-- 中间分割线和操作按钮 -->
        <div class="divider-with-actions">
          <div class="divider-line"></div>
          <div class="action-buttons">
            <button 
              class="btn-action btn-add" 
              @click="addStrategyToModel"
              :disabled="!selectedLeftStrategyId"
              title="添加到模型"
            >
              <i class="bi bi-arrow-right"></i>
            </button>
            <button 
              class="btn-action btn-remove" 
              @click="removeStrategyFromModel"
              :disabled="!selectedRightStrategyId"
              title="从模型移除"
            >
              <i class="bi bi-arrow-left"></i>
            </button>
          </div>
        </div>

        <!-- 右侧：模型已关联的策略列表 -->
        <div class="strategy-list-panel right-panel">
          <div class="panel-header">
            <h4>已配置策略</h4>
          </div>
          <div v-if="loading" class="loading-container">
            <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary);"></i>
            <p style="margin-top: 12px; color: var(--text-2);">加载中...</p>
          </div>
          <div v-else class="strategy-list">
            <div
              v-for="item in modelStrategies"
              :key="item.id || item.strategy_id"
              :class="['strategy-item', { selected: selectedRightStrategyId === (item.id || item.strategy_id) }]"
              @click="selectRightStrategy(item.id || item.strategy_id)"
            >
              <div class="strategy-item-right">
                <div class="strategy-info">
                  <div class="strategy-name">{{ item.strategy_name || getStrategyName(item.strategy_id || item.strategyId) }}</div>
                  <div class="strategy-meta">
                    <span :class="['badge', (item.strategy_type || item.type) === 'buy' ? 'badge-long' : 'badge-short']">
                      {{ (item.strategy_type || item.type) === 'buy' ? '买' : '卖' }}
                    </span>
                  </div>
                </div>
                <div class="priority-input-group">
                  <label>优先级:</label>
                  <input 
                    type="number" 
                    class="priority-input" 
                    :value="item.priority || 0"
                    @input="updatePriority(item.id || item.strategy_id, $event.target.value)"
                    @click.stop
                    min="0"
                  />
                </div>
              </div>
            </div>
            <div v-if="modelStrategies.length === 0" class="empty-state">
              暂无已配置策略
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作按钮 -->
      <div class="footer-actions">
        <button class="btn-secondary" @click="handleClose">取消</button>
        <button class="btn-primary" @click="handleSave" :disabled="saving">
          <i v-if="saving" class="bi bi-arrow-repeat spin"></i>
          <span v-else>保存</span>
        </button>
      </div>
    </div>
  </Modal>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import Modal from './Modal.vue'
import { modelApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  modelId: {
    type: String,
    default: null
  },
  modelName: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:visible', 'close', 'saved'])

// 状态
const loading = ref(false)
const saving = ref(false)
const searchForm = ref({
  name: '',
  type: ''
})
const allStrategies = ref([])
const modelStrategies = ref([])
const selectedLeftStrategyId = ref(null)
const selectedRightStrategyId = ref(null)
const priorityMap = ref({}) // 存储每个策略的优先级
// 分页状态
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const totalPages = ref(0)

// 计算属性：过滤后的所有策略（排除已关联的策略）
const filteredAllStrategies = computed(() => {
  const modelStrategyIds = new Set(modelStrategies.value.map(ms => ms.strategy_id || ms.strategyId))
  return allStrategies.value.filter(strategy => !modelStrategyIds.has(strategy.id))
})

// 分页处理
const handlePageChange = async (page) => {
  if (page < 1 || page > totalPages.value) return
  currentPage.value = page
  await loadData()
}

// 根据策略ID获取策略名称
const getStrategyName = (strategyId) => {
  const strategy = allStrategies.value.find(s => s.id === strategyId)
  return strategy ? strategy.name : `策略 #${strategyId}`
}

// 格式化日期时间
const formatDateTime = (dateTime) => {
  if (!dateTime) return ''
  try {
    const date = new Date(dateTime)
    if (isNaN(date.getTime())) return ''
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    return `${year}-${month}-${day} ${hours}:${minutes}`
  } catch (error) {
    console.error('格式化日期时间失败:', error, dateTime)
    return ''
  }
}

// 选择左侧策略
const selectLeftStrategy = (strategyId) => {
  selectedLeftStrategyId.value = strategyId
  selectedRightStrategyId.value = null
}

// 选择右侧策略
const selectRightStrategy = (strategyId) => {
  selectedRightStrategyId.value = strategyId
  selectedLeftStrategyId.value = null
}

// 添加策略到模型
const addStrategyToModel = () => {
  if (!selectedLeftStrategyId.value) return
  
  const strategy = allStrategies.value.find(s => s.id === selectedLeftStrategyId.value)
  if (!strategy) return
  
  // 检查是否已存在
  const exists = modelStrategies.value.find(ms => (ms.strategy_id || ms.strategyId) === selectedLeftStrategyId.value)
  if (exists) {
    alert('该策略已添加到模型中')
    return
  }
  
  // 添加到模型策略列表
  const newModelStrategy = {
    id: `temp_${Date.now()}_${Math.random()}`,
    strategy_id: selectedLeftStrategyId.value,
    strategyId: selectedLeftStrategyId.value,
    strategy_name: strategy.name,
    strategy_type: strategy.type,
    type: strategy.type,
    priority: 0
  }
  modelStrategies.value.push(newModelStrategy)
  priorityMap.value[newModelStrategy.id] = 0
  
  // 清空选择
  selectedLeftStrategyId.value = null
}

// 从模型移除策略
const removeStrategyFromModel = () => {
  if (!selectedRightStrategyId.value) return
  
  const index = modelStrategies.value.findIndex(ms => (ms.id || ms.strategy_id) === selectedRightStrategyId.value)
  if (index !== -1) {
    const removedId = modelStrategies.value[index].id || modelStrategies.value[index].strategy_id
    modelStrategies.value.splice(index, 1)
    delete priorityMap.value[removedId]
  }
  
  // 清空选择
  selectedRightStrategyId.value = null
}

// 更新优先级
const updatePriority = (modelStrategyId, value) => {
  const priority = parseInt(value) || 0
  priorityMap.value[modelStrategyId] = priority
  
  // 同时更新modelStrategies中的优先级
  const item = modelStrategies.value.find(ms => (ms.id || ms.strategy_id) === modelStrategyId)
  if (item) {
    item.priority = priority
  }
}

// 搜索策略
const handleSearch = async () => {
  currentPage.value = 1 // 搜索时重置到第一页
  await loadData()
}

// 加载数据
const loadData = async () => {
  if (!props.modelId) return
  
  loading.value = true
  try {
    // 构建查询参数，空字符串或空值时不传递该参数（实现全查询）
    const params = {
      pageNum: currentPage.value,
      pageSize: pageSize.value
    }
    // 只有当策略名称不为空时才添加name参数
    if (searchForm.value.name && searchForm.value.name.trim()) {
      params.name = searchForm.value.name.trim()
    }
    // 只有当策略类型不为空时才添加type参数
    if (searchForm.value.type && searchForm.value.type.trim()) {
      params.type = searchForm.value.type.trim()
    }
    const response = await modelApi.getStrategyConfig(props.modelId, params)
    allStrategies.value = response.strategies || []
    modelStrategies.value = response.modelStrategies || []
    
    // 更新分页信息
    total.value = response.total || 0
    currentPage.value = response.pageNum || 1
    pageSize.value = response.pageSize || 10
    totalPages.value = response.totalPages || 0
    
    // 初始化优先级映射
    priorityMap.value = {}
    modelStrategies.value.forEach(ms => {
      const id = ms.id || ms.strategy_id
      priorityMap.value[id] = ms.priority || 0
    })
  } catch (error) {
    console.error('加载策略配置失败:', error)
    alert('加载策略配置失败: ' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

// 保存配置
const handleSave = async () => {
  if (!props.modelId) return
  
  saving.value = true
  try {
    // 构建保存数据
    const strategies = modelStrategies.value.map(ms => {
      const id = ms.id || ms.strategy_id
      return {
        strategyId: ms.strategy_id || ms.strategyId,
        priority: priorityMap.value[id] || ms.priority || 0
      }
    })
    
    await modelApi.saveStrategyConfig(props.modelId, { strategies })
    
    alert('策略配置保存成功')
    emit('saved')
    handleClose()
  } catch (error) {
    console.error('保存策略配置失败:', error)
    alert('保存策略配置失败: ' + (error.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

// 关闭弹窗
const handleClose = () => {
  searchForm.value = {
    name: '',
    type: ''
  }
  currentPage.value = 1
  selectedLeftStrategyId.value = null
  selectedRightStrategyId.value = null
  emit('update:visible', false)
  emit('close')
}

// 监听visible变化，打开时加载数据
watch(() => props.visible, (newVal) => {
  if (newVal && props.modelId) {
    loadData()
  }
})

// 监听modelId变化
watch(() => props.modelId, () => {
  if (props.visible && props.modelId) {
    loadData()
  }
})
</script>

<style scoped>
.strategy-config-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
}

.search-section {
  margin-bottom: 20px;
}

.search-form {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.search-form .form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.search-form .form-group:first-child {
  flex: 1;
}

.search-form .form-group:nth-child(2) {
  width: 150px;
}

.search-form .form-input {
  width: 100%;
}

.strategy-config-layout {
  display: flex;
  flex: 1;
  gap: 0;
  min-height: 400px;
  position: relative;
}

.strategy-list-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-1);
  border-radius: 8px;
  overflow: hidden;
}

.panel-header {
  padding: 12px 16px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border-1);
}

.panel-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}

.strategy-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.strategy-item {
  padding: 12px;
  margin-bottom: 8px;
  border: 1px solid var(--border-1);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-1);
}

.strategy-item:hover {
  border-color: var(--primary);
  background: var(--bg-2);
}

.strategy-item.selected {
  border-color: var(--primary);
  background: rgba(51, 112, 255, 0.1);
}

.strategy-name {
  font-weight: 500;
  color: var(--text-1);
  margin-bottom: 6px;
}

.strategy-item-left {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.strategy-item-right {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.strategy-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.strategy-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.badge-long {
  background: rgba(0, 180, 42, 0.1);
  color: var(--success);
}

.badge-short {
  background: rgba(245, 63, 63, 0.1);
  color: var(--danger);
}

.strategy-time {
  font-size: 12px;
  color: var(--text-2);
}

.priority-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.priority-input-group label {
  font-size: 12px;
  color: var(--text-2);
  white-space: nowrap;
}

.priority-input {
  width: 80px;
  padding: 4px 8px;
  border: 1px solid var(--border-1);
  border-radius: 4px;
  font-size: 12px;
  text-align: center;
}

.divider-with-actions {
  position: relative;
  width: 2px;
  background: var(--border-1);
  flex-shrink: 0;
  margin: 0;
  height: 100%;
}

.divider-line {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--border-1);
}

.action-buttons {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  gap: 16px;
  z-index: 10;
}

.btn-action {
  width: 40px;
  height: 40px;
  border: 2px solid var(--bg-1);
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-add {
  background: var(--primary);
  color: white;
}

.btn-add:hover:not(:disabled) {
  background: #1e5ae6;
  transform: scale(1.1);
  box-shadow: 0 4px 12px rgba(51, 112, 255, 0.3);
}

.btn-remove {
  background: var(--danger);
  color: white;
}

.btn-remove:hover:not(:disabled) {
  background: #d32f2f;
  transform: scale(1.1);
  box-shadow: 0 4px 12px rgba(245, 63, 63, 0.3);
}

.footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-1);
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-2);
  font-size: 14px;
}

.pagination-section {
  padding: 12px 16px;
  border-top: 1px solid var(--border-1);
  background: var(--bg-2);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pagination-info {
  font-size: 12px;
  color: var(--text-2);
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-small {
  padding: 4px 12px;
  font-size: 12px;
}

.page-info {
  font-size: 12px;
  color: var(--text-2);
  min-width: 60px;
  text-align: center;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
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

