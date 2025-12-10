"""Executable integration checks for MySQL leaderboard synchronization.

Run with:

    python tests/test_leaderboard_sync.py

The script reuses the main MySQL configuration from common.config and will
exit with non-zero status if any check fails.

Note: This test imports functions from backend.app, which requires the Flask
application context to be properly initialized.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable, List, Tuple
from datetime import datetime, timezone

from backend.app import (
    start_mysql_leaderboard_sync,
    stop_mysql_leaderboard_sync,
    mysql_leaderboard_stop_event,
    mysql_leaderboard_running,
    mysql_leaderboard_thread
)
from common.database_mysql import MySQLDatabase


def _require_mysql() -> MySQLDatabase:
    try:
        return MySQLDatabase(auto_init_tables=True)
    except Exception as exc:
        raise RuntimeError(f"MySQL unavailable: {exc}") from exc


def _check_leaderboard_sync_starts() -> None:
    """Check that the leaderboard sync thread can be started"""
    # Ensure any existing thread is stopped
    if mysql_leaderboard_running:
        stop_mysql_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
    
    # Verify initial state
    assert not mysql_leaderboard_running, "Leaderboard sync should not be running initially"
    
    # Start the sync thread
    start_mysql_leaderboard_sync()
    
    # Check that it's running
    assert mysql_leaderboard_running, "Leaderboard sync should be running after start"
    assert not mysql_leaderboard_stop_event.is_set(), "Stop event should not be set after start"
    
    # Check that thread exists and is alive
    assert mysql_leaderboard_thread is not None, "Leaderboard thread should not be None"
    assert mysql_leaderboard_thread.is_alive(), "Leaderboard thread should be alive"
    
    # Try to start again - should not create a new thread
    thread_id_before = mysql_leaderboard_thread.ident
    start_mysql_leaderboard_sync()
    thread_id_after = mysql_leaderboard_thread.ident
    assert thread_id_before == thread_id_after, "Thread ID should be the same after second start call"
    
    # Stop the thread
    stop_mysql_leaderboard_sync()
    time.sleep(0.1)  # Give time for thread to stop
    
    # Check that it's stopped
    assert not mysql_leaderboard_running, "Leaderboard sync should not be running after stop"


def _check_leaderboard_sync_functionality(db: MySQLDatabase) -> None:
    """Check that the leaderboard sync actually performs synchronization"""
    # Ensure any existing thread is stopped
    if mysql_leaderboard_running:
        stop_mysql_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
    
    # Clear any existing data in leaderboard table
    try:
        db.command(f"TRUNCATE TABLE `{db.leaderboard_table}`")
    except Exception:
        pass  # Ignore if table doesn't exist
    
    # Ensure the leaderboard table exists
    db.ensure_leaderboard_table()
    
    # Insert some test data into market_ticker_table to have something to sync
    db.ensure_market_ticker_table()
    
    # Insert test ticker data with positive and negative price changes
    current_time = datetime.now(timezone.utc)
    test_tickers = [
        {
            "event_time": current_time,
            "symbol": "TEST1USDT",
            "price_change": 10.0,
            "price_change_percent": 5.0,  # Gainer
            "average_price": 200.0,
            "last_price": 210.0,
            "last_trade_volume": 1.0,
            "open_price": 200.0,
            "high_price": 215.0,
            "low_price": 195.0,
            "base_volume": 100.0,
            "quote_volume": 20000.0,
            "stats_open_time": current_time,
            "stats_close_time": current_time,
            "first_trade_id": 1,
            "last_trade_id": 10,
            "trade_count": 10,
        },
        {
            "event_time": current_time,
            "symbol": "TEST2USDT",
            "price_change": -20.0,
            "price_change_percent": -8.0,  # Loser
            "average_price": 250.0,
            "last_price": 230.0,
            "last_trade_volume": 1.5,
            "open_price": 250.0,
            "high_price": 255.0,
            "low_price": 225.0,
            "base_volume": 150.0,
            "quote_volume": 35000.0,
            "stats_open_time": current_time,
            "stats_close_time": current_time,
            "first_trade_id": 11,
            "last_trade_id": 20,
            "trade_count": 10,
        }
    ]
    
    db.insert_market_tickers(test_tickers)
    
    # Start the sync thread with a larger time window to ensure test data is captured
    # We use a 60-second window to make sure our test data is included
    import common.config as app_config
    
    # Temporarily modify the time window for testing
    original_time_window = getattr(app_config, 'MYSQL_LEADERBOARD_TIME_WINDOW', 5)
    app_config.MYSQL_LEADERBOARD_TIME_WINDOW = 60  # Use 60 seconds for testing
    
    try:
        start_mysql_leaderboard_sync()
        
        # Wait a bit for the sync to happen (with a timeout)
        timeout = time.time() + 10  # 10 seconds timeout
        synced = False
        while time.time() < timeout:
            # Check that data was synced to leaderboard table
            try:
                result = db.query(f"SELECT COUNT(*) FROM `{db.leaderboard_table}`")
                count = result[0][0] if result else 0
                if count > 0:
                    synced = True
                    break
            except Exception:
                pass  # Ignore exceptions during polling
            time.sleep(0.5)
        
        # Stop the thread
        stop_mysql_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
        
        # Verify that sync happened
        assert synced, "Leaderboard table should have data after sync within timeout"
    finally:
        # Restore original time window
        app_config.MYSQL_LEADERBOARD_TIME_WINDOW = original_time_window


def _check_leaderboard_sync_stop_functionality() -> None:
    """Check that the leaderboard sync can be properly stopped"""
    # Ensure any existing thread is stopped
    if mysql_leaderboard_running:
        stop_mysql_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
    
    # Start the sync thread
    start_mysql_leaderboard_sync()
    
    # Verify it's running
    assert mysql_leaderboard_running, "Leaderboard sync should be running after start"
    
    # Stop the thread
    stop_mysql_leaderboard_sync()
    time.sleep(0.1)  # Give time for thread to stop
    
    # Verify it's stopped
    assert not mysql_leaderboard_running, "Leaderboard sync should not be running after stop"
    assert mysql_leaderboard_stop_event.is_set(), "Stop event should be set after stop"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        db = _require_mysql()
    except RuntimeError as exc:
        logging.error(exc)
        return 1

    checks: List[Tuple[str, Callable[[], None] | Callable[[MySQLDatabase], None]]] = [
        ("leaderboard_sync_starts", _check_leaderboard_sync_starts),
        ("leaderboard_sync_stop_functionality", _check_leaderboard_sync_stop_functionality),
        ("leaderboard_sync_functionality", lambda: _check_leaderboard_sync_functionality(db)),
    ]

    all_passed = True
    for name, func in checks:
        try:
            logging.info("Running %s...", name)
            func()
            logging.info("%s passed", name)
        except AssertionError as err:
            all_passed = False
            logging.error("%s failed: %s", name, err)
        except Exception as err:
            all_passed = False
            logging.exception("%s raised unexpected error", name)

    if all_passed:
        logging.info("All leaderboard sync checks passed")
        return 0

    logging.error("One or more leaderboard sync checks failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())