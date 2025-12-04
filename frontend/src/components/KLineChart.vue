<template>
  <Teleport to="body">
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
        <div class="kline-modal-body">
          <div :id="chartContainerId" class="kline-chart-container"></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { KLineChartPro } from '@klinecharts/pro'
import '@klinecharts/pro/dist/klinecharts-pro.css'
import { CustomDatafeed } from '../utils/customDatafeed.js'

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

// 生成唯一的容器 ID
const chartContainerId = ref(`kline-chart-${Math.random().toString(36).slice(2, 11)}`)
const chart = ref(null)
const datafeed = ref(null)
const currentInterval = ref(props.interval)
const title = ref(`${props.symbol} - K线图`)

const timeframes = [
  { value: '1m', label: '1分钟', period: { multiplier: 1, timespan: 'minute', text: '1m' } },
  { value: '5m', label: '5分钟', period: { multiplier: 5, timespan: 'minute', text: '5m' } },
  { value: '15m', label: '15分钟', period: { multiplier: 15, timespan: 'minute', text: '15m' } },
  { value: '1h', label: '1小时', period: { multiplier: 1, timespan: 'hour', text: '1h' } },
  { value: '4h', label: '4小时', period: { multiplier: 4, timespan: 'hour', text: '4h' } },
  { value: '1d', label: '1天', period: { multiplier: 1, timespan: 'day', text: '1d' } },
  { value: '1w', label: '1周', period: { multiplier: 1, timespan: 'week', text: '1w' } }
]

// 将 interval 字符串转换为 Period 对象
const intervalToPeriod = (interval) => {
  const tf = timeframes.find(t => t.value === interval)
  return tf ? tf.period : timeframes[1].period // 默认 5m
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
    type: 'PERPETUAL'
  }
}

// 初始化图表
const initChart = async () => {
  // 等待 DOM 完全渲染，增加延迟并添加重试机制
  await nextTick()
  
  const containerId = chartContainerId.value
  let containerElement = document.getElementById(containerId)
  
  // 如果容器元素不存在，重试最多5次，每次等待100ms
  let retryCount = 0
  const maxRetries = 5
  while (!containerElement && retryCount < maxRetries) {
    await new Promise(resolve => setTimeout(resolve, 100))
    containerElement = document.getElementById(containerId)
    retryCount++
    if (containerElement) {
      console.log(`[KLineChart] Container element found after ${retryCount} retries`)
      break
    }
  }
  
  // 额外等待确保DOM完全渲染
  await new Promise(resolve => setTimeout(resolve, 100))

  try {
    if (!containerElement) {
      console.error('[KLineChart] Container element not found after retries:', containerId)
      console.error('[KLineChart] Available elements with similar IDs:', 
        Array.from(document.querySelectorAll('[id^="kline-chart-"]')).map(el => el.id))
      return
    }
    
    // 确保容器元素可见且有尺寸
    if (containerElement.offsetWidth === 0 || containerElement.offsetHeight === 0) {
      console.warn('[KLineChart] Container element has zero dimensions, waiting...')
      await new Promise(resolve => setTimeout(resolve, 200))
      // 再次检查
      if (containerElement.offsetWidth === 0 || containerElement.offsetHeight === 0) {
        console.error('[KLineChart] Container element still has zero dimensions:', {
          width: containerElement.offsetWidth,
          height: containerElement.offsetHeight,
          display: window.getComputedStyle(containerElement).display,
          visibility: window.getComputedStyle(containerElement).visibility
        })
      }
    }

    // 如果图表已存在，先销毁
    if (chart.value) {
      try {
<<<<<<< HEAD
        // 尝试多种销毁方法（根据官方文档，可能使用不同的方法名）
        if (chart.value && typeof chart.value === 'object') {
          if (typeof chart.value.destroy === 'function') {
            chart.value.destroy()
            console.log('[KLineChart] Chart destroyed using destroy() method')
          } else if (typeof chart.value.dispose === 'function') {
            chart.value.dispose()
            console.log('[KLineChart] Chart destroyed using dispose() method')
          } else {
            // 如果没有销毁方法，尝试清空容器内容
            if (containerElement) {
              containerElement.innerHTML = ''
              console.log('[KLineChart] Chart container cleared (no destroy method found)')
            }
          }
        }
      } catch (e) {
        console.error('[KLineChart] Error destroying chart:', e)
        // 即使销毁失败，也清空容器
        if (containerElement) {
          containerElement.innerHTML = ''
        }
      } finally {
        chart.value = null
=======
        chart.value.destroy()
      } catch (e) {
        console.warn('[KLineChart] Error destroying chart:', e)
>>>>>>> 67af25c5c7cb7448695b7e3844d3ee693d5c4712
      }
      chart.value = null
    }

    // 如果 Datafeed 已存在，先清理
    if (datafeed.value) {
      try {
        datafeed.value.destroy()
      } catch (e) {
        console.warn('[KLineChart] Error destroying datafeed:', e)
      }
    }

    console.log('[KLineChart] Initializing KLineChart Pro with container ID:', containerId)
    console.log('[KLineChart] Symbol:', props.symbol, 'Interval:', currentInterval.value)

    // 创建自定义 Datafeed 实例
    datafeed.value = new CustomDatafeed()

    // 转换 symbol 和 period
    const symbolInfo = symbolToSymbolInfo(props.symbol)
    const period = intervalToPeriod(currentInterval.value)

    console.log('[KLineChart] SymbolInfo:', symbolInfo)
    console.log('[KLineChart] Period:', period)

<<<<<<< HEAD
    // 创建 KLineChart Pro 实例（严格按照官方文档）
    try {
      // 确保容器元素为空（避免重复初始化问题）
      if (containerElement.innerHTML.trim() !== '') {
        console.warn('[KLineChart] Container element is not empty, clearing it...')
        containerElement.innerHTML = ''
        // 等待DOM更新
        await new Promise(resolve => setTimeout(resolve, 50))
      }

      // 验证容器元素尺寸
      const rect = containerElement.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) {
        console.error('[KLineChart] Container element has zero dimensions:', {
          width: rect.width,
          height: rect.height,
          computedStyle: {
            width: window.getComputedStyle(containerElement).width,
            height: window.getComputedStyle(containerElement).height,
            display: window.getComputedStyle(containerElement).display
          }
        })
        throw new Error(`Container element has zero dimensions: ${rect.width}x${rect.height}`)
      }

      console.log('[KLineChart] Creating KLineChartPro instance with:', {
        containerId,
        containerSize: { width: rect.width, height: rect.height },
        symbol: symbolInfo,
        period: period
      })

      chart.value = new KLineChartPro({
        container: containerElement,  // 直接传入DOM元素，不是ID
        symbol: symbolInfo,
        period: period,
        datafeed: datafeed.value
      })

      // 验证图表实例是否创建成功
      if (!chart.value || typeof chart.value !== 'object') {
        throw new Error('KLineChartPro instance creation failed: invalid instance')
      }

      console.log('[KLineChart] Chart initialized successfully', {
        hasChart: !!chart.value,
        chartType: typeof chart.value,
        chartMethods: Object.keys(chart.value).filter(key => typeof chart.value[key] === 'function').slice(0, 10)
      })
    } catch (initError) {
      console.error('[KLineChart] Failed to create chart instance:', initError, {
        containerId,
        containerExists: !!containerElement,
        containerSize: containerElement ? {
          width: containerElement.offsetWidth,
          height: containerElement.offsetHeight
        } : null
      })
      chart.value = null
      // 不抛出错误，避免影响UI
    }
=======
    // 创建 KLineChart Pro 实例
    chart.value = new KLineChartPro({
      container: containerElement,
      symbol: symbolInfo,
      period: period,
      datafeed: datafeed.value
    })

    console.log('[KLineChart] Chart initialized successfully')
>>>>>>> 67af25c5c7cb7448695b7e3844d3ee693d5c4712

  } catch (error) {
    console.error('[KLineChart] Failed to initialize chart:', error)
  }
}

// 切换时间间隔
const handleTimeframeChange = async (interval) => {
  currentInterval.value = interval
  emit('interval-change', interval)
  
  if (chart.value) {
    try {
      const period = intervalToPeriod(interval)
      console.log('[KLineChart] Changing period to:', period)
      
      // 使用 setPeriod 方法切换周期
      if (typeof chart.value.setPeriod === 'function') {
        chart.value.setPeriod(period)
        console.log('[KLineChart] Period changed successfully')
      } else {
        console.warn('[KLineChart] setPeriod method not available, reinitializing chart')
        initChart()
      }
    } catch (error) {
      console.error('[KLineChart] Error changing period:', error)
      initChart() // 重新初始化
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
    // 等待 DOM 更新后再初始化，增加延迟确保DOM完全渲染
    await nextTick()
    // 增加延迟时间，确保模态框和容器元素完全渲染
    await new Promise(resolve => setTimeout(resolve, 300))
    initChart()
  } else {
    // 销毁图表和 Datafeed
<<<<<<< HEAD
    await destroyChart()
=======
    if (chart.value) {
      try {
        chart.value.destroy()
      } catch (e) {
        console.warn('[KLineChart] Error destroying chart:', e)
      }
      chart.value = null
    }
    
    if (datafeed.value) {
      try {
        datafeed.value.destroy()
      } catch (e) {
        console.warn('[KLineChart] Error destroying datafeed:', e)
      }
      datafeed.value = null
    }
>>>>>>> 67af25c5c7cb7448695b7e3844d3ee693d5c4712
  }
}, { immediate: false })

// 监听 symbol 变化
watch(() => props.symbol, async (newVal) => {
  if (newVal && props.visible && chart.value) {
    title.value = `${newVal} - K线图`
    
    try {
      const symbolInfo = symbolToSymbolInfo(newVal)
      console.log('[KLineChart] Changing symbol to:', symbolInfo)
      
      // 使用 setSymbol 方法切换标的
      if (typeof chart.value.setSymbol === 'function') {
        chart.value.setSymbol(symbolInfo)
        console.log('[KLineChart] Symbol changed successfully')
      } else {
        console.warn('[KLineChart] setSymbol method not available, reinitializing chart')
        initChart()
      }
    } catch (error) {
      console.error('[KLineChart] Error changing symbol:', error)
      initChart() // 重新初始化
    }
  }
})

<<<<<<< HEAD
// 统一的销毁函数
const destroyChart = async () => {
  // 销毁 Datafeed
  if (datafeed.value) {
    try {
      if (datafeed.value && typeof datafeed.value === 'object' && typeof datafeed.value.destroy === 'function') {
        datafeed.value.destroy()
        console.log('[KLineChart] Datafeed destroyed successfully')
      }
    } catch (e) {
      console.error('[KLineChart] Error destroying datafeed:', e)
    } finally {
      datafeed.value = null
=======
// 组件卸载时清理
onUnmounted(() => {
  if (chart.value) {
    try {
      chart.value.destroy()
    } catch (e) {
      console.warn('[KLineChart] Error destroying chart on unmount:', e)
    }
    chart.value = null
  }
  
  if (datafeed.value) {
    try {
      datafeed.value.destroy()
    } catch (e) {
      console.warn('[KLineChart] Error destroying datafeed on unmount:', e)
>>>>>>> 67af25c5c7cb7448695b7e3844d3ee693d5c4712
    }
    datafeed.value = null
  }

  // 销毁图表
  if (chart.value) {
    try {
      const containerElement = document.getElementById(chartContainerId.value)
      
      if (chart.value && typeof chart.value === 'object') {
        // 尝试多种销毁方法
        if (typeof chart.value.destroy === 'function') {
          chart.value.destroy()
          console.log('[KLineChart] Chart destroyed using destroy() method')
        } else if (typeof chart.value.dispose === 'function') {
          chart.value.dispose()
          console.log('[KLineChart] Chart destroyed using dispose() method')
        } else {
          // 如果没有销毁方法，清空容器
          if (containerElement) {
            containerElement.innerHTML = ''
            console.log('[KLineChart] Chart container cleared (no destroy method found)')
          }
        }
      }
      
      // 清空容器内容（确保完全清理）
      if (containerElement) {
        containerElement.innerHTML = ''
      }
    } catch (e) {
      console.error('[KLineChart] Error destroying chart:', e)
      // 即使销毁失败，也清空容器
      const containerElement = document.getElementById(chartContainerId.value)
      if (containerElement) {
        containerElement.innerHTML = ''
      }
    } finally {
      chart.value = null
    }
  }
}

// 组件卸载时清理
onUnmounted(() => {
  destroyChart()
})
</script>

<style scoped>
/* 基础布局样式 - 仅保留必要的布局 */
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
  z-index: 10000;
}

.kline-modal-content {
  background: #1a1a2e;
  width: 95%;
  max-width: 1400px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kline-modal .modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
}

.kline-modal .modal-header h3 {
  margin: 0;
  color: #fff;
  font-size: 18px;
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

.kline-modal .timeframe-btn {
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #ccc;
  cursor: pointer;
  font-size: 13px;
}

.kline-modal .timeframe-btn.active {
  background: #4a90e2;
  color: #fff;
}

.kline-modal .btn-icon {
  background: transparent;
  border: none;
  color: #ccc;
  cursor: pointer;
  padding: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.kline-modal-body {
  flex: 1;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.kline-chart-container {
  width: 100%;
  height: 100%;
  min-height: 600px;
  flex: 1;
  background: #1a1a1a;
  position: relative;
  overflow: hidden;
  display: block;
  box-sizing: border-box;
}

/* KlineChart库相关样式 - 仅保留必要的样式隔离 */
.kline-chart-container :deep(*) {
  box-sizing: border-box;
}

.kline-modal :deep(.klinecharts-pro) {
  width: 100% !important;
  height: 100% !important;
  min-height: 600px !important;
  background-color: #1a1a1a !important;
  display: block !important;
  position: relative !important;
}

.kline-modal :deep(.klinecharts-pro-container) {
  width: 100% !important;
  height: 100% !important;
  min-height: 600px !important;
  background-color: #1a1a1a !important;
  display: block !important;
  position: relative !important;
}

.kline-modal :deep(.klinecharts-pro-chart-container) {
  width: 100% !important;
  height: 100% !important;
  min-height: 600px !important;
  background-color: #1a1a1a !important;
  display: block !important;
  position: relative !important;
}

.kline-modal :deep(canvas) {
  display: block !important;
  width: 100% !important;
  height: 100% !important;
  position: relative !important;
}

.kline-modal :deep([class*="klinecharts"]) {
  display: block !important;
  width: 100% !important;
  height: 100% !important;
}
</style>
