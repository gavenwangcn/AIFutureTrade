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
 * ATR 的计算分为三步：
 * 1. 计算真实波幅（TR）：
 *    TR = max(以下三者)：
 *      - 当日最高价 - 当日最低价
 *      - |当日最高价 - 前日收盘价|
 *      - |当日最低价 - 前日收盘价|
 * 2. 计算 ATR：
 *    ATR = SMA(TR, N)  # N为周期，通常14
 * 
 * 显示方式：
 * - 在独立的副图区域以曲线形式显示
 * - ATR7、ATR14、ATR21分别用不同颜色的曲线表示
 * - 曲线平滑，便于观察波动率趋势
 */
const atr: IndicatorTemplate<Atr, number> = {
  name: 'ATR',
  shortName: 'ATR',
  precision: 4,
  calcParams: [7, 14, 21],
  figures: [
    {
      key: 'atr1',
      title: 'ATR7: ',
      type: 'line',
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
  calc: (dataList, indicator) => {
    const { calcParams: params, figures } = indicator
    
    // 为每个周期维护TR的累积和
    const trSums: number[] = []
    
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
        // 如果数据足够，先移除最旧的TR值（滑动窗口）
        if (i >= period) {
          const oldTrIndex = i - period
          const oldKLineData = dataList[oldTrIndex]
          const oldPrevClose = oldTrIndex > 0 ? dataList[oldTrIndex - 1].close : oldKLineData.close
          const oldTr1 = oldKLineData.high - oldKLineData.low
          const oldTr2 = Math.abs(oldKLineData.high - oldPrevClose)
          const oldTr3 = Math.abs(oldKLineData.low - oldPrevClose)
          const oldTr = Math.max(oldTr1, oldTr2, oldTr3)
          trSums[index] = (trSums[index] ?? 0) - oldTr
        }
        
        // 累积当前TR值
        trSums[index] = (trSums[index] ?? 0) + tr
        
        // 如果数据足够，计算ATR（SMA of TR）
        if (i >= period - 1) {
          // 计算TR的简单移动平均（SMA）
          const atrValue = trSums[index] / period
          atr[figures[index].key] = atrValue
        }
      })
      
      return atr
    })
  }
}

export default atr
