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
  precision: 2,
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
    
    // 计算每个周期的RSI值
    for (let i = 0; i < dataList.length; i++) {
      const rsiValues: Record<string, number> = {}
      
      for (let j = 0; j < calcParams.length; j++) {
        const period = calcParams[j]
        const key = `rsi${j + 1}`
        
        if (i < period) {
          rsiValues[key] = 0
          continue
        }
        
        // 计算上涨和下跌的平均值
        let gainSum = 0
        let lossSum = 0
        
        for (let k = i - period + 1; k <= i; k++) {
          const closeDiff = dataList[k].close - dataList[k - 1].close
          if (closeDiff > 0) {
            gainSum += closeDiff
          } else {
            lossSum += Math.abs(closeDiff)
          }
        }
        
        const avgGain = gainSum / period
        const avgLoss = lossSum / period
        
        // 计算RSI
        if (avgLoss === 0) {
          rsiValues[key] = 100
        } else {
          const rs = avgGain / avgLoss
          rsiValues[key] = 100 - (100 / (1 + rs))
        }
      }
      
      result.push(rsiValues)
    }
    
    return result
  }
}

export default rsi
