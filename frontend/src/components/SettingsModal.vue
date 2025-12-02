<template>
  <Modal
    :visible="visible"
    title="系统设置"
    @update:visible="$emit('update:visible', $event)"
    @close="$emit('close')"
  >
    <div class="form-group">
      <label>交易频率（分钟）</label>
      <input
        v-model.number="formData.tradingFrequency"
        type="number"
        min="1"
        max="1440"
        class="form-input"
        placeholder="60"
      />
      <small class="form-help">设置AI交易决策的时间间隔（1-1440分钟）</small>
    </div>
    <div class="form-group">
      <label>交易费率</label>
      <input
        v-model.number="formData.tradingFeeRate"
        type="number"
        min="0"
        max="0.01"
        step="0.0001"
        class="form-input"
        placeholder="0.001"
      />
      <small class="form-help">每笔交易的手续费费率（0-0.01，例如0.001表示0.1%）</small>
    </div>
    <div class="form-group">
      <label>AI对话显示系统提交</label>
      <div class="toggle-input">
        <input
          v-model="formData.showSystemPrompt"
          type="checkbox"
          id="showSystemPrompt"
        />
        <span>开启显示</span>
      </div>
      <small class="form-help">开启后，AI对话列表会展示系统提交给模型的提示词。</small>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="handleCancel">取消</button>
      <button class="btn-primary" @click="handleSave">保存设置</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { settingsApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close'])

const formData = ref({
  tradingFrequency: 60,
  tradingFeeRate: 0.001,
  showSystemPrompt: false
})

const loading = ref(false)

// 加载设置
const loadSettings = async () => {
  try {
    const data = await settingsApi.get()
    formData.value = {
      tradingFrequency: data.trading_frequency_minutes || 60,
      tradingFeeRate: data.trading_fee_rate || 0.001,
      showSystemPrompt: Boolean(data.show_system_prompt)
    }
  } catch (error) {
    console.error('[SettingsModal] Error loading settings:', error)
    alert('加载设置失败')
  }
}

// 保存设置
const handleSave = async () => {
  loading.value = true
  try {
    await settingsApi.update({
      trading_frequency_minutes: formData.value.tradingFrequency,
      trading_fee_rate: formData.value.tradingFeeRate,
      show_system_prompt: formData.value.showSystemPrompt
    })
    alert('设置保存成功')
    emit('update:visible', false)
    emit('close')
  } catch (error) {
    console.error('[SettingsModal] Error saving settings:', error)
    alert('保存设置失败')
  } finally {
    loading.value = false
  }
}

const handleCancel = () => {
  emit('update:visible', false)
  emit('close')
}

// 当模态框显示时加载设置
watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadSettings()
  }
})
</script>

