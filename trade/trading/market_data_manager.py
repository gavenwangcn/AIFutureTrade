"""
市场数据管理器模块 - 封装市场数据获取和处理逻辑

本模块提供MarketDataManager类，用于管理市场数据的获取、验证和处理。
将市场数据相关的逻辑从TradingEngine中抽象出来，提高代码的可维护性。
"""
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MarketDataManager:
    """
    市场数据管理器类
    
    负责管理市场数据的获取、验证和处理，包括：
    - 获取市场状态信息
    - 验证symbol数据有效性
    - 合并时间框架数据
    - 构建候选symbol的市场状态
    """
    
    def __init__(
        self,
        model_id: int,
        market_fetcher,
        merge_timeframe_data_func,
        validate_symbol_market_data_func,
        get_portfolio_func,
        build_account_info_func,
        get_symbol_volumes_func
    ):
        """
        初始化市场数据管理器
        
        Args:
            model_id: 模型ID
            market_fetcher: 市场数据获取器
            merge_timeframe_data_func: 合并时间框架数据的函数
            validate_symbol_market_data_func: 验证symbol市场数据的函数
            get_portfolio_func: 获取portfolio的函数
            build_account_info_func: 构建account_info的函数
            get_symbol_volumes_func: 获取symbol成交量的函数
        """
        self.model_id = model_id
        self.market_fetcher = market_fetcher
        self._merge_timeframe_data = merge_timeframe_data_func
        self._validate_symbol_market_data = validate_symbol_market_data_func
        self._get_portfolio = get_portfolio_func
        self._build_account_info = build_account_info_func
        self._get_symbol_volumes = get_symbol_volumes_func
    
    def refresh_portfolio_and_account_info(
        self,
        portfolio: Dict,
        account_info: Dict,
        constraints: Optional[Dict],
        current_prices: Dict[str, float]
    ) -> None:
        """
        刷新portfolio和account_info
        
        Args:
            portfolio: 持仓组合信息（会被更新）
            account_info: 账户信息（会被更新）
            constraints: 约束条件（可选，会被更新）
            current_prices: 当前价格字典
        """
        try:
            updated_portfolio = self._get_portfolio(self.model_id, current_prices)
            portfolio.update(updated_portfolio)
            updated_account_info = self._build_account_info(updated_portfolio)
            account_info.update(updated_account_info)
            
            if constraints is not None:
                constraints['occupied'] = len(updated_portfolio.get('positions', []) or [])
                constraints['available_cash'] = updated_portfolio.get('cash', 0)
            
            logger.debug(f"[Model {self.model_id}] portfolio和account_info已更新: "
                        f"现金=${portfolio.get('cash', 0):.2f}, "
                        f"持仓数={len(portfolio.get('positions', []) or [])}, "
                        f"总收益率={account_info.get('total_return', 0):.2f}%")
        except Exception as e:
            logger.error(f"[Model {self.model_id}] 刷新portfolio和account_info失败: {e}")
            raise
    
    def build_batch_market_state(
        self,
        batch_symbols: List[str],
        market_state: Dict,
        batch_num: int
    ) -> Dict:
        """
        为批次构建市场状态子集（包含技术指标）
        
        Args:
            batch_symbols: 批次symbol列表
            market_state: 完整市场状态字典
            batch_num: 批次号
        
        Returns:
            Dict: 批次市场状态字典
        """
        batch_market_state = {}
        for symbol in batch_symbols:
            if symbol == 'N/A':
                continue
            
            symbol_upper = symbol.upper()
            if symbol_upper not in market_state:
                continue
            
            batch_market_state[symbol_upper] = market_state[symbol_upper].copy()
            
            market_info = market_state[symbol_upper]
            symbol_source_for_batch = market_info.get('source', 'leaderboard')
            
            if symbol_source_for_batch == 'future':
                query_symbol = market_info.get('contract_symbol') or f"{symbol}USDT"
            else:
                query_symbol = symbol_upper
            
            try:
                logger.debug(f"[Model {self.model_id}] [批次 {batch_num}] 正在获取 {symbol_upper} ({query_symbol}) 的技术指标...")
                merged_data = self._merge_timeframe_data(query_symbol)
                timeframes_data = merged_data.get(query_symbol, {}) if merged_data else {}
                
                if timeframes_data:
                    batch_market_state[symbol_upper]['indicators'] = {'timeframes': timeframes_data}
                else:
                    batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
            except Exception as e:
                logger.error(f"[Model {self.model_id}] [批次 {batch_num}] 获取 {symbol_upper} 技术指标失败: {e}")
                batch_market_state[symbol_upper]['indicators'] = {'timeframes': {}}
        
        return batch_market_state

