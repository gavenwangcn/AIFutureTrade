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

interface Ema {
  ema1?: number
  ema2?: number
  ema3?: number
  ema4?: number
  ema5?: number
}

/**
 * EMA（指数移动平均线）指标
 * 支持 EMA5、EMA20、EMA30、EMA60、EMA99
 * EMA计算公式：EMA(t) = Close(t) * α + EMA(t-1) * (1 - α)
 * 其中 α = 2 / (N + 1)
 */
const ema: IndicatorTemplate<Ema, number> = {
  name: 'EMA',
  shortName: 'EMA',
  series: 'price',
  calcParams: [5, 20, 30, 60, 99],
  precision: 6,
  shouldOhlc: true,
  figures: [
    { key: 'ema1', title: 'EMA5: ', type: 'line' },
    { key: 'ema2', title: 'EMA20: ', type: 'line' },
    { key: 'ema3', title: 'EMA30: ', type: 'line' },
    { key: 'ema4', title: 'EMA60: ', type: 'line' },
    { key: 'ema5', title: 'EMA99: ', type: 'line' }
  ],
  regenerateFigures: (params) => params.map((p, i) => ({ key: `ema${i + 1}`, title: `EMA${p}: `, type: 'line' })),
  calc: (dataList, indicator) => {
    const { calcParams: params, figures } = indicator
    const emaValues: number[] = []
    const closeSums: number[] = []
    
    return dataList.map((kLineData, i) => {
      const ema: Ema = {}
      const close = kLineData.close
      
      params.forEach((p, index) => {
        if (i === 0) {
          // 第一个值，使用收盘价作为初始值
          emaValues[index] = close
          closeSums[index] = close
        } else if (i < p - 1) {
          // 在周期内，累加收盘价用于计算初始 SMA
          closeSums[index] = (closeSums[index] ?? 0) + close
          emaValues[index] = closeSums[index] / (i + 1)
        } else if (i === p - 1) {
          // 达到周期长度，使用 SMA 作为初始 EMA
          closeSums[index] = (closeSums[index] ?? 0) + close
          emaValues[index] = closeSums[index] / p
        } else {
          // 计算 EMA：EMA(t) = Close(t) * α + EMA(t-1) * (1 - α)
          // α = 2 / (N + 1)
          const alpha = 2 / (p + 1)
          emaValues[index] = close * alpha + emaValues[index] * (1 - alpha)
        }
        
        if (i >= p - 1) {
          ema[figures[index].key] = emaValues[index]
        }
      })
      
      return ema
    })
  }
}

export default ema

