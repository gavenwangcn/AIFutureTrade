<template>
  <Modal
    :visible="visible"
    title="API提供方管理"
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="form-group">
      <label>API名称</label>
      <input v-model="formData.name" type="text" class="form-input" placeholder="例如: OpenAI" />
    </div>
    <div class="form-group">
      <label>提供方类型</label>
      <select v-model="formData.providerType" class="form-input">
        <option value="openai">OpenAI 兼容</option>
        <option value="azure_openai">Azure OpenAI</option>
        <option value="anthropic">Anthropic (Claude)</option>
        <option value="deepseek">DeepSeek</option>
        <option value="gemini">Google Gemini</option>
        <option value="custom">自定义/其他</option>
      </select>
      <small class="form-help">用于确定如何调用该 API（影响提示词格式与参数）。</small>
    </div>
    <div class="form-group">
      <label>API地址</label>
      <input v-model="formData.apiUrl" type="text" class="form-input" placeholder="https://api.openai.com" />
    </div>
    <div class="form-group">
      <label>API密钥</label>
      <input v-model="formData.apiKey" type="password" class="form-input" placeholder="sk-..." />
    </div>
    <div class="form-group">
      <label>可用模型</label>
      <div class="model-input-group">
        <input v-model="formData.models" type="text" class="form-input" placeholder="gpt-4, gpt-3.5-turbo" />
        <button type="button" class="btn-secondary" @click="handleFetchModels" :disabled="fetchingModels">
          <i :class="['bi', fetchingModels ? 'bi-arrow-clockwise spin' : 'bi-arrow-clockwise']"></i>
          {{ fetchingModels ? '获取中...' : '获取模型' }}
        </button>
      </div>
      <small class="form-help">手动输入模型名称，用逗号分隔，或点击获取模型按钮自动获取</small>
    </div>
    <div class="form-group">
      <label>已保存的API提供方</label>
      <div class="provider-list">
        <div v-for="provider in providers" :key="provider.id" class="provider-item">
          <div class="provider-info">
            <div class="provider-name">{{ provider.name }}</div>
            <div class="provider-url">{{ provider.api_url }}</div>
            <div v-if="provider.models" class="provider-models">
              <span v-for="model in getProviderModels(provider.models)" :key="model" class="model-tag">{{ model }}</span>
            </div>
          </div>
          <div class="provider-actions">
            <span class="provider-delete" @click="handleDelete(provider.id)" title="删除">
              <i class="bi bi-trash"></i>
            </span>
          </div>
        </div>
        <div v-if="providers.length === 0" class="empty-state">暂无API提供方</div>
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="handleClose">取消</button>
      <button class="btn-primary" @click="handleSave" :disabled="loading">保存</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { providerApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close', 'refresh'])

const formData = ref({
  name: '',
  providerType: 'openai',
  apiUrl: '',
  apiKey: '',
  models: ''
})

const providers = ref([])
const loading = ref(false)
const fetchingModels = ref(false)

// 获取提供方的模型列表
const getProviderModels = (modelsStr) => {
  if (!modelsStr) return []
  return modelsStr.split(',').map(m => m.trim()).filter(m => m)
}

// 加载提供方列表
const loadProviders = async () => {
  try {
    const data = await providerApi.getAll()
    providers.value = Array.isArray(data) ? data : []
  } catch (err) {
    console.error('[ApiProviderModal] Error loading providers:', err)
  }
}

// 获取模型列表
const handleFetchModels = async () => {
  if (!formData.value.apiUrl || !formData.value.apiKey) {
    alert('请先填写API地址和密钥')
    return
  }
  
  fetchingModels.value = true
  try {
    const data = await providerApi.fetchModels({
      apiUrl: formData.value.apiUrl,
      apiKey: formData.value.apiKey
    })
    if (data.models && data.models.length > 0) {
      formData.value.models = data.models.join(', ')
      alert(`成功获取 ${data.models.length} 个模型`)
    } else {
      alert('未获取到模型列表，请手动输入')
    }
  } catch (err) {
    console.error('[ApiProviderModal] Error fetching models:', err)
    alert('获取模型列表失败')
  } finally {
    fetchingModels.value = false
  }
}

// 保存提供方
const handleSave = async () => {
  if (!formData.value.name || !formData.value.apiUrl || !formData.value.apiKey) {
    alert('请填写所有必填字段')
    return
  }
  
  loading.value = true
  try {
    await providerApi.create({
      name: formData.value.name,
      apiUrl: formData.value.apiUrl,
      apiKey: formData.value.apiKey,
      models: formData.value.models,
      providerType: formData.value.providerType
    })
    alert('API提供方保存成功')
    clearForm()
    await loadProviders()
    emit('refresh')
  } catch (err) {
    console.error('[ApiProviderModal] Error saving provider:', err)
    alert('保存API提供方失败')
  } finally {
    loading.value = false
  }
}

// 删除提供方
const handleDelete = async (providerId) => {
  if (!confirm('确定要删除这个API提供方吗？')) return
  
  try {
    await providerApi.delete(providerId)
    alert('API提供方删除成功')
    await loadProviders()
    emit('refresh')
  } catch (err) {
    console.error('[ApiProviderModal] Error deleting provider:', err)
    alert('删除API提供方失败')
  }
}

const clearForm = () => {
  formData.value = {
    name: '',
    providerType: 'openai',
    apiUrl: '',
    apiKey: '',
    models: ''
  }
}

const handleClose = () => {
  clearForm()
  emit('update:visible', false)
  emit('close')
}

// 当模态框显示时加载数据
watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadProviders()
  }
})
</script>

