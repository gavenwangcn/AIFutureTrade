/**
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at

 * http://www.apache.org/licenses/LICENSE-2.0

 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import type { KLineData } from '../../common/Data'
import type { IndicatorTemplate } from '../../component/Indicator'

import { getMaxMin } from '../../common/utils/number'

interface Kdj {
  k?: number
  d?: number
  j?: number
}

/**
 * KDJ（随机指标）
 *
 * 使用TradingView的计算逻辑
 * 参考：https://www.tradingview.com/support/solutions/43000521824-stochastic-oscillator/
 *
 * TradingView的KDJ计算逻辑（参数60,20,5）：
 * 1. 计算原始%K（RSV）：RSV = 100 * (Close - LowestLow) / (HighestHigh - LowestLow)
 * 2. 第一次平滑得到K值：使用SMA平滑RSV（周期为smooth_k）
 * 3. 第二次平滑得到D值：使用SMA平滑K值（周期为smooth_d）
 * 4. 计算J值：J = 3K - 2D
 */
const stoch: IndicatorTemplate<Kdj, number> = {
  name: 'KDJ',
  shortName: 'KDJ',
  calcParams: [60, 20, 5],
  figures: [
    { key: 'k', title: 'K: ', type: 'line' },
    { key: 'd', title: 'D: ', type: 'line' },
    { key: 'j', title: 'J: ', type: 'line' }
  ],
  calc: (dataList, indicator) => {
    const params = indicator.calcParams
    const rsvPeriod = params[0] // RSV计算周期（通常为9）
    const smoothK = params[1] // K值平滑周期（通常为3）
    const smoothD = params[2] // D值平滑周期（通常为3）

    const result: Kdj[] = []
    // 存储原始%K（RSV）值
    const rawKValues: number[] = []
    // 存储K值
    const kValues: number[] = []
    // 存储D值
    const dValues: number[] = []

    dataList.forEach((kLineData, i) => {
      const kdj: Kdj = {}
      const close = kLineData.close

      // 1. 计算原始%K（RSV）
      if (i >= rsvPeriod - 1) {
        const lhn = getMaxMin<KLineData>(dataList.slice(i - (rsvPeriod - 1), i + 1), 'high', 'low')
        const hn = lhn[0]
        const ln = lhn[1]
        const hnSubLn = hn - ln

        // 计算RSV（原始%K）
        const rsv = hnSubLn !== 0
          ? ((close - ln) / hnSubLn) * 100
          : 50

        rawKValues.push(rsv)

        // 2. 第一次平滑得到K值（使用SMA平滑RSV）
        if (rawKValues.length >= smoothK) {
          // 计算SMA：取最近smoothK个RSV值的平均值
          let sum = 0
          for (let j = rawKValues.length - smoothK; j < rawKValues.length; j++) {
            sum += rawKValues[j]
          }
          const k = sum / smoothK
          kValues.push(k)

          // 3. 第二次平滑得到D值（使用SMA平滑K值）
          if (kValues.length >= smoothD) {
            // 计算SMA：取最近smoothD个K值的平均值
            let dSum = 0
            for (let j = kValues.length - smoothD; j < kValues.length; j++) {
              dSum += kValues[j]
            }
            const d = dSum / smoothD
            dValues.push(d)

            // 4. 计算J值：J = 3K - 2D
            kdj.k = k
            kdj.d = d
            kdj.j = 3.0 * k - 2.0 * d
          }
        }
      }

      result.push(kdj)
    })
    return result
  }
}

export default stoch
