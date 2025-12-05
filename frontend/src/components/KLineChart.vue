<template>
  <Teleport to="body">
    <div class="kline-modal" v-if="visible" @click.self="handleClose">
      <div class="kline-modal-content">
        <div class="kline-modal-header">
          <h3>{{ title }}</h3>
          <div class="kline-toolbar">
            <div class="kline-timeframes">
              <button
                v-for="tf in timeframes"
                :key="tf.value"
                :class="{ 'timeframe-btn': true, 'active': currentInterval === tf.value }"
                @click="handleTimeframeChange(tf.value)"
              >
                {{ tf.label }}
              </button>
            </div>
            <button class="close-btn" @click="handleClose">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
        </div>
        <div class="kline-modal-body">
          <div ref="chartContainerRef" class="kline-chart-container"></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { CustomDatafeed } from '../utils/customDatafeed.js'
// 直接导入自构建的 klinecharts-pro 包
import { KLineChartPro } from '@klinecharts/pro'
import '@klinecharts/pro/dist/klinecharts-pro.css'

// Props
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

// Emits
const emit = defineEmits(['close', 'interval-change'])

// Reactive data
const chartContainerRef = ref(null)
const chartInstance = ref(null)
const datafeedInstance = ref(null)
const currentInterval = ref(props.interval)
const title = ref(`${props.symbol} - K线图`)

// Timeframes configuration
const timeframes = [
  { value: '1m', label: '1分钟', period: { multiplier: 1, timespan: 'minute', text: '1m' } },
  { value: '5m', label: '5分钟', period: { multiplier: 5, timespan: 'minute', text: '5m' } },
  { value: '15m', label: '15分钟', period: { multiplier: 15, timespan: 'minute', text: '15m' } },
  { value: '1h', label: '1小时', period: { multiplier: 1, timespan: 'hour', text: '1h' } },
  { value: '4h', label: '4小时', period: { multiplier: 4, timespan: 'hour', text: '4h' } },
  { value: '1d', label: '1天', period: { multiplier: 1, timespan: 'day', text: '1d' } },
  { value: '1w', label: '1周', period: { multiplier: 1, timespan: 'week', text: '1w' } }
]

// Convert interval string to Period object
const intervalToPeriod = (interval) => {
  const timeframe = timeframes.find(tf => tf.value === interval)
  return timeframe ? timeframe.period : timeframes[1].period // Default to 5m
}

// Convert symbol string to SymbolInfo object
const symbolToSymbolInfo = (symbol) => {
  return {
    ticker: symbol,
    shortName: symbol.replace('USDT', ''),
    name: `${symbol}永续合约`,
    exchange: 'BINANCE',
    market: 'futures',
    priceCurrency: 'usd',
    type: 'PERPETUAL'
  }
}

// Initialize chart
const initChart = async () => {
  // Wait for DOM to be ready
  await nextTick()
  
  // Destroy existing chart if it exists
  destroyChart()
  
  if (!chartContainerRef.value) {
    console.error('[KLineChart] Chart container not found')
    return
  }
  
  try {
    // Clear container
    chartContainerRef.value.innerHTML = ''
    
    // Create datafeed instance
    datafeedInstance.value = new CustomDatafeed()
    
    // Convert symbol and period
    const symbolInfo = symbolToSymbolInfo(props.symbol)
    const period = intervalToPeriod(currentInterval.value)
    
    // Create KLineChartPro instance
    // 使用 klinecharts-pro 中的默认配置（periods, mainIndicators, subIndicators）
    // 默认配置在 frontend/klinecharts-pro/src/KLineChartPro.tsx 中定义
    chartInstance.value = new KLineChartPro({
      container: chartContainerRef.value,
      symbol: symbolInfo,
      period: period,
      // periods 不指定，使用 klinecharts-pro 默认值：['1m', '5m', '15m', '1h', '4h', '1d', '1w']
      // mainIndicators 不指定，使用 klinecharts-pro 默认值：['MA']
      // subIndicators 不指定，使用 klinecharts-pro 默认值：['MA', 'RSI', 'MACD', 'VOL']
      datafeed: datafeedInstance.value,
      theme: 'light'
    })
    
    console.log('[KLineChart] Chart initialized successfully')
  } catch (error) {
    console.error('[KLineChart] Failed to initialize chart:', error)
  }
}

// Handle timeframe change
const handleTimeframeChange = (interval) => {
  currentInterval.value = interval
  emit('interval-change', interval)
  
  if (chartInstance.value && typeof chartInstance.value.setPeriod === 'function') {
    const period = intervalToPeriod(interval)
    chartInstance.value.setPeriod(period)
  }
}

// Handle close
const handleClose = () => {
  emit('close')
}

// Watch for visibility changes
watch(() => props.visible, async (newVal) => {
  if (newVal) {
    title.value = `${props.symbol} - K线图`
    currentInterval.value = props.interval
    await nextTick()
    // Add small delay to ensure modal is fully rendered
    setTimeout(() => {
      initChart()
    }, 100)
  } else {
    destroyChart()
  }
}, { immediate: false })

// Watch for symbol changes
watch(() => props.symbol, (newVal) => {
  if (newVal && props.visible) {
    title.value = `${newVal} - K线图`
    
    if (chartInstance.value && typeof chartInstance.value.setSymbol === 'function') {
      const symbolInfo = symbolToSymbolInfo(newVal)
      chartInstance.value.setSymbol(symbolInfo)
    } else {
      // Reinitialize if setSymbol is not available
      initChart()
    }
  }
})

// Watch for interval changes
watch(() => props.interval, (newVal) => {
  if (newVal && props.visible) {
    currentInterval.value = newVal
    
    if (chartInstance.value && typeof chartInstance.value.setPeriod === 'function') {
      const period = intervalToPeriod(newVal)
      chartInstance.value.setPeriod(period)
    }
  }
})

// Destroy chart and cleanup
const destroyChart = () => {
  // Destroy datafeed
  if (datafeedInstance.value && typeof datafeedInstance.value.destroy === 'function') {
    try {
      datafeedInstance.value.destroy()
    } catch (error) {
      console.error('[KLineChart] Error destroying datafeed:', error)
    }
  }
  datafeedInstance.value = null
  
  // Destroy chart
  if (chartInstance.value) {
    try {
      // Try multiple destruction methods
      if (typeof chartInstance.value.destroy === 'function') {
        chartInstance.value.destroy()
      } else if (typeof chartInstance.value.dispose === 'function') {
        chartInstance.value.dispose()
      }
      
      // Clear container
      if (chartContainerRef.value) {
        chartContainerRef.value.innerHTML = ''
      }
    } catch (error) {
      console.error('[KLineChart] Error destroying chart:', error)
      
      // Fallback: clear container
      if (chartContainerRef.value) {
        chartContainerRef.value.innerHTML = ''
      }
    }
  }
  chartInstance.value = null
}

// Cleanup on unmount
onUnmounted(() => {
  destroyChart()
})
</script>

<style scoped>
.kline-modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.kline-modal-content {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  width: 75%;
  height: 75vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kline-modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kline-modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.kline-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kline-timeframes {
  display: flex;
  gap: 8px;
}

.timeframe-btn {
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.timeframe-btn:hover {
  background: #f5f5f5;
}

.timeframe-btn.active {
  background: #1677ff;
  color: white;
  border-color: #1677ff;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.2s;
}

.close-btn:hover {
  background: #f5f5f5;
}

.kline-modal-body {
  flex: 1;
  padding: 0;
  min-height: 500px;
  display: flex;
  flex-direction: column;
}

.kline-chart-container {
  flex: 1;
  min-height: 500px;
  width: 100%;
}

/* Scoped styles for klinecharts-pro component */
.kline-chart-container :deep(.klinecharts-pro) {
  width: 100%;
  height: 100%;
  /* Light theme colors (default) */
  --klinecharts-pro-primary-color: #1677ff;
  --klinecharts-pro-hover-background-color: rgba(22, 119, 255, 0.15);
  --klinecharts-pro-background-color: #FFFFFF;
  --klinecharts-pro-popover-background-color: #FFFFFF;
  --klinecharts-pro-text-color: #051441;
  --klinecharts-pro-text-second-color: #76808F;
  --klinecharts-pro-border-color: #ebedf1;
  --klinecharts-pro-selected-color: rgba(22, 119, 255, 0.15);
}

/* Dark theme support */
.kline-chart-container :deep(.klinecharts-pro[data-theme="dark"]) {
  --klinecharts-pro-hover-background-color: rgba(22, 119, 255, 0.15);
  --klinecharts-pro-background-color: #151517;
  --klinecharts-pro-popover-background-color: #1c1c1f;
  --klinecharts-pro-text-color: #F8F8F8;
  --klinecharts-pro-text-second-color: #929AA5;
  --klinecharts-pro-border-color: #292929;
}

/* 确保全局样式正确加载 */
:global(.klinecharts-pro) {
  width: 100%;
  height: 100%;
}
</style>