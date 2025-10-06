"""Insert signals for NEXT wave (correct timestamp for wave detection)"""
import asyncio
import asyncpg
import json
from datetime import datetime, timedelta
import random

async def insert_next_wave():
    """Insert signals for the next wave check"""
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
    
    # Calculate NEXT wave timestamp
    now = datetime.utcnow()
    current_minute = now.minute
    
    # Wave check minutes: 4, 18, 33, 48
    wave_check_minutes = [4, 18, 33, 48]
    
    # Find next wave check minute
    next_wave_minute = None
    for minute in wave_check_minutes:
        if minute > current_minute:
            next_wave_minute = minute
            break
    
    if next_wave_minute is None:
        # Next wave is in the next hour
        next_wave_minute = wave_check_minutes[0]
        next_wave_time = now.replace(minute=next_wave_minute, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_wave_time = now.replace(minute=next_wave_minute, second=0, microsecond=0)
    
    # Wave timestamp is 3 minutes BEFORE the check (candle close time)
    wave_timestamp = next_wave_time - timedelta(minutes=3)
    
    # Get wave number based on this timestamp
    wave_number = await conn.fetchval(
        "SELECT FLOOR(EXTRACT(EPOCH FROM ($1 - '2025-10-04 00:00:00'::timestamp)) / 900) + 1",
        wave_timestamp
    )
    
    # Calculate wave boundaries
    wave_boundaries = await conn.fetchrow(
        "SELECT * FROM test.get_wave_boundaries($1)",
        wave_number
    )
    
    print(f"\n🚀 Inserting {len(pairs)} signals for NEXT wave...")
    print(f"⏰ Current time:     {now.strftime('%H:%M:%S')} UTC")
    print(f"📅 Wave check time:  {next_wave_time.strftime('%H:%M:%S')} UTC (in {(next_wave_time - now).total_seconds() / 60:.1f} min)")
    print(f"🎯 Wave timestamp:   {wave_timestamp.strftime('%H:%M:%S')} UTC")
    print(f"🌊 Wave number:      {wave_number}")
    print(f"📊 Wave period:      {wave_boundaries['wave_start']} - {wave_boundaries['wave_end']}")
    print("")
    
    inserted = 0
    skipped = 0
    
    for pair in pairs:
        try:
            # Generate realistic score (70-95)
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
                wave_timestamp,  # Important: use calculated wave timestamp!
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
    print(f"   • Wave timestamp: {wave_timestamp}")
    print(f"   • Bot will detect at: {next_wave_time}")
    print(f"   • Time until detection: {(next_wave_time - now).total_seconds() / 60:.1f} minutes")
    print(f"{'━'*70}")
    print(f"✅ Next wave ready! Bot will pick up these signals in ~{(next_wave_time - now).total_seconds() / 60:.0f} minutes!")

if __name__ == "__main__":
    asyncio.run(insert_next_wave())

