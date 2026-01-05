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

// 使用相对路径导入 registerIndicator，避免循环依赖
// 注意：在构建时，这个导入会被 Rollup 正确处理
import { registerIndicator } from '../src/extension/indicator/index'

import ma from './ma'
import ema from './ema'
import macd from './macd'
import rsi from './rsi'
import vol from './vol'
import kdj from './kdj'

// 注册自定义指标
registerIndicator(ma)
registerIndicator(ema)
registerIndicator(macd)
registerIndicator(rsi)
registerIndicator(vol)
registerIndicator(kdj)

export {
  ma,
  ema,
  macd,
  rsi,
  vol,
  kdj
}

