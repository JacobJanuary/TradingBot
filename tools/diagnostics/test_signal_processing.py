#!/usr/bin/env python3
"""Test signal processing without running the bot"""
import asyncio
import logging
import os
from dotenv import load_dotenv
from database.repository import Repository
from models.validation import validate_signal
from config.settings import Settings

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_signal_processing():
    """Test signal fetching and validation"""
    settings = Settings()

    # Initialize repository
    repository = Repository(settings.database)
    await repository.initialize()

    try:
        # Fetch signals
        logger.info("Fetching signals...")
        signals = await repository.get_unprocessed_signals(
            min_score_week=50.0,
            min_score_month=50.0,
            time_window_minutes=1440,
            limit=5
        )

        logger.info(f"Fetched {len(signals)} signals")

        for signal in signals:
            logger.info(f"\nProcessing signal #{signal['id']}")
            logger.info(f"  Symbol: {signal.get('symbol')}")
            logger.info(f"  Action: {signal.get('action')}")
            logger.info(f"  Exchange: {signal.get('exchange')}")
            logger.info(f"  Score week: {signal.get('score_week')}")
            logger.info(f"  Score month: {signal.get('score_month')}")

            # Try to validate
            validated = validate_signal(signal)
            if validated:
                logger.info(f"  ✅ Validation passed")
                logger.info(f"     Action enum: {validated.action}")
            else:
                logger.warning(f"  ❌ Validation failed")

    finally:
        await repository.close()

if __name__ == "__main__":
    asyncio.run(test_signal_processing())