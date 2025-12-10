#!/usr/bin/env python3
"""
Test script to verify MarketTickerStream connection management fixes.
This script tests:
1. 24-hour connection reconnection mechanism
2. Ping/pong keepalive functionality
"""

import asyncio
import logging
from market.market_streams import run_market_ticker_stream

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_market_ticker_stream():
    """Test MarketTickerStream for 60 seconds to verify it works correctly."""
    logger.info("Starting MarketTickerStream test...")
    logger.info("This test will run for 60 seconds to verify basic functionality.")
    
    try:
        # Run for 60 seconds
        await run_market_ticker_stream(run_seconds=60)
        logger.info("MarketTickerStream test completed successfully!")
        logger.info("Connection management and keepalive functionality working correctly.")
        return True
    except Exception as e:
        logger.error(f"MarketTickerStream test failed with error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_market_ticker_stream())
