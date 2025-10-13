#!/usr/bin/env python3
"""
Полный анализ логов торгового бота за 8+ часов работы
"""

import re
from collections import defaultdict
from datetime import datetime

# Читаем лог
with open('logs/trading_bot.log', 'r') as f:
    lines = f.readlines()

print("="*80)
print("📊 ПОЛНЫЙ АНАЛИЗ ЛОГОВ ТОРГОВОГО БОТА")
print("="*80)
print()

# Временной диапазон
first_line = lines[0]
last_line = lines[-1]
start_time = first_line.split()[0] + " " + first_line.split()[1].split(',')[0]
end_time = last_line.split()[0] + " " + last_line.split()[1].split(',')[0]

print(f"📅 Период работы:")
print(f"   Начало: {start_time}")
print(f"   Конец:  {end_time}")
print(f"   Строк в логе: {len(lines):,}")
print()

# ==================== 1. АНАЛИЗ ВОЛН ====================
print("="*80)
print("1️⃣ АНАЛИЗ ВОЛН")
print("="*80)
print()

waves = []
wave_signals = {}
for line in lines:
    if '🌊 Starting wave processing' in line:
        match = re.search(r'(\d+) signals at timestamp (\S+)', line)
        if match:
            signal_count = int(match.group(1))
            timestamp = match.group(2)
            wave_time = line.split()[0] + " " + line.split()[1].split(',')[0]
            waves.append({
                'time': wave_time,
                'timestamp': timestamp,
                'signals': signal_count
            })
            wave_signals[timestamp] = signal_count

total_waves = len(waves)
total_signals = sum(w['signals'] for w in waves)

print(f"📈 Всего волн обработано: {total_waves}")
print(f"📊 Всего сигналов: {total_signals}")
print(f"📊 Среднее сигналов на волну: {total_signals/total_waves:.1f}")
print()

# Распределение по количеству сигналов
signal_distribution = defaultdict(int)
for w in waves:
    signal_distribution[w['signals']] += 1

print("Распределение волн по количеству сигналов:")
for sig_count in sorted(signal_distribution.keys()):
    print(f"   {sig_count} сигналов: {signal_distribution[sig_count]} волн")
print()

# Последние 10 волн
print("Последние 10 волн:")
for w in waves[-10:]:
    print(f"   {w['time']}: {w['signals']} сигналов ({w['timestamp']})")
print()

# ==================== 2. АНАЛИЗ ОТКРЫТЫХ ПОЗИЦИЙ ====================
print("="*80)
print("2️⃣ АНАЛИЗ ОТКРЫТЫХ ПОЗИЦИЙ")
print("="*80)
print()

positions_opened = []
positions_failed = []

for line in lines:
    if '✅ Position opened successfully' in line:
        positions_opened.append(line)
    elif 'position_created:' in line:
        match = re.search(r"'symbol': '(\w+)'.*'exchange': '(\w+)'.*'side': '(\w+)'", line)
        if match:
            positions_opened.append({
                'symbol': match.group(1),
                'exchange': match.group(2),
                'side': match.group(3),
                'time': line.split()[0] + " " + line.split()[1].split(',')[0]
            })
    elif 'Error opening position' in line or 'failed' in line.lower() and 'position' in line.lower():
        positions_failed.append(line)

print(f"✅ Успешно открытых позиций: {len([p for p in positions_opened if isinstance(p, dict)])}")
print(f"❌ Неудачных попыток: {len(positions_failed)}")
print()

# Группировка по биржам
by_exchange = defaultdict(int)
for p in positions_opened:
    if isinstance(p, dict):
        by_exchange[p['exchange']] += 1

print("Позиции по биржам:")
for exchange in sorted(by_exchange.keys()):
    print(f"   {exchange}: {by_exchange[exchange]} позиций")
print()

# Группировка по стороне
by_side = defaultdict(int)
for p in positions_opened:
    if isinstance(p, dict):
        by_side[p['side']] += 1

print("Позиции по направлению:")
for side in sorted(by_side.keys()):
    print(f"   {side}: {by_side[side]} позиций")
print()

# Причины отказов
print("Примеры причин отказа в открытии:")
failure_reasons = defaultdict(int)
for line in positions_failed[:20]:
    if 'Error' in line:
        # Извлекаем причину
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                reason = parts[-1].strip()[:50]
                failure_reasons[reason] += 1

for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"   {reason}: {count} раз")
print()

# ==================== 3. АНАЛИЗ ЗАЩИТЫ STOP-LOSS ====================
print("="*80)
print("3️⃣ АНАЛИЗ ЗАЩИТЫ STOP-LOSS")
print("="*80)
print()

sl_set = []
sl_errors = []
unprotected = []

for line in lines:
    if '✅ Stop-loss set' in line or 'Stop-loss placed successfully' in line:
        sl_set.append(line)
    elif 'Failed to set stop-loss' in line or 'stop-loss' in line.lower() and 'error' in line.lower():
        sl_errors.append(line)
    elif 'CRITICAL: Position without SL' in line or 'unprotected' in line.lower():
        unprotected.append(line)

print(f"✅ Stop-Loss успешно установлено: {len(sl_set)}")
print(f"❌ Ошибок установки SL: {len(sl_errors)}")
print(f"⚠️  Позиций без защиты: {len(unprotected)}")
print()

if sl_errors:
    print("Примеры ошибок SL:")
    for line in sl_errors[:5]:
        error_part = line.split(' - ')[-1].strip()[:80]
        print(f"   {error_part}")
    print()

# Текущие незащищенные позиции
current_unprotected = []
for line in reversed(lines):
    if 'Position without SL' in line and 'closing' not in line.lower():
        current_unprotected.append(line)
        if len(current_unprotected) >= 5:
            break

if current_unprotected:
    print("⚠️  Недавние случаи позиций без SL:")
    for line in current_unprotected:
        print(f"   {line.strip()}")
    print()

# ==================== 4. АНАЛИЗ TRAILING STOP ====================
print("="*80)
print("4️⃣ АНАЛИЗ TRAILING STOP")
print("="*80)
print()

ts_activated = []
ts_sl_updated = []

for line in lines:
    if 'Trailing stop activated' in line or 'TS activated' in line:
        ts_activated.append(line)
    elif 'trailing' in line.lower() and 'updated' in line.lower():
        ts_sl_updated.append(line)
    elif 'Moving stop-loss' in line or 'SL moved' in line:
        ts_sl_updated.append(line)

print(f"🎯 Trailing Stop активировано: {len(ts_activated)}")
print(f"📈 SL обновлено для TS: {len(ts_sl_updated)}")
print()

if ts_activated:
    print("Примеры активации TS:")
    for line in ts_activated[:5]:
        print(f"   {line.strip()}")
    print()

if ts_sl_updated:
    print("Примеры обновления SL при TS:")
    for line in ts_sl_updated[:5]:
        print(f"   {line.strip()}")
    print()

# ==================== 5. АНАЛИЗ AGED ПОЗИЦИЙ ====================
print("="*80)
print("5️⃣ АНАЛИЗ AGED ПОЗИЦИЙ")
print("="*80)
print()

aged_detected = []
aged_closed = []

for line in lines:
    if 'aged position' in line.lower() and 'detected' in line.lower():
        aged_detected.append(line)
    elif 'aged position' in line.lower() and ('clos' in line.lower() or 'exit' in line.lower()):
        aged_closed.append(line)

print(f"⏰ Aged позиций обнаружено: {len(aged_detected)}")
print(f"✅ Aged позиций закрыто: {len(aged_closed)}")
print()

if aged_detected:
    print("Примеры обнаружения aged позиций:")
    for line in aged_detected[:5]:
        print(f"   {line.strip()}")
    print()

if aged_closed:
    print("Примеры закрытия aged позиций:")
    for line in aged_closed[:5]:
        print(f"   {line.strip()}")
    print()

# ==================== 6. КРИТИЧЕСКИЕ ОШИБКИ ====================
print("="*80)
print("6️⃣ КРИТИЧЕСКИЕ ОШИБКИ")
print("="*80)
print()

critical_errors = []
errors = []

for line in lines:
    if 'CRITICAL' in line or 'ERROR' in line:
        if 'CRITICAL' in line:
            critical_errors.append(line)
        else:
            errors.append(line)

print(f"🔴 CRITICAL ошибок: {len(critical_errors)}")
print(f"⚠️  ERROR ошибок: {len(errors)}")
print()

if critical_errors:
    print("CRITICAL ошибки:")
    critical_unique = {}
    for line in critical_errors:
        error_text = line.split(' - ')[-1].strip()[:60]
        critical_unique[error_text] = critical_unique.get(error_text, 0) + 1

    for error, count in sorted(critical_unique.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   [{count}x] {error}")
    print()

# ==================== 7. ИТОГОВАЯ СТАТИСТИКА ====================
print("="*80)
print("7️⃣ ИТОГОВАЯ СТАТИСТИКА")
print("="*80)
print()

print(f"📊 Волны:")
print(f"   Обработано волн: {total_waves}")
print(f"   Всего сигналов: {total_signals}")
print(f"   Среднее сигналов/волну: {total_signals/total_waves:.1f}")
print()

print(f"💼 Позиции:")
opened_count = len([p for p in positions_opened if isinstance(p, dict)])
print(f"   Открыто успешно: {opened_count}")
print(f"   Неудачные попытки: {len(positions_failed)}")
if opened_count > 0:
    success_rate = opened_count / (opened_count + len(positions_failed)) * 100
    print(f"   Success rate: {success_rate:.1f}%")
print()

print(f"🛡️  Stop-Loss:")
print(f"   Установлено: {len(sl_set)}")
print(f"   Ошибок: {len(sl_errors)}")
print(f"   Случаев без защиты: {len(unprotected)}")
print()

print(f"📈 Trailing Stop:")
print(f"   Активировано: {len(ts_activated)}")
print(f"   SL обновлено: {len(ts_sl_updated)}")
print()

print(f"⏰ Aged позиции:")
print(f"   Обнаружено: {len(aged_detected)}")
print(f"   Закрыто: {len(aged_closed)}")
print()

print(f"⚠️  Ошибки:")
print(f"   CRITICAL: {len(critical_errors)}")
print(f"   ERROR: {len(errors)}")
print()

print("="*80)
print("✅ АНАЛИЗ ЗАВЕРШЕН")
print("="*80)
