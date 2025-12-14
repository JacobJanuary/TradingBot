#!/usr/bin/env python3
"""
Binance Futures 24h Trading Report

Uses Income API for accurate realized PnL data.
Shows: closed trades, commissions, funding fees, and summary.
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

# Add project root to path
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
        self.income_data = []
        self.trades_data = []
        self.start_ts = 0
        self.end_ts = 0

    async def fetch_income_history(self):
        """Fetch all income records for the period."""
        all_income = []
        params = {"startTime": self.start_ts, "endTime": self.end_ts, "limit": 1000}
        
        while True:
            income = await self.exchange.fapiPrivateGetIncome(params)
            if not income:
                break
            all_income.extend(income)
            if len(income) < 1000:
                break
            last_time = int(income[-1].get('time', 0))
            params['startTime'] = last_time + 1
        
        return all_income

    async def fetch_trades_for_symbol(self, symbol_raw: str):
        """Fetch trades for a symbol using direct API."""
        try:
            params = {
                'symbol': symbol_raw,
                'startTime': self.start_ts,
                'endTime': self.end_ts,
                'limit': 500
            }
            return await self.exchange.fapiPrivateGetUserTrades(params)
        except Exception as e:
            logger.warning(f"Failed to fetch trades for {symbol_raw}: {e}")
            return []

    async def run_analysis(self):
        try:
            now = datetime.now()
            self.end_ts = int(now.timestamp() * 1000)
            self.start_ts = int((now - timedelta(hours=24)).timestamp() * 1000)
            
            print(f"⏱  Период: {(now - timedelta(hours=24)).strftime('%d.%m %H:%M')} - {now.strftime('%d.%m %H:%M')}")
            print()

            print(f"{Fore.CYAN}📊 Загрузка Income History...{Style.RESET_ALL}")
            income_records = await self.fetch_income_history()
            
            if not income_records:
                print(f"{Fore.YELLOW}⚠️ Нет данных за период{Style.RESET_ALL}")
                return
            
            realized_pnl = []
            commissions = []
            funding_fees = []
            symbols = set()
            
            for record in income_records:
                income_type = record.get('incomeType')
                symbol = record.get('symbol', '')
                amount = Decimal(str(record.get('income', 0)))
                time = int(record.get('time', 0))
                dt = datetime.fromtimestamp(time / 1000)
                
                if income_type == 'REALIZED_PNL':
                    realized_pnl.append({'symbol': symbol, 'pnl': amount, 'time': time, 'dt': dt})
                    symbols.add(symbol)
                elif income_type == 'COMMISSION':
                    commissions.append({'symbol': symbol, 'amount': amount, 'time': time})
                elif income_type == 'FUNDING_FEE':
                    funding_fees.append({'symbol': symbol, 'amount': amount, 'time': time})
            
            print(f"   Записей: {len(income_records)} | PnL: {len(realized_pnl)} | Comm: {len(commissions)} | Fund: {len(funding_fees)}")
            print()

            print(f"{Fore.CYAN}📊 Загрузка деталей сделок...{Style.RESET_ALL}")
            
            for symbol_raw in symbols:
                trades = await self.fetch_trades_for_symbol(symbol_raw)
                if trades:
                    for trade in trades:
                        self.trades_data.append({
                            'symbol': symbol_raw,
                            'side': trade.get('side'),
                            'price': Decimal(str(trade.get('price', 0))),
                            'qty': Decimal(str(trade.get('qty', 0))),
                            'realized_pnl': Decimal(str(trade.get('realizedPnl', 0))),
                            'commission': Decimal(str(trade.get('commission', 0))),
                            'time': int(trade.get('time', 0)),
                            'dt': datetime.fromtimestamp(int(trade.get('time', 0)) / 1000)
                        })
                    print(f"   {symbol_raw}: {len(trades)} trades")
            
            self.income_data = {
                'realized_pnl': realized_pnl,
                'commissions': commissions,
                'funding_fees': funding_fees,
                'symbols': symbols
            }
            print()

        finally:
            await self.exchange.close()

    def generate_report(self):
        if not self.income_data:
            print("Нет данных.")
            return

        data = self.income_data
        
        total_pnl = sum(r['pnl'] for r in data['realized_pnl'])
        total_commission = sum(abs(c['amount']) for c in data['commissions'])
        total_funding = sum(f['amount'] for f in data['funding_fees'])
        net_total = total_pnl - total_commission + total_funding
        
        wins = sum(1 for r in data['realized_pnl'] if r['pnl'] > 0)
        losses = sum(1 for r in data['realized_pnl'] if r['pnl'] < 0)
        total_trades = len(data['realized_pnl'])
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        if self.trades_data:
            self.trades_data.sort(key=lambda x: x['time'])
            
            table_rows = []
            for trade in self.trades_data:
                pnl = trade['realized_pnl']
                if pnl == 0:
                    continue
                color = Fore.GREEN if pnl > 0 else Fore.RED
                
                table_rows.append([
                    trade['dt'].strftime('%d.%m %H:%M'),
                    trade['symbol'].replace('USDT', ''),
                    trade['side'],
                    f"{float(trade['price']):.4f}",
                    f"{float(trade['qty']):.4f}",
                    f"{float(trade['commission']):.4f}",
                    f"{color}{float(pnl):+.2f}{Style.RESET_ALL}"
                ])
            
            if table_rows:
                print("=" * 90)
                print("📊 ЗАКРЫТЫЕ СДЕЛКИ (24ч)")
                print("=" * 90)
                
                headers = ["Время", "Symbol", "Side", "Price", "Qty", "Comm", "PnL"]
                if HAS_TABULATE:
                    print(tabulate(table_rows, headers=headers, tablefmt="simple_grid"))
                else:
                    print(" | ".join(headers))
                    print("-" * 90)
                    for row in table_rows:
                        print(" | ".join(str(x) for x in row))
        
        if data['funding_fees']:
            print()
            print("💰 FUNDING FEES:")
            for fee in data['funding_fees'][:5]:
                dt = datetime.fromtimestamp(fee['time'] / 1000)
                color = Fore.GREEN if fee['amount'] > 0 else Fore.RED
                print(f"   {dt.strftime('%H:%M')} | {fee['symbol'].replace('USDT', '')}: {color}{float(fee['amount']):+.4f}{Style.RESET_ALL}")
            if len(data['funding_fees']) > 5:
                print(f"   ... и еще {len(data['funding_fees']) - 5}")

        print()
        print("=" * 50)
        print("📈 ИТОГО (24ч)")
        print("=" * 50)
        color_pnl = Fore.GREEN if total_pnl > 0 else Fore.RED
        color_net = Fore.GREEN if net_total > 0 else Fore.RED
        
        print(f"Realized PnL:    {color_pnl}{float(total_pnl):+.2f} USDT{Style.RESET_ALL}")
        print(f"Комиссии:        {Fore.RED}-{float(total_commission):.2f} USDT{Style.RESET_ALL}")
        print(f"Funding:         {float(total_funding):+.4f} USDT")
        print("-" * 50)
        print(f"NET TOTAL:       {color_net}{float(net_total):+.2f} USDT{Style.RESET_ALL}")
        print("-" * 50)
        print(f"Сделок:          {total_trades} (Win: {Fore.GREEN}{wins}{Style.RESET_ALL} / Loss: {Fore.RED}{losses}{Style.RESET_ALL})")
        print(f"Win Rate:        {win_rate:.1f}%")
        print("=" * 50)
        
        self._save_markdown(data, total_pnl, total_commission, total_funding, net_total, wins, losses, win_rate)

    def _save_markdown(self, data, total_pnl, total_commission, total_funding, net_total, wins, losses, win_rate):
        reports_dir = project_root / "reports"
        reports_dir.mkdir(exist_ok=True)
        filename = reports_dir / f"binance_24h_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.md"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# Binance Futures - Отчет 24ч\n")
            f.write(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            
            f.write("## Итого\n| Параметр | Значение |\n|---|---:|\n")
            f.write(f"| **Net Total** | **{float(net_total):+.2f} USDT** |\n")
            f.write(f"| Realized PnL | {float(total_pnl):+.2f} USDT |\n")
            f.write(f"| Комиссии | -{float(total_commission):.2f} USDT |\n")
            f.write(f"| Funding | {float(total_funding):+.4f} USDT |\n")
            f.write(f"| Win/Loss | {wins}/{losses} |\n")
            f.write(f"| Win Rate | {win_rate:.1f}% |\n\n")
            
            if self.trades_data:
                f.write("## Сделки\n| Время | Symbol | Side | Price | Qty | PnL |\n|---|---|---|---:|---:|---:|\n")
                for trade in sorted(self.trades_data, key=lambda x: x['time']):
                    pnl = trade['realized_pnl']
                    if pnl == 0:
                        continue
                    icon = "🟢" if pnl > 0 else "🔴"
                    f.write(f"| {trade['dt'].strftime('%d.%m %H:%M')} | {trade['symbol'].replace('USDT', '')} | "
                            f"{trade['side']} | {float(trade['price']):.4f} | {float(trade['qty']):.4f} | "
                            f"{icon} {float(pnl):+.2f} |\n")
        
        print(f"\n📄 Отчет: {Fore.CYAN}{filename}{Style.RESET_ALL}")


async def main():
    print()
    print(f"{Fore.CYAN}{'='*50}")
    print("   BINANCE FUTURES - ОТЧЕТ 24Ч")
    print(f"{'='*50}{Style.RESET_ALL}")
    print()
    
    reporter = BinanceReporter()
    await reporter.run_analysis()
    reporter.generate_report()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Прервано")
