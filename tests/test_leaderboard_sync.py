"""Executable integration checks for ClickHouse leaderboard synchronization.

Run with:

    python tests/test_leaderboard_sync.py

The script reuses the main ClickHouse configuration from config.py and will
exit with non-zero status if any check fails.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable, List, Tuple

from app import (
    start_clickhouse_leaderboard_sync,
    stop_clickhouse_leaderboard_sync,
    clickhouse_leaderboard_stop_event,
    clickhouse_leaderboard_running
)
from database_clickhouse import ClickHouseDatabase


def _require_clickhouse() -> ClickHouseDatabase:
    try:
        return ClickHouseDatabase(auto_init_tables=True)
    except Exception as exc:
        raise RuntimeError(f"ClickHouse unavailable: {exc}") from exc


def _check_leaderboard_sync_starts() -> None:
    """Check that the leaderboard sync thread can be started"""
    # Ensure any existing thread is stopped
    if clickhouse_leaderboard_running:
        stop_clickhouse_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
    
    # Verify initial state
    assert not clickhouse_leaderboard_running, "Leaderboard sync should not be running initially"
    
    # Start the sync thread
    start_clickhouse_leaderboard_sync()
    
    # Check that it's running
    assert clickhouse_leaderboard_running, "Leaderboard sync should be running after start"
    assert not clickhouse_leaderboard_stop_event.is_set(), "Stop event should not be set after start"
    
    # Check that thread exists and is alive
    from app import clickhouse_leaderboard_thread
    assert clickhouse_leaderboard_thread is not None, "Leaderboard thread should not be None"
    assert clickhouse_leaderboard_thread.is_alive(), "Leaderboard thread should be alive"
    
    # Try to start again - should not create a new thread
    thread_id_before = clickhouse_leaderboard_thread.ident
    start_clickhouse_leaderboard_sync()
    thread_id_after = clickhouse_leaderboard_thread.ident
    assert thread_id_before == thread_id_after, "Thread ID should be the same after second start call"
    
    # Stop the thread
    stop_clickhouse_leaderboard_sync()
    time.sleep(0.1)  # Give time for thread to stop
    
    # Check that it's stopped
    assert not clickhouse_leaderboard_running, "Leaderboard sync should not be running after stop"


def _check_leaderboard_sync_functionality(db: ClickHouseDatabase) -> None:
    """Check that the leaderboard sync actually performs synchronization"""
    # Ensure any existing thread is stopped
    if clickhouse_leaderboard_running:
        stop_clickhouse_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
    
    # Clear any existing data in leaderboard table
    try:
        db._client.command(f"TRUNCATE TABLE IF EXISTS {db.leaderboard_table}")
    except Exception:
        pass  # Ignore if table doesn't exist
    
    # Ensure the leaderboard table exists
    db.ensure_leaderboard_table()
    
    # Insert some test data into market_ticker_table to have something to sync
    db.ensure_market_ticker_table()
    
    # Insert test ticker data with positive and negative price changes
    current_time = int(time.time() * 1000)
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
            "stats_open_time": current_time - 60000,
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
            "stats_open_time": current_time - 60000,
            "stats_close_time": current_time,
            "first_trade_id": 11,
            "last_trade_id": 20,
            "trade_count": 10,
        }
    ]
    
    db.insert_market_tickers(test_tickers)
    
    # Start the sync thread with a larger time window to ensure test data is captured
    # We use a 60-second window to make sure our test data is included
    from app import clickhouse_leaderboard_thread, clickhouse_leaderboard_running
    from app import start_clickhouse_leaderboard_sync, stop_clickhouse_leaderboard_sync
    from app import clickhouse_leaderboard_stop_event
    import config as app_config
    
    # Temporarily modify the time window for testing
    original_time_window = getattr(app_config, 'CLICKHOUSE_LEADERBOARD_TIME_WINDOW', 5)
    app_config.CLICKHOUSE_LEADERBOARD_TIME_WINDOW = 60  # Use 60 seconds for testing
    
    try:
        start_clickhouse_leaderboard_sync()
        
        # Wait a bit for the sync to happen (with a timeout)
        timeout = time.time() + 10  # 10 seconds timeout
        synced = False
        while time.time() < timeout:
            # Check that data was synced to leaderboard table
            try:
                result = db._client.query(f"SELECT count() FROM {db.leaderboard_table}")
                count = result.result_rows[0][0]
                if count > 0:
                    synced = True
                    break
            except Exception:
                pass  # Ignore exceptions during polling
            time.sleep(0.5)
        
        # Stop the thread
        stop_clickhouse_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
        
        # Verify that sync happened
        assert synced, "Leaderboard table should have data after sync within timeout"
    finally:
        # Restore original time window
        app_config.CLICKHOUSE_LEADERBOARD_TIME_WINDOW = original_time_window


def _check_leaderboard_sync_stop_functionality() -> None:
    """Check that the leaderboard sync can be properly stopped"""
    # Ensure any existing thread is stopped
    if clickhouse_leaderboard_running:
        stop_clickhouse_leaderboard_sync()
        time.sleep(0.1)  # Give time for thread to stop
    
    # Start the sync thread
    start_clickhouse_leaderboard_sync()
    
    # Verify it's running
    assert clickhouse_leaderboard_running, "Leaderboard sync should be running after start"
    
    # Stop the thread
    stop_clickhouse_leaderboard_sync()
    time.sleep(0.1)  # Give time for thread to stop
    
    # Verify it's stopped
    assert not clickhouse_leaderboard_running, "Leaderboard sync should not be running after stop"
    assert clickhouse_leaderboard_stop_event.is_set(), "Stop event should be set after stop"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        db = _require_clickhouse()
    except RuntimeError as exc:
        logging.error(exc)
        return 1

    checks: List[Tuple[str, Callable[[], None] | Callable[[ClickHouseDatabase], None]]] = [
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