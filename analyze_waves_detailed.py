#!/usr/bin/env python3
"""
Детальный анализ волн с момента последнего старта бота
Анализирует каждую волну, каждую позицию, каждую ошибку
"""

import re
from datetime import datetime
from collections import defaultdict

# Читаем лог с последнего старта
with open('logs/trading_bot.log', 'r') as f:
    all_lines = f.readlines()

# Найти последний старт
last_start_idx = None
for i, line in enumerate(all_lines):
    if '🚀 Starting trading bot' in line:
        last_start_idx = i

if last_start_idx is None:
    print("❌ Не найден старт бота")
    exit(1)

lines = all_lines[last_start_idx:]
start_time = lines[0].split()[0] + " " + lines[0].split()[1].split(',')[0]
end_time = lines[-1].split()[0] + " " + lines[-1].split()[1].split(',')[0]

print("="*100)
print("📊 ДЕТАЛЬНЫЙ АНАЛИЗ ВОЛН С ПОСЛЕДНЕГО СТАРТА БОТА")
print("="*100)
print()
print(f"⏰ Период работы:")
print(f"   Старт:  {start_time}")
print(f"   Конец:  {end_time}")
print(f"   Строк:  {len(lines):,}")
print()

# Собираем волны
waves = []
current_wave = None

for i, line in enumerate(lines):
    # Начало волны
    if '🌊 Starting wave processing' in line:
        match = re.search(r'(\d+) signals at timestamp (\S+)', line)
        if match:
            signal_count = int(match.group(1))
            timestamp = match.group(2)
            wave_time = line.split()[0] + " " + line.split()[1].split(',')[0]

            current_wave = {
                'time': wave_time,
                'timestamp': timestamp,
                'total_signals': signal_count,
                'signals': [],
                'positions_opened': [],
                'positions_failed': [],
                'start_line': i
            }
            waves.append(current_wave)

    # Выполнение сигнала
    elif current_wave and '📈 Executing signal' in line:
        match = re.search(r'signal (\d+)/(\d+): (\w+)', line)
        if match:
            sig_num = int(match.group(1))
            total = int(match.group(2))
            symbol = match.group(3)

            # Следующая строка содержит детали
            if i+1 < len(lines):
                next_line = lines[i+1]
                match2 = re.search(r'#(\d+): (\w+) on (\w+) \(week: ([\d.]+), month: ([\d.]+)\)', next_line)
                if match2:
                    current_wave['signals'].append({
                        'num': sig_num,
                        'symbol': symbol,
                        'signal_id': int(match2.group(1)),
                        'exchange': match2.group(3),
                        'week_score': float(match2.group(4)),
                        'month_score': float(match2.group(5)),
                        'status': 'processing'
                    })

    # Успешное открытие позиции
    elif current_wave and 'position_created:' in line:
        match = re.search(r"'symbol': '(\w+)'.*'exchange': '(\w+)'.*'side': '(\w+)'.*'entry_price': ([\d.]+)", line)
        if match:
            symbol = match.group(1)
            exchange = match.group(2)
            side = match.group(3)
            entry_price = float(match.group(4))

            current_wave['positions_opened'].append({
                'symbol': symbol,
                'exchange': exchange,
                'side': side,
                'entry_price': entry_price,
                'time': line.split()[0] + " " + line.split()[1].split(',')[0]
            })

            # Обновить статус сигнала
            for sig in current_wave['signals']:
                if sig['symbol'] == symbol:
                    sig['status'] = 'opened'
                    sig['entry_price'] = entry_price
                    sig['side'] = side

    # Ошибка открытия позиции
    elif current_wave and ('Error opening position' in line or 'Position creation rolled back' in line):
        match = re.search(r'position for (\w+):(.*)', line)
        if match:
            symbol = match.group(1)
            error = match.group(2).strip()

            current_wave['positions_failed'].append({
                'symbol': symbol,
                'error': error[:100],  # Первые 100 символов
                'time': line.split()[0] + " " + line.split()[1].split(',')[0]
            })

            # Обновить статус сигнала
            for sig in current_wave['signals']:
                if sig['symbol'] == symbol:
                    sig['status'] = 'failed'
                    sig['error'] = error[:80]

# Вывод детального анализа
print("="*100)
print(f"📊 ВСЕГО ВОЛН: {len(waves)}")
print("="*100)
print()

total_signals = sum(w['total_signals'] for w in waves)
total_opened = sum(len(w['positions_opened']) for w in waves)
total_failed = sum(len(w['positions_failed']) for w in waves)

print(f"📈 Общая статистика:")
print(f"   Всего сигналов:      {total_signals}")
print(f"   Позиций открыто:     {total_opened}")
print(f"   Позиций НЕ открыто:  {total_failed}")
if total_signals > 0:
    print(f"   Success Rate:        {total_opened/total_signals*100:.1f}%")
print()

# Детальный анализ каждой волны
for wave_num, wave in enumerate(waves, 1):
    print("="*100)
    print(f"🌊 ВОЛНА #{wave_num}")
    print("="*100)
    print()

    print(f"⏰ Время:      {wave['time']}")
    print(f"📅 Timestamp:  {wave['timestamp']}")
    print(f"📊 Сигналов:   {wave['total_signals']}")
    print(f"✅ Открыто:    {len(wave['positions_opened'])}")
    print(f"❌ Отказано:   {len(wave['positions_failed'])}")
    print()

    # Детали по каждому сигналу
    if wave['signals']:
        print(f"📋 ДЕТАЛИ ПО СИГНАЛАМ:")
        print()

        for sig in wave['signals']:
            status_emoji = "✅" if sig['status'] == 'opened' else "❌" if sig['status'] == 'failed' else "⏳"
            print(f"   {status_emoji} Сигнал #{sig['num']}/{wave['total_signals']}: {sig['symbol']}")
            print(f"      ID:       #{sig['signal_id']}")
            print(f"      Биржа:    {sig['exchange']}")
            print(f"      Scores:   week={sig['week_score']}, month={sig['month_score']}")

            if sig['status'] == 'opened':
                print(f"      Статус:   ОТКРЫТА")
                print(f"      Сторона:  {sig.get('side', 'N/A')}")
                print(f"      Цена:     {sig.get('entry_price', 'N/A')}")
            elif sig['status'] == 'failed':
                print(f"      Статус:   ОТКАЗ")
                print(f"      Причина:  {sig.get('error', 'Unknown')}")
            else:
                print(f"      Статус:   {sig['status']}")
            print()

    # Успешные позиции
    if wave['positions_opened']:
        print(f"✅ УСПЕШНО ОТКРЫТЫЕ ПОЗИЦИИ:")
        print()
        for pos in wave['positions_opened']:
            print(f"   • {pos['symbol']} ({pos['exchange']})")
            print(f"     Направление: {pos['side']}")
            print(f"     Entry Price: {pos['entry_price']}")
            print(f"     Время:       {pos['time']}")
            print()

    # Неудачные попытки
    if wave['positions_failed']:
        print(f"❌ НЕУДАЧНЫЕ ПОПЫТКИ:")
        print()
        for fail in wave['positions_failed']:
            print(f"   • {fail['symbol']}")
            print(f"     Ошибка: {fail['error']}")
            print(f"     Время:  {fail['time']}")
            print()

    print()

# Статистика по ошибкам
print("="*100)
print("📊 СТАТИСТИКА ОШИБОК")
print("="*100)
print()

error_types = defaultdict(int)
for wave in waves:
    for fail in wave['positions_failed']:
        error = fail['error']
        # Классифицируем ошибку
        if 'Max positions limit' in error:
            error_types['Max positions limit'] += 1
        elif 'already exists' in error:
            error_types['Position already exists'] += 1
        elif 'Min notional' in error or 'minimum' in error.lower():
            error_types['Minimum order size'] += 1
        elif 'retCode' in error:
            # Извлекаем код ошибки
            match = re.search(r'retCode["\']?:(\d+)', error)
            if match:
                code = match.group(1)
                error_types[f'Bybit error {code}'] += 1
            else:
                error_types['Bybit error (unknown)'] += 1
        elif 'Entry order failed' in error:
            error_types['Entry order failed'] += 1
        else:
            error_types['Other'] += 1

if error_types:
    print("Топ-10 типов ошибок:")
    for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   [{count:3d}x] {error_type}")
    print()
else:
    print("✅ Ошибок не обнаружено!")
    print()

# Статистика по биржам
print("="*100)
print("📊 СТАТИСТИКА ПО БИРЖАМ")
print("="*100)
print()

by_exchange = defaultdict(int)
for wave in waves:
    for pos in wave['positions_opened']:
        by_exchange[pos['exchange']] += 1

if by_exchange:
    for exchange in sorted(by_exchange.keys()):
        print(f"   {exchange}: {by_exchange[exchange]} позиций")
    print()

# Статистика по направлениям
print("="*100)
print("📊 СТАТИСТИКА ПО НАПРАВЛЕНИЯМ")
print("="*100)
print()

by_side = defaultdict(int)
for wave in waves:
    for pos in wave['positions_opened']:
        by_side[pos['side']] += 1

if by_side:
    for side in sorted(by_side.keys()):
        print(f"   {side}: {by_side[side]} позиций")
    print()

# Топ символов
print("="*100)
print("📊 ТОП-10 СИМВОЛОВ")
print("="*100)
print()

symbol_count = defaultdict(int)
for wave in waves:
    for pos in wave['positions_opened']:
        symbol_count[pos['symbol']] += 1

if symbol_count:
    print("Успешно открытые позиции:")
    for symbol, count in sorted(symbol_count.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   {symbol}: {count} раз")
    print()

print("="*100)
print("✅ ДЕТАЛЬНЫЙ АНАЛИЗ ЗАВЕРШЕН")
print("="*100)
