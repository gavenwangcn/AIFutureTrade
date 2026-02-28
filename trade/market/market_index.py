"""
市场指标计算模块

提供市场波动率和趋势强度的计算方法，用于辅助交易决策。

主要功能：
1. 计算市场波动率指标（基于ATR百分比）
2. 计算市场趋势强度指标（基于ADX）
3. 综合市场状态评估

使用场景：
- 在买入/卖出循环中计算市场指标
- 输入候选合约列表及其K线数据
- 输出市场状态指标供策略使用
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import talib

logger = logging.getLogger(__name__)


class MarketIndexCalculator:
    """市场指标计算器"""

    def __init__(self, atr_period: int = 14, adx_period: int = 14,
                 hist_vol_period: int = 20, quantile_window: int = 365):
        """
        初始化市场指标计算器

        Args:
            atr_period: ATR计算周期，默认14
            adx_period: ADX计算周期，默认14
            hist_vol_period: 历史波动率计算周期，默认20
            quantile_window: 分位数计算窗口，默认365
        """
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.hist_vol_period = hist_vol_period
        self.quantile_window = quantile_window

    def compute_atr_percent(self, high: np.ndarray, low: np.ndarray,
                           close: np.ndarray) -> Optional[np.ndarray]:
        """
        计算单个合约的ATR百分比：ATR / close

        Args:
            high: 最高价数组
            low: 最低价数组
            close: 收盘价数组

        Returns:
            ATR百分比数组，如果计算失败返回None
        """
        try:
            if len(high) < self.atr_period or len(low) < self.atr_period or len(close) < self.atr_period:
                logger.warning(f"数据长度不足，需要至少{self.atr_period}条数据")
                return None

            atr = talib.ATR(high, low, close, timeperiod=self.atr_period)
            atr_pct = atr / close
            return atr_pct
        except Exception as e:
            logger.error(f"计算ATR百分比失败: {e}")
            return None

    def compute_adx(self, high: np.ndarray, low: np.ndarray,
                   close: np.ndarray) -> Optional[np.ndarray]:
        """
        计算单个合约的ADX（平均趋向指数）

        Args:
            high: 最高价数组
            low: 最低价数组
            close: 收盘价数组

        Returns:
            ADX数组，如果计算失败返回None
        """
        try:
            if len(high) < self.adx_period or len(low) < self.adx_period or len(close) < self.adx_period:
                logger.warning(f"数据长度不足，需要至少{self.adx_period}条数据")
                return None

            adx = talib.ADX(high, low, close, timeperiod=self.adx_period)
            return adx
        except Exception as e:
            logger.error(f"计算ADX失败: {e}")
            return None

    def compute_hist_volatility(self, close: np.ndarray,
                                annualize: bool = False) -> Optional[np.ndarray]:
        """
        计算历史波动率（基于对数收益率的滚动标准差）

        Args:
            close: 收盘价数组
            annualize: 是否年化，默认False

        Returns:
            历史波动率数组，如果计算失败返回None
        """
        try:
            if len(close) < self.hist_vol_period + 1:
                logger.warning(f"数据长度不足，需要至少{self.hist_vol_period + 1}条数据")
                return None

            # 计算对数收益率
            close_series = pd.Series(close)
            returns = np.log(close_series / close_series.shift(1))

            # 计算滚动标准差
            hist_vol = returns.rolling(window=self.hist_vol_period).std()

            # 年化（假设日线数据，年化因子为sqrt(365)）
            if annualize:
                hist_vol = hist_vol * np.sqrt(365)

            return hist_vol.values
        except Exception as e:
            logger.error(f"计算历史波动率失败: {e}")
            return None

    def calculate_market_volatility(self, klines_data: Dict[str, Dict]) -> Dict[str, float]:
        """
        方法1：计算市场波动率指标（基于ATR百分比）

        Args:
            klines_data: K线数据字典，格式为 {symbol: {'high': [...], 'low': [...], 'close': [...]}}

        Returns:
            市场波动率指标字典，包含：
            - market_atr_pct_mean: 市场平均ATR百分比
            - market_atr_pct_median: 市场中位数ATR百分比
            - high_vol_ratio: 高波动合约占比
            - vol_state: 波动率状态（'低波动'/'正常波动'/'高波动'）
        """
        try:
            atr_pct_values = []
            valid_symbols = []

            # 计算每个合约的ATR百分比
            for symbol, data in klines_data.items():
                try:
                    high = np.array(data.get('high', []))
                    low = np.array(data.get('low', []))
                    close = np.array(data.get('close', []))

                    if len(high) == 0 or len(low) == 0 or len(close) == 0:
                        continue

                    atr_pct = self.compute_atr_percent(high, low, close)
                    if atr_pct is not None and len(atr_pct) > 0:
                        # 取最新值
                        latest_atr_pct = atr_pct[-1]
                        if not np.isnan(latest_atr_pct):
                            atr_pct_values.append(latest_atr_pct)
                            valid_symbols.append(symbol)
                except Exception as e:
                    logger.warning(f"计算{symbol}的ATR百分比失败: {e}")
                    continue

            if len(atr_pct_values) == 0:
                logger.warning("没有有效的ATR百分比数据")
                return {
                    'market_atr_pct_mean': 0.0,
                    'market_atr_pct_median': 0.0,
                    'high_vol_ratio': 0.0,
                    'vol_state': '未知'
                }

            # 计算市场指标
            market_atr_pct_mean = float(np.mean(atr_pct_values))
            market_atr_pct_median = float(np.median(atr_pct_values))

            # 计算高波动合约占比（ATR百分比 > 5%）
            high_vol_threshold = 0.05
            high_vol_count = sum(1 for v in atr_pct_values if v > high_vol_threshold)
            high_vol_ratio = high_vol_count / len(atr_pct_values)

            # 判断波动率状态（基于均值）
            if market_atr_pct_mean < 0.02:
                vol_state = '低波动'
            elif market_atr_pct_mean < 0.05:
                vol_state = '正常波动'
            else:
                vol_state = '高波动'

            result = {
                'market_atr_pct_mean': market_atr_pct_mean,
                'market_atr_pct_median': market_atr_pct_median,
                'high_vol_ratio': high_vol_ratio,
                'vol_state': vol_state,
                'valid_symbols_count': len(valid_symbols)
            }

            logger.info(f"市场波动率指标: 均值={market_atr_pct_mean:.4f}, "
                       f"中位数={market_atr_pct_median:.4f}, "
                       f"高波动占比={high_vol_ratio:.2%}, 状态={vol_state}")

            return result

        except Exception as e:
            logger.error(f"计算市场波动率指标失败: {e}", exc_info=True)
            return {
                'market_atr_pct_mean': 0.0,
                'market_atr_pct_median': 0.0,
                'high_vol_ratio': 0.0,
                'vol_state': '未知'
            }

    def calculate_market_trend_strength(self, klines_data: Dict[str, Dict]) -> Dict[str, float]:
        """
        方法2：计算市场趋势强度指标（基于ADX）

        Args:
            klines_data: K线数据字典，格式为 {symbol: {'high': [...], 'low': [...], 'close': [...]}}

        Returns:
            市场趋势强度指标字典，包含：
            - market_adx_mean: 市场平均ADX
            - market_adx_median: 市场中位数ADX
            - strong_trend_ratio: 强趋势合约占比（ADX > 25）
            - trend_state: 趋势状态（'震荡'/'弱趋势'/'强趋势'）
        """
        try:
            adx_values = []
            valid_symbols = []

            # 计算每个合约的ADX
            for symbol, data in klines_data.items():
                try:
                    high = np.array(data.get('high', []))
                    low = np.array(data.get('low', []))
                    close = np.array(data.get('close', []))

                    if len(high) == 0 or len(low) == 0 or len(close) == 0:
                        continue

                    adx = self.compute_adx(high, low, close)
                    if adx is not None and len(adx) > 0:
                        # 取最新值
                        latest_adx = adx[-1]
                        if not np.isnan(latest_adx):
                            adx_values.append(latest_adx)
                            valid_symbols.append(symbol)
                except Exception as e:
                    logger.warning(f"计算{symbol}的ADX失败: {e}")
                    continue

            if len(adx_values) == 0:
                logger.warning("没有有效的ADX数据")
                return {
                    'market_adx_mean': 0.0,
                    'market_adx_median': 0.0,
                    'strong_trend_ratio': 0.0,
                    'trend_state': '未知'
                }

            # 计算市场指标
            market_adx_mean = float(np.mean(adx_values))
            market_adx_median = float(np.median(adx_values))

            # 计算强趋势合约占比（ADX > 25）
            strong_trend_threshold = 25
            strong_trend_count = sum(1 for v in adx_values if v > strong_trend_threshold)
            strong_trend_ratio = strong_trend_count / len(adx_values)

            # 判断趋势状态（基于均值）
            if market_adx_mean < 20:
                trend_state = '震荡'
            elif market_adx_mean < 25:
                trend_state = '弱趋势'
            else:
                trend_state = '强趋势'

            result = {
                'market_adx_mean': market_adx_mean,
                'market_adx_median': market_adx_median,
                'strong_trend_ratio': strong_trend_ratio,
                'trend_state': trend_state,
                'valid_symbols_count': len(valid_symbols)
            }

            logger.info(f"市场趋势强度指标: 均值={market_adx_mean:.2f}, "
                       f"中位数={market_adx_median:.2f}, "
                       f"强趋势占比={strong_trend_ratio:.2%}, 状态={trend_state}")

            return result

        except Exception as e:
            logger.error(f"计算市场趋势强度指标失败: {e}", exc_info=True)
            return {
                'market_adx_mean': 0.0,
                'market_adx_median': 0.0,
                'strong_trend_ratio': 0.0,
                'trend_state': '未知'
            }

    def calculate_comprehensive_market_state(self, klines_data: Dict[str, Dict]) -> Dict[str, any]:
        """
        综合计算市场状态（波动率 + 趋势强度）

        Args:
            klines_data: K线数据字典

        Returns:
            综合市场状态字典，包含波动率和趋势强度的所有指标
        """
        try:
            volatility_metrics = self.calculate_market_volatility(klines_data)
            trend_metrics = self.calculate_market_trend_strength(klines_data)

            # 合并结果
            result = {
                **volatility_metrics,
                **trend_metrics,
                'market_state_summary': f"{volatility_metrics['vol_state']}/{trend_metrics['trend_state']}"
            }

            logger.info(f"综合市场状态: {result['market_state_summary']}")

            return result

        except Exception as e:
            logger.error(f"计算综合市场状态失败: {e}", exc_info=True)
            return {}


# 便捷函数
def calculate_market_indicators(klines_data: Dict[str, Dict],
                                atr_period: int = 14,
                                adx_period: int = 14) -> Dict[str, any]:
    """
    便捷函数：计算市场指标

    Args:
        klines_data: K线数据字典，格式为 {symbol: {'high': [...], 'low': [...], 'close': [...]}}
        atr_period: ATR计算周期
        adx_period: ADX计算周期

    Returns:
        市场指标字典

    Example:
        >>> klines_data = {
        ...     'BTCUSDT': {
        ...         'high': [50000, 51000, 52000, ...],
        ...         'low': [49000, 50000, 51000, ...],
        ...         'close': [49500, 50500, 51500, ...]
        ...     },
        ...     'ETHUSDT': {...}
        ... }
        >>> indicators = calculate_market_indicators(klines_data)
        >>> print(indicators['market_atr_pct_mean'])  # 市场平均ATR百分比
        >>> print(indicators['market_adx_mean'])  # 市场平均ADX
        >>> print(indicators['vol_state'])  # 波动率状态
        >>> print(indicators['trend_state'])  # 趋势状态
    """
    calculator = MarketIndexCalculator(atr_period=atr_period, adx_period=adx_period)
    return calculator.calculate_comprehensive_market_state(klines_data)
