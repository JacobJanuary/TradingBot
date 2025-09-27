#!/usr/bin/env python3
"""
Быстрая проверка Bybit подключения
"""
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

def check_bybit():
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    
    print("="*50)
    print("BYBIT CONNECTION CHECK")
    print("="*50)
    
    if not api_key or not api_secret:
        print("❌ API keys not found in .env")
        return
    
    print(f"✅ API Key: {api_key[:8]}...")
    
    # Create exchange
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'testnet': True,
        'options': {
            'defaultType': 'future',
            'accountType': 'UNIFIED'
        }
    })
    
    exchange.set_sandbox_mode(True)
    
    try:
        # Try to fetch balance
        print("\nTrying to fetch balance...")
        balance = exchange.fetch_balance()
        usdt = balance.get('USDT', {}).get('free', 0)
        print(f"✅ SUCCESS! USDT Balance: {usdt:.2f}")
        print("\n🎉 Your Bybit UNIFIED account is working!")
        
    except Exception as e:
        error_msg = str(e)
        if "accountType only support UNIFIED" in error_msg:
            print("❌ ERROR: Your account is NOT UNIFIED")
            print("\n📋 TO FIX:")
            print("1. Go to https://testnet.bybit.com")
            print("2. Login → Assets → Account Type")
            print("3. Click 'Upgrade to Unified Account'")
            print("4. Create NEW API keys")
            print("5. Update .env file")
            print("\nSee BYBIT_QUICK_FIX.md for details")
        else:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_bybit()