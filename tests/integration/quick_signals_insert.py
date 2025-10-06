"""Quick script to insert first wave of test signals"""
import asyncio
import asyncpg
import json
from datetime import datetime
import random

async def insert_first_wave():
    """Insert first wave of 60 signals"""
    print("🔌 Connecting to database...")
    
    # Connect to database
    conn = await asyncpg.connect(
        host='localhost',
        port=5433,
        database='fox_crypto',
        user='elcrypto',
        password='LohNeMamont@!21'
    )
    
    print("📊 Loading liquid pairs...")
    
    # Load liquid pairs
    with open('tests/integration/liquid_pairs.json', 'r') as f:
        data = json.load(f)
    
    pairs = data['all_pairs']
    
    # Get current wave number
    wave_number = await conn.fetchval("SELECT test.get_current_wave()")
    now = datetime.utcnow()
    
    # Calculate wave boundaries once
    wave_boundaries = await conn.fetchrow(
        "SELECT * FROM test.get_wave_boundaries($1)",
        wave_number
    )
    
    print(f"\n🚀 Inserting {len(pairs)} signals for wave {wave_number}...")
    print(f"⏰ Timestamp: {now}")
    print(f"📅 Wave: {wave_boundaries['wave_start']} - {wave_boundaries['wave_end']}")
    print("")
    
    inserted = 0
    skipped = 0
    
    for pair in pairs:
        try:
            # Generate realistic score (75-95)
            score = round(70.0 + random.uniform(0, 25), 2)
            confidence = round(60.0 + random.uniform(0, 35), 2)
            
            result = await conn.execute("""
                INSERT INTO test.scoring_history (
                    symbol, exchange, timeframe, timestamp, wave_number,
                    score, signal_type, confidence, volume_24h, price_change_24h,
                    wave_start, wave_end
                ) VALUES (
                    $1, $2, '15m', $3, $4, $5, 'MOMENTUM', $6, $7, $8, $9, $10
                )
                ON CONFLICT (symbol, exchange, wave_number) DO NOTHING
            """,
                pair['symbol'],
                pair['exchange'],
                now,
                wave_number,
                score,
                confidence,
                pair['volume_24h_usd'],
                round(random.uniform(-5.0, 15.0), 4),  # Price change
                wave_boundaries['wave_start'],
                wave_boundaries['wave_end']
            )
            
            if 'INSERT' in result:
                inserted += 1
                print(f"  ✅ {pair['symbol']:15} ({pair['exchange']:8}) - Score: {score:5.1f}")
            else:
                skipped += 1
                
        except Exception as e:
            print(f"  ❌ {pair['symbol']}: {e}")
            skipped += 1
    
    await conn.close()
    
    print(f"\n{'━'*70}")
    print(f"📊 Wave {wave_number} Statistics:")
    print(f"   • Signals inserted: {inserted}")
    print(f"   • Signals skipped: {skipped}")
    print(f"   • Total pairs: {len(pairs)}")
    print(f"{'━'*70}")
    print(f"✅ First wave ready!")

if __name__ == "__main__":
    asyncio.run(insert_first_wave())

