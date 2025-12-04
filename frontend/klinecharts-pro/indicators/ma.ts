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
 * MA（移动平均线）指标
 * 支持 MA5、MA20、MA60、MA99
 */
const ma: IndicatorTemplate = {
  name: 'MA',
  shortName: 'MA',
  series: IndicatorSeries.Price,
  calcParams: [5, 20, 60, 99],
  precision: 2,
  shouldOhlc: true,
  shouldFormatBigNumber: false,
  visible: true,
  zLevel: 0,
  extendData: undefined,
  figures: [
    { key: 'ma1', title: 'MA5', type: 'line' },
    { key: 'ma2', title: 'MA20', type: 'line' },
    { key: 'ma3', title: 'MA60', type: 'line' },
    { key: 'ma4', title: 'MA99', type: 'line' }
  ],
  styles: {
    lines: [
      { color: '#FF9600', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] },
      { color: '#9D65C9', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] },
      { color: '#2196F3', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] },
      { color: '#F23645', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] }
    ]
  },
  calc: (dataList, indicator) => {
    const { calcParams } = indicator
    const result: Array<Record<string, number>> = []
    
    for (let i = 0; i < dataList.length; i++) {
      const maValues: Record<string, number> = {}
      
      for (let j = 0; j < calcParams.length; j++) {
        const period = calcParams[j]
        const key = `ma${j + 1}`
        
        if (i < period - 1) {
          maValues[key] = 0
          continue
        }
        
        // 计算移动平均：使用收盘价
        let sum = 0
        for (let k = i - period + 1; k <= i; k++) {
          sum += dataList[k].close
        }
        maValues[key] = sum / period
      }
      
      result.push(maValues)
    }
    
    return result
  }
}

export default ma

