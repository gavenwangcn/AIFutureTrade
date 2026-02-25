"""
订单执行器模块 - 封装订单执行相关逻辑

本模块提供OrderExecutor类，用于执行各种类型的交易订单（买入、卖出、平仓、止损、止盈）。
将订单执行的通用逻辑从TradingEngine中抽象出来，提高代码的可维护性和可读性。
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    订单执行器类
    
    负责执行各种类型的交易订单，包括：
    - 买入/开仓（buy_to_long, buy_to_short）
    - 卖出/平仓（sell_to_long, sell_to_short）
    - 平仓（close_position）
    - 止损（stop_loss）
    - 止盈（take_profit）
    
    主要功能：
    1. 统一处理订单执行的通用逻辑（创建客户端、设置杠杆、调用SDK等）
    2. 计算交易费用和盈亏
    3. 更新数据库记录
    4. 记录交易日志
    """
    
    def __init__(
        self,
        model_id: int,
        trade_fee_rate: float,
        create_binance_client_func,
        update_position_func,
        close_position_func,
        insert_trade_func,
        get_trade_context_func,
        get_conversation_id_func,
        handle_sdk_error_func,
        log_trade_record_func,
        record_account_snapshot_func,
        resolve_leverage_func
    ):
        """
        初始化订单执行器
        
        Args:
            model_id: 模型ID
            trade_fee_rate: 交易费率
            create_binance_client_func: 创建Binance客户端的函数
            update_position_func: 更新持仓的函数
            close_position_func: 平仓的函数
            insert_trade_func: 插入交易记录的函数
            get_trade_context_func: 获取交易上下文的函数
            get_conversation_id_func: 获取对话ID的函数
            handle_sdk_error_func: 处理SDK错误的函数
            log_trade_record_func: 记录交易日志的函数
            record_account_snapshot_func: 记录账户快照的函数
            resolve_leverage_func: 解析杠杆的函数
        """
        self.model_id = model_id
        self.trade_fee_rate = trade_fee_rate
        self._create_binance_client = create_binance_client_func
        self._update_position = update_position_func
        self._close_position = close_position_func
        self._insert_trade = insert_trade_func
        self._get_trade_context = get_trade_context_func
        self._get_conversation_id = get_conversation_id_func
        self._handle_sdk_error = handle_sdk_error_func
        self._log_trade_record = log_trade_record_func
        self._record_account_snapshot = record_account_snapshot_func
        self._resolve_leverage = resolve_leverage_func
    
    def _calculate_pnl(
        self,
        entry_price: float,
        current_price: float,
        quantity: float,
        position_side: str
    ) -> Tuple[float, float, float]:
        """
        计算盈亏
        
        Args:
            entry_price: 开仓价格
            current_price: 当前价格
            quantity: 数量
            position_side: 持仓方向（LONG或SHORT）
        
        Returns:
            Tuple[float, float, float]: (毛盈亏, 手续费, 净盈亏)
        """
        if position_side == 'LONG':
            gross_pnl = (current_price - entry_price) * quantity
        else:  # SHORT
            gross_pnl = (entry_price - current_price) * quantity
        
        trade_amount = quantity * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee
        
        return gross_pnl, trade_fee, net_pnl
    
    def _execute_sdk_trade(
        self,
        symbol: str,
        binance_client,
        method_name: str,
        **kwargs
    ) -> Tuple[Optional[Dict], bool, Optional[str]]:
        """
        执行SDK交易调用
        
        Args:
            symbol: 交易对符号
            binance_client: Binance客户端实例
            method_name: SDK方法名称
            **kwargs: SDK方法参数
        
        Returns:
            Tuple[Optional[Dict], bool, Optional[str]]: (SDK响应, 是否跳过, 跳过原因)
        """
        if not binance_client:
            return None, True, "Binance client not available"
        
        try:
            method = getattr(binance_client, method_name)
            logger.info(f"@API@ [Model {self.model_id}] [{method_name}] === 准备调用接口 === | symbol={symbol} | kwargs={kwargs}")
            response = method(**kwargs)
            logger.info(f"@API@ [Model {self.model_id}] [{method_name}] === 接口调用成功 === | symbol={symbol} | response={response}")
            return response, False, None
        except Exception as e:
            logger.error(f"@API@ [Model {self.model_id}] [{method_name}] === 接口调用失败 === | symbol={symbol} | error={e}", exc_info=True)
            return None, True, str(e)
    
    def _set_leverage(
        self,
        symbol: str,
        leverage: int,
        binance_client
    ) -> bool:
        """
        设置杠杆
        
        Args:
            symbol: 交易对符号
            leverage: 杠杆倍数
            binance_client: Binance客户端实例
        
        Returns:
            bool: 是否成功
        """
        if not binance_client:
            return False
        
        try:
            logger.info(f"@API@ [Model {self.model_id}] [change_initial_leverage] === 准备设置杠杆 === | symbol={symbol} | leverage={leverage}")
            binance_client.change_initial_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"@API@ [Model {self.model_id}] [change_initial_leverage] === 杠杆设置成功 === | symbol={symbol} | leverage={leverage}")
            return True
        except Exception as e:
            logger.error(f"@API@ [Model {self.model_id}] [change_initial_leverage] === 杠杆设置失败 === | symbol={symbol} | error={e}", exc_info=True)
            return False
    
    def _save_trade_record(
        self,
        trade_id: str,
        model_uuid: str,
        symbol: str,
        signal: str,
        quantity: float,
        price: float,
        leverage: int,
        side: str,
        pnl: float,
        fee: float
    ) -> None:
        """
        保存交易记录到数据库
        
        Args:
            trade_id: 交易ID
            model_uuid: 模型UUID
            symbol: 交易对符号
            signal: 交易信号
            quantity: 数量
            price: 价格
            leverage: 杠杆
            side: 方向（buy/sell）
            pnl: 盈亏
            fee: 手续费
        """
        try:
            self._insert_trade(
                [[trade_id, model_uuid, symbol.upper(), signal, quantity, price, leverage, side, pnl, fee, 
                  datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)]],
                ["id", "model_id", "future", "signal", "quantity", "price", "leverage", "side", "pnl", "fee", "timestamp"]
            )
            logger.info(f"TRADE: RECORDED - Model {self.model_id} {signal.upper()} {symbol}")
        except Exception as e:
            logger.error(f"TRADE: Add trade failed ({signal.upper()}) model={self.model_id} future={symbol}: {e}")
            raise
    
    def _record_snapshot_after_trade(self, market_state: Dict) -> None:
        """
        交易后记录账户快照
        
        Args:
            market_state: 市场状态字典
        """
        try:
            current_prices = {s: m.get('price', 0) for s, m in market_state.items()}
            logger.debug(f"[Model {self.model_id}] 交易已记录到trades表，立即记录账户价值快照")
            self._record_account_snapshot(current_prices)
            logger.debug(f"[Model {self.model_id}] 账户价值快照已记录")
        except Exception as e:
            logger.error(f"[Model {self.model_id}] 记录账户价值快照失败: {e}", exc_info=True)
            # 不抛出异常，避免影响主流程

