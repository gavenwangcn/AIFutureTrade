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
    <div class="form-grid-2col">
      <div class="form-group">
        <label>初始资金</label>
        <input v-model.number="formData.initialCapital" type="number" class="form-input" />
      </div>
      <div class="form-group">
        <label title="同时持有的最大交易对数量，默认为3">最大持仓数量</label>
        <input v-model.number="formData.maxPositions" type="number" class="form-input" min="1" />
      </div>
      <div class="form-group">
        <label title="当损失本金达到此百分比时自动平仓（例如：10 表示损失10%本金时自动平仓）。留空或0表示不启用自动平仓。">自动平仓百分比</label>
        <input v-model.number="formData.autoClosePercent" type="number" class="form-input" min="0" max="100" step="0.1" />
      </div>
      <div class="form-group">
        <label title="只交易当日成交额大于此阈值的合约（以千万为单位，例如：10 表示1亿成交额）。留空或0表示不过滤。">当日成交额过滤阈值（千万单位）</label>
        <input v-model.number="formData.baseVolume" type="number" class="form-input" min="0" step="0.1" />
      </div>
      <div class="form-group">
        <label title="设置目标每日收益率（百分比，例如：5 表示5%）。当当日收益率达到此值时，将不再进行买入交易。留空或0表示不限制。">目标每日收益率（百分比）</label>
        <input v-model.number="formData.dailyReturn" type="number" class="form-input" min="0" step="0.1" />
      </div>
      <div class="form-group">
        <label title="设置连续亏损次数阈值（例如：3 表示连续3笔亏损后暂停买入交易）。留空或0表示不限制。">连续亏损次数阈值</label>
        <input v-model.number="formData.lossesNum" type="number" class="form-input" min="1" />
      </div>
      <div class="form-group">
        <label>禁止买入开始</label>
        <TimePicker v-model="formData.forbidBuyStart" />
      </div>
      <div class="form-group">
        <label>禁止买入结束</label>
        <TimePicker v-model="formData.forbidBuyEnd" />
      </div>
      <div class="form-group">
        <label title="同一合约在指定分钟数内禁止再次买入。留空或0表示不过滤。">相同合约禁止买入间隔（分钟）</label>
        <input v-model.number="formData.sameSymbolInterval" type="number" class="form-input" min="0" placeholder="留空不过滤" />
        <small class="form-help">同一symbol在此时长内已有买入记录则不再买入，留空表示不过滤</small>
      </div>
    </div>
    <div v-if="timeRangeError" class="form-help" style="color: #dc3545; margin-top: 8px;">
      {{ timeRangeError }}
    </div>
    <div class="form-group">
      <label>选择账户 <span style="color: red;">*</span></label>
      <select v-model="formData.accountAlias" class="form-input" required>
        <option value="">请选择账户</option>
        <option v-for="account in accounts" :key="account.account_alias" :value="account.account_alias">
          {{ account.account_name || account.account_alias }}
        </option>
      </select>
      <small class="form-help">从已添加的账户中选择（必填）</small>
      <div v-if="accounts.length === 0" class="form-help" style="color: red;">
        暂无可用账户，请先添加账户
      </div>
    </div>
    <div class="form-group">
      <label>是否虚拟</label>
      <div class="radio-group">
        <label class="radio-label">
          <input 
            type="radio" 
            v-model="formData.isVirtual" 
            :value="false" 
            class="radio-input"
          />
          <span>否</span>
        </label>
        <label class="radio-label">
          <input 
            type="radio" 
            v-model="formData.isVirtual" 
            :value="true" 
            class="radio-input"
          />
          <span>是</span>
        </label>
      </div>
    </div>
    <div class="form-group">
      <label>交易对数据源</label>
      <div class="radio-group">
        <label class="radio-label">
          <input 
            type="radio" 
            v-model="formData.symbolSource" 
            value="leaderboard" 
            class="radio-input"
          />
          <span>涨跌榜</span>
        </label>
        <label class="radio-label">
          <input 
            type="radio" 
            v-model="formData.symbolSource" 
            value="future" 
            class="radio-input"
          />
          <span>合约配置信息</span>
        </label>
      </div>
    </div>
    <div class="form-group">
      <label style="font-weight: 600; margin-bottom: 12px; display: block;">买入批次配置</label>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
        <div>
          <label style="font-size: 13px; color: var(--text-2);">批次大小</label>
          <input v-model.number="formData.buyBatchSize" type="number" class="form-input" min="1" />
          <small class="form-help">每次提交给AI的symbol数量，默认1</small>
        </div>
        <div>
          <label style="font-size: 13px; color: var(--text-2);">执行间隔（秒）</label>
          <input v-model.number="formData.buyBatchExecutionInterval" type="number" class="form-input" min="0" />
          <small class="form-help">批次执行间隔，默认60</small>
        </div>
        <div>
          <label style="font-size: 13px; color: var(--text-2);">分组大小</label>
          <input v-model.number="formData.buyBatchExecutionGroupSize" type="number" class="form-input" min="1" />
          <small class="form-help">每N个批次统一处理，默认1</small>
        </div>
      </div>
    </div>
    <div class="form-group">
      <label style="font-weight: 600; margin-bottom: 12px; display: block;">卖出批次配置</label>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
        <div>
          <label style="font-size: 13px; color: var(--text-2);">批次大小</label>
          <input v-model.number="formData.sellBatchSize" type="number" class="form-input" min="1" />
          <small class="form-help">每次提交给AI的symbol数量，默认1</small>
        </div>
        <div>
          <label style="font-size: 13px; color: var(--text-2);">执行间隔（秒）</label>
          <input v-model.number="formData.sellBatchExecutionInterval" type="number" class="form-input" min="0" />
          <small class="form-help">批次执行间隔，默认60</small>
        </div>
        <div>
          <label style="font-size: 13px; color: var(--text-2);">分组大小</label>
          <input v-model.number="formData.sellBatchExecutionGroupSize" type="number" class="form-input" min="1" />
          <small class="form-help">每N个批次统一处理，默认1</small>
        </div>
      </div>
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
import TimePicker from './TimePicker.vue'
import { providerApi, modelApi, accountApi } from '../services/api.js'

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
  initialCapital: 100000,
  maxPositions: 3,  // 默认最大持仓数量为3
  autoClosePercent: null,  // 自动平仓百分比，默认不启用
  baseVolume: null,  // 当日成交额过滤阈值（千万单位），默认不过滤
  dailyReturn: null,  // 目标每日收益率（百分比），默认不限制
  lossesNum: null,  // 连续亏损次数阈值，默认不限制
  forbidBuyStart: null, // 禁止买入开始时间 HH:mm:ss（UTC+8）
  forbidBuyEnd: null, // 禁止买入结束时间 HH:mm:ss（UTC+8）
  sameSymbolInterval: null, // 相同合约禁止买入间隔（分钟），null表示不过滤
  accountAlias: '',
  isVirtual: true,  // 默认值为 true（虚拟账户）
  symbolSource: 'leaderboard',  // 默认使用涨跌榜
  buyBatchSize: 1,
  buyBatchExecutionInterval: 60,
  buyBatchExecutionGroupSize: 1,
  sellBatchSize: 1,
  sellBatchExecutionInterval: 60,
  sellBatchExecutionGroupSize: 1
})

const timeRangeError = ref('')

const providers = ref([])
const accounts = ref([])
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

// 加载账户列表
const loadAccounts = async () => {
  try {
    const data = await accountApi.getAll()
    accounts.value = Array.isArray(data) ? data : []
  } catch (err) {
    console.error('[AddModelModal] Error loading accounts:', err)
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
  
  // 检查账户列表是否为空
  if (accounts.value.length === 0) {
    alert('暂无可用账户，请先添加账户')
    return
  }
  
  // 检查是否选择了账户
  if (!formData.value.accountAlias || !formData.value.accountAlias.trim()) {
    alert('请选择账户（必填）')
    return
  }
  
  if (!formData.value.initialCapital || formData.value.initialCapital <= 0) {
    alert('请输入有效的初始资金')
    return
  }
  
  if (!formData.value.maxPositions || formData.value.maxPositions < 1) {
    alert('请输入有效的最大持仓数量（必须 >= 1）')
    return
  }

  // 禁止买入时间段必须成对设置
  const start = formData.value.forbidBuyStart
  const end = formData.value.forbidBuyEnd
  timeRangeError.value = ''
  if ((start && !end) || (!start && end)) {
    timeRangeError.value = '禁止买入开始/结束必须同时设置（或同时清空）'
    alert(timeRangeError.value)
    return
  }
  
  loading.value = true
  try {
    await modelApi.create({
      providerId: formData.value.providerId,
      modelName: formData.value.modelName,
      name: formData.value.displayName,
      initialCapital: formData.value.initialCapital,
      maxPositions: formData.value.maxPositions,
      autoClosePercent: formData.value.autoClosePercent || null,
      baseVolume: formData.value.baseVolume || null,
      dailyReturn: formData.value.dailyReturn || null,
      lossesNum: formData.value.lossesNum || null,
      forbidBuyStart: formData.value.forbidBuyStart || null,
      forbidBuyEnd: formData.value.forbidBuyEnd || null,
      sameSymbolInterval: formData.value.sameSymbolInterval && formData.value.sameSymbolInterval > 0 ? formData.value.sameSymbolInterval : null,
      accountAlias: formData.value.accountAlias,
      isVirtual: formData.value.isVirtual,
      symbolSource: formData.value.symbolSource,
      buyBatchSize: formData.value.buyBatchSize || 1,
      buyBatchExecutionInterval: formData.value.buyBatchExecutionInterval || 60,
      buyBatchExecutionGroupSize: formData.value.buyBatchExecutionGroupSize || 1,
      sellBatchSize: formData.value.sellBatchSize || 1,
      sellBatchExecutionInterval: formData.value.sellBatchExecutionInterval || 60,
      sellBatchExecutionGroupSize: formData.value.sellBatchExecutionGroupSize || 1
    })
    alert('模型添加成功')
    clearForm()
    emit('update:visible', false)
    emit('close')
    emit('refresh')
  } catch (err) {
    console.error('[AddModelModal] Error creating model:', err)
    alert('添加模型失败: ' + (err.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

const clearForm = () => {
  formData.value = {
    providerId: '',
    modelName: '',
    displayName: '',
    initialCapital: 100000,
    maxPositions: 3,  // 重置为默认值3
    autoClosePercent: null,  // 重置为默认值
    baseVolume: null,  // 重置为默认值
    dailyReturn: null,  // 重置为默认值
    lossesNum: null,  // 重置为默认值
    forbidBuyStart: null,
    forbidBuyEnd: null,
    sameSymbolInterval: null,
    accountAlias: '',
    isVirtual: true,  // 重置为默认值 true（虚拟账户）
    symbolSource: 'leaderboard',  // 重置为默认值
    buyBatchSize: 1,
    buyBatchExecutionInterval: 60,
    buyBatchExecutionGroupSize: 1,
    sellBatchSize: 1,
    sellBatchExecutionInterval: 60,
    sellBatchExecutionGroupSize: 1
  }
  availableModels.value = []
  timeRangeError.value = ''
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
    loadAccounts()
  }
})
</script>

<style scoped>
.form-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* 小屏幕自动单列 */
@media (max-width: 768px) {
  .form-grid-2col {
    grid-template-columns: 1fr;
  }
}
</style>
