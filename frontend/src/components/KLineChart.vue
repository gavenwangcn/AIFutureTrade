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
          <div ref="chartContainerRef" class="kline-chart-container">
            <div class="loading-overlay" v-if="isLoading">
              <div class="loader"></div>
              <div class="loading-text">加载中...</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { createDataLoader } from '../utils/customDatafeed.js'

// 使用 UMD 方式引入 KLineChart 10.0.0
// 文件由 Dockerfile 构建时从 KLineChart/dist/umd/ 复制到 public/klinecharts/
const getKLineCharts = () => {
  if (typeof window !== 'undefined' && window.klinecharts) {
    return window.klinecharts
  }
  
  // 如果 UMD 版本不可用，说明构建或加载有问题
  throw new Error(
    'klinecharts (UMD) is not available. ' +
    'Please ensure /klinecharts/klinecharts.min.js is loaded via script tag in index.html. ' +
    'This should be handled automatically by Dockerfile build process.'
  )
}

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
const dataLoader = ref(null)
const currentInterval = ref(props.interval)
const title = ref(`${props.symbol} - K线图`)
const isLoading = ref(false)

// Timeframes configuration
// KLineChart 10.0.0 使用 { span: number, type: string } 格式
const timeframes = [
  { value: '1m', label: '1分钟', period: { span: 1, type: 'minute' } },
  { value: '5m', label: '5分钟', period: { span: 5, type: 'minute' } },
  { value: '15m', label: '15分钟', period: { span: 15, type: 'minute' } },
  { value: '1h', label: '1小时', period: { span: 1, type: 'hour' } },
  { value: '4h', label: '4小时', period: { span: 4, type: 'hour' } },
  { value: '1d', label: '1天', period: { span: 1, type: 'day' } },
  { value: '1w', label: '1周', period: { span: 1, type: 'week' } }
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
    type: 'PERPETUAL',
    pricePrecision: 6,  // 价格精度设置为6位小数
    volumePrecision: 0  // 成交量精度保持0位小数
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
    // 获取 klinecharts 库（UMD 方式）
    const klinecharts = getKLineCharts()
    const { init, dispose } = klinecharts
    
    // Clear container
    chartContainerRef.value.innerHTML = ''
    
    // Create data loader with loading callbacks
    dataLoader.value = createDataLoader(
      () => { isLoading.value = true },
      () => { isLoading.value = false }
    )
    
    // Convert symbol and period
    const symbolInfo = symbolToSymbolInfo(props.symbol)
    const period = intervalToPeriod(currentInterval.value)
    
    // 定义K线样式：红涨绿跌（中国股市习惯）
    // 参考文档：https://klinecharts.com/guide/styles
    const chartStyles = {
      candle: {
        type: 'candle_solid',
        bar: {
          // 'current_open' | 'previous_close'
          compareRule: 'current_open',
          // 上涨用红色（红涨）
          upColor: '#F92855',
          upBorderColor: '#F92855',
          upWickColor: '#F92855',
          // 下跌用绿色（绿跌）
          downColor: '#2DC08E',
          downBorderColor: '#2DC08E',
          downWickColor: '#2DC08E',
          // 无变化用灰色
          noChangeColor: '#888888',
          noChangeBorderColor: '#888888',
          noChangeWickColor: '#888888'
        },
        priceMark: {
          show: true,
          last: {
            show: true,
            compareRule: 'current_open',
            // 上涨用红色
            upColor: '#F92855',
            // 下跌用绿色
            downColor: '#2DC08E',
            // 无变化用灰色
            noChangeColor: '#888888',
            line: {
              show: true,
              style: 'dashed',
              dashedValue: [4, 4],
              size: 1
            },
            text: {
              show: true,
              style: 'fill',
              size: 12,
              paddingLeft: 4,
              paddingTop: 4,
              paddingRight: 4,
              paddingBottom: 4,
              borderStyle: 'solid',
              borderSize: 0,
              borderColor: 'transparent',
              borderDashedValue: [2, 2],
              color: '#FFFFFF',
              family: 'Helvetica Neue',
              weight: 'normal',
              borderRadius: 2
            }
          }
        }
      }
    }
    
    // Initialize chart using KLineChart 10.0.0 API
    // 参考文档：https://klinecharts.com/api/chart/init
    // 在初始化时通过 options.styles 设置样式
    chartInstance.value = init(chartContainerRef.value, {
      styles: chartStyles
    })
    
    // Set symbol and period
    chartInstance.value.setSymbol(symbolInfo)
    chartInstance.value.setPeriod(period)
    
    // Set data loader
    chartInstance.value.setDataLoader(dataLoader.value)
    
    // 确保样式正确应用（使用 setStyles 方法再次设置，确保样式生效）
    // 参考文档：https://klinecharts.com/api/instance/setStyles
    if (typeof chartInstance.value.setStyles === 'function') {
      chartInstance.value.setStyles(chartStyles)
    }
    
    // Create default indicators
    // 主指标（叠加在K线上）：MA
    chartInstance.value.createIndicator('MA', false, { id: 'candle_pane' })
    // 副指标（独立面板）：VOL, MACD, RSI
    chartInstance.value.createIndicator('VOL', false)
    chartInstance.value.createIndicator('MACD', false)
    chartInstance.value.createIndicator('RSI', false)
    
    console.log('[KLineChart] Chart initialized successfully with red-up-green-down style')
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
  // Destroy chart using KLineChart 10.0.0 API
  if (chartInstance.value && chartContainerRef.value) {
    try {
      const klinecharts = getKLineCharts()
      const { dispose } = klinecharts
      dispose(chartContainerRef.value)
    } catch (error) {
      console.error('[KLineChart] Error destroying chart:', error)
    }
  }
  
  // Clear references
  chartInstance.value = null
  dataLoader.value = null
  
  // Clear container
  if (chartContainerRef.value) {
    chartContainerRef.value.innerHTML = ''
  }
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
  width: 80%;
  height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 响应式调整，确保在不同屏幕尺寸下都能占满3/4屏幕 */
@media (max-width: 1200px) {
  .kline-modal-content {
    width: 85%;
    height: 90vh;
  }
}

@media (max-width: 768px) {
  .kline-modal-content {
    width: 95%;
    height: 95vh;
  }
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

/* Scoped styles for klinecharts component */
.kline-chart-container {
  width: 100%;
  height: 100%;
  position: relative;
}

/* Loading styles */
.loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(255, 255, 255, 0.7);
  z-index: 100;
}

.loader {
  width: 48px;
  height: 48px;
  border: 5px solid #f3f3f3;
  border-top: 5px solid #1677ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-text {
  font-size: 16px;
  color: #666;
  font-weight: 500;
}
</style>