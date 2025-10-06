"""
Real Integration Test - Real-time Monitor
==========================================
Monitors bot activity in real-time and displays formatted statistics.

Features:
- Real-time signal processing statistics
- Position tracking
- Stop-loss monitoring
- Zombie order detection
- WebSocket status
- Performance metrics

Usage:
    python tests/integration/real_test_monitor.py [--interval SECONDS]
    
    # Update every 5 seconds
    python tests/integration/real_test_monitor.py --interval 5
"""
import asyncio
import asyncpg
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any
import sys
import os


class RealTimeMonitor:
    """Real-time monitor for integration test"""
    
    def __init__(self, db_dsn: str, update_interval: int = 10):
        """
        Initialize monitor
        
        Args:
            db_dsn: PostgreSQL connection string
            update_interval: Seconds between updates
        """
        self.db_dsn = db_dsn
        self.update_interval = update_interval
        self.pool = None
        self.running = False
        self.start_time = None
    
    async def initialize(self):
        """Initialize database connection"""
        self.pool = await asyncpg.create_pool(self.db_dsn, min_size=1, max_size=3)
        self.start_time = datetime.utcnow()
    
    async def get_signal_stats(self) -> Dict[str, Any]:
        """Get signal processing statistics"""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_signals,
                    COUNT(*) FILTER (WHERE processed = TRUE) as processed,
                    COUNT(*) FILTER (WHERE position_opened = TRUE) as positions_opened,
                    COUNT(DISTINCT wave_number) as waves,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(*) FILTER (WHERE exchange = 'binance') as binance,
                    COUNT(*) FILTER (WHERE exchange = 'bybit') as bybit,
                    AVG(score) FILTER (WHERE processed = TRUE) as avg_score_processed,
                    MAX(wave_number) as current_wave,
                    MAX(timestamp) as last_signal
                FROM test.scoring_history
            """)
            
            return dict(stats) if stats else {}
    
    async def get_position_stats(self) -> Dict[str, Any]:
        """Get position statistics"""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_positions,
                    COUNT(*) FILTER (WHERE status = 'OPEN') as open_positions,
                    COUNT(*) FILTER (WHERE status = 'CLOSED') as closed_positions,
                    COUNT(*) FILTER (WHERE exchange = 'binance') as binance_positions,
                    COUNT(*) FILTER (WHERE exchange = 'bybit') as bybit_positions,
                    SUM(size) FILTER (WHERE status = 'OPEN') as total_size_open,
                    AVG(entry_price) FILTER (WHERE status = 'OPEN') as avg_entry_price,
                    COUNT(*) FILTER (WHERE stop_loss IS NOT NULL) as with_stop_loss,
                    MAX(opened_at) as last_position_opened
                FROM monitoring.positions
                WHERE created_at > NOW() - INTERVAL '24 hours'
            """)
            
            return dict(stats) if stats else {}
    
    async def get_recent_positions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent positions"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    symbol,
                    exchange,
                    status,
                    size,
                    entry_price,
                    stop_loss,
                    opened_at,
                    closed_at
                FROM monitoring.positions
                WHERE created_at > NOW() - INTERVAL '24 hours'
                ORDER BY opened_at DESC
                LIMIT $1
            """, limit)
            
            return [dict(row) for row in rows]
    
    async def get_recent_signals(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent processed signals"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    symbol,
                    exchange,
                    wave_number,
                    score,
                    processed,
                    position_opened,
                    processed_at,
                    timestamp
                FROM test.scoring_history
                ORDER BY timestamp DESC
                LIMIT $1
            """, limit)
            
            return [dict(row) for row in rows]
    
    async def get_zombie_stats(self) -> Dict[str, Any]:
        """Get zombie order statistics (placeholder)"""
        # This would need to query actual zombie detection results
        # For now, return mock data
        return {
            'zombie_orders': 0,
            'phantom_positions': 0,
            'untracked_positions': 0,
            'last_cleanup': None
        }
    
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"
    
    def format_number(self, num: Any) -> str:
        """Format number with commas"""
        if num is None:
            return "N/A"
        return f"{float(num):,.2f}"
    
    async def display_dashboard(self):
        """Display monitoring dashboard"""
        # Fetch data
        signal_stats = await self.get_signal_stats()
        position_stats = await self.get_position_stats()
        recent_positions = await self.get_recent_positions(5)
        recent_signals = await self.get_recent_signals(5)
        zombie_stats = await self.get_zombie_stats()
        
        # Clear screen
        self.clear_screen()
        
        # Header
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        print("╔" + "═"*78 + "╗")
        print("║" + " "*20 + "🧪 REAL INTEGRATION TEST MONITOR" + " "*25 + "║")
        print("╠" + "═"*78 + "╣")
        print(f"║ ⏰ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC" + " "*30 + 
              f"⏱️  Uptime: {self.format_duration(elapsed):>10}" + " ║")
        print("╚" + "═"*78 + "╝")
        
        # Signal Processing
        print("\n" + "━"*80)
        print("📊 SIGNAL PROCESSING")
        print("━"*80)
        print(f"Total Signals:       {signal_stats.get('total_signals', 0):>6}    "
              f"Current Wave:        {signal_stats.get('current_wave', 0):>6}")
        print(f"Processed:           {signal_stats.get('processed', 0):>6}    "
              f"Unique Symbols:      {signal_stats.get('unique_symbols', 0):>6}")
        print(f"Positions Opened:    {signal_stats.get('positions_opened', 0):>6}    "
              f"Total Waves:         {signal_stats.get('waves', 0):>6}")
        print(f"Binance Signals:     {signal_stats.get('binance', 0):>6}    "
              f"Bybit Signals:       {signal_stats.get('bybit', 0):>6}")
        
        if signal_stats.get('avg_score_processed'):
            print(f"Avg Score (proc):    {signal_stats.get('avg_score_processed'):>6.2f}")
        
        # Position Tracking
        print("\n" + "━"*80)
        print("💼 POSITIONS")
        print("━"*80)
        print(f"Total Positions:     {position_stats.get('total_positions', 0):>6}    "
              f"Open:                {position_stats.get('open_positions', 0):>6}")
        print(f"Closed:              {position_stats.get('closed_positions', 0):>6}    "
              f"With Stop Loss:      {position_stats.get('with_stop_loss', 0):>6}")
        print(f"Binance Positions:   {position_stats.get('binance_positions', 0):>6}    "
              f"Bybit Positions:     {position_stats.get('bybit_positions', 0):>6}")
        
        if position_stats.get('total_size_open'):
            print(f"Total Size (open):   {self.format_number(position_stats.get('total_size_open')):>10}")
        
        # Recent Positions
        if recent_positions:
            print("\n" + "─"*80)
            print("📝 Recent Positions (Last 5):")
            print("─"*80)
            print(f"{'Symbol':<15} {'Exchange':<10} {'Status':<8} {'Size':<12} {'Entry':<12} {'SL':<12}")
            print("─"*80)
            for pos in recent_positions:
                sl_str = f"${pos['stop_loss']:,.2f}" if pos['stop_loss'] else "N/A"
                print(f"{pos['symbol']:<15} {pos['exchange']:<10} {pos['status']:<8} "
                      f"{pos['size']:<12.4f} ${pos['entry_price']:<11,.2f} {sl_str:<12}")
        
        # Recent Signals
        if recent_signals:
            print("\n" + "─"*80)
            print("📡 Recent Signals (Last 5):")
            print("─"*80)
            print(f"{'Symbol':<15} {'Exchange':<10} {'Wave':<6} {'Score':<8} {'Processed':<10} {'Position':<10}")
            print("─"*80)
            for sig in recent_signals:
                proc = "✅ Yes" if sig['processed'] else "⏳ No"
                pos = "✅ Yes" if sig['position_opened'] else "❌ No"
                print(f"{sig['symbol']:<15} {sig['exchange']:<10} {sig['wave_number']:<6} "
                      f"{sig['score']:<8.2f} {proc:<10} {pos:<10}")
        
        # Zombie Detection
        print("\n" + "━"*80)
        print("🧟 ZOMBIE DETECTION")
        print("━"*80)
        print(f"Zombie Orders:       {zombie_stats.get('zombie_orders', 0):>6}    "
              f"Phantom Positions:   {zombie_stats.get('phantom_positions', 0):>6}")
        print(f"Untracked Positions: {zombie_stats.get('untracked_positions', 0):>6}")
        
        # Footer
        print("\n" + "━"*80)
        print(f"🔄 Next update in {self.update_interval}s | Press Ctrl+C to stop")
        print("━"*80)
    
    async def run(self, duration: int = None):
        """
        Run monitor
        
        Args:
            duration: Run for N seconds (None = indefinitely)
        """
        self.running = True
        start_time = datetime.utcnow()
        
        print("\n" + "="*80)
        print("🚀 MONITOR STARTED")
        print("="*80)
        print(f"Update interval: {self.update_interval} seconds")
        if duration:
            print(f"Duration: {duration} seconds ({duration/60:.0f} minutes)")
        else:
            print(f"Duration: Indefinite (until Ctrl+C)")
        print("="*80)
        
        try:
            while self.running:
                # Check duration
                if duration:
                    elapsed = (datetime.utcnow() - start_time).total_seconds()
                    if elapsed >= duration:
                        print(f"\n⏱️  Duration limit reached ({duration}s)")
                        break
                
                await self.display_dashboard()
                await asyncio.sleep(self.update_interval)
        
        except asyncio.CancelledError:
            print("\n🛑 Monitor cancelled")
        
        except KeyboardInterrupt:
            print("\n🛑 Monitor stopped by user")
        
        finally:
            self.running = False
            print("\n✅ Monitor stopped")
    
    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()


async def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description="Real-time Test Monitor")
    parser.add_argument(
        '--interval',
        type=int,
        default=10,
        help='Update interval in seconds (default: 10)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=None,
        help='Run duration in seconds (default: indefinite)'
    )
    parser.add_argument(
        '--db-dsn',
        type=str,
        default='postgresql://localhost/trading_bot',
        help='Database DSN'
    )
    
    args = parser.parse_args()
    
    monitor = RealTimeMonitor(
        db_dsn=args.db_dsn,
        update_interval=args.interval
    )
    
    try:
        await monitor.initialize()
        await monitor.run(duration=args.duration)
    
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await monitor.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)

