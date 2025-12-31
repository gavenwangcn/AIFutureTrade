<template>
  <div v-if="visible" class="modal show" @click.self="handleClose">
    <div class="modal-content trade-logs-modal">
      <div class="modal-header">
        <h3>交易日志 - {{ modelName }}</h3>
        <button class="btn-close" @click="handleClose">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="log-dialog-header">
        <div class="log-controls-header">
          <button
            v-if="!isLogConnected"
            class="btn btn-primary btn-sm"
            :disabled="logConnecting"
            @click="startLogStream"
          >
            {{ logConnecting ? '连接中...' : '开始查看日志' }}
          </button>
          <button
            v-else
            class="btn btn-danger btn-sm"
            @click="stopLogStream"
          >
            停止查看
          </button>
          <button class="btn btn-secondary btn-sm" @click="clearLogs">
            清空日志
          </button>
          <button class="btn btn-secondary btn-sm" @click="scrollToBottom">
            滚动到底部
          </button>
          <div class="log-status">
            <span :class="{
              'status-connected': isLogConnected,
              'status-disconnected': !isLogConnected
            }">
              {{ isLogConnected ? '已连接' : '未连接' }}
            </span>
          </div>
          <div class="log-search-container">
            <input
              v-model="searchKeyword"
              type="text"
              class="form-control form-control-sm"
              placeholder="搜索日志内容"
              style="width: 200px; margin-right: 8px"
              @keyup.enter="() => performSearch(true)"
            />
            <button
              class="btn btn-secondary btn-sm"
              @click="() => performSearch(true)"
            >
              搜索
            </button>
            <button
              class="btn btn-secondary btn-sm"
              :class="{ 'btn-primary': isFilterMode }"
              :disabled="!searchKeyword.trim() || totalMatches === 0"
              @click="toggleFilterMode"
            >
              {{ isFilterMode ? '取消筛选' : '筛选' }}
            </button>
            <span v-if="totalMatches > 0" class="search-info">
              {{ currentMatchIndex + 1 }}/{{ totalMatches }}
            </span>
            <button
              class="btn btn-secondary btn-sm"
              :disabled="totalMatches === 0"
              @click="goToPreviousMatch"
            >
              上一个
            </button>
            <button
              class="btn btn-secondary btn-sm"
              :disabled="totalMatches === 0"
              @click="goToNextMatch"
            >
              下一个
            </button>
          </div>
        </div>
        <span class="dialog-title">交易日志: {{ modelName }}</span>
      </div>
      <div class="log-container">
        <div
          ref="logContentRef"
          class="log-content"
          :class="{ 'loading': logConnecting }"
          @scroll="handleScroll"
        >
          <div v-if="logConnecting" class="loading-message">
            正在连接日志流...
          </div>
          <div v-else-if="filteredLogMessages.length === 0" class="no-logs">
            暂无日志数据
          </div>
          <div
            v-else
            v-for="(message, index) in filteredLogMessages"
            :key="getLogKey(message, index)"
            class="log-line"
            :class="{
              'log-error': message.includes('ERROR') || message.includes('Exception') || message.includes('Error'),
              'log-warn': message.includes('WARN') || message.includes('Warning'),
              'log-info': message.includes('INFO') || message.includes('Info'),
              'log-debug': message.includes('DEBUG') || message.includes('Debug')
            }"
            v-html="highlightSearchKeyword(message, getOriginalIndex(message, index))"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUnmount, watch } from 'vue'
import { API_BASE_URL } from '../config/api.js'
import { AnsiUp } from 'ansi_up'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  modelId: {
    type: [Number, String],
    default: null
  },
  modelName: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:visible', 'close'])

// 日志相关状态
const logSocket = ref(null)
const logConnecting = ref(false)
const isLogConnected = ref(false)
const logMessages = ref([])
const logContentRef = ref(null)
const isUserScrolling = ref(false)
const searchKeyword = ref('')
const searchMatches = ref([])
const currentMatchIndex = ref(-1)
const totalMatches = ref(0)
const isFilterMode = ref(false)

// ANSI 转 HTML 转换器（支持日志自带颜色显示）
const ansiUp = new AnsiUp()
ansiUp.escape_html = true
ansiUp.use_classes = false

// 创建WebSocket URL
const createTradeLogStreamUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // 如果API_BASE_URL是完整URL，提取host；否则使用当前host
  let host
  if (API_BASE_URL && (API_BASE_URL.startsWith('http://') || API_BASE_URL.startsWith('https://'))) {
    try {
      const url = new URL(API_BASE_URL)
      host = url.host
    } catch (e) {
      host = window.location.host
    }
  } else {
    host = window.location.host
  }
  return `${protocol}//${host}/ws/trade-logs`
}

// 转换ANSI颜色代码为HTML
const convertAnsiToHtml = (message) => {
  return ansiUp.ansi_to_html(message)
}

// 过滤后的日志消息
const filteredLogMessages = computed(() => {
  if (!isFilterMode.value || !searchKeyword.value.trim()) {
    return logMessages.value
  }
  const keyword = searchKeyword.value.toLowerCase()
  return logMessages.value.filter(msg => msg.toLowerCase().includes(keyword))
})

// 获取日志行的key
const getLogKey = (message, index) => {
  if (isFilterMode.value) {
    return `${message.slice(0, 50)}-${index}`
  }
  return index
}

// 获取原始索引
const getOriginalIndex = (message, filteredIndex) => {
  if (!isFilterMode.value) {
    return filteredIndex
  }
  return logMessages.value.findIndex(item => item === message)
}

// 获取过滤后的索引
const getFilteredIndex = (originalIndex) => {
  if (!isFilterMode.value) {
    return originalIndex
  }
  const targetMessage = logMessages.value[originalIndex]
  return filteredLogMessages.value.findIndex(msg => msg === targetMessage)
}

// 高亮搜索关键词（支持ANSI颜色）
const highlightSearchKeyword = (message, originalIndex) => {
  // 首先转换ANSI颜色代码为HTML
  let processedMessage = convertAnsiToHtml(message)

  if (!searchKeyword.value.trim()) {
    return processedMessage
  }

  const keyword = searchKeyword.value
  const keywordRegex = new RegExp(
    `(${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`,
    'gi'
  )

  const currentMatch =
    currentMatchIndex.value >= 0 &&
    searchMatches.value[currentMatchIndex.value] === originalIndex

  const highlightClass = currentMatch
    ? 'search-highlight-current'
    : 'search-highlight'

  if (!message.toLowerCase().includes(keyword.toLowerCase())) {
    return processedMessage
  }

  // 在已转换的HTML中高亮关键词（需要处理可能包含HTML标签的情况）
  return processedMessage.replace(
    keywordRegex,
    `<span class="${highlightClass}">$1</span>`
  )
}

// 开始日志流
const startLogStream = () => {
  if (logSocket.value) {
    logSocket.value.close()
    logSocket.value = null
  }

  logConnecting.value = true
  isLogConnected.value = false
  logMessages.value = []

  const wsUrl = createTradeLogStreamUrl()

  try {
    logSocket.value = new WebSocket(wsUrl)
  } catch (error) {
    console.error('创建WebSocket失败:', error)
    logConnecting.value = false
    alert('日志连接失败')
    return
  }

  logSocket.value.onopen = () => {
    logConnecting.value = false
    isLogConnected.value = true
    console.log('日志连接成功')
  }

  logSocket.value.onmessage = (event) => {
    if (event.data && event.data.trim()) {
      logMessages.value.push(event.data)
    }

    // 限制日志条数，避免内存溢出
    if (logMessages.value.length > 1500) {
      logMessages.value = logMessages.value.slice(-1200)
    }

    nextTick(() => {
      if (!isUserScrolling.value || isAtBottom()) {
        scrollToBottom()
      }
    })
  }

  logSocket.value.onerror = (error) => {
    console.error('WebSocket错误:', error)
    logConnecting.value = false
    isLogConnected.value = false
    alert('日志连接失败')
  }

  logSocket.value.onclose = () => {
    logConnecting.value = false
    isLogConnected.value = false
  }
}

// 停止日志流
const stopLogStream = () => {
  if (logSocket.value) {
    logSocket.value.close()
    logSocket.value = null
  }
  isLogConnected.value = false
}

// 清空日志
const clearLogs = () => {
  logMessages.value = []
  searchMatches.value = []
  currentMatchIndex.value = -1
  totalMatches.value = 0
}

// 滚动到底部
const scrollToBottom = () => {
  if (logContentRef.value) {
    logContentRef.value.scrollTop = logContentRef.value.scrollHeight
    isUserScrolling.value = false
  }
}

// 检查是否在底部
const isAtBottom = () => {
  if (!logContentRef.value) return false
  const { scrollTop, scrollHeight, clientHeight } = logContentRef.value
  return scrollTop + clientHeight >= scrollHeight - 10
}

// 处理滚动
const handleScroll = () => {
  if (!logContentRef.value) return
  isUserScrolling.value = !isAtBottom()
}

// 滚动到匹配项
const scrollToMatch = (originalIndex) => {
  if (!logContentRef.value || originalIndex < 0) return

  const domIndex = isFilterMode.value
    ? getFilteredIndex(originalIndex)
    : originalIndex

  if (domIndex < 0) return

  nextTick(() => {
    const logLines = logContentRef.value.querySelectorAll('.log-line')
    const targetElement = logLines[domIndex]
    if (!targetElement) return

    const containerHeight = logContentRef.value.clientHeight
    const elementTop = targetElement.offsetTop
    const elementHeight = targetElement.offsetHeight
    const scrollTop = elementTop - containerHeight / 2 + elementHeight / 2

    logContentRef.value.scrollTo({
      top: Math.max(0, scrollTop),
      behavior: 'smooth'
    })
  })
}

// 执行搜索
const performSearch = (forceFirstMatch = false) => {
  if (!searchKeyword.value.trim()) {
    searchMatches.value = []
    currentMatchIndex.value = -1
    totalMatches.value = 0
    return
  }

  const keyword = searchKeyword.value.toLowerCase()

  let currentMatchContent = ''
  if (currentMatchIndex.value >= 0 && searchMatches.value.length > 0) {
    const currentLineIndex = searchMatches.value[currentMatchIndex.value]
    if (currentLineIndex < logMessages.value.length) {
      currentMatchContent = logMessages.value[currentLineIndex]
    }
  }

  const matches = []
  logMessages.value.forEach((message, index) => {
    if (message.toLowerCase().includes(keyword)) {
      matches.push(index)
    }
  })

  searchMatches.value = matches
  totalMatches.value = matches.length

  if (matches.length === 0) {
    currentMatchIndex.value = -1
    return
  }

  let newMatchIndex = 0
  if (forceFirstMatch) {
    newMatchIndex = 0
  } else if (currentMatchContent) {
    const sameContentIndex = matches.findIndex(
      index => logMessages.value[index] === currentMatchContent
    )
    if (sameContentIndex >= 0) {
      newMatchIndex = sameContentIndex
    } else {
      const prevIndex =
        searchMatches.value[currentMatchIndex.value] ?? matches[0]
      let closestIdx = 0
      let minDistance = Math.abs(matches[0] - prevIndex)
      for (let i = 1; i < matches.length; i++) {
        const distance = Math.abs(matches[i] - prevIndex)
        if (distance < minDistance) {
          minDistance = distance
          closestIdx = i
        }
      }
      newMatchIndex = closestIdx
    }
  }

  currentMatchIndex.value = newMatchIndex
  scrollToMatch(matches[newMatchIndex])
}

// 上一个匹配
const goToPreviousMatch = () => {
  if (searchMatches.value.length === 0) return
  currentMatchIndex.value =
    (currentMatchIndex.value - 1 + searchMatches.value.length) %
    searchMatches.value.length
  scrollToMatch(searchMatches.value[currentMatchIndex.value])
}

// 下一个匹配
const goToNextMatch = () => {
  if (searchMatches.value.length === 0) return
  currentMatchIndex.value =
    (currentMatchIndex.value + 1) % searchMatches.value.length
  scrollToMatch(searchMatches.value[currentMatchIndex.value])
}

// 切换筛选模式
const toggleFilterMode = () => {
  if (!searchKeyword.value.trim()) return
  isFilterMode.value = !isFilterMode.value
  performSearch(true)
}

// 关闭对话框
const handleClose = () => {
  stopLogStream()
  clearLogs()
  searchKeyword.value = ''
  isFilterMode.value = false
  emit('update:visible', false)
  emit('close')
}

// 监听visible变化
watch(() => props.visible, (newVal) => {
  if (!newVal) {
    // 对话框关闭时，停止日志流
    stopLogStream()
    clearLogs()
  }
})

// 组件卸载时清理
onBeforeUnmount(() => {
  stopLogStream()
})
</script>

<style scoped>
.trade-logs-modal {
  width: 33.33%;
  max-width: 600px;
  min-width: 400px;
  height: 33.33vh;
  max-height: 500px;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  margin: auto;
  position: relative;
  top: 50%;
  transform: translateY(-50%);
}

.modal-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.log-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  min-height: 150px;
}

.log-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 28px;
  padding: 8px 0;
  margin: 0;
  border-bottom: 1px solid #dcdfe6;
  flex-wrap: wrap;
}

.dialog-title {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
  margin-left: auto;
}

.log-controls-header {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.log-controls-header .btn {
  height: 28px;
  padding: 4px 12px;
  font-size: 12px;
}

.log-status {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-left: 12px;
}

.status-connected {
  font-weight: 600;
  color: #67c23a;
}

.status-disconnected {
  font-weight: 600;
  color: #f56c6c;
}

.log-search-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.search-info {
  font-size: 12px;
  color: #909399;
  margin: 0 4px;
}

.log-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.4;
  color: #d4d4d4;
  word-break: break-all;
  white-space: pre-wrap;
  background-color: #1e1e1e;
  border-radius: 4px;
}

.log-content.loading {
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-message {
  padding: 40px 0;
  font-size: 14px;
  color: #909399;
  text-align: center;
}

.no-logs {
  padding: 40px 0;
  font-size: 14px;
  color: #909399;
  text-align: center;
}

.log-line {
  padding: 2px 4px;
  margin-bottom: 2px;
}

/* 多色标记各级别异常 */
.log-error {
  color: #f56c6c;
  background-color: rgba(245, 108, 108, 0.1);
  border-radius: 2px;
}

.log-warn {
  color: #e6a23c;
  background-color: rgba(230, 162, 60, 0.1);
  border-radius: 2px;
}

.log-info {
  color: #409eff;
}

.log-debug {
  color: #909399;
}

/* 搜索高亮 */
.search-highlight {
  padding: 0 2px;
  color: #fff;
  background: rgba(247, 186, 29, 0.4);
  border-radius: 2px;
}

.search-highlight-current {
  padding: 0 2px;
  color: #fff;
  background: rgba(64, 158, 255, 0.6);
  border-radius: 2px;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.8);
}

/* 确保ANSI颜色样式正确显示 */
.log-content :deep(span[style*="color"]) {
  display: inline;
}
</style>
