<template>
  <Modal
    :visible="visible"
    title="添加交易模型"
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="form-group">
      <label>选择API提供方</label>
      <select v-model="formData.providerId" class="form-input" @change="handleProviderChange">
        <option value="">请选择API提供方</option>
        <option v-for="provider in providers" :key="provider.id" :value="provider.id">
          {{ provider.name }}
        </option>
      </select>
    </div>
    <div class="form-group">
      <label>模型</label>
      <select v-model="formData.modelName" class="form-input">
        <option value="">请选择API提供方</option>
        <option v-for="model in availableModels" :key="model" :value="model">
          {{ model }}
        </option>
      </select>
    </div>
    <div class="form-group">
      <label>模型显示名称</label>
      <input v-model="formData.displayName" type="text" class="form-input" placeholder="例如: GPT-4交易员" />
      <small class="form-help">用于显示的友好名称</small>
    </div>
    <div class="form-group">
      <label>初始资金</label>
      <input v-model.number="formData.initialCapital" type="number" class="form-input" />
    </div>
    <template #footer>
      <button class="btn-secondary" @click="handleClose">取消</button>
      <button class="btn-primary" @click="handleSubmit" :disabled="loading">确认添加</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { providerApi, modelApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close', 'refresh'])

const formData = ref({
  providerId: '',
  modelName: '',
  displayName: '',
  initialCapital: 100000
})

const providers = ref([])
const availableModels = ref([])
const loading = ref(false)

// 加载提供方列表
const loadProviders = async () => {
  try {
    const data = await providerApi.getAll()
    providers.value = Array.isArray(data) ? data : []
  } catch (err) {
    console.error('[AddModelModal] Error loading providers:', err)
  }
}

// 处理提供方变化
const handleProviderChange = () => {
  const provider = providers.value.find(p => p.id == formData.value.providerId)
  if (provider && provider.models) {
    availableModels.value = provider.models.split(',').map(m => m.trim()).filter(m => m)
  } else {
    availableModels.value = []
  }
  formData.value.modelName = ''
}

// 提交模型
const handleSubmit = async () => {
  if (!formData.value.providerId || !formData.value.modelName || !formData.value.displayName) {
    alert('请填写所有必填字段')
    return
  }
  
  if (!formData.value.initialCapital || formData.value.initialCapital <= 0) {
    alert('请输入有效的初始资金')
    return
  }
  
  loading.value = true
  try {
    await modelApi.create({
      provider_id: formData.value.providerId,
      model_name: formData.value.modelName,
      name: formData.value.displayName,
      initial_capital: formData.value.initialCapital
    })
    alert('模型添加成功')
    clearForm()
    emit('update:visible', false)
    emit('close')
    emit('refresh')
  } catch (err) {
    console.error('[AddModelModal] Error creating model:', err)
    alert('添加模型失败')
  } finally {
    loading.value = false
  }
}

const clearForm = () => {
  formData.value = {
    providerId: '',
    modelName: '',
    displayName: '',
    initialCapital: 100000
  }
  availableModels.value = []
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

