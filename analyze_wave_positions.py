#!/usr/bin/env python3
"""
Анализ: Сколько позиций открывается за волну
"""
import re
from collections import defaultdict
from datetime import datetime

def analyze_waves():
    print("=" * 80)
    print("🔍 ANALYSIS: Positions per wave")
    print("=" * 80)
    print()

    with open('logs/trading_bot.log', 'r') as f:
        lines = f.readlines()

    # Extract position_created events
    positions = []
    for line in lines:
        if 'position_created:' in line:
            # Extract timestamp
            match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if not match:
                continue
            
            timestamp_str = match.group(1)
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            
            # Check if it has symbol (real position) or position_id (confirmation)
            if "'symbol':" in line:
                # Extract symbol
                symbol_match = re.search(r"'symbol': '([^']+)'", line)
                symbol = symbol_match.group(1) if symbol_match else 'UNKNOWN'
                positions.append({
                    'timestamp': timestamp,
                    'type': 'creation',
                    'symbol': symbol,
                    'line': line.strip()
                })
            elif "'position_id':" in line:
                # Extract position_id
                pid_match = re.search(r"'position_id': (\d+)", line)
                pid = pid_match.group(1) if pid_match else 'UNKNOWN'
                positions.append({
                    'timestamp': timestamp,
                    'type': 'confirmation',
                    'position_id': pid,
                    'line': line.strip()
                })

    # Group by minute (wave = same minute)
    waves = defaultdict(lambda: {'creations': [], 'confirmations': []})
    
    for pos in positions:
        wave_key = pos['timestamp'].strftime('%Y-%m-%d %H:%M')
        if pos['type'] == 'creation':
            waves[wave_key]['creations'].append(pos)
        else:
            waves[wave_key]['confirmations'].append(pos)

    # Analyze each wave
    print(f"Найдено волн: {len(waves)}")
    print()

    over_limit_waves = []
    
    for wave_time in sorted(waves.keys()):
        wave = waves[wave_time]
        creations_count = len(wave['creations'])
        confirmations_count = len(wave['confirmations'])
        
        if creations_count > 0:
            if creations_count > 5:
                status = "⚠️  OVER LIMIT!"
                over_limit_waves.append((wave_time, creations_count, wave))
            else:
                status = "✅ OK"
            
            print(f"{wave_time} | Creations: {creations_count:2d} | Confirmations: {confirmations_count:2d} | {status}")

    # Detailed analysis of over-limit waves
    if over_limit_waves:
        print()
        print("=" * 80)
        print("⚠️  WAVES WITH MORE THAN 5 POSITIONS")
        print("=" * 80)
        print()
        
        for wave_time, count, wave in over_limit_waves:
            print(f"🌊 Wave: {wave_time} ({count} positions)")
            print()
            print("Positions:")
            for i, pos in enumerate(wave['creations'], 1):
                print(f"  {i}. {pos['symbol']}")
            print()
    else:
        print()
        print("=" * 80)
        print("✅ ALL WAVES WITHIN LIMIT")
        print("=" * 80)
        print()
        print("Все волны открыли <= 5 позиций")
        print("Лимит работает корректно!")

if __name__ == "__main__":
    analyze_waves()
