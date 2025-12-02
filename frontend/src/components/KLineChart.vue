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

// 加载K线数据
const loadKlineData = async (symbol, interval) => {
  try {
    console.log('[KLineChart] Loading K-line data:', { symbol, interval })
    const response = await marketApi.getKlines(symbol, interval, 500)
    
    if (response && response.data && Array.isArray(response.data)) {
      // 转换数据格式为 klinecharts 需要的格式
      const bars = response.data.map(kline => {
        // 处理时间戳：后端返回的 timestamp 可能是数字或字符串
        let timestamp = kline.timestamp
        if (typeof timestamp === 'string') {
          timestamp = new Date(timestamp).getTime()
        } else if (typeof timestamp !== 'number') {
          // 如果没有 timestamp，尝试使用其他时间字段
          if (kline.kline_start_time) {
            timestamp = new Date(kline.kline_start_time).getTime()
          } else {
            timestamp = Date.now()
          }
        }
        
        return {
          timestamp: timestamp,
          open: parseFloat(kline.open) || 0,
          high: parseFloat(kline.high) || 0,
          low: parseFloat(kline.low) || 0,
          close: parseFloat(kline.close) || 0,
          volume: parseFloat(kline.volume) || 0
        }
      }).filter(bar => bar.timestamp > 0 && bar.close > 0) // 过滤无效数据
      
      console.log('[KLineChart] Data loaded:', bars.length, 'bars')
      return bars
    } else {
      console.warn('[KLineChart] Invalid data format:', response)
      return []
    }
  } catch (error) {
    console.error('[KLineChart] Error loading K-line data:', error)
    return []
  }
}

// 初始化图表
const initChart = async () => {
  // 等待 DOM 完全渲染
  await nextTick()
  // 额外等待一小段时间确保容器元素已完全渲染
  await new Promise(resolve => setTimeout(resolve, 150))

  try {
    const containerId = chartContainerId.value
    const containerElement = document.getElementById(containerId)
    
    if (!containerElement) {
      console.error('[KLineChart] Container element not found:', containerId)
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

    console.log('[KLineChart] Initializing chart with container ID:', containerId)
    
    if (typeof init !== 'function') {
      console.error('[KLineChart] init is not a function:', typeof init)
      return
    }
    
    // 初始化图表实例（使用 DOM 元素）
    let chartInstance
    try {
      chartInstance = init(containerElement)
    } catch (e) {
      console.warn('[KLineChart] Failed to init with DOM element, trying with ID:', e)
      chartInstance = init(containerId)
    }
    
    if (!chartInstance) {
      console.error('[KLineChart] Failed to initialize chart - init returned:', chartInstance)
      return
    }
    
    chart.value = chartInstance
    
    console.log('[KLineChart] Chart instance created')
    console.log('[KLineChart] Available methods:', Object.keys(chartInstance || {}).slice(0, 20))

    // 加载初始数据
    const bars = await loadKlineData(props.symbol, currentInterval.value)
    
    if (bars.length === 0) {
      console.warn('[KLineChart] No data loaded, chart may be empty')
    }

    // 尝试多种方式加载数据到图表
    let dataLoaded = false
    
    // 方法1: 使用 applyNewData（klinecharts 9.0.0+）
    if (typeof chartInstance.applyNewData === 'function') {
      try {
        chartInstance.applyNewData(bars, true) // true 表示替换现有数据
        console.log('[KLineChart] Data loaded via applyNewData')
        dataLoaded = true
      } catch (e) {
        console.warn('[KLineChart] applyNewData failed:', e)
      }
    }
    
    // 方法2: 使用 setDataLoader（如果支持）
    if (!dataLoaded && typeof chartInstance.setDataLoader === 'function') {
      try {
        chartInstance.setDataLoader({
          getBars: async ({ callback, symbol, interval, from, to }) => {
            const requestSymbol = symbol || props.symbol
            const requestInterval = interval || currentInterval.value
            const bars = await loadKlineData(requestSymbol, requestInterval)
            callback(bars)
          }
        })
        // 触发数据加载
        if (typeof chartInstance.loadData === 'function') {
          chartInstance.loadData()
        } else if (typeof chartInstance.reload === 'function') {
          chartInstance.reload()
        }
        console.log('[KLineChart] Data loader set successfully')
        dataLoaded = true
      } catch (e) {
        console.warn('[KLineChart] setDataLoader failed:', e)
      }
    }
    
    // 方法3: 使用 createDataSource 和 applyNewData
    if (!dataLoaded && typeof chartInstance.createDataSource === 'function') {
      try {
        const dataSource = chartInstance.createDataSource()
        if (dataSource && typeof dataSource.applyNewData === 'function') {
          dataSource.applyNewData(bars, true)
          console.log('[KLineChart] Data loaded via createDataSource')
          dataLoaded = true
        }
      } catch (e) {
        console.warn('[KLineChart] createDataSource failed:', e)
      }
    }
    
    // 方法4: 直接设置数据（如果图表支持）
    if (!dataLoaded) {
      // 检查图表实例是否有 data 属性
      if (chartInstance.data && Array.isArray(chartInstance.data)) {
        chartInstance.data = bars
        console.log('[KLineChart] Data set directly')
        dataLoaded = true
      }
    }
    
    if (!dataLoaded) {
      console.warn('[KLineChart] Could not load data using any available method')
      console.warn('[KLineChart] Chart instance methods:', Object.keys(chartInstance))
    }

    // 设置周期（如果支持）
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
        console.warn('[KLineChart] setPeriod failed:', e)
      }
    }

    console.log('[KLineChart] Chart initialized successfully')
  } catch (error) {
    console.error('[KLineChart] Failed to initialize chart:', error)
  }
}

// 切换时间间隔
const handleTimeframeChange = async (interval) => {
  currentInterval.value = interval
  emit('interval-change', interval)
  
  if (chart.value) {
    // 加载新周期的数据
    const bars = await loadKlineData(props.symbol, interval)
    
    if (bars.length > 0) {
      // 尝试更新数据
      if (typeof chart.value.applyNewData === 'function') {
        try {
          chart.value.applyNewData(bars, true)
          console.log('[KLineChart] Data updated via applyNewData')
        } catch (e) {
          console.warn('[KLineChart] applyNewData failed:', e)
          initChart() // 重新初始化
        }
      } else if (typeof chart.value.reload === 'function') {
        try {
          chart.value.reload()
        } catch (e) {
          console.warn('[KLineChart] reload failed:', e)
          initChart() // 重新初始化
        }
      } else {
        // 如果没有更新方法，重新初始化图表
        console.log('[KLineChart] Reloading chart for new interval')
        initChart()
      }
    } else {
      console.warn('[KLineChart] No data loaded for interval:', interval)
      initChart() // 重新初始化以尝试加载数据
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
watch(() => props.symbol, async (newVal) => {
  if (newVal && props.visible && chart.value) {
    title.value = `${newVal} - K线图`
    
    // 加载新 symbol 的数据
    const bars = await loadKlineData(newVal, currentInterval.value)
    
    if (bars.length > 0) {
      // 尝试更新数据
      if (typeof chart.value.applyNewData === 'function') {
        try {
          chart.value.applyNewData(bars, true)
          console.log('[KLineChart] Data updated for new symbol via applyNewData')
        } catch (e) {
          console.warn('[KLineChart] applyNewData failed:', e)
          initChart() // 重新初始化
        }
      } else if (typeof chart.value.reload === 'function') {
        try {
          chart.value.reload()
        } catch (e) {
          console.warn('[KLineChart] reload failed:', e)
          initChart() // 重新初始化
        }
      } else {
        // 如果没有更新方法，重新初始化图表
        console.log('[KLineChart] Reloading chart for new symbol')
        initChart()
      }
    } else {
      console.warn('[KLineChart] No data loaded for symbol:', newVal)
      initChart() // 重新初始化以尝试加载数据
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

