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

import { IndicatorTemplate, IndicatorSeries, LineType, PolygonType } from 'klinecharts'

/**
 * MACD（指数平滑异同移动平均线）指标
 * DIF（差离值）、DEA（信号线）、BAR（柱状线）
 */
const macd: IndicatorTemplate = {
  name: 'MACD',
  shortName: 'MACD',
  series: IndicatorSeries.Normal,
  calcParams: [12, 26, 9], // 快线周期、慢线周期、信号线周期
  precision: 6,
  shouldOhlc: false,
  shouldFormatBigNumber: false,
  visible: true,
  zLevel: 0,
  extendData: undefined,
  figures: [
    { key: 'dif', title: 'DIF', type: 'line' },
    { key: 'dea', title: 'DEA', type: 'line' },
    { key: 'bar', title: 'BAR', type: 'bar' }
  ],
  styles: {
    lines: [
      { color: '#FF9600', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] },
      { color: '#9D65C9', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] }
    ],
    bars: [
      { 
        upColor: '#2196F3', 
        downColor: '#2196F3',
        noChangeColor: '#2196F3',
        style: PolygonType.Fill,
        borderSize: 1,
        borderStyle: LineType.Solid,
        borderDashedValue: [2, 2]
      }
    ]
  },
  calc: (dataList, indicator) => {
    const { calcParams } = indicator
    const fastPeriod = calcParams[0] || 12
    const slowPeriod = calcParams[1] || 26
    const signalPeriod = calcParams[2] || 9
    
    const result: Array<Record<string, number>> = []
    const emaFast: number[] = [] // 快线EMA
    const emaSlow: number[] = [] // 慢线EMA
    const dif: number[] = [] // 差离值
    const dea: number[] = [] // 信号线
    
    for (let i = 0; i < dataList.length; i++) {
      const close = dataList[i].close
      
      // 计算快线EMA
      if (i === 0) {
        emaFast[i] = close
      } else {
        const multiplier = 2 / (fastPeriod + 1)
        emaFast[i] = (close - emaFast[i - 1]) * multiplier + emaFast[i - 1]
      }
      
      // 计算慢线EMA
      if (i === 0) {
        emaSlow[i] = close
      } else {
        const multiplier = 2 / (slowPeriod + 1)
        emaSlow[i] = (close - emaSlow[i - 1]) * multiplier + emaSlow[i - 1]
      }
      
      // 计算DIF（差离值）
      dif[i] = emaFast[i] - emaSlow[i]
      
      // 计算DEA（信号线，DIF的移动平均）
      if (i === 0) {
        dea[i] = dif[i]
      } else if (i < signalPeriod) {
        // 前signalPeriod个周期使用简单平均
        let sum = 0
        for (let j = 0; j <= i; j++) {
          sum += dif[j]
        }
        dea[i] = sum / (i + 1)
      } else {
        // 之后使用EMA
        const multiplier = 2 / (signalPeriod + 1)
        dea[i] = (dif[i] - dea[i - 1]) * multiplier + dea[i - 1]
      }
      
      // 计算BAR（柱状线，DIF与DEA的差值，简化版不乘以2）
      const bar = dif[i] - dea[i]
      
      result.push({
        dif: dif[i],
        dea: dea[i],
        bar: bar
      })
    }
    
    return result
  }
}

export default macd

