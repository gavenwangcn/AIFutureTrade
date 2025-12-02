<template>
  <Modal
    :visible="visible"
    title="USDS-M 合约配置"
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div class="form-group">
      <label>合约简称</label>
      <input v-model="formData.symbol" type="text" class="form-input" placeholder="例如：BTC" />
      <small class="form-help">用于内部展示与交易策略引用的代称</small>
    </div>
    <div class="form-group">
      <label>合约代码（USDS-M）</label>
      <input v-model="formData.contractSymbol" type="text" class="form-input" placeholder="例如：BTCUSDT" />
      <small class="form-help">与 Binance 合约代码保持一致，包含报价资产</small>
    </div>
    <div class="form-group">
      <label>合约名称</label>
      <input v-model="formData.name" type="text" class="form-input" placeholder="例如：BTC 永续合约" />
    </div>
    <div class="form-group">
      <label>交易所</label>
      <input v-model="formData.exchange" type="text" class="form-input" placeholder="例如：BINANCE_FUTURES" />
    </div>
    <div class="form-group">
      <label>合约链接（可选）</label>
      <input v-model="formData.link" type="text" class="form-input" placeholder="官方文档或介绍链接" />
    </div>
    <div class="form-group">
      <label>排序 No（可选）</label>
      <input v-model.number="formData.sortOrder" type="number" class="form-input" placeholder="越大越靠前" />
    </div>
    <div class="form-group">
      <label>已配置合约</label>
      <div class="provider-list">
        <div v-for="future in futures" :key="future.id" class="provider-item">
          <div class="provider-info">
            <div class="provider-name">{{ future.symbol }} / {{ future.contract_symbol }} - {{ future.name }}</div>
            <div class="provider-url">{{ future.exchange }}<span v-if="future.link"> · <a :href="future.link" target="_blank">合约介绍</a></span></div>
            <div class="provider-meta">排序: {{ future.sort_order || 0 }}</div>
          </div>
          <div class="provider-actions">
            <span class="provider-delete" @click="handleDelete(future.id)" title="删除">
              <i class="bi bi-trash"></i>
            </span>
          </div>
        </div>
        <div v-if="futures.length === 0" class="empty-state">暂无合约配置</div>
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="handleClose">取消</button>
      <button class="btn-primary" @click="handleSave" :disabled="loading">保存合约</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { futuresApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close', 'refresh'])

const formData = ref({
  symbol: '',
  contractSymbol: '',
  name: '',
  exchange: 'BINANCE_FUTURES',
  link: '',
  sortOrder: 0
})

const futures = ref([])
const error = ref('')
const loading = ref(false)

// 加载合约列表
const loadFutures = async () => {
  try {
    const data = await futuresApi.getAll()
    futures.value = Array.isArray(data) ? data : []
  } catch (err) {
    console.error('[FutureConfigModal] Error loading futures:', err)
    error.value = '加载合约配置失败'
  }
}

// 保存合约
const handleSave = async () => {
  error.value = ''
  
  if (!formData.value.symbol || !formData.value.contractSymbol || !formData.value.name) {
    error.value = '请填写币种简称、合约代码与名称'
    return
  }
  
  loading.value = true
  try {
    await futuresApi.create({
      symbol: formData.value.symbol.toUpperCase(),
      contract_symbol: formData.value.contractSymbol.toUpperCase(),
      name: formData.value.name,
      exchange: formData.value.exchange.toUpperCase() || 'BINANCE_FUTURES',
      link: formData.value.link || null,
      sort_order: formData.value.sortOrder || 0
    })
    alert('合约保存成功')
    clearForm()
    await loadFutures()
    emit('refresh')
  } catch (err) {
    console.error('[FutureConfigModal] Error saving future:', err)
    error.value = err.message || '保存合约失败'
  } finally {
    loading.value = false
  }
}

// 删除合约
const handleDelete = async (futureId) => {
  if (!confirm('确定要删除该合约吗？')) return
  
  try {
    await futuresApi.delete(futureId)
    alert('合约删除成功')
    await loadFutures()
    emit('refresh')
  } catch (err) {
    console.error('[FutureConfigModal] Error deleting future:', err)
    alert('删除合约失败')
  }
}

const clearForm = () => {
  formData.value = {
    symbol: '',
    contractSymbol: '',
    name: '',
    exchange: 'BINANCE_FUTURES',
    link: '',
    sortOrder: 0
  }
  error.value = ''
}

const handleClose = () => {
  clearForm()
  emit('update:visible', false)
  emit('close')
}

// 当模态框显示时加载数据
watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadFutures()
  }
})
</script>

<style scoped>
.provider-meta {
  font-size: 12px;
  color: var(--text-3);
  margin-top: 4px;
}
</style>

