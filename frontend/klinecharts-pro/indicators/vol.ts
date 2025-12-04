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
 * VOL（成交量）指标
 * 包含 VOL（成交量）、MAVOL5（5周期成交量均线）、MAVOL10（10周期成交量均线）
 */
const vol: IndicatorTemplate = {
  name: 'VOL',
  shortName: 'VOL',
  series: IndicatorSeries.Volume,
  calcParams: [5, 10], // MAVOL5、MAVOL10
  precision: 0,
  shouldOhlc: false,
  shouldFormatBigNumber: true,
  visible: true,
  zLevel: 0,
  extendData: undefined,
  figures: [
    { key: 'vol', title: 'VOL', type: 'bar' },
    { key: 'mavol1', title: 'MAVOL5', type: 'line' },
    { key: 'mavol2', title: 'MAVOL10', type: 'line' }
  ],
  styles: {
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
    ],
    lines: [
      { color: '#FF9600', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] },
      { color: '#9D65C9', smooth: false, style: LineType.Solid, size: 1, dashedValue: [2, 2] }
    ]
  },
  calc: (dataList, indicator) => {
    const { calcParams } = indicator
    const result: Array<Record<string, number>> = []
    
    for (let i = 0; i < dataList.length; i++) {
      const volValues: Record<string, number> = {}
      
      // VOL：当前K线的成交量
      volValues.vol = dataList[i].volume || 0
      
      // 计算成交量均线
      for (let j = 0; j < calcParams.length; j++) {
        const period = calcParams[j]
        const key = `mavol${j + 1}`
        
        if (i < period - 1) {
          volValues[key] = 0
          continue
        }
        
        // 计算移动平均
        let sum = 0
        for (let k = i - period + 1; k <= i; k++) {
          sum += dataList[k].volume || 0
        }
        volValues[key] = sum / period
      }
      
      result.push(volValues)
    }
    
    return result
  }
}

export default vol

