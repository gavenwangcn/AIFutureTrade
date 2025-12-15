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
import { isValid } from '../src/common/utils/typeChecks'
import { hexToRgb } from '../src/common/utils/color'

import type { IndicatorTemplate, IndicatorFigure } from '../src/component/Indicator'

// 颜色常量：红涨绿跌（与K线颜色对齐）
const COLOR_RED = '#F92855'   // 红色（K线涨时）
const COLOR_GREEN = '#2DC08E' // 绿色（K线跌时）

interface Vol {
  open: number
  close: number
  volume?: number
  ma1?: number
  ma2?: number
}

function getVolumeFigure (): IndicatorFigure<Vol> {
  return {
    key: 'volume',
    title: 'VOLUME: ',
    type: 'bar',
    baseValue: 0,
    styles: ({ data, indicator }) => {
      const current = data.current
      // VOL颜色规则：与K线颜色对齐（K线涨→红色，跌→绿色）
      let color = formatValue(indicator.styles, 'bars[0].noChangeColor', hexToRgb(COLOR_RED, 0.7)) as string
      if (isValid(current)) {
        if (current.close > current.open) {
          // K线涨，使用红色
          color = formatValue(indicator.styles, 'bars[0].upColor', hexToRgb(COLOR_RED, 0.7)) as string
        } else if (current.close < current.open) {
          // K线跌，使用绿色
          color = formatValue(indicator.styles, 'bars[0].downColor', hexToRgb(COLOR_GREEN, 0.7)) as string
        }
      }
      return { color }
    }
  }
}

/**
 * VOL（成交量）指标
 * 包含 VOL（成交量）、MAVOL5（5周期成交量均线）、MAVOL10（10周期成交量均线）
 * 参考官方实现：volume
 */
const vol: IndicatorTemplate<Vol, number> = {
  name: 'VOL',
  shortName: 'VOL',
  series: 'volume',
  calcParams: [5, 10],
  shouldFormatBigNumber: true,
  precision: 0,
  minValue: 0,
  figures: [
    { key: 'ma1', title: 'MA5: ', type: 'line' },
    { key: 'ma2', title: 'MA10: ', type: 'line' },
    getVolumeFigure()
  ],
  regenerateFigures: (params) => {
    const figures: Array<IndicatorFigure<Vol>> = params.map((p, i) => ({ key: `ma${i + 1}`, title: `MA${p}: `, type: 'line' }))
    figures.push(getVolumeFigure())
    return figures
  },
  calc: (dataList, indicator) => {
    const { calcParams: params, figures } = indicator
    const volSums: number[] = []
    return dataList.map((kLineData, i) => {
      const volume = kLineData.volume ?? 0
      const vol: Vol = { volume, open: kLineData.open, close: kLineData.close }
      params.forEach((p, index) => {
        volSums[index] = (volSums[index] ?? 0) + volume
        if (i >= p - 1) {
          vol[figures[index].key] = volSums[index] / p
          volSums[index] -= (dataList[i - (p - 1)].volume ?? 0)
        }
      })
      return vol
    })
  }
}

export default vol

