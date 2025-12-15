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
  shouldOhlc: true,  // 设置为true，使VOL柱状图颜色根据K线涨跌判断
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
        // VOL柱状图颜色：与K线颜色一致（K线涨为红色，跌为绿色）
        upColor: '#F53F3F',   // 红色（K线涨时）
        downColor: '#00B42A', // 绿色（K线跌时）
        noChangeColor: '#F53F3F',
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
  },
  draw: (ctx: CanvasRenderingContext2D, chart: any, indicator: any, bounding: any, xAxis: any) => {
    // 获取可见范围
    const [realFrom, realTo] = chart.getVisibleRange()
    const { gapBar, halfGapBar } = chart.getBarSpace()
    const result = indicator.result || []
    const dataList = indicator.dataList || []
    
    if (result.length === 0 || dataList.length === 0) return true
    
    // 获取 Rect 图形类
    const Rect = chart.getFigureClass?.('rect') || chart.getFigureClass?.('bar')
    if (!Rect) return true
    
    // 计算成交量的最大值，用于归一化高度
    let maxVolume = 0
    for (let i = realFrom; i <= realTo; i++) {
      const data = result[i]
      if (data && data.vol !== undefined) {
        if (data.vol > maxVolume) {
          maxVolume = data.vol
        }
      }
    }
    
    if (maxVolume === 0) return true
    
    // 设置柱状图高度（使用 bounding 高度的 40%）
    const totalHeight = bounding.height * 0.4
    
    // 定义颜色：红涨绿跌
    const COLOR_UP = '#F53F3F'   // 红色（K线涨时）
    const COLOR_DOWN = '#00B42A' // 绿色（K线跌时）
    
    // 绘制每个 bar
    for (let i = realFrom; i <= realTo; i++) {
      const data = result[i]
      const klineData = dataList[i]
      
      if (!data || data.vol === undefined || !klineData) continue
      
      const volume = data.vol
      const height = Math.round(volume / maxVolume * totalHeight)
      
      if (height === 0) continue
      
      // 根据 K 线的 open 和 close 判断涨跌，确定颜色
      const color = klineData.close >= klineData.open ? COLOR_UP : COLOR_DOWN
      
      // 计算 y 坐标（从底部向上绘制）
      const y = bounding.height - height
      
      // 创建并绘制矩形
      new Rect({
        name: 'rect',
        attrs: {
          x: xAxis.convertToPixel(i) - halfGapBar,
          y: y,
          width: gapBar,
          height: height
        },
        styles: {
          color: color
        }
      }).draw(ctx)
    }
    
    return true
  }
}

export default vol

