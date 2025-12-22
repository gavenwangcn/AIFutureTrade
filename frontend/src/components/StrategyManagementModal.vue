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
          <button class="btn-secondary" @click="handleOpenStrategyProviderModal">
            <i class="bi bi-gear"></i>
            设置策略API提供方
          </button>
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
                  <button class="btn-icon" @click="handleViewCode(strategy)" title="查看策略代码">
                    <i class="bi bi-code-slash"></i>
                  </button>
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
            <div class="code-input-group">
              <textarea 
                v-model="strategyForm.strategy_code" 
                class="form-textarea" 
                rows="10"
                placeholder="请输入策略代码"
                style="font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;"
              ></textarea>
              <button 
                type="button" 
                class="btn-secondary btn-fetch-code" 
                @click="handleFetchStrategyCode" 
                :disabled="fetchingCode || !strategyForm.type || !strategyForm.strategy_context"
              >
                <i :class="['bi', fetchingCode ? 'bi-arrow-clockwise spin' : 'bi-arrow-clockwise']"></i>
                {{ fetchingCode ? '生成中...' : '获取代码' }}
              </button>
            </div>
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

    <!-- 设置策略API提供方弹框 -->
    <div v-if="showStrategyProviderModal" class="modal-overlay" @click.self="closeStrategyProviderModal">
      <div class="modal-content strategy-provider-modal">
        <div class="modal-header">
          <h3>设置策略API提供方</h3>
          <button class="btn-close" @click="closeStrategyProviderModal">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>选择API提供方</label>
            <select v-model="strategyProviderForm.providerId" class="form-input" @change="handleProviderChange">
              <option value="">请选择API提供方</option>
              <option v-for="provider in providers" :key="provider.id" :value="provider.id">
                {{ provider.name }}
              </option>
            </select>
          </div>
          <div class="form-group">
            <label>模型</label>
            <select v-model="strategyProviderForm.modelName" class="form-input">
              <option value="">请先选择API提供方</option>
              <option v-for="model in availableModels" :key="model" :value="model">
                {{ model }}
              </option>
            </select>
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label>Temperature (温度)</label>
              <input 
                v-model.number="strategyProviderForm.strategy_temperature" 
                type="number" 
                step="0.1" 
                min="0" 
                max="2" 
                class="form-input"
                placeholder="0.0"
              />
              <small class="form-hint">控制输出的随机性，范围 0-2，默认 0.0</small>
            </div>
            <div class="form-group">
              <label>Max Tokens (最大Token数)</label>
              <input 
                v-model.number="strategyProviderForm.strategy_max_tokens" 
                type="number" 
                min="1" 
                max="8192" 
                class="form-input"
                placeholder="8192"
              />
              <small class="form-hint">最大输出Token数，范围 1-8192，默认 8192</small>
            </div>
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label>Top P (核采样)</label>
              <input 
                v-model.number="strategyProviderForm.strategy_top_p" 
                type="number" 
                step="0.1" 
                min="0" 
                max="1" 
                class="form-input"
                placeholder="0.9"
              />
              <small class="form-hint">核采样参数，范围 0-1，默认 0.9</small>
            </div>
            <div class="form-group">
              <label>Top K (Top-K采样)</label>
              <input 
                v-model.number="strategyProviderForm.strategy_top_k" 
                type="number" 
                min="1" 
                max="100" 
                class="form-input"
                placeholder="50"
              />
              <small class="form-hint">Top-K采样参数，范围 1-100，默认 50（仅部分模型支持）</small>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="closeStrategyProviderModal">取消</button>
          <button class="btn-primary" @click="handleSaveStrategyProvider" :disabled="savingProvider">
            {{ savingProvider ? '保存中...' : '确认' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 查看策略代码弹框 -->
    <div v-if="showCodeModal" class="modal-overlay" @click.self="closeCodeModal">
      <div class="modal-content code-view-modal">
        <div class="modal-header">
          <h3>策略代码</h3>
          <button class="btn-close" @click="closeCodeModal">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <pre class="code-content">{{ viewingCode }}</pre>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="closeCodeModal">关闭</button>
        </div>
      </div>
    </div>

    <!-- 测试结果弹框 -->
    <div v-if="showTestResult" class="modal-overlay" @click.self="closeTestResult">
      <div class="modal-content test-result-modal">
        <div class="modal-header">
          <h3>策略代码测试结果</h3>
          <button class="btn-close" @click="closeTestResult">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div v-if="testResult" class="test-result-content">
            <div class="test-status" :class="testResult.passed ? 'status-passed' : 'status-failed'">
              <i :class="testResult.passed ? 'bi bi-check-circle-fill' : 'bi bi-x-circle-fill'"></i>
              <span>{{ testResult.passed ? '测试通过' : '测试失败' }}</span>
            </div>
            
            <div v-if="testResult.errors && testResult.errors.length > 0" class="test-errors">
              <h4>错误信息：</h4>
              <ul>
                <li v-for="(error, index) in testResult.errors" :key="index">{{ error }}</li>
              </ul>
            </div>
            
            <div v-if="testResult.warnings && testResult.warnings.length > 0" class="test-warnings">
              <h4>警告信息：</h4>
              <ul>
                <li v-for="(warning, index) in testResult.warnings" :key="index">{{ warning }}</li>
              </ul>
            </div>
            
            <div v-if="testResult.test_results" class="test-details">
              <h4>测试详情：</h4>
              <div v-for="(result, testName) in testResult.test_results" :key="testName" class="test-item">
                <span :class="result.passed ? 'test-passed' : 'test-failed'">
                  {{ result.passed ? '✓' : '✗' }} {{ testName }}: {{ result.message }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="closeTestResult">关闭</button>
          <button v-if="!testResult || !testResult.passed" class="btn-primary" @click="handleRetryGenerate">
            重新生成
          </button>
          <button v-if="testResult && testResult.passed" class="btn-primary" @click="handleSaveWithTestedCode">
            保存策略
          </button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import Modal from './Modal.vue'
import { strategyApi, providerApi, settingsApi, aiProviderApi } from '../services/api.js'

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

// 设置策略API提供方相关
const showStrategyProviderModal = ref(false)
const strategyProviderForm = ref({
  providerId: '',
  modelName: '',
  strategy_temperature: 0.7,
  strategy_max_tokens: 8192,
  strategy_top_p: 0.9,
  strategy_top_k: 50
})
const providers = ref([])
const availableModels = ref([])
const savingProvider = ref(false)

// 查看策略代码相关
const showCodeModal = ref(false)
const viewingCode = ref('')

// 获取策略代码相关
const fetchingCode = ref(false)
const testResult = ref(null)
const showTestResult = ref(false)

// 计算总页数
const totalPages = computed(() => {
  return Math.ceil(total.value / pageSize.value)
})

// 加载策略列表
const loadStrategies = async () => {
  loading.value = true
  try {
    // 构建查询参数，只包含非空值的参数
    const params = {
      pageNum: currentPage.value,
      pageSize: pageSize.value
    }
    
    // 只在name有值时添加到参数中
    if (searchForm.value.name && searchForm.value.name.trim()) {
      params.name = searchForm.value.name.trim()
    }
    
    // 只在type有值时添加到参数中
    if (searchForm.value.type) {
      params.type = searchForm.value.type
    }
    
    const result = await strategyApi.getPage(params)
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

// 打开设置策略API提供方弹框
const handleOpenStrategyProviderModal = async () => {
  try {
    // 加载提供方列表
    const providersData = await providerApi.getAll()
    providers.value = Array.isArray(providersData) ? providersData : []
    
    // 加载当前设置
    const settings = await settingsApi.get()
    if (settings.strategy_provider) {
      strategyProviderForm.value.providerId = settings.strategy_provider
      await handleProviderChange()
      // 如果已设置模型，选中该模型
      if (settings.strategy_model) {
        strategyProviderForm.value.modelName = settings.strategy_model
      }
    }
    // 加载策略参数设置
    if (settings.strategy_temperature !== undefined) {
      strategyProviderForm.value.strategy_temperature = settings.strategy_temperature
    }
    if (settings.strategy_max_tokens !== undefined) {
      strategyProviderForm.value.strategy_max_tokens = settings.strategy_max_tokens
    }
    if (settings.strategy_top_p !== undefined) {
      strategyProviderForm.value.strategy_top_p = settings.strategy_top_p
    }
    if (settings.strategy_top_k !== undefined) {
      strategyProviderForm.value.strategy_top_k = settings.strategy_top_k
    }
    
    showStrategyProviderModal.value = true
  } catch (err) {
    console.error('[StrategyManagementModal] Error loading providers:', err)
    alert('加载API提供方列表失败')
  }
}

// 关闭设置策略API提供方弹框
const   closeStrategyProviderModal = () => {
  showStrategyProviderModal.value = false
  strategyProviderForm.value = {
    providerId: '',
    modelName: '',
    strategy_temperature: 0.0,
    strategy_max_tokens: 8192,
    strategy_top_p: 0.9,
    strategy_top_k: 50
  }
  availableModels.value = []
}

// 处理提供方变化
const handleProviderChange = async () => {
  const provider = providers.value.find(p => p.id == strategyProviderForm.value.providerId)
  if (provider && provider.models) {
    availableModels.value = provider.models.split(',').map(m => m.trim()).filter(m => m)
  } else {
    availableModels.value = []
  }
  strategyProviderForm.value.modelName = ''
}

// 保存策略API提供方设置
const handleSaveStrategyProvider = async () => {
  if (!strategyProviderForm.value.providerId) {
    alert('请选择API提供方')
    return
  }
  
  if (!strategyProviderForm.value.modelName) {
    alert('请选择模型')
    return
  }
  
  savingProvider.value = true
  try {
    await settingsApi.update({
      strategy_provider: strategyProviderForm.value.providerId,
      strategy_model: strategyProviderForm.value.modelName,
      strategy_temperature: strategyProviderForm.value.strategy_temperature,
      strategy_max_tokens: strategyProviderForm.value.strategy_max_tokens,
      strategy_top_p: strategyProviderForm.value.strategy_top_p,
      strategy_top_k: strategyProviderForm.value.strategy_top_k
    })
    alert('设置成功')
    closeStrategyProviderModal()
  } catch (err) {
    console.error('[StrategyManagementModal] Error saving strategy provider:', err)
    alert('保存失败: ' + (err.message || '未知错误'))
  } finally {
    savingProvider.value = false
  }
}

// 获取策略代码
const handleFetchStrategyCode = async () => {
  if (!strategyForm.value.type) {
    alert('请先选择策略类型')
    return
  }
  
  if (!strategyForm.value.strategy_context || !strategyForm.value.strategy_context.trim()) {
    alert('请先输入策略内容')
    return
  }
  
  // 获取策略提供方设置
  let providerId, modelName
  try {
    const settings = await settingsApi.get()
    providerId = settings.strategy_provider
    modelName = settings.strategy_model
    
    if (!providerId) {
      alert('请先设置策略API提供方')
      handleOpenStrategyProviderModal()
      return
    }
    
    if (!modelName) {
      // 如果没有设置模型，从提供方获取第一个模型
      const providersList = await providerApi.getAll()
      const provider = Array.isArray(providersList) ? providersList.find(p => p.id === providerId) : null
      
      if (!provider) {
        alert('API提供方不存在')
        return
      }
      
      // 获取模型列表（优先从提供方的models字段获取，如果没有则调用API获取）
      let models = []
      if (provider.models) {
        models = provider.models.split(',').map(m => m.trim()).filter(m => m)
      }
      
      if (models.length === 0) {
        // 尝试从API获取模型列表
        try {
          const modelsResult = await aiProviderApi.fetchModels(providerId)
          if (modelsResult.models && modelsResult.models.length > 0) {
            models = modelsResult.models
          }
        } catch (err) {
          console.warn('Failed to fetch models from API:', err)
        }
      }
      
      if (models.length === 0) {
        alert('该API提供方没有可用模型，请先配置模型')
        return
      }
      
      // 使用第一个模型
      modelName = models[0]
    }
  } catch (err) {
    console.error('[StrategyManagementModal] Error loading settings:', err)
    alert('加载设置失败')
    return
  }
  
  fetchingCode.value = true
  try {
    const result = await aiProviderApi.generateStrategyCode({
      providerId: providerId,
      modelName: modelName,
      strategyContext: strategyForm.value.strategy_context,
      strategyType: strategyForm.value.type
    })
    
    if (result.strategyCode) {
      strategyForm.value.strategy_code = result.strategyCode
      
      // 显示测试结果
      if (result.testResult) {
        testResult.value = result.testResult
        showTestResult.value = true
        
        if (result.testPassed) {
          alert('策略代码生成成功，测试通过！')
        } else {
          const errors = result.testResult.errors || []
          const errorMsg = errors.length > 0 
            ? '策略代码生成成功，但测试未通过：\n' + errors.join('\n')
            : '策略代码生成成功，但测试未通过'
          alert(errorMsg)
        }
      } else {
        alert('策略代码生成成功')
      }
    } else {
      alert('生成失败：未返回策略代码')
    }
  } catch (err) {
    console.error('[StrategyManagementModal] Error generating strategy code:', err)
    alert('生成策略代码失败: ' + (err.message || '未知错误'))
  } finally {
    fetchingCode.value = false
  }
}

// 查看策略代码
const handleViewCode = (strategy) => {
  viewingCode.value = strategy.strategy_code || '暂无策略代码'
  showCodeModal.value = true
}

// 关闭测试结果弹框
const closeTestResult = () => {
  showTestResult.value = false
  testResult.value = null
}

// 重新生成代码
const handleRetryGenerate = () => {
  closeTestResult()
  handleFetchStrategyCode()
}

// 保存已测试通过的代码
const handleSaveWithTestedCode = () => {
  closeTestResult()
  // 如果表单未打开，先打开表单
  if (!showStrategyForm.value) {
    handleAddStrategy()
  }
  // 表单中已经有代码了，直接保存
  handleSaveStrategy()
}

// 关闭查看代码弹框
const closeCodeModal = () => {
  showCodeModal.value = false
  viewingCode.value = ''
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

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-2);
  font-style: italic;
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

.code-input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.btn-fetch-code {
  align-self: flex-start;
  display: flex;
  align-items: center;
  gap: 6px;
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

.strategy-provider-modal,
.code-view-modal {
  background: var(--bg-1);
  border-radius: var(--radius);
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow: auto;
}

.code-view-modal {
  max-width: 800px;
}

.code-content {
  background: var(--bg-2);
  padding: 16px;
  border-radius: var(--radius);
  overflow-x: auto;
  max-height: 60vh;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.test-result-modal {
  max-width: 600px;
}

.test-result-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.test-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-radius: var(--radius);
  font-size: 16px;
  font-weight: 600;
}

.test-status.status-passed {
  background: rgba(40, 167, 69, 0.1);
  color: #28a745;
}

.test-status.status-failed {
  background: rgba(220, 53, 69, 0.1);
  color: #dc3545;
}

.test-errors, .test-warnings {
  padding: 12px;
  border-radius: var(--radius);
  background: var(--bg-2);
}

.test-errors {
  border-left: 4px solid #dc3545;
}

.test-warnings {
  border-left: 4px solid #ffc107;
}

.test-errors h4, .test-warnings h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
}

.test-errors ul, .test-warnings ul {
  margin: 0;
  padding-left: 20px;
}

.test-errors li, .test-warnings li {
  margin: 4px 0;
  font-size: 13px;
}

.test-details {
  padding: 12px;
  border-radius: var(--radius);
  background: var(--bg-2);
}

.test-details h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
}

.test-item {
  margin: 4px 0;
  font-size: 13px;
}

.test-passed {
  color: #28a745;
}

.test-failed {
  color: #dc3545;
}
</style>

