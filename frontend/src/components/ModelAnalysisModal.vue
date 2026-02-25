<template>
  <Modal
    :visible="visible"
    title="交易模型数据分析"
    large
    width="960px"
    @update:visible="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="analysis-container">
      <div v-if="loading" class="loading-container">
        <i class="bi bi-arrow-repeat spin" style="font-size: 24px; color: var(--primary);"></i>
        <p style="margin-top: 12px; color: var(--text-2);">加载中...</p>
      </div>
      <div v-else-if="error" class="error-container">
        <i class="bi bi-exclamation-triangle" style="font-size: 24px; color: var(--danger);"></i>
        <p style="margin-top: 12px; color: var(--danger);">{{ error }}</p>
      </div>
      <div v-else>
        <div v-if="analysisData.length === 0" class="empty-state">
          <i class="bi bi-inbox" style="font-size: 48px; color: var(--text-3);"></i>
          <p style="margin-top: 16px; color: var(--text-2);">暂无分析数据</p>
        </div>
        <div v-else class="analysis-table-container">
          <table class="analysis-table">
            <thead>
              <tr>
                <th>模型信息</th>
                <th>交易次数</th>
                <th>胜率</th>
                <th>平均盈利</th>
                <th>平均亏损</th>
                <th>盈亏比</th>
                <th>总盈亏比</th>
                <th>期望值</th>
                <th>每笔交易平均时长</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in analysisData"
                :key="index"
                :class="{ 'negative-row': isNegativeRow(item) }"
              >
                <td class="strategy-name">{{ item.strategy_name || item.model_name || '未知策略' }}</td>
                <td>{{ item.trade_count || 0 }}</td>
                <td>
                  <span v-if="item.win_rate !== null && item.win_rate !== undefined">
                    {{ formatPercentage(item.win_rate) }}
                  </span>
                  <span v-else class="empty-value">-</span>
                </td>
                <td>
                  <span v-if="item.avg_profit !== null && item.avg_profit !== undefined" class="profit-value">
                    {{ formatNumber(item.avg_profit) }}
                  </span>
                  <span v-else class="empty-value">-</span>
                </td>
                <td>
                  <span v-if="item.avg_loss !== null && item.avg_loss !== undefined" class="loss-value">
                    {{ formatNumber(item.avg_loss) }}
                  </span>
                  <span v-else class="empty-value">-</span>
                </td>
                <td>
                  <span v-if="item.profit_loss_ratio !== null && item.profit_loss_ratio !== undefined">
                    {{ formatNumber(item.profit_loss_ratio, 2) }}
                  </span>
                  <span v-else class="empty-value">-</span>
                </td>
                <td>
                  <span v-if="item.total_profit_ratio !== null && item.total_profit_ratio !== undefined">
                    {{ formatNumber(item.total_profit_ratio, 2) }}
                  </span>
                  <span v-else class="empty-value">-</span>
                </td>
                <td>
                  <span v-if="item.expected_value !== null && item.expected_value !== undefined" 
                        :class="getExpectedValueClass(item.expected_value)">
                    {{ formatExpectedValue(item.expected_value) }}
                  </span>
                  <span v-else class="empty-value">-</span>
                </td>
                <td>
                  <span v-if="getAvgDurationSeconds(item) !== null && getAvgDurationSeconds(item) !== undefined">
                    {{ formatDuration(getAvgDurationSeconds(item)) }}
                  </span>
                  <span v-else class="empty-value">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
import { ref, watch } from 'vue'
import Modal from './Modal.vue'
import { modelApi } from '../services/api.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close'])

const loading = ref(false)
const error = ref(null)
const analysisData = ref([])

// 判断是否为负收益行（需要红色高亮）
const isNegativeRow = (item) => {
  // 如果胜率为0或平均盈利为空且平均亏损不为空，则标记为负收益行
  return (item.win_rate === 0 || (item.win_rate !== null && item.win_rate < 0.5)) && 
         (item.avg_profit === null || item.avg_profit === undefined) &&
         (item.avg_loss !== null && item.avg_loss !== undefined)
}

// 格式化百分比
const formatPercentage = (value) => {
  if (value === null || value === undefined) return '-'
  return (value * 100).toFixed(2) + '%'
}

// 格式化数字
const formatNumber = (value, decimals = 2) => {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(decimals)
}

// 格式化期望值（带正负号）
const formatExpectedValue = (value) => {
  if (value === null || value === undefined) return '-'
  const num = Number(value)
  const sign = num >= 0 ? '+' : ''
  return sign + num.toFixed(2)
}

// 获取期望值的样式类
const getExpectedValueClass = (value) => {
  if (value === null || value === undefined) return ''
  const num = Number(value)
  return num >= 0 ? 'expected-value-positive' : 'expected-value-negative'
}

// 获取每笔交易平均时长（兼容 camelCase 和 snake_case）
const getAvgDurationSeconds = (item) => {
  return item.avgDurationSeconds ?? item.avg_duration_seconds
}

// 格式化时长（秒 -> 分钟，支持小数，不满1分钟的显示小数）
const formatDuration = (seconds) => {
  if (seconds === null || seconds === undefined || isNaN(Number(seconds))) return '-'
  const s = Number(seconds)
  if (s < 0) return '-'
  const minutes = (s / 60).toFixed(2)
  return `${minutes}分钟`
}

// 加载分析数据
const loadAnalysisData = async () => {
  loading.value = true
  error.value = null
  analysisData.value = []

  try {
    const data = await modelApi.getAllModelsAnalysis()
    analysisData.value = data || []
  } catch (err) {
    console.error('加载分析数据失败:', err)
    error.value = err.message || '加载分析数据失败'
  } finally {
    loading.value = false
  }
}

// 关闭对话框
const handleClose = () => {
  emit('update:visible', false)
  emit('close')
}

// 监听visible变化，当对话框打开时加载数据
watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadAnalysisData()
  }
})
</script>

<style scoped>
.analysis-container {
  padding: 20px;
  min-height: 400px;
}

.loading-container,
.error-container,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.analysis-table-container {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid var(--border-color, #dcdfe6);
}

.analysis-table {
  width: 100%;
  border-collapse: collapse;
  background-color: #fff;
  font-size: 14px;
}

.analysis-table thead {
  background-color: #f5f7fa;
}

.analysis-table th {
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  color: #303133;
  border-bottom: 2px solid #dcdfe6;
  white-space: nowrap;
}

.analysis-table td {
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
  color: #606266;
}

.analysis-table tbody tr:hover {
  background-color: #f5f7fa;
}

.analysis-table tbody tr.negative-row {
  background-color: #fef0f0;
}

.analysis-table tbody tr.negative-row:hover {
  background-color: #fde2e2;
}

.strategy-name {
  font-weight: 500;
  color: #303133;
}

.profit-value {
  color: #67c23a;
  font-weight: 500;
}

.loss-value {
  color: #f56c6c;
  font-weight: 500;
}

.expected-value-positive {
  color: #67c23a;
  font-weight: 500;
}

.expected-value-negative {
  color: #f56c6c;
  font-weight: 500;
}

.empty-value {
  color: #c0c4cc;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .analysis-table-container {
    font-size: 12px;
  }

  .analysis-table th,
  .analysis-table td {
    padding: 8px 12px;
  }
}
</style>
