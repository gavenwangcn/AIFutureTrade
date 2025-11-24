from datetime import datetime
from typing import Dict, List
import json
import logging

logger = logging.getLogger(__name__)

try:
    import config as app_config
except ImportError:  # pragma: no cover
    import config_example as app_config

from prompt_defaults import DEFAULT_BUY_CONSTRAINTS, DEFAULT_SELL_CONSTRAINTS

class TradingEngine:
    def __init__(self, model_id: int, db, market_fetcher, ai_trader, trade_fee_rate: float = 0.001):
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.ai_trader = ai_trader
        self.trade_fee_rate = trade_fee_rate  # 从配置中传入费率
        self.max_positions = 3

    def _get_tracked_symbols(self):
        return [future['symbol'] for future in self.db.get_future_configs()]
    
    def execute_trading_cycle(self) -> Dict:
        try:
            market_state = self._get_market_state()
            current_prices = self._extract_price_map(market_state)
            portfolio = self.db.get_portfolio(self.model_id, current_prices)
            account_info = self._build_account_info(portfolio)
            prompt_templates = self._get_prompt_templates()
            market_snapshot = self._get_prompt_market_snapshot()
            self.current_model_leverage = self._get_model_leverage()

            executions = []
            conversation_prompts = []

            # ---- 先处理卖出/风控决策 ----
            sell_payload = self.ai_trader.make_sell_decision(
                portfolio,
                market_state,
                account_info,
                constraints_text=prompt_templates['sell'],
                market_snapshot=market_snapshot
            )
            if not sell_payload.get('skipped') and sell_payload.get('prompt'):
                self._record_ai_conversation(sell_payload)
                sell_results = self._execute_decisions(
                    sell_payload.get('decisions') or {},
                    market_state,
                    portfolio
                )
                executions.extend(sell_results)
                conversation_prompts.append('sell')
                portfolio = self.db.get_portfolio(self.model_id, current_prices)
                account_info = self._build_account_info(portfolio)

            # ---- 获取涨幅榜候选，进行买入决策 ----
            buy_candidates = self._select_buy_candidates(portfolio)
            if buy_candidates:
                market_state = self._augment_market_state_with_candidates(market_state, buy_candidates)
                current_prices = self._extract_price_map(market_state)
                constraints = {
                    'max_positions': self.max_positions,
                    'occupied': len(portfolio.get('positions', []) or []),
                    'available_cash': portfolio.get('cash', 0)
                }
                buy_payload = self.ai_trader.make_buy_decision(
                    buy_candidates,
                    portfolio,
                    account_info,
                    constraints,
                    constraints_text=prompt_templates['buy'],
                    market_snapshot=market_snapshot
                )
                if not buy_payload.get('skipped') and buy_payload.get('prompt'):
                    self._record_ai_conversation(buy_payload)
                    buy_results = self._execute_decisions(
                        buy_payload.get('decisions') or {},
                        market_state,
                        portfolio
                    )
                    executions.extend(buy_results)
                    conversation_prompts.append('buy')
                    portfolio = self.db.get_portfolio(self.model_id, current_prices)
                    account_info = self._build_account_info(portfolio)

            updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            self.db.record_account_value(
                self.model_id,
                updated_portfolio['total_value'],
                updated_portfolio['cash'],
                updated_portfolio['positions_value']
            )

            return {
                'success': True,
                'executions': executions,
                'portfolio': updated_portfolio,
                'conversations': conversation_prompts
            }

        except Exception as e:
            logger.error(f"Trading cycle failed (Model {self.model_id}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_market_state(self) -> Dict:
        market_state = {}
        symbols = self._get_tracked_symbols()
        prices = self.market_fetcher.get_prices(symbols)
        
        for symbol in symbols:
            price_info = prices.get(symbol)
            if price_info:
                market_state[symbol] = price_info.copy()
                indicators = self.market_fetcher.calculate_technical_indicators(symbol)
                market_state[symbol]['indicators'] = indicators

        return market_state
    
    def _build_account_info(self, portfolio: Dict) -> Dict:
        model = self.db.get_model(self.model_id)
        initial_capital = model['initial_capital']
        total_value = portfolio['total_value']
        total_return = ((total_value - initial_capital) / initial_capital) * 100
        
        return {
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_return': total_return,
            'initial_capital': initial_capital
        }
    
    def _format_prompt(self, market_state: Dict, portfolio: Dict, 
                      account_info: Dict) -> str:
        return f"Market State: {len(market_state)} futures, Portfolio: {len(portfolio['positions'])} positions"

    def _get_prompt_templates(self) -> Dict[str, str]:
        prompt_config = self.db.get_model_prompt(self.model_id) or {}
        buy_prompt = prompt_config.get('buy_prompt') or DEFAULT_BUY_CONSTRAINTS
        sell_prompt = prompt_config.get('sell_prompt') or DEFAULT_SELL_CONSTRAINTS
        return {'buy': buy_prompt, 'sell': sell_prompt}

    def _record_ai_conversation(self, payload: Dict):
        prompt = payload.get('prompt')
        raw_response = payload.get('raw_response')
        cot_trace = payload.get('cot_trace') or ''
        if not isinstance(raw_response, str):
            raw_response = json.dumps(payload.get('decisions', {}), ensure_ascii=False)
        self.db.add_conversation(
            self.model_id,
            user_prompt=prompt,
            ai_response=raw_response,
            cot_trace=cot_trace
        )

    def _select_buy_candidates(self, portfolio: Dict) -> list:
        try:
            leaderboard = self.market_fetcher.get_leaderboard()
        except Exception as exc:
            logger.warning(f"[Model {self.model_id}] 获取涨幅榜候选失败: {exc}")
            return []

        gainers = leaderboard.get('gainers') or []
        if not gainers:
            return []

        held = {pos['future'] for pos in (portfolio.get('positions') or [])}
        available_slots = max(0, self.max_positions - len(held))
        if available_slots <= 0:
            return []

        filtered = [item for item in gainers if item.get('symbol') not in held]
        return filtered[:available_slots]

    def _get_prompt_market_snapshot(self) -> List[Dict]:
        limit = getattr(app_config, 'PROMPT_MARKET_SYMBOL_LIMIT', 5)
        limit = max(1, int(limit))

        try:
            leaderboard = self.market_fetcher.get_leaderboard(limit=limit)
        except Exception as exc:
            logger.warning(f"[Model {self.model_id}] 获取提示词市场快照失败: {exc}")
            return []

        entries = leaderboard.get('gainers') or []
        snapshot = []
        for entry in entries[:limit]:
            symbol = entry.get('symbol')
            if not symbol:
                continue
            snapshot.append({
                'symbol': symbol,
                'contract_symbol': entry.get('contract_symbol'),
                'price': entry.get('price'),
                'quote_volume': entry.get('quote_volume'),
                'timeframes': entry.get('timeframes') or {}
            })

        return snapshot

    def _augment_market_state_with_candidates(self, market_state: Dict, candidates: list) -> Dict:
        augmented = dict(market_state)
        for entry in candidates:
            symbol = entry.get('symbol')
            if not symbol:
                continue
            symbol = symbol.upper()
            if symbol in augmented and augmented[symbol].get('price'):
                continue
            augmented[symbol] = {
                'price': entry.get('price', 0),
                'name': entry.get('name', symbol),
                'exchange': entry.get('exchange', 'BINANCE_FUTURES'),
                'contract_symbol': entry.get('contract_symbol') or f"{symbol}USDT",
                'timeframes': entry.get('timeframes') or {},
                'source': 'leaderboard'
            }
        return augmented

    def _extract_price_map(self, market_state: Dict) -> Dict[str, float]:
        prices = {}
        for symbol, payload in (market_state or {}).items():
            price = payload.get('price') if isinstance(payload, dict) else None
            if price is not None:
                prices[symbol] = price
        return prices
    
    def _execute_decisions(self, decisions: Dict, market_state: Dict, 
                          portfolio: Dict) -> list:
        results = []
        
        tracked = set(self._get_tracked_symbols())
        positions_map = {pos['future']: pos for pos in portfolio.get('positions', [])}

        for symbol, decision in decisions.items():
            if symbol not in tracked:
                continue
            
            signal = decision.get('signal', '').lower()
            
            try:
                if signal == 'buy_to_enter':
                    result = self._execute_buy(symbol, decision, market_state, portfolio)
                elif signal == 'sell_to_enter':
                    result = {'future': symbol, 'error': '当前账户暂不支持做空'}
                elif signal == 'close_position':
                    if symbol not in positions_map:
                        result = {'future': symbol, 'error': 'No position to close'}
                    else:
                        result = self._execute_close(symbol, decision, market_state, portfolio)
                elif signal == 'hold':
                    result = {'future': symbol, 'signal': 'hold', 'message': '保持观望'}
                else:
                    result = {'future': symbol, 'error': f'Unknown signal: {signal}'}
                
                results.append(result)
                
            except Exception as e:
                results.append({'future': symbol, 'error': str(e)})
        
        return results
    
    def _execute_buy(self, symbol: str, decision: Dict, market_state: Dict, 
                    portfolio: Dict) -> Dict:
        quantity = decision.get('quantity', 0)
        leverage = self._resolve_leverage(decision)
        price = market_state[symbol]['price']
        
        positions = portfolio.get('positions', [])
        existing_symbols = {pos['future'] for pos in positions}
        if symbol not in existing_symbols and len(existing_symbols) >= self.max_positions:
            return {'future': symbol, 'error': '达到最大持仓数量，无法继续开仓'}

        max_affordable_qty = portfolio['cash'] / (price * (1 + self.trade_fee_rate))
        risk_pct = float(decision.get('risk_budget_pct', 3)) / 100
        risk_pct = min(max(risk_pct, 0.01), 0.05)
        risk_based_qty = (portfolio['cash'] * risk_pct) / (price * (1 + self.trade_fee_rate))

        quantity = float(quantity)
        if quantity <= 0 or quantity > max_affordable_qty:
            quantity = min(max_affordable_qty, risk_based_qty if risk_based_qty > 0 else max_affordable_qty)

        if quantity <= 0:
            return {'future': symbol, 'error': '现金不足，无法买入'}
        
        trade_amount = quantity * price  # 交易额
        trade_fee = trade_amount * self.trade_fee_rate  # 交易费（0.1%）
        required_margin = (quantity * price) / leverage  # 保证金
        
        # 总需资金 = 保证金 + 交易费
        total_required = required_margin + trade_fee
        if total_required > portfolio['cash']:
            return {'future': symbol, 'error': '可用资金不足（含手续费）'}
        
        # 更新持仓
        try:
            self.db.update_position(
                self.model_id, symbol, quantity, price, leverage, 'long'
            )
        except Exception as db_err:
            logger.error(f"TRADE: Update position failed (BUY) model={self.model_id} future={symbol}: {db_err}")
            raise
        
        # 记录交易（包含交易费）
        logger.info(f"TRADE: PENDING - Model {self.model_id} BUY {symbol} qty={quantity} price={price} fee={trade_fee}")
        try:
            self.db.add_trade(
                self.model_id, symbol, 'buy_to_enter', quantity, 
                price, leverage, 'long', pnl=0, fee=trade_fee  # 新增fee参数
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (BUY) model={self.model_id} future={symbol}: {db_err}")
            raise
        logger.info(f"TRADE: RECORDED - Model {self.model_id} BUY {symbol}")
        
        return {
            'future': symbol,
            'signal': 'buy_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,  # 返回费用信息
            'message': f'买入 {symbol} {quantity:.4f} @ ${price:.2f} (手续费: ${trade_fee:.2f})'
        }

    def _get_model_leverage(self) -> int:
        try:
            model = self.db.get_model(self.model_id)
        except Exception as exc:
            logger.warning(f"[Model {self.model_id}] 读取杠杆失败: {exc}")
            return 10

        if not model:
            return 10

        leverage = model.get('leverage', 10)
        try:
            leverage = int(leverage)
        except (TypeError, ValueError):
            leverage = 10
        return max(0, leverage)

    def _resolve_leverage(self, decision: Dict) -> int:
        configured = getattr(self, 'current_model_leverage', None)
        if configured is None:
            configured = self._get_model_leverage()

        ai_leverage = decision.get('leverage')
        try:
            ai_leverage = int(ai_leverage)
        except (TypeError, ValueError):
            ai_leverage = 1

        ai_leverage = max(1, ai_leverage)

        if configured == 0:
            return ai_leverage

        return max(1, configured)

    def _ensure_future_record(self, symbol: str, market_meta: Optional[Dict]):
        if not symbol:
            return
        market_meta = market_meta or {}
        contract_symbol = market_meta.get('contract_symbol') or f"{symbol}USDT"
        name = market_meta.get('name') or symbol
        exchange = market_meta.get('exchange', 'BINANCE_FUTURES')
        link = market_meta.get('link')
        sort_order = market_meta.get('rank', 0) if isinstance(market_meta.get('rank'), int) else 0
        try:
            self.db.upsert_future(
                symbol=symbol,
                contract_symbol=contract_symbol,
                name=name,
                exchange=exchange,
                link=link,
                sort_order=sort_order
            )
        except Exception as exc:
            logger.warning(f"[Model {self.model_id}] 写入持仓合约失败 {symbol}: {exc}")
    
    def _execute_close(self, symbol: str, decision: Dict, market_state: Dict, 
                    portfolio: Dict) -> Dict:
        position = None
        for pos in portfolio['positions']:
            if pos['future'] == symbol:
                position = pos
                break
        
        if not position:
            return {'future': symbol, 'error': 'Position not found'}
        
        current_price = market_state[symbol]['price']
        entry_price = position['avg_price']
        quantity = position['quantity']
        side = position['side']
        
        # 计算平仓利润（未扣费）
        if side == 'long':
            gross_pnl = (current_price - entry_price) * quantity
        else:  # short
            gross_pnl = (entry_price - current_price) * quantity
        
        # 计算平仓交易费（按平仓时的交易额）
        trade_amount = quantity * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee  # 净利润 = 毛利润 - 交易费
        
        # 关闭持仓
        try:
            self.db.close_position(self.model_id, symbol, side)
        except Exception as db_err:
            logger.error(f"TRADE: Close position failed model={self.model_id} future={symbol}: {db_err}")
            raise
        
        # 记录平仓交易（包含费用和净利润）
        logger.info(f"TRADE: PENDING - Model {self.model_id} CLOSE {symbol} side={side} qty={quantity} price={current_price} fee={trade_fee} net_pnl={net_pnl}")
        try:
            self.db.add_trade(
                self.model_id, symbol, 'close_position', quantity,
                current_price, position['leverage'], side, pnl=net_pnl, fee=trade_fee  # 新增fee参数
            )
        except Exception as db_err:
            logger.error(f"TRADE: Add trade failed (CLOSE) model={self.model_id} future={symbol}: {db_err}")
            raise
        logger.info(f"TRADE: RECORDED - Model {self.model_id} CLOSE {symbol}")
        
        return {
            'future': symbol,
            'signal': 'close_position',
            'quantity': quantity,
            'price': current_price,
            'pnl': net_pnl,
            'fee': trade_fee,
            'message': f'平仓 {symbol}, 毛收益 ${gross_pnl:.2f}, 手续费 ${trade_fee:.2f}, 净收益 ${net_pnl:.2f}'
        }
