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

import type { IndicatorTemplate } from '../src/component/Indicator'

interface Rsi {
  rsi1?: number
  rsi2?: number
}

/**
 * RSI（相对强弱指数）指标
 * 支持 RSI6、RSI9
 * 
 * 使用TradingView的计算逻辑（Wilder's Smoothing方法）
 * 参考：https://www.tradingview.com/support/solutions/43000521824-relative-strength-index-rsi/
 * 
 * Wilder's Smoothing公式：
 * - AvgGain = (PrevAvgGain * (period - 1) + CurrentGain) / period
 * - AvgLoss = (PrevAvgLoss * (period - 1) + CurrentLoss) / period
 * - RS = AvgGain / AvgLoss
 * - RSI = 100 - (100 / (1 + RS))
 */
const rsi: IndicatorTemplate<Rsi, number> = {
  name: 'RSI',
  shortName: 'RSI',
  calcParams: [6, 9],
  figures: [
    { key: 'rsi1', title: 'RSI1: ', type: 'line' },
    { key: 'rsi2', title: 'RSI2: ', type: 'line' }
  ],
  regenerateFigures: (params) => params.map((_, index) => {
    const num = index + 1
    return { key: `rsi${num}`, title: `RSI${num}: `, type: 'line' }
  }),
  calc: (dataList, indicator) => {
    const { calcParams: params, figures } = indicator
    // 为每个周期维护AvgGain和AvgLoss（使用Wilder's Smoothing）
    const avgGains: number[] = []
    const avgLosses: number[] = []
    
    return dataList.map((kLineData, i) => {
      const rsi: Rsi = {}
      const prevClose = i > 0 ? dataList[i - 1].close : kLineData.close
      const change = kLineData.close - prevClose
      const gain = change > 0 ? change : 0
      const loss = change < 0 ? -change : 0
      
      params.forEach((period, index) => {
        if (i === 0) {
          // 第一根K线：初始化AvgGain和AvgLoss
          avgGains[index] = gain
          avgLosses[index] = loss
        } else if (i < period) {
          // 前period根K线：使用简单平均
          avgGains[index] = (avgGains[index] ?? 0) + gain
          avgLosses[index] = (avgLosses[index] ?? 0) + loss
          
          if (i === period - 1) {
            // 第period根K线：计算初始平均值
            avgGains[index] = avgGains[index] / period
            avgLosses[index] = avgLosses[index] / period
          }
        } else {
          // 第period+1根K线开始：使用Wilder's Smoothing
          // AvgGain = (PrevAvgGain * (period - 1) + CurrentGain) / period
          // AvgLoss = (PrevAvgLoss * (period - 1) + CurrentLoss) / period
          avgGains[index] = (avgGains[index] * (period - 1) + gain) / period
          avgLosses[index] = (avgLosses[index] * (period - 1) + loss) / period
        }
        
        // 计算RSI（需要至少period根K线）
        if (i >= period - 1) {
          if (avgLosses[index] !== 0) {
            const rs = avgGains[index] / avgLosses[index]
            rsi[figures[index].key] = 100 - (100 / (1 + rs))
          } else {
            // 如果AvgLoss为0，RSI为100（所有都是上涨）
            rsi[figures[index].key] = avgGains[index] > 0 ? 100 : 50
          }
        }
      })
      
      return rsi
    })
  }
}

export default rsi
