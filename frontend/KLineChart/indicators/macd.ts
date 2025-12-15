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
import { hexToRgb } from '../src/common/utils/color'

import type { IndicatorTemplate } from '../src/component/Indicator'

// 颜色常量：红涨绿跌
const COLOR_RED = '#F92855'   // 红色（MACD值为正数时）
const COLOR_GREEN = '#2DC08E' // 绿色（MACD值为负数时）

interface Macd {
  dif?: number
  dea?: number
  macd?: number
}

/**
 * MACD（指数平滑异同移动平均线）指标
 * DIF（差离值）、DEA（信号线）、MACD（柱状线）
 * 参考官方实现：movingAverageConvergenceDivergence
 */
const macd: IndicatorTemplate<Macd, number> = {
  name: 'MACD',
  shortName: 'MACD',
  calcParams: [12, 26, 9],
  figures: [
    { key: 'dif', title: 'DIF: ', type: 'line' },
    { key: 'dea', title: 'DEA: ', type: 'line' },
    {
      key: 'macd',
      title: 'MACD: ',
      type: 'bar',
      baseValue: 0,
      styles: ({ data, indicator, defaultStyles }) => {
        const { prev, current } = data
        const prevMacd = prev?.macd ?? Number.MIN_SAFE_INTEGER
        const currentMacd = current?.macd ?? Number.MIN_SAFE_INTEGER
        // MACD颜色规则：正数（涨）→ 红色，负数（跌）→ 绿色
        let color = ''
        if (currentMacd > 0) {
          // MACD值为正数，使用红色（涨）
          color = formatValue(indicator.styles, 'bars[0].upColor', hexToRgb(COLOR_RED, 0.7)) as string
        } else if (currentMacd < 0) {
          // MACD值为负数，使用绿色（跌）
          color = formatValue(indicator.styles, 'bars[0].downColor', hexToRgb(COLOR_GREEN, 0.7)) as string
        } else {
          color = formatValue(indicator.styles, 'bars[0].noChangeColor', (defaultStyles!.bars)[0].noChangeColor) as string
        }
        const style = prevMacd < currentMacd ? 'stroke' : 'fill'
        return { style, color, borderColor: color }
      }
    }
  ],
  calc: (dataList, indicator) => {
    const params = indicator.calcParams
    let closeSum = 0
    let emaShort = 0
    let emaLong = 0
    let dif = 0
    let difSum = 0
    let dea = 0
    const maxPeriod = Math.max(params[0], params[1])
    return dataList.map((kLineData, i) => {
      const macd: Macd = {}
      const close = kLineData.close
      closeSum += close
      if (i >= params[0] - 1) {
        if (i > params[0] - 1) {
          emaShort = (2 * close + (params[0] - 1) * emaShort) / (params[0] + 1)
        } else {
          emaShort = closeSum / params[0]
        }
      }
      if (i >= params[1] - 1) {
        if (i > params[1] - 1) {
          emaLong = (2 * close + (params[1] - 1) * emaLong) / (params[1] + 1)
        } else {
          emaLong = closeSum / params[1]
        }
      }
      if (i >= maxPeriod - 1) {
        dif = emaShort - emaLong
        macd.dif = dif
        difSum += dif
        if (i >= maxPeriod + params[2] - 2) {
          if (i > maxPeriod + params[2] - 2) {
            dea = (dif * 2 + dea * (params[2] - 1)) / (params[2] + 1)
          } else {
            dea = difSum / params[2]
          }
          macd.macd = (dif - dea) * 2
          macd.dea = dea
        }
      }
      return macd
    })
  }
}

export default macd

