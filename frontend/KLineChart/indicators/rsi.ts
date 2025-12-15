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

import { IndicatorTemplate, IndicatorSeries, LineType } from 'klinecharts'

/**
 * RSI（相对强弱指数）指标
 * 支持 RSI6、RSI9
 */
const rsi: IndicatorTemplate = {
  name: 'RSI',
  shortName: 'RSI',
  series: IndicatorSeries.Normal,
  calcParams: [6, 9], // RSI6、RSI9
  precision: 6,
  shouldOhlc: false,
  shouldFormatBigNumber: false,
  visible: true,
  zLevel: 0,
  extendData: undefined,
  figures: [
    { key: 'rsi1', title: 'RSI6', type: 'line' },
    { key: 'rsi2', title: 'RSI9', type: 'line' }
  ],
  minValue: 0,
  maxValue: 100,
  styles: {
    lines: [
      { color: '#FF9600', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] },
      { color: '#9D65C9', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] }
    ]
  },
  calc: (dataList, indicator) => {
    const { calcParams } = indicator
    const result: Array<Record<string, number>> = []
    
    // 存储每个周期的平均涨幅和平均跌幅（用于Wilder's平滑）
    const avgGains: Record<number, number> = {}
    const avgLosses: Record<number, number> = {}
    
    // 计算每个周期的RSI值（使用Wilder's平滑算法，与后端finta库保持一致）
    for (let i = 0; i < dataList.length; i++) {
      const rsiValues: Record<string, number> = {}
      
      for (let j = 0; j < calcParams.length; j++) {
        const period = calcParams[j]
        const key = `rsi${j + 1}`
        
        if (i < period) {
          rsiValues[key] = 0
          continue
        }
        
        // 计算当前K线的涨跌幅
        const closeDiff = dataList[i].close - dataList[i - 1].close
        const currentGain = closeDiff > 0 ? closeDiff : 0
        const currentLoss = closeDiff < 0 ? Math.abs(closeDiff) : 0
        
        // 使用Wilder's平滑算法计算平均涨幅和平均跌幅
        // 第一个周期：使用简单平均
        if (i === period) {
          let gainSum = 0
          let lossSum = 0
          
          for (let k = i - period + 1; k <= i; k++) {
            const diff = dataList[k].close - dataList[k - 1].close
            if (diff > 0) {
              gainSum += diff
            } else {
              lossSum += Math.abs(diff)
            }
          }
          
          avgGains[period] = gainSum / period
          avgLosses[period] = lossSum / period
        } else {
          // 后续周期：使用Wilder's平滑
          // Wilder's平滑公式：新平均值 = (旧平均值 * (周期 - 1) + 当前值) / 周期
          if (avgGains[period] === undefined) {
            avgGains[period] = 0
          }
          if (avgLosses[period] === undefined) {
            avgLosses[period] = 0
          }
          
          avgGains[period] = (avgGains[period] * (period - 1) + currentGain) / period
          avgLosses[period] = (avgLosses[period] * (period - 1) + currentLoss) / period
        }
        
        // 计算RSI
        if (avgLosses[period] === 0) {
          rsiValues[key] = 100
        } else {
          const rs = avgGains[period] / avgLosses[period]
          rsiValues[key] = 100 - (100 / (1 + rs))
        }
      }
      
      result.push(rsiValues)
    }
    
    return result
  }
}

export default rsi
