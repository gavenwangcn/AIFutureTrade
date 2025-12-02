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
// API 服务
import { marketApi } from '../services/api.js'

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

    // 创建新图表（优先使用 DOM 元素，如果失败则使用 ID）
    // 注意：init 可以接受容器 ID 字符串或 DOM 元素
    console.log('[KLineChart] Initializing chart with container ID:', containerId)
    console.log('[KLineChart] Container element:', containerElement)
    console.log('[KLineChart] Init function:', init)
    
    if (typeof init !== 'function') {
      console.error('[KLineChart] init is not a function:', typeof init)
      return
    }
    
    // 尝试使用 DOM 元素初始化（更可靠）
    try {
      chart.value = init(containerElement)
    } catch (e) {
      console.warn('[KLineChart] Failed to init with DOM element, trying with ID:', e)
      // 如果使用 DOM 元素失败，尝试使用 ID
      chart.value = init(containerId)
    }
    
    if (!chart.value) {
      console.error('[KLineChart] Failed to initialize chart - init returned:', chart.value)
      return
    }
    
    console.log('[KLineChart] Chart instance created:', chart.value)
    console.log('[KLineChart] Chart instance type:', typeof chart.value)
    console.log('[KLineChart] Chart instance methods:', Object.keys(chart.value || {}))

    // 获取图表实例（处理可能的响应式包装）
    const chartInstance = chart.value
    
    // 检查图表实例是否有必要的方法
    if (typeof chartInstance !== 'object' || chartInstance === null) {
      console.error('[KLineChart] Invalid chart instance:', chartInstance)
      return
    }

    // 注意：klinecharts 9.0.0 可能不支持 setTheme，或者主题设置方式不同
    // 如果图表库支持主题设置，可以通过 CSS 或其他方式实现
    // 暂时跳过主题设置，避免错误
    
    // 设置交易对（可选，某些版本可能不需要）
    if (typeof chartInstance.setSymbol === 'function') {
      try {
        chartInstance.setSymbol({ ticker: props.symbol })
        console.log('[KLineChart] Symbol set:', props.symbol)
      } catch (e) {
        console.warn('[KLineChart] setSymbol failed (non-critical):', e)
      }
    } else {
      console.warn('[KLineChart] setSymbol method not available (may not be required in this version)')
      // 不返回，继续初始化，因为 symbol 可以通过 setDataLoader 传递
    }
    
    // 设置周期（可选，某些版本可能不需要）
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
    if (typeof chartInstance.setPeriod === 'function') {
      try {
        chartInstance.setPeriod(period)
        console.log('[KLineChart] Period set:', period)
      } catch (e) {
        console.warn('[KLineChart] setPeriod failed (non-critical):', e)
      }
    } else {
      console.warn('[KLineChart] setPeriod method not available (may not be required in this version)')
      // 不返回，继续初始化，因为 period 可以通过 setDataLoader 传递
    }

    // 设置数据加载器（这是必需的，用于加载K线数据）
    if (typeof chartInstance.setDataLoader === 'function') {
      try {
        chartInstance.setDataLoader({
          getBars: async ({ callback, symbol, interval, from, to }) => {
            try {
              // 使用传入的 symbol 和 interval，如果没有则使用 props 中的值
              const requestSymbol = symbol || props.symbol
              const requestInterval = interval || currentInterval.value
              
              console.log('[KLineChart] Loading data for:', { requestSymbol, requestInterval, from, to })
              
              // 调用后端API获取K线数据
              const data = await marketApi.getKlines(
                requestSymbol,
                requestInterval,
                500
              )
              
              // 后端返回格式：{ symbol, interval, data: [...] }
              // 其中 data 数组中的每个元素格式为：
              // { timestamp: 毫秒时间戳, open, high, low, close, volume, ... }
              if (data && data.data && Array.isArray(data.data)) {
                // 转换数据格式（后端已经返回了正确的格式，只需要确保类型正确）
                const bars = data.data.map(kline => ({
                  timestamp: typeof kline.timestamp === 'number' 
                    ? kline.timestamp 
                    : (kline.kline_start_time 
                        ? new Date(kline.kline_start_time).getTime() 
                        : Date.now()),
                  open: parseFloat(kline.open) || 0,
                  high: parseFloat(kline.high) || 0,
                  low: parseFloat(kline.low) || 0,
                  close: parseFloat(kline.close) || 0,
                  volume: parseFloat(kline.volume) || 0
                })).filter(bar => bar.timestamp > 0) // 过滤无效数据
                
                console.log('[KLineChart] Data loaded:', bars.length, 'bars')
                callback(bars)
              } else {
                console.warn('[KLineChart] No data received or invalid format:', data)
                callback([])
              }
            } catch (error) {
              console.error('[KLineChart] Error loading data:', error)
              callback([])
            }
          }
        })
        console.log('[KLineChart] Data loader set successfully')
      } catch (e) {
        console.error('[KLineChart] setDataLoader failed:', e)
        throw e // 重新抛出错误，因为这是必需的
      }
    } else {
      console.error('[KLineChart] setDataLoader method not available - this is required!')
      // 如果 setDataLoader 不可用，尝试直接加载数据
      // 某些版本的 klinecharts 可能需要不同的初始化方式
      try {
        // 尝试直接加载初始数据
        const data = await marketApi.getKlines(props.symbol, currentInterval.value, 500)
        if (data && data.data && Array.isArray(data.data)) {
          const bars = data.data.map(kline => ({
            timestamp: typeof kline.timestamp === 'number' 
              ? kline.timestamp 
              : (kline.kline_start_time 
                  ? new Date(kline.kline_start_time).getTime() 
                  : Date.now()),
            open: parseFloat(kline.open) || 0,
            high: parseFloat(kline.high) || 0,
            low: parseFloat(kline.low) || 0,
            close: parseFloat(kline.close) || 0,
            volume: parseFloat(kline.volume) || 0
          })).filter(bar => bar.timestamp > 0)
          
          // 如果图表实例有 loadMore 或其他方法，尝试使用
          if (typeof chartInstance.loadMore === 'function') {
            chartInstance.loadMore(bars)
          } else if (typeof chartInstance.updateData === 'function') {
            chartInstance.updateData(bars)
          } else {
            console.warn('[KLineChart] No method available to load data directly')
          }
        }
      } catch (error) {
        console.error('[KLineChart] Failed to load initial data:', error)
      }
    }

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
    
    // 尝试设置周期（如果方法可用）
    if (typeof chart.value.setPeriod === 'function') {
      try {
        chart.value.setPeriod(period)
        console.log('[KLineChart] Period changed to:', period)
      } catch (e) {
        console.warn('[KLineChart] setPeriod failed (non-critical):', e)
      }
    }
    
    // 重新加载数据
    if (typeof chart.value.reload === 'function') {
      try {
        chart.value.reload()
      } catch (e) {
        console.warn('[KLineChart] reload failed:', e)
        // 如果 reload 失败，重新初始化图表
        initChart()
      }
    } else {
      // 如果没有 reload 方法，重新初始化图表以加载新周期的数据
      console.log('[KLineChart] Reloading chart for new interval')
      initChart()
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
    // 如果 setSymbol 可用，尝试设置 symbol
    if (typeof chart.value.setSymbol === 'function') {
      try {
        chart.value.setSymbol({ ticker: newVal })
      } catch (e) {
        console.warn('[KLineChart] setSymbol failed (non-critical):', e)
      }
    }
    // 重新加载数据（通过 reload 或重新初始化数据加载器）
    if (typeof chart.value.reload === 'function') {
      try {
        chart.value.reload()
      } catch (e) {
        console.warn('[KLineChart] reload failed:', e)
        // 如果 reload 失败，重新初始化图表
        initChart()
      }
    } else {
      // 如果没有 reload 方法，重新初始化图表
      console.log('[KLineChart] Reloading chart for new symbol')
      initChart()
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

