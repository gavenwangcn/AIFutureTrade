"""
Database management module
"""
import sqlite3
import json
import logging
import config as app_config
from datetime import datetime
from typing import List, Dict, Optional



logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = 'trading_bot.db'):
        self.db_path = db_path

    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ============ Database Initialization ============

    def init_db(self):
        """Initialize database tables - only CREATE TABLE IF NOT EXISTS, no migration logic"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Providers table (API提供方)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                api_url TEXT NOT NULL,
                api_key TEXT NOT NULL,
                models TEXT,
                provider_type TEXT DEFAULT 'openai',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Models table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider_id INTEGER,
                model_name TEXT NOT NULL,
                initial_capital REAL DEFAULT 10000,
                leverage INTEGER DEFAULT 10,
                auto_trading_enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES providers(id)
            )
        ''')

        # Portfolios table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                future TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id),
                UNIQUE(model_id, future, side)
            )
        ''')

        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                future TEXT NOT NULL,
                signal TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                pnl REAL DEFAULT 0,
                fee REAL DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')

        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                user_prompt TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                cot_trace TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')

        # Account values history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                total_value REAL NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')

        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_frequency_minutes INTEGER DEFAULT 60,
                trading_fee_rate REAL DEFAULT 0.001,
                show_system_prompt INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Model prompts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL UNIQUE,
                buy_prompt TEXT,
                sell_prompt TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')

        # Model-specific futures configuration table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_futures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                contract_symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                exchange TEXT NOT NULL DEFAULT 'BINANCE_FUTURES',
                link TEXT,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(model_id, symbol),
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')

        # Futures table (USDS-M contract universe)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS futures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                contract_symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                exchange TEXT NOT NULL DEFAULT 'BINANCE_FUTURES',
                link TEXT,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Futures leaderboard table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS futures_leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                contract_symbol TEXT NOT NULL,
                name TEXT,
                exchange TEXT NOT NULL DEFAULT 'BINANCE_FUTURES',
                side TEXT NOT NULL CHECK(side IN ('gainer', 'loser')),
                rank INTEGER NOT NULL,
                price REAL,
                change_percent REAL,
                quote_volume REAL,
                timeframes TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, side)
            )
        ''')

        # Daily closing prices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                price_date TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, price_date)
            )
        ''')

        # Insert default settings if no settings exist
        cursor.execute('SELECT COUNT(*) FROM settings')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO settings (trading_frequency_minutes, trading_fee_rate, show_system_prompt)
                VALUES (60, 0.001, 0)
            ''')

        conn.commit()
        conn.close()

    # ============ Provider Management ============

    def add_provider(self, name: str, api_url: str, api_key: str, models: str = '', provider_type: str = 'openai') -> int:
        """Add new API provider"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO providers (name, api_url, api_key, models, provider_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, api_url, api_key, models, provider_type.lower()))
        provider_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return provider_id

    def get_provider(self, provider_id: int) -> Optional[Dict]:
        """Get provider information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM providers WHERE id = ?', (provider_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_providers(self) -> List[Dict]:
        """Get all API providers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM providers ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_provider(self, provider_id: int, name: str, api_url: str, api_key: str, models: str, provider_type: str = 'openai'):
        """Update provider information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE providers
            SET name = ?, api_url = ?, api_key = ?, models = ?, provider_type = ?
            WHERE id = ?
        ''', (name, api_url, api_key, models, provider_type.lower(), provider_id))
        conn.commit()
        conn.close()

    def delete_provider(self, provider_id: int):
        """Delete provider"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM providers WHERE id = ?', (provider_id,))
        conn.commit()
        conn.close()

    # ============ Model Management ============

    def add_model(self, name: str, provider_id: int, model_name: str,
                 initial_capital: float = 10000, leverage: int = 10) -> int:
        """Add new trading model"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO models (name, provider_id, model_name, initial_capital, leverage)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, provider_id, model_name, initial_capital, leverage))
        model_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return model_id

    def get_model(self, model_id: int) -> Optional[Dict]:
        """Get model information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*, p.api_key, p.api_url, p.provider_type
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            WHERE m.id = ?
        ''', (model_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_models(self) -> List[Dict]:
        """Get all trading models"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*, p.name as provider_name
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            ORDER BY m.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_model(self, model_id: int):
        """Delete model and related data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM models WHERE id = ?', (model_id,))
        cursor.execute('DELETE FROM portfolios WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM trades WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM conversations WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM account_values WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM model_futures WHERE model_id = ?', (model_id,))
        conn.commit()
        conn.close()

    def set_model_auto_trading(self, model_id: int, enabled: bool) -> bool:
        """Enable or disable auto trading for a model"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE models
                SET auto_trading_enabled = ?
                WHERE id = ?
            ''', (1 if enabled else 0, model_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to update auto trading flag for model {model_id}: {exc}")
            return False
        finally:
            conn.close()

    def is_model_auto_trading_enabled(self, model_id: int) -> bool:
        """Check auto trading flag for a model"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT auto_trading_enabled FROM models WHERE id = ?', (model_id,))
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return False
        return bool(row['auto_trading_enabled'])

    def set_model_leverage(self, model_id: int, leverage: int) -> bool:
        """Update model leverage"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE models SET leverage = ? WHERE id = ?', (leverage, model_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to update leverage for model {model_id}: {exc}")
            return False
        finally:
            conn.close()

    # ============ Portfolio Management ============

    def update_position(self, model_id: int, future: str, quantity: float,
                       avg_price: float, leverage: int = 1, side: str = 'long'):
        """Update position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO portfolios (model_id, future, quantity, avg_price, leverage, side, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model_id, future, side) DO UPDATE SET
                quantity = excluded.quantity,
                avg_price = excluded.avg_price,
                leverage = excluded.leverage,
                updated_at = CURRENT_TIMESTAMP
        ''', (model_id, future.upper(), quantity, avg_price, leverage, side))
        conn.commit()
        conn.close()

    def get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get portfolio with positions and P&L
        
        Args:
            model_id: Model ID
            current_prices: Current market prices {symbol: price} for unrealized P&L calculation
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get positions
        cursor.execute('''
            SELECT * FROM portfolios WHERE model_id = ? AND quantity > 0
        ''', (model_id,))
        positions = [dict(row) for row in cursor.fetchall()]

        # Get initial capital
        cursor.execute('SELECT initial_capital FROM models WHERE id = ?', (model_id,))
        model_row = cursor.fetchone()
        if model_row is None:
            conn.close()
            raise ValueError(f"Model {model_id} not found")
        initial_capital = model_row['initial_capital']

        # Calculate realized P&L (sum of all trade P&L)
        cursor.execute('''
            SELECT COALESCE(SUM(pnl), 0) as total_pnl FROM trades WHERE model_id = ?
        ''', (model_id,))
        realized_pnl = cursor.fetchone()['total_pnl']

        # Calculate margin used
        margin_used = sum([p['quantity'] * p['avg_price'] / p['leverage'] for p in positions])

        # Calculate unrealized P&L (if prices provided)
        unrealized_pnl = 0
        if current_prices:
            for pos in positions:
                symbol = pos['future']
                if symbol in current_prices:
                    current_price = current_prices[symbol]
                    entry_price = pos['avg_price']
                    quantity = pos['quantity']

                    # Add current price to position
                    pos['current_price'] = current_price

                    # Calculate position P&L
                    if pos['side'] == 'long':
                        pos_pnl = (current_price - entry_price) * quantity
                    else:  # short
                        pos_pnl = (entry_price - current_price) * quantity

                    pos['pnl'] = pos_pnl
                    unrealized_pnl += pos_pnl
                else:
                    pos['current_price'] = None
                    pos['pnl'] = 0
        else:
            for pos in positions:
                pos['current_price'] = None
                pos['pnl'] = 0

        # Cash = initial capital + realized P&L - margin used
        cash = initial_capital + realized_pnl - margin_used

        # Position value = quantity * entry price (not margin!)
        positions_value = sum([p['quantity'] * p['avg_price'] for p in positions])

        # Total account value = initial capital + realized P&L + unrealized P&L
        total_value = initial_capital + realized_pnl + unrealized_pnl

        conn.close()

        return {
            'model_id': model_id,
            'initial_capital': initial_capital,
            'cash': cash,
            'positions': positions,
            'positions_value': positions_value,
            'margin_used': margin_used,
            'total_value': total_value,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl
        }

    def close_position(self, model_id: int, future: str, side: str = 'long'):
        """Close position and clean up futures universe if unused"""
        conn = self.get_connection()
        cursor = conn.cursor()

        normalized_symbol = future.upper()
        cursor.execute('''
            DELETE FROM portfolios
            WHERE model_id = ? AND UPPER(future) = ? AND side = ?
        ''', (model_id, normalized_symbol, side))
        conn.commit()

        cursor.execute('''
            SELECT EXISTS(
                SELECT 1 FROM portfolios
                WHERE UPPER(future) = ? AND quantity > 0
            ) as has_positions
        ''', (normalized_symbol,))
        has_positions = cursor.fetchone()['has_positions']

        if not has_positions:
            cursor.execute('DELETE FROM futures WHERE UPPER(symbol) = ?', (normalized_symbol,))
            conn.commit()

        conn.close()

    # ============ Trade Records ============

    def add_trade(self, model_id: int, future: str, signal: str, quantity: float,
              price: float, leverage: int = 1, side: str = 'long', pnl: float = 0, fee: float = 0):
        """Add trade record with fee"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (model_id, future, signal, quantity, price, leverage, side, pnl, fee)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (model_id, future.upper(), signal, quantity, price, leverage, side, pnl, fee))
        conn.commit()
        conn.close()

    def get_trades(self, model_id: int, limit: int = 50) -> List[Dict]:
        """Get trade history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM trades WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ============ Conversation History ============

    def add_conversation(self, model_id: int, user_prompt: str,
                        ai_response: str, cot_trace: str = ''):
        """Add conversation record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (model_id, user_prompt, ai_response, cot_trace)
            VALUES (?, ?, ?, ?)
        ''', (model_id, user_prompt, ai_response, cot_trace))
        conn.commit()
        conn.close()

    def get_conversations(self, model_id: int, limit: int = 20) -> List[Dict]:
        """Get conversation history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM conversations WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ============ Account Value History ============

    def record_account_value(self, model_id: int, total_value: float,
                            cash: float, positions_value: float):
        """Record account value snapshot"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO account_values (model_id, total_value, cash, positions_value)
            VALUES (?, ?, ?, ?)
        ''', (model_id, total_value, cash, positions_value))
        conn.commit()
        conn.close()

    def get_account_value_history(self, model_id: int, limit: int = 100) -> List[Dict]:
        """Get account value history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM account_values WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_aggregated_account_value_history(self, limit: int = 100) -> List[Dict]:
        """Get aggregated account value history across all models"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT timestamp,
                   SUM(total_value) as total_value,
                   SUM(cash) as cash,
                   SUM(positions_value) as positions_value,
                   COUNT(DISTINCT model_id) as model_count
            FROM (
                SELECT timestamp,
                       total_value,
                       cash,
                       positions_value,
                       model_id,
                       ROW_NUMBER() OVER (PARTITION BY model_id, DATE(timestamp) ORDER BY timestamp DESC) as rn
                FROM account_values
            ) grouped
            WHERE rn <= 10
            GROUP BY DATE(timestamp), HOUR(timestamp)
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            result.append({
                'timestamp': row['timestamp'],
                'total_value': row['total_value'],
                'cash': row['cash'],
                'positions_value': row['positions_value'],
                'model_count': row['model_count']
            })

        return result

    def get_multi_model_chart_data(self, limit: int = 100) -> List[Dict]:
        """Get chart data for all models to display in multi-line chart"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get all models
        cursor.execute('SELECT id, name FROM models')
        models = cursor.fetchall()

        chart_data = []

        for model in models:
            model_id = model['id']
            model_name = model['name']

            # Get account value history for this model
            cursor.execute('''
                SELECT timestamp, total_value FROM account_values
                WHERE model_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (model_id, limit))

            history = cursor.fetchall()

            if history:
                # Convert to list of dicts with model info
                model_data = {
                    'model_id': model_id,
                    'model_name': model_name,
                    'data': [
                        {
                            'timestamp': row['timestamp'],
                            'value': row['total_value']
                        } for row in history
                    ]
                }
                chart_data.append(model_data)

        conn.close()
        return chart_data

    # ============ Prompt Configuration ============

    def get_model_prompt(self, model_id: int) -> Optional[Dict]:
        """Get model prompt configuration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT model_id, buy_prompt, sell_prompt, updated_at
            FROM model_prompts
            WHERE model_id = ?
        ''', (model_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def upsert_model_prompt(self, model_id: int, buy_prompt: Optional[str], sell_prompt: Optional[str]) -> bool:
        """Insert or update model prompt configuration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if (not buy_prompt or not buy_prompt.strip()) and (not sell_prompt or not sell_prompt.strip()):
                cursor.execute('DELETE FROM model_prompts WHERE model_id = ?', (model_id,))
                conn.commit()
                return True

            cursor.execute('''
                INSERT INTO model_prompts (model_id, buy_prompt, sell_prompt)
                VALUES (?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    buy_prompt = excluded.buy_prompt,
                    sell_prompt = excluded.sell_prompt,
                    updated_at = CURRENT_TIMESTAMP
            ''', (model_id, buy_prompt, sell_prompt))
            conn.commit()
            return True
        except Exception as exc:
            logger.error(f"Error updating prompts for model {model_id}: {exc}")
            conn.rollback()
            return False
        finally:
            conn.close()

    # ============ Futures Universe Management ============

    def get_futures(self) -> List[Dict]:
        """Get all futures configurations"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM futures ORDER BY sort_order DESC, created_at DESC, symbol ASC')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def add_future(self, symbol: str, contract_symbol: str, name: str,
                   exchange: str = 'BINANCE_FUTURES', link: Optional[str] = None, sort_order: int = 0) -> int:
        """Add new future configuration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO futures (symbol, contract_symbol, name, exchange, link, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            symbol.upper(),
            contract_symbol.upper(),
            name,
            exchange.upper(),
            (link or '').strip() or None,
            sort_order
        ))
        future_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return future_id

    def upsert_future(self, symbol: str, contract_symbol: str, name: str,
                     exchange: str = 'BINANCE_FUTURES', link: Optional[str] = None, sort_order: int = 0):
        """Insert or update a futures configuration identified by symbol"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO futures (symbol, contract_symbol, name, exchange, link, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                exchange = excluded.exchange,
                contract_symbol = excluded.contract_symbol,
                link = excluded.link,
                sort_order = excluded.sort_order
        ''', (
            symbol.upper(),
            contract_symbol.upper(),
            name,
            exchange.upper(),
            (link or '').strip() or None,
            sort_order
        ))
        conn.commit()
        conn.close()

    def delete_future(self, future_id: int):
        """Delete future configuration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM futures WHERE id = ?', (future_id,))
        conn.commit()
        conn.close()

    def get_future_configs(self) -> List[Dict]:
        """Get future configurations"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT symbol, contract_symbol, name, exchange, link, sort_order
            FROM futures
            ORDER BY sort_order DESC, symbol ASC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_future_symbols(self) -> List[str]:
        """Get list of future symbols"""
        return [future['symbol'] for future in self.get_future_configs()]

    # ============ Model Futures Configuration ============

    def add_model_future(self, model_id: int, symbol: str, contract_symbol: str,
                         name: str, exchange: str = 'BINANCE_FUTURES',
                         link: Optional[str] = None, sort_order: int = 0) -> int:
        """Add model-specific future configuration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO model_futures (model_id, symbol, contract_symbol, name, exchange, link, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_id, symbol) DO UPDATE SET
                contract_symbol = excluded.contract_symbol,
                name = excluded.name,
                exchange = excluded.exchange,
                link = excluded.link,
                sort_order = excluded.sort_order
        ''', (
            model_id,
            symbol.upper(),
            contract_symbol.upper(),
            name,
            exchange.upper(),
            (link or '').strip() or None,
            sort_order
        ))
        inserted_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return inserted_id

    def delete_model_future(self, model_id: int, symbol: str):
        """Delete model-specific future configuration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM model_futures WHERE model_id = ? AND symbol = ?', (model_id, symbol.upper()))
        conn.commit()
        conn.close()

    def get_model_futures(self, model_id: int) -> List[Dict]:
        """Get model-specific future configurations"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, model_id, symbol, contract_symbol, name, exchange, link, sort_order
            FROM model_futures
            WHERE model_id = ?
            ORDER BY sort_order DESC, symbol ASC
        ''', (model_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def clear_model_futures(self, model_id: int):
        """Clear all model-specific future configurations"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM model_futures WHERE model_id = ?', (model_id,))
        conn.commit()
        conn.close()

    # ============ Settings Management ============

    def get_settings(self) -> Dict:
        """Get system settings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT trading_frequency_minutes, trading_fee_rate,
                   COALESCE(show_system_prompt, 0) as show_system_prompt
            FROM settings
            ORDER BY id DESC
            LIMIT 1
        ''')

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'trading_frequency_minutes': row['trading_frequency_minutes'],
                'trading_fee_rate': row['trading_fee_rate'],
                'show_system_prompt': row['show_system_prompt'] if 'show_system_prompt' in row.keys() else 1
            }
        else:
            # Return default settings if none exist
            return {
                'trading_frequency_minutes': 60,
                'trading_fee_rate': 0.001,
                'show_system_prompt': 1
            }

    def update_settings(self, trading_frequency_minutes: int, trading_fee_rate: float,
                        show_system_prompt: int) -> bool:
        """Update system settings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE settings
                SET trading_frequency_minutes = ?,
                    trading_fee_rate = ?,
                    show_system_prompt = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM settings ORDER BY id DESC LIMIT 1
                )
            ''', (trading_frequency_minutes, trading_fee_rate, show_system_prompt))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            conn.close()
            return False

    # ============ Daily Closing Prices ============

    def upsert_daily_price(self, symbol: str, price: float, price_date: Optional[str] = None):
        """Store or update daily closing price for a symbol"""
        if price is None:
            return

        price_date = price_date or datetime.now().strftime('%Y-%m-%d')
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO daily_prices (symbol, price, price_date)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol, price_date) DO UPDATE SET
                price = excluded.price,
                updated_at = CURRENT_TIMESTAMP
        ''', (symbol, price, price_date))
        conn.commit()
        conn.close()

    def get_latest_daily_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Get the latest stored closing price per symbol"""
        conn = self.get_connection()
        cursor = conn.cursor()

        params: List = []
        symbol_filter = ''
        if symbols:
            placeholders = ','.join(['?'] * len(symbols))
            symbol_filter = f'WHERE symbol IN ({placeholders})'
            params.extend(symbols)

        query = f'''
            WITH latest AS (
                SELECT symbol, MAX(price_date) AS price_date
                FROM daily_prices
                {symbol_filter}
                GROUP BY symbol
            )
            SELECT dp.symbol, dp.price, dp.price_date
            FROM daily_prices dp
            JOIN latest ON dp.symbol = latest.symbol AND dp.price_date = latest.price_date
        '''

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return {row['symbol']: {'price': row['price'], 'price_date': row['price_date']} for row in rows}

    def get_daily_prices_for_date(self, price_date: str, symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Get stored closing prices for a specific date"""
        conn = self.get_connection()
        cursor = conn.cursor()

        params: List = [price_date]
        symbol_filter = ''
        if symbols:
            placeholders = ','.join(['?'] * len(symbols))
            symbol_filter = f' AND symbol IN ({placeholders})'
            params.extend(symbols)

        cursor.execute(f'''
            SELECT symbol, price, price_date
            FROM daily_prices
            WHERE price_date = ?{symbol_filter}
        ''', params)

        rows = cursor.fetchall()
        conn.close()
        return {row['symbol']: {'price': row['price'], 'price_date': row['price_date']} for row in rows}

    # ============ Leaderboard Management ============

    def upsert_leaderboard_entries(self, entries: List[Dict]):
        """Insert or update leaderboard entries"""
        if not entries:
            return

        conn = self.get_connection()
        cursor = conn.cursor()
        payload = []
        for entry in entries:
            try:
                payload.append((
                    entry['symbol'],
                    entry['contract_symbol'],
                    entry.get('name'),
                    entry.get('exchange', 'BINANCE_FUTURES'),
                    entry['side'],
                    entry['rank'],
                    entry.get('price'),
                    entry.get('change_percent'),
                    entry.get('quote_volume'),
                    json.dumps(entry.get('timeframes', {}), ensure_ascii=False)
                ))
            except KeyError as exc:
                logger.warning(f"[DB] 无法写入涨跌幅榜：缺少字段 {exc}")

        if payload:
            cursor.executemany('''
                INSERT INTO futures_leaderboard (
                    symbol, contract_symbol, name, exchange,
                    side, rank, price, change_percent, quote_volume, timeframes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol, side) DO UPDATE SET
                    contract_symbol = excluded.contract_symbol,
                    name = excluded.name,
                    exchange = excluded.exchange,
                    rank = excluded.rank,
                    price = excluded.price,
                    change_percent = excluded.change_percent,
                    quote_volume = excluded.quote_volume,
                    timeframes = excluded.timeframes,
                    updated_at = CURRENT_TIMESTAMP
            ''', payload)
            conn.commit()

        conn.close()

    def get_futures_leaderboard(self, side: Optional[str] = None, limit: int = 10) -> Dict[str, List[Dict]]:
        """Get futures leaderboard data"""
        conn = self.get_connection()
        cursor = conn.cursor()

        def fetch(side_key: str) -> List[Dict]:
            cursor.execute('''
                SELECT symbol, contract_symbol, name, exchange, side,
                       rank, price, change_percent, quote_volume, timeframes, updated_at
                FROM futures_leaderboard
                WHERE side = ?
                ORDER BY rank ASC
                LIMIT ?
            ''', (side_key, limit))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                try:
                    tf = json.loads(row['timeframes']) if row['timeframes'] else {}
                except json.JSONDecodeError:
                    tf = {}
                result.append({
                    'symbol': row['symbol'],
                    'contract_symbol': row['contract_symbol'],
                    'name': row['name'],
                    'exchange': row['exchange'],
                    'side': row['side'],
                    'rank': row['rank'],
                    'price': row['price'],
                    'change_percent': row['change_percent'],
                    'quote_volume': row['quote_volume'],
                    'timeframes': tf,
                    'updated_at': row['updated_at']
                })
            return result

        result: Dict[str, List[Dict]] = {'gainers': [], 'losers': []}
        side_map = {'gainer': 'gainers', 'loser': 'losers'}

        if side:
            normalized = side_map.get(side, side)
            result[normalized] = fetch(side)
        else:
            for raw_key, target_key in side_map.items():
                result[target_key] = fetch(raw_key)

        conn.close()
        return result
