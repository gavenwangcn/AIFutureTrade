<template>
  <Modal
    :visible="visible"
    title="模型策略配置"
    :subtitle="subtitle"
    extraLarge
    @update:visible="$emit('update:visible', $event)"
    @close="$emit('close')"
  >
    <div class="strategy-config-container">
      <div class="form-group">
        <label class="form-label-large">买入提示词</label>
        <textarea
          v-model="formData.buyPrompt"
          class="form-textarea-large"
          placeholder="输入买入策略提示词"
        ></textarea>
        <small class="form-help">留空将使用系统默认买入策略提示词。</small>
      </div>
      <div class="form-group">
        <label class="form-label-large">卖出提示词</label>
        <textarea
          v-model="formData.sellPrompt"
          class="form-textarea-large"
          placeholder="输入卖出/风控策略提示词"
        ></textarea>
        <small class="form-help">留空将使用系统默认卖出策略提示词。</small>
      </div>
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
    const response = await modelApi.updatePrompts(props.modelId, {
      buy_prompt: formData.value.buyPrompt || null,
      sell_prompt: formData.value.sellPrompt || null
    })
    
    // 检查响应是否成功
    if (response && response.success) {
      alert('策略配置保存成功')
      // 保存成功后关闭弹框
      emit('update:visible', false)
      emit('close')
    } else {
      throw new Error(response?.error || '保存失败')
    }
  } catch (error) {
    console.error('[StrategyModal] Error saving prompts:', error)
    alert('保存策略配置失败: ' + (error.message || '未知错误'))
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
.strategy-config-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
  height: 100%;
}

.form-group {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.form-label-large {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: 12px;
}

.form-textarea-large {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius);
  font-size: 14px;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  resize: none;
  flex: 1;
  min-height: 200px;
  line-height: 1.6;
  background: var(--bg-1);
  color: var(--text-1);
}

.form-textarea-large:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.1);
}

.form-help {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-3);
}
</style>

