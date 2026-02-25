<template>
  <Modal
    :visible="visible"
    title="系统设置"
    @update:visible="$emit('update:visible', $event)"
    @close="$emit('close')"
  >
    <div class="form-group">
      <label>买入执行频率（分钟）</label>
      <input
        v-model.number="formData.buyFrequency"
        type="number"
        min="1"
        max="1440"
        class="form-input"
        placeholder="5"
      />
      <small class="form-help">设置AI买入决策的时间间隔（1-1440分钟）</small>
    </div>
    <div class="form-group">
      <label>卖出执行频率（分钟）</label>
      <input
        v-model.number="formData.sellFrequency"
        type="number"
        min="1"
        max="1440"
        class="form-input"
        placeholder="5"
      />
      <small class="form-help">设置AI卖出决策的时间间隔（1-1440分钟）</small>
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
    <div class="form-group">
      <label>AI对话显示数量</label>
      <input
        v-model.number="formData.conversationLimit"
        type="number"
        min="1"
        max="100"
        class="form-input"
        placeholder="5"
      />
      <small class="form-help">设置AI对话模块显示的最大对话记录数量（1-100，默认5条）</small>
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
  buyFrequency: 5,
  sellFrequency: 5,
  tradingFeeRate: 0.001,
  showSystemPrompt: false,
  conversationLimit: 5
})

const loading = ref(false)

// 加载设置
const loadSettings = async () => {
  try {
    const data = await settingsApi.get()
    formData.value = {
      buyFrequency: data.buy_frequency_minutes || 5,
      sellFrequency: data.sell_frequency_minutes || 5,
      tradingFeeRate: data.trading_fee_rate || 0.001,
      showSystemPrompt: Boolean(data.show_system_prompt),
      conversationLimit: data.conversation_limit || 5
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
      buy_frequency_minutes: formData.value.buyFrequency,
      sell_frequency_minutes: formData.value.sellFrequency,
      trading_fee_rate: formData.value.tradingFeeRate,
      show_system_prompt: formData.value.showSystemPrompt,
      conversation_limit: formData.value.conversationLimit
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

