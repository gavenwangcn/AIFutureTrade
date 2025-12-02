<template>
  <Modal
    :visible="visible"
    title="模型策略配置"
    :subtitle="subtitle"
    large
    @update:visible="$emit('update:visible', $event)"
    @close="$emit('close')"
  >
    <div class="form-group">
      <label>买入提示词</label>
      <textarea
        v-model="formData.buyPrompt"
        class="form-textarea"
        rows="8"
        placeholder="输入买入策略提示词"
      ></textarea>
      <small class="form-help">留空将使用系统默认买入策略提示词。</small>
    </div>
    <div class="form-group">
      <label>卖出提示词</label>
      <textarea
        v-model="formData.sellPrompt"
        class="form-textarea"
        rows="8"
        placeholder="输入卖出/风控策略提示词"
      ></textarea>
      <small class="form-help">留空将使用系统默认卖出策略提示词。</small>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="handleCancel">取消</button>
      <button class="btn-primary" @click="handleSave">保存策略</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import Modal from './Modal.vue'
import { modelApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  modelId: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['update:visible', 'close'])

const formData = ref({
  buyPrompt: '',
  sellPrompt: ''
})

const loading = ref(false)

const subtitle = computed(() => {
  return props.modelId ? `配置模型 #${props.modelId} 的买入/卖出提示词` : '配置当前模型的买入/卖出提示词'
})

// 加载策略配置
const loadPrompts = async () => {
  if (!props.modelId) return
  
  try {
    const data = await modelApi.getPrompts(props.modelId)
    formData.value = {
      buyPrompt: data.buy_prompt || '',
      sellPrompt: data.sell_prompt || ''
    }
  } catch (error) {
    console.error('[StrategyModal] Error loading prompts:', error)
  }
}

// 保存策略配置
const handleSave = async () => {
  if (!props.modelId) {
    alert('请先选择模型')
    return
  }
  
  loading.value = true
  try {
    await modelApi.updatePrompts(props.modelId, {
      buy_prompt: formData.value.buyPrompt || null,
      sell_prompt: formData.value.sellPrompt || null
    })
    alert('策略配置保存成功')
    emit('update:visible', false)
    emit('close')
  } catch (error) {
    console.error('[StrategyModal] Error saving prompts:', error)
    alert('保存策略配置失败')
  } finally {
    loading.value = false
  }
}

const handleCancel = () => {
  emit('update:visible', false)
  emit('close')
}

// 当模态框显示时加载配置
watch(() => props.visible, (newVal) => {
  if (newVal && props.modelId) {
    loadPrompts()
  }
})
</script>

<style scoped>
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius);
  font-size: 14px;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  resize: vertical;
  min-height: 150px;
}

.form-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.1);
}
</style>

