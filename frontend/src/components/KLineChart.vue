<template>
  <Teleport to="body">
    <div class="kline-modal" v-if="visible" @click.self="handleClose">
      <div class="kline-modal-content">
        <div class="kline-modal-header">
          <h3>{{ title }}</h3>
          <div class="kline-toolbar">
            <div class="kline-indicator-buttons">
              <button
                :class="{ 'indicator-btn': true, 'active': currentIndicator === 'MA' }"
                @click="handleIndicatorChange('MA')"
              >
                MA
              </button>
              <button
                :class="{ 'indicator-btn': true, 'active': currentIndicator === 'EMA' }"
                @click="handleIndicatorChange('EMA')"
              >
                EMA
              </button>
            </div>
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
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { createDataLoader } from '../utils/customDatafeed.js'

// 获取 KLineChart 库（UMD 方式）
const getKLineCharts = () => {
  if (typeof window !== 'undefined' && window.klinecharts) {
    return window.klinecharts
  }
  throw new Error(
    'klinecharts (UMD) is not available. ' +
    'Please ensure /klinecharts/klinecharts.min.js is loaded via script tag in index.html.'
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
const isInitializing = ref(false) // 标记是否正在初始化
const initTimeoutId = ref(null) // 存储初始化定时器ID
const currentIndicator = ref('MA') // 当前显示的指标：'MA' 或 'EMA'

// 时间周期配置
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

// 将 interval 字符串转换为 Period 对象
const intervalToPeriod = (interval) => {
  const timeframe = timeframes.find(tf => tf.value === interval)
  return timeframe ? timeframe.period : timeframes[1].period // 默认 5m
}

// 将 symbol 字符串转换为 SymbolInfo 对象
const symbolToSymbolInfo = (symbol) => {
  return {
    ticker: symbol,
    shortName: symbol.replace('USDT', ''),
    name: `${symbol}永续合约`,
    exchange: 'BINANCE',
    market: 'futures',
    priceCurrency: 'usd',
    type: 'PERPETUAL',
    pricePrecision: 6,
    volumePrecision: 0
  }
}

// 初始化图表
const initChart = async () => {
  if (!props.visible || !chartContainerRef.value) {
    return
  }

  // 如果正在初始化，直接返回，避免重复初始化
  if (isInitializing.value) {
    console.log('[KLineChart] Chart is already initializing, skipping...')
    return
  }

  // 清除之前的定时器
  if (initTimeoutId.value) {
    clearTimeout(initTimeoutId.value)
    initTimeoutId.value = null
  }

  // 标记为正在初始化
  isInitializing.value = true

  try {
  // 等待 DOM 渲染完成
  await nextTick()

  // 检查容器尺寸
  const container = chartContainerRef.value
  const rect = container.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    console.warn('[KLineChart] Container has zero size, retrying...')
      // 使用ref存储定时器ID，以便后续清除
      initTimeoutId.value = setTimeout(() => {
        initTimeoutId.value = null
        isInitializing.value = false
        initChart()
      }, 100)
    return
  }

    // 销毁已存在的图表
    if (chartInstance.value) {
      destroyChart()
      await nextTick()
    }

    // 清空容器
    container.innerHTML = ''

    // 获取 KLineChart 库
    const klinecharts = getKLineCharts()
    const { init } = klinecharts

    // 创建数据加载器
    dataLoader.value = createDataLoader()

    // 转换 symbol 和 period
    const symbolInfo = symbolToSymbolInfo(props.symbol)
    const period = intervalToPeriod(currentInterval.value)

    // K线样式配置：红涨绿跌（中国股市习惯）
    // 参考：https://klinecharts.com/guide/styles
    const chartStyles = {
      candle: {
        type: 'candle_solid',
        bar: {
          compareRule: 'current_open',
          upColor: '#F92855',
          upBorderColor: '#F92855',
          upWickColor: '#F92855',
          downColor: '#2DC08E',
          downBorderColor: '#2DC08E',
          downWickColor: '#2DC08E',
          noChangeColor: '#888888',
          noChangeBorderColor: '#888888',
          noChangeWickColor: '#888888'
        },
        priceMark: {
          show: true,
          last: {
            show: true,
            compareRule: 'current_open',
            upColor: '#F92855',
            downColor: '#2DC08E',
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
              color: '#FFFFFF',
              family: 'Helvetica Neue',
              weight: 'normal',
              borderRadius: 2
            }
          }
        }
      }
    }

    // 初始化图表
    // 参考：https://klinecharts.com/api/chart/init
    chartInstance.value = init(container, {
      styles: chartStyles
    })

    // 设置标的和周期
    chartInstance.value.setSymbol(symbolInfo)
    chartInstance.value.setPeriod(period)

    // 设置数据加载器
    chartInstance.value.setDataLoader(dataLoader.value)

    // 创建默认指标（根据当前选中的指标类型）
    chartInstance.value.createIndicator(currentIndicator.value, false, { id: 'candle_pane' })
    chartInstance.value.createIndicator('VOL', false)
    chartInstance.value.createIndicator('MACD', false)
    chartInstance.value.createIndicator('KDJ', false)
    chartInstance.value.createIndicator('RSI', false)
    
    // 创建ATR指标（ATR指标应在构建时已包含在klinecharts.min.js中）
    const supportedIndicators = klinecharts.getSupportedIndicators()
    console.log('[KLineChart] Supported indicators:', supportedIndicators)
    
    if (supportedIndicators.includes('ATR')) {
      const atrIndicatorId = chartInstance.value.createIndicator('ATR', false)
      console.log('[KLineChart] ATR indicator created with id:', atrIndicatorId)
    } else {
      console.error('[KLineChart] ATR indicator is not registered! Please rebuild KLineChart library with custom indicators.')
    }

    console.log('[KLineChart] Chart initialized successfully')
  } catch (error) {
    console.error('[KLineChart] Failed to initialize chart:', error)
  } finally {
    // 初始化完成，重置标志
    isInitializing.value = false
    initTimeoutId.value = null
  }
}

// 处理指标切换
const handleIndicatorChange = (indicator) => {
  if (!chartInstance.value || currentIndicator.value === indicator) {
    return
  }

  // 移除当前指标
  chartInstance.value.removeIndicator({ 
    name: currentIndicator.value, 
    paneId: 'candle_pane' 
  })

  // 创建新指标
  chartInstance.value.createIndicator(indicator, false, { id: 'candle_pane' })

  // 更新当前指标状态
  currentIndicator.value = indicator

  console.log(`[KLineChart] Indicator switched to: ${indicator}`)
}

// 处理时间周期切换
const handleTimeframeChange = (interval) => {
  // 如果interval没有变化，直接返回，避免重复调用
  if (currentInterval.value === interval && chartInstance.value) {
    console.log('[KLineChart] Interval unchanged, skipping update:', interval)
    return
  }

  currentInterval.value = interval
  emit('interval-change', interval)

  // 只有在图表已初始化且interval确实变化时才调用setPeriod
  if (chartInstance.value) {
    const period = intervalToPeriod(interval)
    chartInstance.value.setPeriod(period)
  }
}

// 处理关闭
const handleClose = () => {
  emit('close')
}

// 销毁图表
const destroyChart = () => {
  // 清除初始化定时器
  if (initTimeoutId.value) {
    clearTimeout(initTimeoutId.value)
    initTimeoutId.value = null
  }

  // 重置初始化标志
  isInitializing.value = false

  if (chartInstance.value) {
    try {
      const klinecharts = getKLineCharts()
      const { dispose } = klinecharts

      if (chartContainerRef.value && chartContainerRef.value.parentNode) {
        dispose(chartContainerRef.value)
      }
    } catch (error) {
      console.error('[KLineChart] Error destroying chart:', error)
    }
  }

  chartInstance.value = null
  dataLoader.value = null

  if (chartContainerRef.value) {
    chartContainerRef.value.innerHTML = ''
  }
}

// 监听 visible 变化
watch(() => props.visible, async (newVal) => {
  if (newVal) {
    // 清除之前的定时器
    if (initTimeoutId.value) {
      clearTimeout(initTimeoutId.value)
      initTimeoutId.value = null
    }

    title.value = `${props.symbol} - K线图`
    currentInterval.value = props.interval
    // 等待模态框完全渲染后再初始化
    await nextTick()
    initTimeoutId.value = setTimeout(() => {
      initTimeoutId.value = null
      if (props.visible && !isInitializing.value) {
        initChart()
      }
    }, 100)
  } else {
    // 清除定时器
    if (initTimeoutId.value) {
      clearTimeout(initTimeoutId.value)
      initTimeoutId.value = null
    }
    destroyChart()
  }
}, { immediate: false })

// 监听 symbol 变化
watch(() => props.symbol, (newVal) => {
  if (newVal && props.visible && chartInstance.value) {
    title.value = `${newVal} - K线图`
    const symbolInfo = symbolToSymbolInfo(newVal)
    chartInstance.value.setSymbol(symbolInfo)
  }
})

// 监听 interval 变化
watch(() => props.interval, (newVal, oldVal) => {
  // 如果interval没有变化，直接返回
  if (newVal === oldVal) {
    return
  }

  // 如果interval与currentInterval相同，说明已经通过handleTimeframeChange更新过了，避免重复调用
  if (newVal === currentInterval.value) {
    return
  }

  if (newVal && props.visible && chartInstance.value) {
    currentInterval.value = newVal
    const period = intervalToPeriod(newVal)
    chartInstance.value.setPeriod(period)
  }
})

// 组件卸载时清理
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
  height: 98vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

@media (max-width: 1200px) {
  .kline-modal-content {
    width: 85%;
    height: 98vh;
  }
}

@media (max-width: 768px) {
  .kline-modal-content {
    width: 95%;
    height: 98vh;
  }
}

.kline-modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
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

.kline-indicator-buttons {
  display: flex;
  gap: 8px;
  margin-right: 8px;
}

.indicator-btn {
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  font-weight: 500;
}

.indicator-btn:hover {
  background: #f5f5f5;
}

.indicator-btn.active {
  background: #1677ff;
  color: white;
  border-color: #1677ff;
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
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  min-height: 0;
}

.kline-chart-container {
  flex: 1;
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  min-height: 0;
}
</style>
