# 自定义指标集成说明

本文档说明如何在 KLineChart 10.0.0 中集成自定义指标。

## 目录结构

```
KLineChart/
├── indicators/          # 自定义指标目录
│   ├── index.ts        # 指标注册入口文件
│   ├── ma.ts          # MA（移动平均线）指标
│   ├── macd.ts        # MACD 指标
│   ├── rsi.ts         # RSI（相对强弱指数）指标
│   └── vol.ts         # VOL（成交量）指标
└── src/
    └── index.ts        # KLineChart 入口文件（导入 indicators/index.ts）
```

## 集成方式

### 1. 指标注册

自定义指标在 `indicators/index.ts` 中注册：

```typescript
import { registerIndicator } from '../src/extension/indicator/index'
import ma from './ma'
import macd from './macd'
import rsi from './rsi'
import vol from './vol'

// 注册自定义指标
registerIndicator(ma)
registerIndicator(macd)
registerIndicator(rsi)
registerIndicator(vol)
```

### 2. 在入口文件中导入

在 `src/index.ts` 中导入 `indicators/index.ts`，确保构建时包含这些指标：

```typescript
// 注册自定义指标（在导出之前注册，确保构建时包含）
import '../indicators/index'
```

### 3. 构建时包含

在 Dockerfile 中确保 indicators 目录被复制：

```dockerfile
COPY frontend/KLineChart/indicators/ ./KLineChart/indicators/
```

## 指标说明

### MA（移动平均线）
- **名称**: MA
- **类型**: 价格指标（叠加在K线上）
- **参数**: [5, 20, 60, 99]
- **图形**: 4条移动平均线（MA5, MA20, MA60, MA99）

### MACD（指数平滑异同移动平均线）
- **名称**: MACD
- **类型**: 普通指标（独立面板）
- **参数**: [12, 26, 9]（快线周期、慢线周期、信号线周期）
- **图形**: DIF线、DEA线、BAR柱状图

### RSI（相对强弱指数）
- **名称**: RSI
- **类型**: 普通指标（独立面板）
- **参数**: [6, 9]（RSI6、RSI9）
- **图形**: 2条RSI线
- **范围**: 0-100

### VOL（成交量）
- **名称**: VOL
- **类型**: 成交量指标（独立面板）
- **参数**: [5, 10]（MAVOL5、MAVOL10）
- **图形**: 成交量柱状图、2条成交量均线

## 使用方式

在图表初始化后，可以直接使用这些指标：

```javascript
const chart = init('chart')
chart.setSymbol({ ticker: 'BTCUSDT' })
chart.setPeriod({ span: 5, type: 'minute' })
chart.setDataLoader(dataLoader)

// 创建主指标（叠加在K线上）
chart.createIndicator('MA', false, { id: 'candle_pane' })

// 创建副指标（独立面板）
chart.createIndicator('VOL', false)
chart.createIndicator('MACD', false)
chart.createIndicator('RSI', false)
```

## 注意事项

1. **循环依赖处理**: 
   - `indicators/index.ts` 使用相对路径导入 `registerIndicator`：`from '../src/extension/indicator/index'`
   - 避免使用 `from 'klinecharts'`，因为这会造成循环依赖

2. **类型导入**:
   - 指标定义文件中的类型导入（如 `IndicatorTemplate`, `IndicatorSeries`, `LineType`）使用 `from 'klinecharts'` 是可以的
   - 这些是类型导入，不会造成运行时循环依赖

3. **构建顺序**:
   - 确保在 `src/index.ts` 导出之前导入 `indicators/index.ts`
   - 这样在构建时，Rollup 会将所有指标打包进最终的 bundle

4. **添加新指标**:
   - 在 `indicators/` 目录下创建新的指标文件
   - 在 `indicators/index.ts` 中导入并注册新指标
   - 确保指标定义符合 `IndicatorTemplate` 接口

## 验证

构建完成后，可以通过以下方式验证指标是否已注册：

```javascript
const klinecharts = window.klinecharts
const supportedIndicators = klinecharts.getSupportedIndicators()
console.log('支持的指标:', supportedIndicators)
// 应该包含: ['MA', 'MACD', 'RSI', 'VOL', ...]
```

