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

interface Kdj {
  k?: number
  d?: number
  j?: number
}

/**
 * KDJ（随机指标）指标
 * K值、D值、J值
 * 标准参数：(9, 3, 3)
 * - 第一个参数：RSV计算周期（通常为9）
 * - 第二个参数：K值平滑周期（通常为3）
 * - 第三个参数：D值平滑周期（通常为3）
 */
const kdj: IndicatorTemplate<Kdj, number> = {
  name: 'KDJ',
  shortName: 'KDJ',
  calcParams: [9, 3, 3],
  figures: [
    { key: 'k', title: 'K: ', type: 'line' },
    { key: 'd', title: 'D: ', type: 'line' },
    { key: 'j', title: 'J: ', type: 'line' }
  ],
  regenerateFigures: (params) => [
    { key: 'k', title: 'K: ', type: 'line' },
    { key: 'd', title: 'D: ', type: 'line' },
    { key: 'j', title: 'J: ', type: 'line' }
  ],
  calc: (dataList, indicator) => {
    const { calcParams: params } = indicator
    const rsvPeriod = params[0] // RSV计算周期
    const kPeriod = params[1]   // K值平滑周期
    const dPeriod = params[2]   // D值平滑周期
    
    let k = 50  // K值初始值
    let d = 50  // D值初始值
    let prevK = 50
    let prevD = 50
    
    return dataList.map((kLineData, i) => {
      const kdj: Kdj = {}
      
      // 计算RSV（未成熟随机值）
      if (i >= rsvPeriod - 1) {
        // 获取最近N周期内的最高价和最低价
        let highest = kLineData.high
        let lowest = kLineData.low
        
        for (let j = i - rsvPeriod + 1; j < i; j++) {
          if (dataList[j].high > highest) {
            highest = dataList[j].high
          }
          if (dataList[j].low < lowest) {
            lowest = dataList[j].low
          }
        }
        
        // 计算RSV
        const rsv = highest !== lowest 
          ? ((kLineData.close - lowest) / (highest - lowest)) * 100 
          : 50
        
        // 计算K值：平滑移动平均
        // K = (2/3) * 前一日K值 + (1/3) * 当日RSV
        if (i === rsvPeriod - 1) {
          // 第一次计算，使用RSV的简单平均
          k = rsv
        } else {
          k = (2 * prevK + rsv) / 3
        }
        
        // 计算D值：K值的平滑移动平均
        // D = (2/3) * 前一日D值 + (1/3) * 当日K值
        if (i === rsvPeriod - 1) {
          d = k
        } else {
          d = (2 * prevD + k) / 3
        }
        
        // 计算J值：J = 3K - 2D
        const j = 3 * k - 2 * d
        
        kdj.k = k
        kdj.d = d
        kdj.j = j
        
        // 更新前一日值
        prevK = k
        prevD = d
      }
      
      return kdj
    })
  }
}

export default kdj

