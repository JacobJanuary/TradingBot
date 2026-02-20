#!/usr/bin/env python3
"""
Binance Futures 24h Trading Report

Uses Income API for accurate realized PnL data.
Fetches entry trades (even if opened before 24h) for complete round-trip details.
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = RED = YELLOW = CYAN = WHITE = ""
    class Style:
        RESET_ALL = ""

logging.basicConfig(level=logging.WARNING, format='%(message)s')
logger = logging.getLogger(__name__)

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

if not API_KEY or not API_SECRET:
    print("❌ API keys not found in .env")
    sys.exit(1)


class BinanceReporter:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.income_data = {}
        self.round_trips = []  # Complete round trips with entry/exit
        self.start_ts = 0
        self.end_ts = 0

    async def fetch_income_history(self):
        """Fetch all income records for the 24h period."""
        all_income = []
        params = {"startTime": self.start_ts, "endTime": self.end_ts, "limit": 1000}
        
        while True:
            income = await self.exchange.fapiPrivateGetIncome(params)
            if not income:
                break
            all_income.extend(income)
            if len(income) < 1000:
                break
            params['startTime'] = int(income[-1].get('time', 0)) + 1
        
        return all_income

    async def fetch_all_trades_for_symbol(self, symbol_raw: str, max_days_back: int = 30):
        """Fetch ALL trades for a symbol going back up to max_days_back days.
        Uses 7-day chunks due to Binance API limit.
        """
        all_trades = []
        
        now_ts = self.end_ts
        # Go back in 7-day chunks
        chunk_days = 7
        chunk_ms = chunk_days * 24 * 60 * 60 * 1000
        
        search_end = now_ts
        oldest_ts = int((datetime.now() - timedelta(days=max_days_back)).timestamp() * 1000)
        
        try:
            while search_end > oldest_ts:
                search_start = max(search_end - chunk_ms, oldest_ts)
                
                params = {
                    'symbol': symbol_raw,
                    'startTime': search_start,
                    'endTime': search_end,
                    'limit': 1000
                }
                
                trades = await self.exchange.fapiPrivateGetUserTrades(params)
                if trades:
                    all_trades.extend(trades)
                
                # Move to previous chunk
                search_end = search_start - 1
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.warning(f"Failed to fetch trades for {symbol_raw}: {e}")
        
        return all_trades


    def build_round_trips(self, trades: list, symbol: str):
        """Build complete round trips from trade history using FIFO."""
        if not trades:
            return []
        
        # Sort by time
        trades = sorted(trades, key=lambda x: int(x.get('time', 0)))
        
        open_queue = []  # [{'qty', 'price', 'time', 'side', 'commission'}]
        round_trips = []
        
        for trade in trades:
            side = trade.get('side', '').upper()
            price = Decimal(str(trade.get('price', 0)))
            qty = Decimal(str(trade.get('qty', 0)))
            time_ms = int(trade.get('time', 0))
            dt = datetime.fromtimestamp(time_ms / 1000)
            commission = Decimal(str(trade.get('commission', 0)))
            realized_pnl = Decimal(str(trade.get('realizedPnl', 0)))
            
            # Is this closing an existing position?
            is_closing = False
            # In Binance, if realizedPnl != 0, it ABSOLUTELY is a closing trade.
            if realized_pnl != 0:
                is_closing = True
            # For exact breakeven closes, rely on FIFO queue presence
            elif open_queue and open_queue[0]['side'] != side:
                is_closing = True
            
            if not is_closing:
                # Opening or adding to position
                open_queue.append({
                    'qty': qty, 
                    'price': price, 
                    'time': time_ms, 
                    'dt': dt,
                    'side': side,
                    'commission': commission
                })
            else:
                # Closing position (FIFO)
                qty_to_close = qty
                
                while qty_to_close > Decimal('1e-9') and open_queue:
                    pos = open_queue[0]
                    matched = min(qty_to_close, pos['qty'])
                    
                    # Direction is based on the OPENING queue side
                    direction = 'LONG' if pos['side'] == 'BUY' else 'SHORT'
                    
                    # Duration
                    duration_sec = (time_ms - pos['time']) / 1000
                    duration = self._format_duration(duration_sec)
                    
                    # Only add if closed within our 24h window
                    if time_ms >= self.start_ts:
                        round_trips.append({
                            'symbol': symbol,
                            'direction': direction,
                            'entry_price': pos['price'],
                            'entry_time': pos['dt'],
                            'exit_price': price,
                            'exit_time': dt,
                            'qty': matched,
                            'gross_pnl': realized_pnl * (matched / qty) if qty > 0 else Decimal(0),
                            'commission': pos['commission'] * (matched / pos['qty']) + commission * (matched / qty),
                            'duration': duration,
                            'duration_sec': duration_sec
                        })
                    
                    pos['qty'] -= matched
                    qty_to_close -= matched
                    
                    if pos['qty'] <= Decimal('1e-9'):
                        open_queue.pop(0)
                
                # If there's STILL qty_to_close > 0, it was an "orphan" close.
                # The position was opened BEFORE our 30-day fetch window.
                # We simply discard this remainder to prevent it from mutating 
                # into a phantom open position! (Fixed Phantom OFFSET Bug)
                if qty_to_close > Decimal('1e-9') and time_ms >= self.start_ts:
                    # Optional: Add an "Orphan" record to visualize that it closed.
                    direction = 'LONG' if side == 'SELL' else 'SHORT'
                    round_trips.append({
                        'symbol': symbol,
                        'direction': direction,
                        'entry_price': Decimal(0),
                        'entry_time': dt, # Unknown entry
                        'exit_price': price,
                        'exit_time': dt,
                        'qty': qty_to_close,
                        'gross_pnl': realized_pnl * (qty_to_close / qty) if qty > 0 else Decimal(0),
                        'commission': commission * (qty_to_close / qty),
                        'duration': '???',
                        'duration_sec': 0
                    })
        
        return round_trips

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds/60)}m"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"
        else:
            days = int(seconds / 86400)
            hours = int((seconds % 86400) / 3600)
            return f"{days}d {hours}h"

    async def run_analysis(self):
        try:
            now = datetime.now()
            self.end_ts = int(now.timestamp() * 1000)
            self.start_ts = int((now - timedelta(hours=24)).timestamp() * 1000)
            
            print(f"⏱  Период: {(now - timedelta(hours=24)).strftime('%d.%m %H:%M')} - {now.strftime('%d.%m %H:%M')}")
            print()

            # 1. Fetch Income History to find symbols with activity
            print(f"{Fore.CYAN}📊 Загрузка Income History...{Style.RESET_ALL}")
            income_records = await self.fetch_income_history()
            
            if not income_records:
                print(f"{Fore.YELLOW}⚠️ Нет данных за период{Style.RESET_ALL}")
                return
            
            # Group by type
            realized_pnl = []
            funding_fees = []
            commissions = []
            symbols = set()
            
            for record in income_records:
                income_type = record.get('incomeType')
                symbol = record.get('symbol', '')
                amount = Decimal(str(record.get('income', 0)))
                time = int(record.get('time', 0))
                
                if income_type == 'REALIZED_PNL':
                    realized_pnl.append({'symbol': symbol, 'pnl': amount, 'time': time})
                    symbols.add(symbol)
                elif income_type == 'FUNDING_FEE':
                    funding_fees.append({'symbol': symbol, 'amount': amount, 'time': time})
                elif income_type == 'COMMISSION':
                    commissions.append({'symbol': symbol, 'amount': amount, 'time': time})
            
            print(f"   Закрытых позиций: {len(realized_pnl)} | Funding: {len(funding_fees)} | Комиссий: {len(commissions)}")
            print()

            # 2. For each symbol with closed trades, fetch FULL trade history
            print(f"{Fore.CYAN}📊 Загрузка полной истории сделок (до 30 дней)...{Style.RESET_ALL}")
            
            for symbol_raw in symbols:
                print(f"   {symbol_raw}...", end=" ")
                trades = await self.fetch_all_trades_for_symbol(symbol_raw, max_days_back=30)
                
                if trades:
                    print(f"{len(trades)} trades")
                    round_trips = self.build_round_trips(trades, symbol_raw)
                    self.round_trips.extend(round_trips)
                else:
                    print("0")
            
            # Store all income data perfectly
            self.income_data = {
                'funding_fees': funding_fees,
                'realized_pnl': realized_pnl,
                'commissions': commissions
            }
            
            print()

        finally:
            await self.exchange.close()

    def generate_report(self):
        if not self.round_trips:
            print("Нет закрытых сделок за период.")
            return

        # Sort by exit time
        self.round_trips.sort(key=lambda x: x['exit_time'])
        
        # Calculate exact totals from Binance Income API for 100% precision
        total_pnl = sum(f['pnl'] for f in self.income_data.get('realized_pnl', []))
        total_commission = sum(abs(f['amount']) for f in self.income_data.get('commissions', []))
        total_funding = sum(f['amount'] for f in self.income_data.get('funding_fees', []))
        net_total = total_pnl - total_commission + total_funding
        
        # Calculate win/loss specifically from realized_pnl since FIFO can have orphans
        if self.income_data.get('realized_pnl'):
            wins = sum(1 for f in self.income_data.get('realized_pnl', []) if f['pnl'] > 0)
            losses = sum(1 for f in self.income_data.get('realized_pnl', []) if f['pnl'] < 0)
        else:
            wins = sum(1 for rt in self.round_trips if rt['gross_pnl'] > 0)
            losses = sum(1 for rt in self.round_trips if rt['gross_pnl'] < 0)
        total_trades = len(self.round_trips)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # Print detailed trades table
        print("=" * 120)
        print("📊 ЗАКРЫТЫЕ СДЕЛКИ (24ч) - ПОЛНАЯ ИСТОРИЯ")
        print("=" * 120)
        
        table_rows = []
        for rt in self.round_trips:
            pnl = float(rt['gross_pnl'])
            color = Fore.GREEN if pnl > 0 else Fore.RED
            
            table_rows.append([
                rt['entry_time'].strftime('%d.%m %H:%M'),
                rt['symbol'].replace('USDT', ''),
                rt['direction'],
                f"{float(rt['entry_price']):.5f}",
                rt['exit_time'].strftime('%d.%m %H:%M'),
                f"{float(rt['exit_price']):.5f}",
                f"{float(rt['qty']):.2f}",
                rt['duration'],
                f"{color}{pnl:+.2f}{Style.RESET_ALL}"
            ])
        
        headers = ["Entry", "Symbol", "Dir", "Entry $", "Exit", "Exit $", "Qty", "Duration", "PnL"]
        
        if HAS_TABULATE:
            print(tabulate(table_rows, headers=headers, tablefmt="simple_grid"))
        else:
            print(" | ".join(headers))
            print("-" * 120)
            for row in table_rows:
                print(" | ".join(str(x) for x in row))
        
        # Funding fees
        funding_fees = self.income_data.get('funding_fees', [])
        if funding_fees:
            print()
            print("💰 FUNDING FEES:")
            for fee in funding_fees[:5]:
                dt = datetime.fromtimestamp(fee['time'] / 1000)
                color = Fore.GREEN if fee['amount'] > 0 else Fore.RED
                print(f"   {dt.strftime('%d.%m %H:%M')} | {fee['symbol'].replace('USDT', '')}: {color}{float(fee['amount']):+.4f}{Style.RESET_ALL}")
            if len(funding_fees) > 5:
                print(f"   ... и еще {len(funding_fees) - 5}")

        # Summary
        print()
        print("=" * 60)
        print("📈 ИТОГО (24ч)")
        print("=" * 60)
        
        color_net = Fore.GREEN if net_total > 0 else Fore.RED
        
        print(f"Gross PnL:       {Fore.GREEN if total_pnl > 0 else Fore.RED}{float(total_pnl):+.2f} USDT{Style.RESET_ALL}")
        print(f"Комиссии:        {Fore.RED}-{float(total_commission):.2f} USDT{Style.RESET_ALL}")
        print(f"Funding:         {float(total_funding):+.4f} USDT")
        print("-" * 60)
        print(f"NET TOTAL:       {color_net}{float(net_total):+.2f} USDT{Style.RESET_ALL}")
        print("-" * 60)
        print(f"Сделок:          {total_trades} (Win: {Fore.GREEN}{wins}{Style.RESET_ALL} / Loss: {Fore.RED}{losses}{Style.RESET_ALL})")
        print(f"Win Rate:        {win_rate:.1f}%")
        
        # Avg duration
        if self.round_trips:
            avg_duration = sum(rt['duration_sec'] for rt in self.round_trips) / len(self.round_trips)
            print(f"Avg Duration:    {self._format_duration(avg_duration)}")
        
        print("=" * 60)
        
        self._save_markdown(total_pnl, total_commission, total_funding, net_total, wins, losses, win_rate)

    def _format_duration(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds/60)}m"
        elif seconds < 86400:
            return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"
        else:
            return f"{int(seconds/86400)}d {int((seconds%86400)/3600)}h"

    def _save_markdown(self, total_pnl, total_commission, total_funding, net_total, wins, losses, win_rate):
        reports_dir = project_root / "reports"
        reports_dir.mkdir(exist_ok=True)
        filename = reports_dir / f"binance_24h_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.md"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# Binance Futures - Отчет 24ч\n")
            f.write(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            
            f.write("## Итого\n| Параметр | Значение |\n|---|---:|\n")
            f.write(f"| **Net Total** | **{float(net_total):+.2f} USDT** |\n")
            f.write(f"| Gross PnL | {float(total_pnl):+.2f} USDT |\n")
            f.write(f"| Комиссии | -{float(total_commission):.2f} USDT |\n")
            f.write(f"| Funding | {float(total_funding):+.4f} USDT |\n")
            f.write(f"| Win/Loss | {wins}/{losses} |\n")
            f.write(f"| Win Rate | {win_rate:.1f}% |\n\n")
            
            f.write("## Сделки\n")
            f.write("| Entry | Symbol | Dir | Entry $ | Exit | Exit $ | Qty | Duration | PnL |\n")
            f.write("|---|---|---|---:|---|---:|---:|---|---:|\n")
            
            for rt in self.round_trips:
                pnl = rt['gross_pnl']
                icon = "🟢" if pnl > 0 else "🔴"
                f.write(f"| {rt['entry_time'].strftime('%d.%m %H:%M')} | {rt['symbol'].replace('USDT', '')} | "
                        f"{rt['direction']} | {float(rt['entry_price']):.5f} | {rt['exit_time'].strftime('%d.%m %H:%M')} | "
                        f"{float(rt['exit_price']):.5f} | {float(rt['qty']):.2f} | {rt['duration']} | "
                        f"{icon} {float(pnl):+.2f} |\n")
        
        print(f"\n📄 Отчет: {Fore.CYAN}{filename}{Style.RESET_ALL}")


async def main():
    print()
    print(f"{Fore.CYAN}{'='*60}")
    print("   BINANCE FUTURES - ОТЧЕТ 24Ч (С ПОЛНОЙ ИСТОРИЕЙ)")
    print(f"{'='*60}{Style.RESET_ALL}")
    print()
    
    reporter = BinanceReporter()
    await reporter.run_analysis()
    reporter.generate_report()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Прервано")
