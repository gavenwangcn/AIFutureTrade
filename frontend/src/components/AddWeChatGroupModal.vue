<template>
  <div v-if="visible" class="modal-overlay" @click.self="handleClose">
    <div class="modal-content wechat-group-form-modal">
      <div class="modal-header">
        <h3>{{ group ? '编辑微信群' : '添加微信群' }}</h3>
        <button class="btn-close" @click="handleClose">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="modal-body">
        <div v-if="error" class="alert alert-error">{{ error }}</div>

        <div class="form-group">
          <label>群组名称 <span class="required">*</span></label>
          <input
            v-model="formData.groupName"
            type="text"
            class="form-input"
            placeholder="请输入群组名称"
          />
        </div>

        <div class="form-group">
          <label>Webhook URL <span class="required">*</span></label>
          <input
            v-model="formData.webhookUrl"
            type="text"
            class="form-input"
            placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
          />
          <div class="form-hint">
            企业微信机器人的Webhook地址
          </div>
        </div>

        <div class="form-group">
          <label>告警类型</label>
          <div class="checkbox-group">
            <label class="checkbox-item">
              <input
                type="checkbox"
                value="ticker_sync_timeout"
                v-model="selectedAlertTypes"
              />
              <span>Ticker同步超时</span>
            </label>
            <label class="checkbox-item">
              <input
                type="checkbox"
                value="container_restart"
                v-model="selectedAlertTypes"
              />
              <span>容器重启</span>
            </label>
            <label class="checkbox-item">
              <input
                type="checkbox"
                value="service_error"
                v-model="selectedAlertTypes"
              />
              <span>服务错误</span>
            </label>
            <label class="checkbox-item">
              <input
                type="checkbox"
                value="trade_alert"
                v-model="selectedAlertTypes"
              />
              <span>交易告警</span>
            </label>
          </div>
          <div class="form-hint">
            不选择则接收所有类型的告警
          </div>
        </div>

        <div class="form-group">
          <label class="checkbox-item">
            <input
              type="checkbox"
              v-model="formData.isEnabled"
            />
            <span>启用此配置</span>
          </label>
        </div>

        <div class="form-group">
          <label>描述</label>
          <textarea
            v-model="formData.description"
            class="form-textarea"
            rows="3"
            placeholder="请输入描述信息(可选)"
          ></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" @click="handleClose">取消</button>
        <button class="btn-primary" @click="handleSave" :disabled="saving">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  group: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:visible', 'saved'])

const formData = ref({
  groupName: '',
  webhookUrl: '',
  alertTypes: '',
  isEnabled: true,
  description: ''
})

const selectedAlertTypes = ref([])
const error = ref('')
const saving = ref(false)

watch(() => props.group, (newGroup) => {
  if (newGroup) {
    formData.value = {
      groupName: newGroup.groupName || '',
      webhookUrl: newGroup.webhookUrl || '',
      alertTypes: newGroup.alertTypes || '',
      isEnabled: newGroup.isEnabled !== false,
      description: newGroup.description || ''
    }
    selectedAlertTypes.value = newGroup.alertTypes ? newGroup.alertTypes.split(',') : []
  } else {
    resetForm()
  }
}, { immediate: true })

watch(selectedAlertTypes, (newTypes) => {
  formData.value.alertTypes = newTypes.join(',')
}, { deep: true })

function resetForm() {
  formData.value = {
    groupName: '',
    webhookUrl: '',
    alertTypes: '',
    isEnabled: true,
    description: ''
  }
  selectedAlertTypes.value = []
  error.value = ''
}

function validateForm() {
  if (!formData.value.groupName.trim()) {
    error.value = '请输入群组名称'
    return false
  }

  if (!formData.value.webhookUrl.trim()) {
    error.value = '请输入Webhook URL'
    return false
  }

  if (!formData.value.webhookUrl.startsWith('http')) {
    error.value = 'Webhook URL格式不正确，必须以http开头'
    return false
  }

  return true
}

async function handleSave() {
  if (!validateForm()) {
    return
  }

  saving.value = true
  error.value = ''

  try {
    const url = props.group
      ? `http://localhost:5005/api/wechat-groups/${props.group.id}`
      : 'http://localhost:5005/api/wechat-groups'

    const method = props.group ? 'PUT' : 'POST'

    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(formData.value)
    })

    if (!response.ok) {
      throw new Error('保存失败')
    }

    emit('saved')
    handleClose()
  } catch (err) {
    console.error('保存失败:', err)
    error.value = '保存失败: ' + err.message
  } finally {
    saving.value = false
  }
}

function handleClose() {
  emit('update:visible', false)
  resetForm()
}
</script>

<style scoped>
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

.wechat-group-form-modal {
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

.btn-close {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-2);
  padding: 4px;
  border-radius: var(--radius);
  transition: all 0.2s;
}

.btn-close:hover {
  background: var(--bg-2);
  color: var(--primary);
}

.modal-body {
  padding: 20px;
}

.alert {
  padding: 12px 14px;
  border-radius: 10px;
  margin-bottom: 18px;
  font-size: 13px;
  border: 1px solid transparent;
}

.alert-error {
  background: rgba(245, 63, 63, 0.1);
  color: var(--danger);
  border-color: rgba(245, 63, 63, 0.3);
}

.form-group {
  margin-bottom: 20px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-group label {
  display: block;
  font-size: 14px;
  color: var(--text-1);
  font-weight: 500;
  margin-bottom: 8px;
}

.required {
  color: #dc3545;
}

.form-input {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius);
  font-size: 14px;
  background: var(--bg-1);
  color: var(--text-1);
}

.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.1);
}

.form-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-1);
  border-radius: var(--radius);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  background: var(--bg-1);
  color: var(--text-1);
}

.form-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(51, 112, 255, 0.1);
}

.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-2);
  font-style: italic;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-1);
}

.checkbox-item input[type="checkbox"] {
  cursor: pointer;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid var(--border-1);
}
</style>
