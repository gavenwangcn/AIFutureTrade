# KLineChart 10.0.0 迁移指南

本文档记录了从 klinecharts-pro + klinecharts 9.x 迁移到 KLineChart 10.0.0 的变更。

## 主要变更

### 1. 依赖变更

**移除的依赖：**
- `@klinecharts/pro`: 不再需要 Pro 版本
- `klinecharts@^9.0.0`: 升级到 10.0.0

**新的构建方式：**
- 使用源码构建：从 `frontend/KLineChart/` 目录构建
- 构建产物：`dist/umd/klinecharts.min.js`

### 2. API 变更

#### 图表初始化

**旧版本（klinecharts-pro）：**
```javascript
const chart = new KLineChartPro({
  container: element,
  symbol: symbolInfo,
  period: period,
  datafeed: datafeedInstance,
  theme: 'light'
})
```

**新版本（KLineChart 10.0.0）：**
```javascript
const { init } = klinecharts
const chart = init(element, {
  layout: {
    type: 'normal',
    header: {
      show: false
    }
  }
})
chart.setSymbol(symbolInfo)
chart.setPeriod(period)
chart.setDataLoader(dataLoader)
```

#### 数据加载器

**旧版本：**
```javascript
class CustomDatafeed {
  async getHistoryKLineData(symbol, period, from, to) {
    // 返回数据数组
  }
  subscribe(symbol, period, callback) {}
  unsubscribe(symbol, period) {}
}
```

**新版本：**
```javascript
function createDataLoader() {
  return {
    getBars: ({ type, timestamp, symbol, period, callback }) => {
      // 调用 callback(data, more) 返回数据
      callback(data, hasMore)
    },
    subscribeBar: ({ symbol, period, callback }) => {},
    unsubscribeBar: ({ symbol, period }) => {}
  }
}
```

#### 周期格式变更

**旧版本：**
```javascript
{ multiplier: 5, timespan: 'minute', text: '5m' }
```

**新版本：**
```javascript
{ span: 5, type: 'minute' }
```

#### 指标创建

**旧版本：**
```javascript
// 通过配置项设置
mainIndicators: ['MA'],
subIndicators: ['RSI', 'MACD', 'VOL']
```

**新版本：**
```javascript
// 主指标（叠加在K线上）
chart.createIndicator('MA', false, { id: 'candle_pane' })
// 副指标（独立面板）
chart.createIndicator('VOL', false)
chart.createIndicator('MACD', false)
chart.createIndicator('RSI', false)
```

#### 图表销毁

**旧版本：**
```javascript
chart.destroy()
```

**新版本：**
```javascript
const { dispose } = klinecharts
dispose(element)
```

### 3. 文件路径变更

**旧版本：**
- `/klinecharts-pro/klinecharts.js`
- `/klinecharts-pro/klinecharts-pro.umd.js`
- `/klinecharts-pro/klinecharts-pro.css`

**新版本：**
- `/klinecharts/klinecharts.min.js`

### 4. Dockerfile 变更

**主要变更：**
1. 构建阶段从 `klinecharts-pro-builder` 改为 `klinecharts-builder`
2. 使用 pnpm 构建 KLineChart（如果可用，否则使用 npm）
3. 构建产物路径从 `dist/klinecharts-pro/` 改为 `dist/klinecharts/`

### 5. 代码文件变更

#### `frontend/src/utils/customDatafeed.js`
- 从 `CustomDatafeed` 类改为 `createDataLoader` 函数
- `getHistoryKLineData` 改为 `getBars`，参数格式变更
- `subscribe/unsubscribe` 改为 `subscribeBar/unsubscribeBar`

#### `frontend/src/components/KLineChart.vue`
- 移除 `KLineChartPro` 相关代码
- 使用 `init` 和 `dispose` API
- 使用 `setDataLoader`、`setSymbol`、`setPeriod` 方法
- 使用 `createIndicator` 创建指标

#### `frontend/index.html`
- 移除 klinecharts-pro CSS 引用
- 更新脚本引用路径

#### `frontend/server.js`
- 更新静态文件服务路径从 `/klinecharts-pro/` 到 `/klinecharts/`

## 迁移检查清单

- [x] 更新 Dockerfile 构建 KLineChart 10.0.0
- [x] 更新 package.json 移除旧依赖
- [x] 修改 customDatafeed.js 适配新 DataLoader 接口
- [x] 修改 KLineChart.vue 使用新版本 API
- [x] 更新 index.html 引入新版本
- [x] 更新 server.js 静态文件路径
- [x] 集成自定义指标（MA, MACD, RSI, VOL）

## 注意事项

1. **数据格式**：KLineChart 10.0.0 要求数据格式为：
   ```javascript
   {
     timestamp: number, // 毫秒时间戳
     open: number,
     high: number,
     low: number,
     close: number,
     volume: number
   }
   ```

2. **回调函数**：`getBars` 的回调函数签名：
   ```javascript
   callback(data: KLineData[], more?: boolean | { backward?: boolean, forward?: boolean })
   ```

3. **指标创建**：主指标需要指定 `{ id: 'candle_pane' }`，副指标会自动创建新面板

4. **构建要求**：KLineChart 使用 pnpm 作为包管理器，Dockerfile 中已处理兼容性

## 自定义指标集成

项目中的自定义指标（MA, MACD, RSI, VOL）已集成到构建流程中：

1. **指标位置**: `frontend/KLineChart/indicators/`
2. **注册方式**: 在 `src/index.ts` 中导入 `indicators/index.ts`
3. **构建包含**: Dockerfile 已确保 indicators 目录被复制

详细说明请参考：[自定义指标集成文档](./KLineChart/CUSTOM_INDICATORS.md)

## 参考文档

- [KLineChart 10.0.0 快速上手](https://klinecharts.com/guide/quick-start)
- [从 V9 到 V10 迁移指南](https://klinecharts.com/guide/v9-to-v10)
- [KLineChart API 文档](https://klinecharts.com/api)
- [自定义技术指标](https://klinecharts.com/guide/indicator)

