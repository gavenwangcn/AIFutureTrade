<template>
  <Modal
    :visible="visible"
    title="账户管理"
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div class="form-group">
      <label>API Key</label>
      <input v-model="formData.apiKey" type="text" class="form-input" placeholder="请输入API Key" />
      <small class="form-help">币安期货API密钥</small>
    </div>
    <div class="form-group">
      <label>API Secret</label>
      <input v-model="formData.apiSecret" type="password" class="form-input" placeholder="请输入API Secret" />
      <small class="form-help">币安期货API密钥</small>
    </div>
    <div class="form-group">
      <label>已添加账户</label>
      <div class="provider-list">
        <div v-for="account in accounts" :key="account.account_alias" class="provider-item">
          <div class="provider-info">
            <div class="provider-name">账户: {{ account.account_alias }}</div>
            <div class="provider-url account-balance">
              <span class="balance-item">总余额: {{ formatBalance(account.balance) }}</span>
              <span class="balance-item">全仓余额: {{ formatBalance(account.crossWalletBalance) }}</span>
              <span class="balance-item">可用余额: {{ formatBalance(account.availableBalance) }}</span>
            </div>
            <div class="provider-meta" v-if="account.created_at">
              创建时间: {{ formatDate(account.created_at) }}
            </div>
          </div>
          <div class="provider-actions">
            <span class="provider-delete" @click="handleDelete(account.account_alias)" title="删除">
              <i class="bi bi-trash"></i>
            </span>
          </div>
        </div>
        <div v-if="accounts.length === 0" class="empty-state">暂无账户</div>
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="handleClose">取消</button>
      <button class="btn-primary" @click="handleSave" :disabled="loading">保存账户</button>
    </template>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { accountApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close', 'refresh'])

const formData = ref({
  apiKey: '',
  apiSecret: ''
})

const accounts = ref([])
const error = ref('')
const loading = ref(false)

// 格式化余额显示
const formatBalance = (balance) => {
  if (balance === null || balance === undefined) return '0.00'
  const num = parseFloat(balance)
  if (isNaN(num)) return '0.00'
  return num.toFixed(2)
}

// 格式化日期显示
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN')
  } catch (e) {
    return dateStr
  }
}

// 加载账户列表
const loadAccounts = async () => {
  try {
    const data = await accountApi.getAll()
    accounts.value = Array.isArray(data) ? data : []
  } catch (err) {
    console.error('[AccountModal] Error loading accounts:', err)
    error.value = '加载账户列表失败'
  }
}

// 保存账户
const handleSave = async () => {
  error.value = ''
  
  if (!formData.value.apiKey || !formData.value.apiSecret) {
    error.value = '请填写API Key和API Secret'
    return
  }
  
  loading.value = true
  try {
    await accountApi.create({
      api_key: formData.value.apiKey.trim(),
      api_secret: formData.value.apiSecret.trim()
    })
    alert('账户添加成功')
    clearForm()
    await loadAccounts()
    emit('refresh')
  } catch (err) {
    console.error('[AccountModal] Error saving account:', err)
    error.value = err.message || '添加账户失败'
  } finally {
    loading.value = false
  }
}

// 删除账户
const handleDelete = async (accountAlias) => {
  if (!confirm('确定要删除该账户吗？')) return
  
  loading.value = true
  error.value = ''
  
  try {
    const result = await accountApi.delete(accountAlias)
    if (result.success !== false) {
      alert('账户删除成功')
      await loadAccounts()
      emit('refresh')
    } else {
      throw new Error(result.error || '删除失败')
    }
  } catch (err) {
    console.error('[AccountModal] Error deleting account:', err)
    error.value = err.message || '删除账户失败'
    alert(`删除账户失败: ${err.message || '未知错误'}`)
  } finally {
    loading.value = false
  }
}

const clearForm = () => {
  formData.value = {
    apiKey: '',
    apiSecret: ''
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
    loadAccounts()
  }
})
</script>

<style scoped>
.account-balance {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 4px;
}

.balance-item {
  font-size: 12px;
  color: var(--text-2);
}

.provider-meta {
  font-size: 12px;
  color: var(--text-3);
  margin-top: 4px;
}
</style>

