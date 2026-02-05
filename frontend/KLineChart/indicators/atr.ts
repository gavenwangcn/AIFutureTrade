/**
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { formatValue } from '../src/common/utils/format'

import type { IndicatorTemplate, IndicatorFigureStyle } from '../src/component/Indicator'

interface Atr {
  atr1?: number
  atr2?: number
  atr3?: number
}

// ATR曲线颜色配置（参考文档：紫色、蓝色、橙色等）
// ATR7: 绿色（短期，更敏感）
// ATR14: 紫色（中期，最常用）
// ATR21: 橙色（长期，更平滑）
const ATR_COLORS = ['#2DC08E', '#935EBD', '#FF9600']

/**
 * ATR（平均真实波幅）指标
 * 支持 ATR7、ATR14、ATR21
 * 
 * 使用TradingView的计算逻辑
 * 参考：https://www.tradingview.com/support/solutions/43000521824-average-true-range-atr/
 * 
 * TradingView的ATR计算逻辑：
 * 1. 计算真实波幅（TR）：
 *    TR = max(以下三者)：
 *      - 当日最高价 - 当日最低价
 *      - |当日最高价 - 前日收盘价|
 *      - |当日最低价 - 前日收盘价|
 * 2. 计算 ATR：
 *    ATR = RMA(TR, N)  # N为周期，通常14
 *    RMA（Wilder's Smoothing）公式：
 *    - 第一个值：RMA = SMA(TR, N)
 *    - 后续值：RMA = (PrevRMA * (N - 1) + CurrentTR) / N
 * 
 * 显示方式：
 * - 在独立的副图区域以曲线形式显示
 * - ATR7、ATR14、ATR21分别用不同颜色的曲线表示
 * - 曲线平滑，便于观察波动率趋势
 */
const atr: IndicatorTemplate<Atr, number> = {
  // 必需字段：指标名称，用于创建或修改的唯一标识
  name: 'ATR',
  // 简短名称，用于提示显示
  shortName: 'ATR',
  // 精度：小数位数
  precision: 4,
  // 计算参数：ATR的周期数组 [7, 14, 21]
  calcParams: [7, 14, 21],
  // 图形配置数组
  // 参考：https://klinecharts.com/api/chart/registerIndicator#figures
  figures: [
    {
      // 数据取值的标识，与 calc 返回的数据子项的 key 对应
      key: 'atr1',
      // 标题，用于提示显示
      title: 'ATR7: ',
      // 图形类型：line（线条）
      type: 'line',
      // 样式函数：返回图形样式配置
      // 参数：{ data: { prev, current, next }, indicator, defaultStyles }
      styles: ({ indicator }): IndicatorFigureStyle => {
        // ATR7使用绿色，线条稍细
        const color = formatValue(indicator.styles, 'lines[0].color', ATR_COLORS[0]) as string
        return {
          color,
          size: 1.5
        }
      }
    },
    {
      key: 'atr2',
      title: 'ATR14: ',
      type: 'line',
      styles: ({ indicator }): IndicatorFigureStyle => {
        // ATR14使用紫色，线条稍粗（最常用）
        const color = formatValue(indicator.styles, 'lines[1].color', ATR_COLORS[1]) as string
        return {
          color,
          size: 2
        }
      }
    },
    {
      key: 'atr3',
      title: 'ATR21: ',
      type: 'line',
      styles: ({ indicator }): IndicatorFigureStyle => {
        // ATR21使用橙色，线条中等
        const color = formatValue(indicator.styles, 'lines[2].color', ATR_COLORS[2]) as string
        return {
          color,
          size: 1.5
        }
      }
    }
  ],
  // 重新生成基础图形配置
  // 当 calcParams 变化时触发，返回值类型同 figures
  // 参考：https://klinecharts.com/api/chart/registerIndicator#regenerateFigures
  regenerateFigures: (params) => params.map((_, index) => {
    const num = index + 1
    const period = params[index]
    return {
      key: `atr${num}`,
      title: `ATR${period}: `,
      type: 'line',
      styles: (): IndicatorFigureStyle => {
        // 根据索引设置颜色
        const color = ATR_COLORS[index % ATR_COLORS.length]
        return {
          color,
          size: index === 1 ? 2 : 1.5 // ATR14（中间那个）线条稍粗
        }
      }
    }
  }),
  // 计算方法：计算指标值
  // 参数：kLineDataList（K线数据数组）, indicator（指标配置对象）
  // 返回：Record<Timestamp, unknown> - 每个时间戳对应的指标值对象
  // 参考：https://klinecharts.com/api/chart/registerIndicator#calc
  calc: (dataList, indicator) => {
    const { calcParams: params, figures } = indicator
    
    // 为每个周期维护RMA值（使用Wilder's Smoothing）
    const rmaValues: number[] = []
    // 为每个周期维护TR值数组（用于计算第一个RMA值）
    const trArrays: number[][] = []
    
    return dataList.map((kLineData, i) => {
      const atr: Atr = {}
      
      // 获取前一日收盘价
      const prevClose = i > 0 ? dataList[i - 1].close : kLineData.close
      
      // 计算真实波幅（TR）
      const tr1 = kLineData.high - kLineData.low  // 当日最高价 - 当日最低价
      const tr2 = Math.abs(kLineData.high - prevClose)  // |当日最高价 - 前日收盘价|
      const tr3 = Math.abs(kLineData.low - prevClose)   // |当日最低价 - 前日收盘价|
      const tr = Math.max(tr1, tr2, tr3)  // TR = max(三者)
      
      // 为每个周期计算ATR
      params.forEach((period, index) => {
        // 初始化TR数组
        if (!trArrays[index]) {
          trArrays[index] = []
        }
        
        // 添加当前TR值
        trArrays[index].push(tr)
        
        // 如果数据足够，计算ATR（使用RMA/Wilder's Smoothing）
        if (i >= period - 1) {
          if (i === period - 1) {
            // 第一个值：使用SMA计算初始RMA
            let sum = 0
            for (let j = 0; j < period; j++) {
              sum += trArrays[index][j]
            }
            rmaValues[index] = sum / period
          } else {
            // 后续值：使用Wilder's Smoothing
            // RMA = (PrevRMA * (period - 1) + CurrentTR) / period
            rmaValues[index] = (rmaValues[index] * (period - 1) + tr) / period
          }
          
          atr[figures[index].key] = rmaValues[index]
        }
      })
      
      return atr
    })
  }
}

export default atr
