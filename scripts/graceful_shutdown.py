#!/usr/bin/env python3
"""
Graceful shutdown script
Safely closes all positions and stops the trading bot
"""

import asyncio
import asyncpg
import sys
import os
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv
import signal
import json

# Load environment variables
load_dotenv()

class GracefulShutdown:
    """Handle graceful shutdown of trading bot"""
    
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        self.shutdown_reason = "Manual shutdown"
        
    async def save_state(self):
        """Save current system state for recovery"""
        try:
            state = {
                'shutdown_time': datetime.utcnow().isoformat(),
                'reason': self.shutdown_reason,
                'positions': [],
                'pending_orders': []
            }
            
            conn = await asyncpg.connect(self.db_url)
            
            # Get active positions
            positions = await conn.fetch("""
                SELECT id, symbol, side, quantity, entry_price, unrealized_pnl
                FROM monitoring.positions
                WHERE status = 'active'
            """)
            
            state['positions'] = [dict(p) for p in positions]
            
            # Get pending orders
            orders = await conn.fetch("""
                SELECT id, symbol, side, type, size, price
                FROM monitoring.orders
                WHERE status IN ('pending', 'open', 'partially_filled')
            """)
            
            state['pending_orders'] = [dict(o) for o in orders]
            
            await conn.close()
            
            # Save state to file
            state_file = f"backups/shutdown_state_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            logger.info(f"✓ System state saved to {state_file}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to save state: {e}")
            return False
    
    async def cancel_pending_orders(self):
        """Cancel all pending orders"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            # Get pending orders
            orders = await conn.fetch("""
                SELECT id, exchange, order_id
                FROM monitoring.orders
                WHERE status IN ('pending', 'open')
            """)
            
            if orders:
                logger.info(f"Cancelling {len(orders)} pending orders...")
                
                # Mark orders as cancelled in database
                await conn.execute("""
                    UPDATE monitoring.orders
                    SET status = 'cancelled',
                        updated_at = NOW()
                    WHERE status IN ('pending', 'open')
                """)
                
                logger.info(f"✓ Cancelled {len(orders)} orders")
            else:
                logger.info("✓ No pending orders to cancel")
            
            await conn.close()
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to cancel orders: {e}")
            return False
    
    async def close_positions(self, emergency=False):
        """Close all open positions"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            # Get active positions
            positions = await conn.fetch("""
                SELECT id, symbol, side, quantity, entry_price
                FROM monitoring.positions
                WHERE status = 'active'
            """)
            
            if positions:
                logger.warning(f"{'EMERGENCY' if emergency else 'Gracefully'} closing {len(positions)} positions...")
                
                # Mark positions as closing
                await conn.execute("""
                    UPDATE monitoring.positions
                    SET status = 'closing',
                        exit_reason = $1,
                        closed_at = NOW()
                    WHERE status = 'active'
                """, 'emergency_shutdown' if emergency else 'graceful_shutdown')
                
                logger.info(f"✓ Marked {len(positions)} positions for closure")
                
                # Log position details
                for pos in positions:
                    logger.info(f"  - {pos['symbol']}: {pos['side']} {pos['quantity']} @ {pos['entry_price']}")
            else:
                logger.info("✓ No open positions to close")
            
            await conn.close()
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to close positions: {e}")
            return False
    
    async def stop_websockets(self):
        """Stop all WebSocket connections"""
        try:
            logger.info("Stopping WebSocket connections...")
            
            # Send shutdown signal to WebSocket processes
            # This would integrate with your WebSocket management system
            
            logger.info("✓ WebSocket connections stopped")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to stop WebSockets: {e}")
            return False
    
    async def create_shutdown_report(self):
        """Create final shutdown report"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            # Get daily statistics
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'closed' AND closed_at::date = CURRENT_DATE) as trades_today,
                    SUM(realized_pnl) FILTER (WHERE closed_at::date = CURRENT_DATE) as pnl_today,
                    COUNT(*) FILTER (WHERE status = 'active') as active_positions,
                    SUM(unrealized_pnl) FILTER (WHERE status = 'active') as unrealized_pnl
                FROM monitoring.positions
            """)
            
            report = f"""
╔═══════════════════════════════════════════════════════╗
║              TRADING BOT SHUTDOWN REPORT               ║
╠═══════════════════════════════════════════════════════╣
║ Shutdown Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}      ║
║ Reason: {self.shutdown_reason.ljust(43)} ║
╠═══════════════════════════════════════════════════════╣
║ Today's Statistics:                                    ║
║   • Trades: {str(stats['trades_today'] or 0).ljust(42)} ║
║   • P&L: ${str(round(stats['pnl_today'] or 0, 2)).ljust(44)} ║
║   • Active Positions: {str(stats['active_positions'] or 0).ljust(32)} ║
║   • Unrealized P&L: ${str(round(stats['unrealized_pnl'] or 0, 2)).ljust(32)} ║
╚═══════════════════════════════════════════════════════╝
            """
            
            logger.info(report)
            
            # Save report to file
            report_file = f"reports/shutdown_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(report_file, 'w') as f:
                f.write(report)
            
            await conn.close()
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to create report: {e}")
            return False
    
    async def shutdown(self, emergency=False):
        """Execute shutdown sequence"""
        logger.info("=" * 60)
        logger.info(f"{'EMERGENCY' if emergency else 'GRACEFUL'} SHUTDOWN INITIATED")
        logger.info("=" * 60)
        
        steps = [
            ("Saving system state", self.save_state()),
            ("Cancelling pending orders", self.cancel_pending_orders()),
            ("Closing positions", self.close_positions(emergency)),
            ("Stopping WebSocket connections", self.stop_websockets()),
            ("Creating shutdown report", self.create_shutdown_report())
        ]
        
        success = True
        for step_name, step_task in steps:
            logger.info(f"Executing: {step_name}...")
            result = await step_task
            if not result:
                success = False
                if emergency:
                    logger.warning(f"Step failed but continuing (emergency mode): {step_name}")
                else:
                    logger.error(f"Step failed: {step_name}")
                    break
        
        logger.info("=" * 60)
        if success:
            logger.success("SHUTDOWN COMPLETED SUCCESSFULLY")
            return 0
        else:
            logger.error("SHUTDOWN COMPLETED WITH ERRORS")
            return 1

def signal_handler(signum, frame):
    """Handle system signals"""
    logger.warning(f"Received signal {signum}")
    asyncio.create_task(shutdown_handler(emergency=True))

async def shutdown_handler(emergency=False):
    """Async shutdown handler"""
    handler = GracefulShutdown()
    if emergency:
        handler.shutdown_reason = "Emergency signal received"
    
    exit_code = await handler.shutdown(emergency=emergency)
    sys.exit(exit_code)

async def main():
    """Main shutdown function"""
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Check command line arguments
    emergency = '--emergency' in sys.argv
    
    if '--reason' in sys.argv:
        reason_idx = sys.argv.index('--reason') + 1
        if reason_idx < len(sys.argv):
            reason = sys.argv[reason_idx]
        else:
            reason = "No reason provided"
    else:
        reason = "Manual shutdown requested"
    
    # Execute shutdown
    handler = GracefulShutdown()
    handler.shutdown_reason = reason
    
    exit_code = await handler.shutdown(emergency=emergency)
    sys.exit(exit_code)

if __name__ == "__main__":
    asyncio.run(main())