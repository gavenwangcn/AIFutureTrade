<template>
  <div class="kline-modal" v-if="visible" @click.self="handleClose">
    <div class="modal-content kline-modal-content">
      <div class="modal-header">
        <h3>{{ title }}</h3>
        <div class="kline-toolbar">
          <div class="kline-timeframes">
            <button
              v-for="tf in timeframes"
              :key="tf.value"
              :class="['timeframe-btn', { active: currentInterval === tf.value }]"
              @click="handleTimeframeChange(tf.value)"
            >
              {{ tf.label }}
            </button>
          </div>
          <button class="btn-icon" @click="handleClose">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
      </div>
      <div class="modal-body kline-modal-body">
        <div :id="chartContainerId" style="width: 100%; height: 600px;"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
// 使用 npm 安装的 klinecharts（按官网要求）
import { init, dispose } from 'klinecharts'
// API 配置
import { API_BASE_URL } from '../config/api.js'

// 检查 klinecharts 是否正确导入
console.log('[KLineChart] klinecharts imported:', { init: typeof init, dispose: typeof dispose })

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  symbol: {
    type: String,
    required: true
  },
  interval: {
    type: String,
    default: '5m'
  }
})

const emit = defineEmits(['close', 'interval-change'])

// 生成唯一的容器 ID（使用 ref 确保 ID 固定，避免使用已废弃的 substr）
const chartContainerId = ref(`kline-chart-${Math.random().toString(36).slice(2, 11)}`)
const chart = ref(null)
const currentInterval = ref(props.interval)
const title = ref(`${props.symbol} - K线图`)

const timeframes = [
  { value: '1m', label: '1分钟' },
  { value: '5m', label: '5分钟' },
  { value: '15m', label: '15分钟' },
  { value: '1h', label: '1小时' },
  { value: '4h', label: '4小时' },
  { value: '1d', label: '1天' },
  { value: '1w', label: '1周' }
]

// 初始化图表
const initChart = async () => {
  // 等待 DOM 完全渲染
  await nextTick()
  // 额外等待一小段时间确保容器元素已完全渲染
  await new Promise(resolve => setTimeout(resolve, 100))

  try {
    const containerId = chartContainerId.value
    const containerElement = document.getElementById(containerId)
    
    if (!containerElement) {
      console.error('[KLineChart] Container element not found:', containerId)
      console.error('[KLineChart] Available elements:', Array.from(document.querySelectorAll('[id^="kline-chart"]')).map(el => el.id))
      return
    }

    // 如果图表已存在，先销毁
    if (chart.value) {
      try {
        dispose(containerId)
      } catch (e) {
        console.warn('[KLineChart] Error disposing chart:', e)
      }
      chart.value = null
    }

    // 创建新图表（使用容器 ID，参考示例代码）
    // 注意：init 可以接受容器 ID 字符串或 DOM 元素
    console.log('[KLineChart] Initializing chart with container ID:', containerId)
    console.log('[KLineChart] Container element:', containerElement)
    console.log('[KLineChart] Init function:', init)
    
    if (typeof init !== 'function') {
      console.error('[KLineChart] init is not a function:', typeof init)
      return
    }
    
    chart.value = init(containerId)
    
    if (!chart.value) {
      console.error('[KLineChart] Failed to initialize chart - init returned:', chart.value)
      return
    }
    
    console.log('[KLineChart] Chart instance created:', chart.value)

    // 设置主题
    chart.value.setTheme('dark')
    
    // 设置交易对
    chart.value.setSymbol({ ticker: props.symbol })
    
    // 设置周期
    const periodMap = {
      '1m': { span: 1, type: 'minute' },
      '5m': { span: 5, type: 'minute' },
      '15m': { span: 15, type: 'minute' },
      '1h': { span: 1, type: 'hour' },
      '4h': { span: 4, type: 'hour' },
      '1d': { span: 1, type: 'day' },
      '1w': { span: 1, type: 'week' }
    }
    
    const period = periodMap[currentInterval.value] || periodMap['5m']
    chart.value.setPeriod(period)

    // 设置数据加载器（参考示例代码格式）
    chart.value.setDataLoader({
      getBars: async ({ callback, symbol, interval, from, to }) => {
        try {
          // 调用后端API获取K线数据
          const response = await fetch(`${API_BASE_URL}/api/market/klines?symbol=${symbol || props.symbol}&interval=${interval || currentInterval.value}&limit=500`)
          const data = await response.json()
          
          if (data.success && data.data) {
            // 转换数据格式（参考示例代码格式）
            const bars = data.data.map(kline => ({
              timestamp: new Date(kline.kline_start_time).getTime(),
              open: parseFloat(kline.open),
              high: parseFloat(kline.high),
              low: parseFloat(kline.low),
              close: parseFloat(kline.close),
              volume: parseFloat(kline.volume)
            }))
            
            callback(bars)
          } else {
            callback([])
          }
        } catch (error) {
          console.error('[KLineChart] Error loading data:', error)
          callback([])
        }
      }
    })

    console.log('[KLineChart] Chart initialized successfully')
  } catch (error) {
    console.error('[KLineChart] Failed to initialize chart:', error)
  }
}

// 切换时间间隔
const handleTimeframeChange = (interval) => {
  currentInterval.value = interval
  emit('interval-change', interval)
  
  if (chart.value) {
    const periodMap = {
      '1m': { span: 1, type: 'minute' },
      '5m': { span: 5, type: 'minute' },
      '15m': { span: 15, type: 'minute' },
      '1h': { span: 1, type: 'hour' },
      '4h': { span: 4, type: 'hour' },
      '1d': { span: 1, type: 'day' },
      '1w': { span: 1, type: 'week' }
    }
    
    const period = periodMap[interval] || periodMap['5m']
    chart.value.setPeriod(period)
    
    // 重新加载数据
    if (chart.value.reload) {
      chart.value.reload()
    }
  }
}

// 关闭弹窗
const handleClose = () => {
  emit('close')
}

// 监听 visible 变化
watch(() => props.visible, async (newVal) => {
  if (newVal) {
    title.value = `${props.symbol} - K线图`
    currentInterval.value = props.interval
    // 等待 DOM 更新后再初始化
    await nextTick()
    // 确保容器元素已渲染
    await new Promise(resolve => setTimeout(resolve, 50))
    initChart()
  } else {
    // 销毁图表（使用容器 ID）
    if (chart.value) {
      try {
        dispose(chartContainerId.value)
      } catch (e) {
        console.warn('[KLineChart] Error disposing chart:', e)
      }
      chart.value = null
    }
  }
}, { immediate: false })

// 监听 symbol 变化
watch(() => props.symbol, (newVal) => {
  if (newVal && props.visible && chart.value) {
    title.value = `${newVal} - K线图`
    chart.value.setSymbol({ ticker: newVal })
    // 重新加载数据
    if (chart.value.reload) {
      chart.value.reload()
    }
  }
})

// 组件卸载时清理（参考示例代码使用 onUnmounted）
onUnmounted(() => {
  if (chart.value) {
    try {
      dispose(chartContainerId.value)
    } catch (e) {
      console.warn('[KLineChart] Error disposing chart on unmount:', e)
    }
    chart.value = null
  }
})
</script>

<style scoped>
.kline-modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.kline-modal-content {
  background: var(--bg-secondary, #1a1a2e);
  border-radius: 12px;
  width: 95%;
  max-width: 1400px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.modal-header h3 {
  margin: 0;
  color: var(--text-primary, #fff);
}

.kline-toolbar {
  display: flex;
  align-items: center;
  gap: 15px;
}

.kline-timeframes {
  display: flex;
  gap: 8px;
}

.timeframe-btn {
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  color: var(--text-secondary, #ccc);
  cursor: pointer;
  transition: all 0.3s;
}

.timeframe-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.timeframe-btn.active {
  background: var(--primary-color, #4a90e2);
  border-color: var(--primary-color, #4a90e2);
  color: #fff;
}

.btn-icon {
  background: transparent;
  border: none;
  color: var(--text-secondary, #ccc);
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all 0.3s;
}

.btn-icon:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary, #fff);
}

.modal-body {
  flex: 1;
  padding: 20px;
  overflow: hidden;
}

.kline-modal-body {
  display: flex;
  flex-direction: column;
}
</style>

