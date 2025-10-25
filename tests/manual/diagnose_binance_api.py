"""
Diagnostic script to check Binance API key permissions
Tests both Spot and Futures endpoints to identify the issue

Usage:
    BINANCE_API_KEY=xxx BINANCE_API_SECRET=yyy python tests/manual/diagnose_binance_api.py

Date: 2025-10-25
"""

import asyncio
import os
import logging
import hmac
import hashlib
import time
import aiohttp
from urllib.parse import urlencode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_signature(query_string: str, api_secret: str) -> str:
    """Create HMAC SHA256 signature"""
    return hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


async def test_spot_api(api_key: str, api_secret: str):
    """Test Spot API access"""
    logger.info("=" * 80)
    logger.info("🔍 Testing SPOT API")
    logger.info("=" * 80)

    url = "https://api.binance.com/api/v3/account"

    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"
    signature = create_signature(query_string, api_secret)

    headers = {
        'X-MBX-APIKEY': api_key
    }

    full_url = f"{url}?{query_string}&signature={signature}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(full_url, headers=headers) as response:
                status = response.status
                data = await response.text()

                if status == 200:
                    logger.info(f"✅ SPOT API: Working (200 OK)")
                    logger.info(f"   API key has Spot access")
                    return True
                else:
                    logger.error(f"❌ SPOT API: Failed ({status})")
                    logger.error(f"   Response: {data}")
                    return False
    except Exception as e:
        logger.error(f"❌ SPOT API: Exception - {e}")
        return False


async def test_futures_api(api_key: str, api_secret: str):
    """Test Futures API access"""
    logger.info("=" * 80)
    logger.info("🔍 Testing FUTURES API")
    logger.info("=" * 80)

    url = "https://fapi.binance.com/fapi/v2/account"

    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"
    signature = create_signature(query_string, api_secret)

    headers = {
        'X-MBX-APIKEY': api_key
    }

    full_url = f"{url}?{query_string}&signature={signature}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(full_url, headers=headers) as response:
                status = response.status
                data = await response.text()

                if status == 200:
                    logger.info(f"✅ FUTURES API: Working (200 OK)")
                    logger.info(f"   API key has Futures access")
                    return True
                else:
                    logger.error(f"❌ FUTURES API: Failed ({status})")
                    logger.error(f"   Response: {data}")
                    return False
    except Exception as e:
        logger.error(f"❌ FUTURES API: Exception - {e}")
        return False


async def test_listen_key(api_key: str, api_secret: str):
    """Test listen key creation for User Data Stream"""
    logger.info("=" * 80)
    logger.info("🔍 Testing LISTEN KEY Creation")
    logger.info("=" * 80)

    url = "https://fapi.binance.com/fapi/v1/listenKey"

    headers = {
        'X-MBX-APIKEY': api_key
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                status = response.status
                data = await response.text()

                if status == 200:
                    logger.info(f"✅ LISTEN KEY: Created successfully")
                    logger.info(f"   Response: {data}")
                    return True
                else:
                    logger.error(f"❌ LISTEN KEY: Failed ({status})")
                    logger.error(f"   Response: {data}")
                    return False
    except Exception as e:
        logger.error(f"❌ LISTEN KEY: Exception - {e}")
        return False


async def diagnose():
    """Run all diagnostic tests"""

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        logger.error("❌ BINANCE_API_KEY and BINANCE_API_SECRET required")
        return

    logger.info("=" * 80)
    logger.info("🩺 BINANCE API DIAGNOSTIC")
    logger.info("=" * 80)
    logger.info(f"API Key: {api_key[:10]}...{api_key[-10:]}")
    logger.info("")

    # Test all endpoints
    spot_ok = await test_spot_api(api_key, api_secret)
    await asyncio.sleep(1)

    futures_ok = await test_futures_api(api_key, api_secret)
    await asyncio.sleep(1)

    listen_key_ok = await test_listen_key(api_key, api_secret)

    # Summary
    logger.info("=" * 80)
    logger.info("📊 DIAGNOSTIC SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Spot API:     {'✅ Working' if spot_ok else '❌ Failed'}")
    logger.info(f"Futures API:  {'✅ Working' if futures_ok else '❌ Failed'}")
    logger.info(f"Listen Key:   {'✅ Working' if listen_key_ok else '❌ Failed'}")
    logger.info("")

    if not futures_ok:
        logger.info("🔴 DIAGNOSIS:")
        logger.info("   The API key does NOT have Futures permissions enabled.")
        logger.info("")
        logger.info("📋 TO FIX:")
        logger.info("   1. Go to: https://www.binance.com/en/my/settings/api-management")
        logger.info("   2. Find your API key")
        logger.info("   3. Click 'Edit restrictions'")
        logger.info("   4. Enable 'Enable Futures' checkbox")
        logger.info("   5. Save changes")
        logger.info("")
        if spot_ok:
            logger.info("   Note: Your API key works for SPOT trading but not FUTURES")
    elif not listen_key_ok:
        logger.info("🔴 DIAGNOSIS:")
        logger.info("   Futures API access works, but Listen Key creation fails.")
        logger.info("   This could be an IP whitelist issue.")
        logger.info("")
        logger.info("📋 TO FIX:")
        logger.info("   1. Go to: https://www.binance.com/en/my/settings/api-management")
        logger.info("   2. Check if IP whitelist is enabled")
        logger.info("   3. Add your current IP or disable whitelist for testing")
    else:
        logger.info("✅ All tests passed! API key is correctly configured for Futures.")


if __name__ == '__main__':
    asyncio.run(diagnose())
