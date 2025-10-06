"""
Real Integration Test - Signal Generator
==========================================
Generates test signals every 15 minutes to simulate wave-based trading.

Features:
- Generates signals for top liquid pairs (30 Binance + 30 Bybit = 60 pairs)
- Wave 1: All pairs (~60 signals)
- Wave 2+: 15-20 pairs per wave (70% new + 30% duplicates)
- Realistic score values (70-95)
- Tracks wave numbers
- Runs indefinitely until stopped

Usage:
    python tests/integration/real_test_signal_generator.py [--duration SECONDS]
    
    # Run for 1 hour (4 waves)
    python tests/integration/real_test_signal_generator.py --duration 3600
    
    # Run indefinitely
    python tests/integration/real_test_signal_generator.py
"""
import asyncio
import asyncpg
import json
import random
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path
import sys


class SignalGenerator:
    """Generates test signals for integration testing"""
    
    def __init__(self, 
                 db_dsn: str,
                 liquid_pairs_file: str = "tests/integration/liquid_pairs.json",
                 wave_interval: int = 900,  # 15 minutes
                 duplicate_ratio: float = 0.3):
        """
        Initialize signal generator
        
        Args:
            db_dsn: PostgreSQL connection string
            liquid_pairs_file: Path to liquid pairs JSON
            wave_interval: Seconds between waves (default: 900 = 15 min)
            duplicate_ratio: Ratio of old pairs to include (default: 0.3 = 30%)
        """
        self.db_dsn = db_dsn
        self.liquid_pairs_file = liquid_pairs_file
        self.wave_interval = wave_interval
        self.duplicate_ratio = duplicate_ratio
        
        self.pool = None
        self.pairs = []
        self.wave_number = 0
        self.previous_wave_pairs = []
        self.running = False
    
    async def initialize(self):
        """Initialize database connection and load pairs"""
        print("🔌 Initializing Signal Generator...")
        
        # Load liquid pairs
        await self._load_liquid_pairs()
        
        # Connect to database
        self.pool = await asyncpg.create_pool(self.db_dsn, min_size=1, max_size=5)
        print("✅ Connected to database")
        
        # Get current wave number
        self.wave_number = await self._get_current_wave()
        print(f"📊 Current wave: {self.wave_number}")
    
    async def _load_liquid_pairs(self):
        """Load liquid pairs from JSON file"""
        pairs_file = Path(self.liquid_pairs_file)
        
        if not pairs_file.exists():
            raise FileNotFoundError(
                f"Liquid pairs file not found: {self.liquid_pairs_file}\n"
                f"Run: python tests/integration/real_test_fetch_liquid_pairs.py"
            )
        
        with open(pairs_file, 'r') as f:
            data = json.load(f)
        
        self.pairs = data.get('all_pairs', [])
        print(f"📊 Loaded {len(self.pairs)} liquid pairs")
        print(f"   - Binance: {len([p for p in self.pairs if p['exchange'] == 'binance'])}")
        print(f"   - Bybit: {len([p for p in self.pairs if p['exchange'] == 'bybit'])}")
    
    async def _get_current_wave(self) -> int:
        """Get current wave number from database"""
        async with self.pool.acquire() as conn:
            wave = await conn.fetchval("SELECT test.get_current_wave()")
            return wave or 1
    
    async def _get_wave_boundaries(self, wave_num: int) -> Dict[str, datetime]:
        """Get wave start and end timestamps"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM test.get_wave_boundaries($1)",
                wave_num
            )
            return {
                'wave_start': result['wave_start'],
                'wave_end': result['wave_end']
            }
    
    def _select_pairs_for_wave(self) -> List[Dict[str, Any]]:
        """
        Select pairs for current wave
        
        Logic:
        - Wave 1: All pairs (~60 pairs)
        - Wave 2+: 15-20 pairs (70% new + 30% duplicates for testing)
        """
        total_pairs = len(self.pairs)
        
        # First wave: all pairs
        if not self.previous_wave_pairs:
            selected = self.pairs.copy()
            random.shuffle(selected)
            return selected
        
        # Subsequent waves: smaller subset with duplicates
        wave_size = random.randint(15, 20)  # 15-20 pairs per wave
        num_duplicates = int(wave_size * self.duplicate_ratio)  # 30%
        num_new = wave_size - num_duplicates  # 70%
        
        # Select duplicates from previous wave
        duplicates = random.sample(
            self.previous_wave_pairs, 
            min(num_duplicates, len(self.previous_wave_pairs))
        )
        
        # Select new pairs (not in previous wave)
        available_new = [p for p in self.pairs if p not in self.previous_wave_pairs]
        
        # If we don't have enough new pairs, use some from the full pool
        if len(available_new) < num_new:
            available_new = [p for p in self.pairs if p not in duplicates]
        
        new_pairs = random.sample(available_new, min(num_new, len(available_new)))
        
        # Combine and shuffle
        selected = duplicates + new_pairs
        random.shuffle(selected)
        
        return selected
    
    def _generate_signal_data(self, 
                              pair: Dict[str, Any], 
                              wave_num: int,
                              wave_boundaries: Dict[str, datetime]) -> Dict[str, Any]:
        """Generate signal data for a pair"""
        # Generate realistic score (70-95 to pass threshold)
        score = round(random.uniform(70.0, 95.0), 2)
        
        # Generate realistic confidence (60-95)
        confidence = round(random.uniform(60.0, 95.0), 2)
        
        # Add some randomness to volume (±20%)
        volume_variation = random.uniform(0.8, 1.2)
        volume_24h = pair['volume_24h_usd'] * volume_variation
        
        # Generate realistic price change (-5% to +15%)
        price_change = round(random.uniform(-5.0, 15.0), 4)
        
        return {
            'symbol': pair['symbol'],
            'exchange': pair['exchange'],
            'timeframe': '15m',
            'timestamp': wave_boundaries['wave_start'],  # Use wave start time, not current time
            'wave_number': wave_num,
            'score': score,
            'signal_type': random.choice(['MOMENTUM', 'BREAKOUT', 'TREND']),
            'confidence': confidence,
            'volume_24h': volume_24h,
            'price_change_24h': price_change,
            'wave_start': wave_boundaries['wave_start'],
            'wave_end': wave_boundaries['wave_end'],
        }
    
    async def _insert_signal(self, signal: Dict[str, Any]):
        """Insert signal into database"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO test.scoring_history (
                        symbol, exchange, timeframe, timestamp, wave_number,
                        score, signal_type, confidence, volume_24h, price_change_24h,
                        wave_start, wave_end
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                    )
                    ON CONFLICT (symbol, exchange, wave_number) DO NOTHING
                """,
                    signal['symbol'],
                    signal['exchange'],
                    signal['timeframe'],
                    signal['timestamp'],
                    signal['wave_number'],
                    signal['score'],
                    signal['signal_type'],
                    signal['confidence'],
                    signal['volume_24h'],
                    signal['price_change_24h'],
                    signal['wave_start'],
                    signal['wave_end']
                )
                return True
            except Exception as e:
                print(f"  ⚠️  Error inserting signal {signal['symbol']}: {e}")
                return False
    
    async def generate_wave(self):
        """Generate signals for current wave"""
        self.wave_number += 1
        
        print(f"\n{'='*70}")
        print(f"🌊 Generating Wave #{self.wave_number}")
        print(f"{'='*70}")
        print(f"⏰ Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        # Get wave boundaries
        wave_boundaries = await self._get_wave_boundaries(self.wave_number)
        print(f"📅 Wave period: {wave_boundaries['wave_start']} - {wave_boundaries['wave_end']}")
        
        # Select pairs for this wave
        selected_pairs = self._select_pairs_for_wave()
        print(f"📊 Selected {len(selected_pairs)} pairs")
        
        # Check for duplicates
        if self.previous_wave_pairs:
            duplicates = [p for p in selected_pairs if p in self.previous_wave_pairs]
            new_pairs = [p for p in selected_pairs if p not in self.previous_wave_pairs]
            print(f"   • New pairs: {len(new_pairs)}")
            print(f"   • Duplicate pairs: {len(duplicates)} (for duplicate detection test)")
        
        # Generate and insert signals
        print("\n📝 Generating signals...")
        inserted = 0
        skipped = 0
        
        for pair in selected_pairs:
            signal = self._generate_signal_data(pair, self.wave_number, wave_boundaries)
            success = await self._insert_signal(signal)
            
            if success:
                inserted += 1
                print(f"  ✅ {signal['symbol']:15} ({signal['exchange']:8}) "
                      f"- Score: {signal['score']:5.1f}")
            else:
                skipped += 1
        
        # Update previous wave pairs
        self.previous_wave_pairs = selected_pairs
        
        # Display statistics
        print(f"\n{'─'*70}")
        print(f"📊 Wave #{self.wave_number} Statistics:")
        print(f"   • Signals inserted: {inserted}")
        print(f"   • Signals skipped: {skipped} (duplicates)")
        print(f"   • Total pairs: {len(selected_pairs)}")
        print(f"{'─'*70}")
        
        # Query current test table statistics
        await self._print_statistics()
    
    async def _print_statistics(self):
        """Print test table statistics"""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow("SELECT * FROM test.signal_statistics")
            
            if stats:
                print(f"\n📈 Overall Statistics:")
                print(f"   • Total signals: {stats['total_signals']}")
                print(f"   • Processed signals: {stats['processed_signals']}")
                print(f"   • Positions opened: {stats['positions_opened']}")
                print(f"   • Total waves: {stats['total_waves']}")
                print(f"   • Unique symbols: {stats['unique_symbols']}")
                print(f"   • Binance signals: {stats['binance_signals']}")
                print(f"   • Bybit signals: {stats['bybit_signals']}")
                print(f"   • Avg score: {stats['avg_score']:.2f}")
    
    async def run(self, duration: int = None):
        """
        Run signal generator
        
        Args:
            duration: Run for N seconds (None = indefinitely)
        """
        self.running = True
        start_time = datetime.utcnow()
        
        print("\n" + "="*70)
        print("🚀 SIGNAL GENERATOR STARTED")
        print("="*70)
        print(f"Wave interval: {self.wave_interval} seconds ({self.wave_interval/60:.0f} minutes)")
        if duration:
            print(f"Duration: {duration} seconds ({duration/60:.0f} minutes)")
            print(f"Expected waves: {duration // self.wave_interval}")
        else:
            print(f"Duration: Indefinite (until Ctrl+C)")
        print("="*70)
        
        try:
            # Generate first wave immediately
            await self.generate_wave()
            
            # Continue generating waves
            wave_count = 1
            
            while self.running:
                # Check duration
                if duration:
                    elapsed = (datetime.utcnow() - start_time).total_seconds()
                    if elapsed >= duration:
                        print(f"\n⏱️  Duration limit reached ({duration}s)")
                        break
                
                # Wait for next wave
                print(f"\n⏳ Waiting {self.wave_interval}s for next wave...")
                await asyncio.sleep(self.wave_interval)
                
                # Generate next wave
                if self.running:
                    await self.generate_wave()
                    wave_count += 1
        
        except asyncio.CancelledError:
            print("\n🛑 Signal generator cancelled")
        
        except KeyboardInterrupt:
            print("\n🛑 Signal generator stopped by user")
        
        finally:
            self.running = False
            print(f"\n{'='*70}")
            print(f"✅ SIGNAL GENERATOR STOPPED")
            print(f"   • Total waves generated: {wave_count}")
            print(f"   • Runtime: {(datetime.utcnow() - start_time).total_seconds():.0f}s")
            print(f"{'='*70}")
    
    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            print("🔌 Database connection closed")


async def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description="Test Signal Generator")
    parser.add_argument(
        '--duration',
        type=int,
        default=None,
        help='Run duration in seconds (default: indefinite)'
    )
    parser.add_argument(
        '--db-dsn',
        type=str,
        default='postgresql://elcrypto:LohNeMamont%40%2121@localhost:5433/fox_crypto',
        help='Database DSN'
    )
    parser.add_argument(
        '--wave-interval',
        type=int,
        default=900,
        help='Wave interval in seconds (default: 900 = 15 min)'
    )
    
    args = parser.parse_args()
    
    generator = SignalGenerator(
        db_dsn=args.db_dsn,
        wave_interval=args.wave_interval
    )
    
    try:
        await generator.initialize()
        await generator.run(duration=args.duration)
    
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await generator.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)

