#!/usr/bin/env python3
"""
Глубокий анализ волны 14:37:03 для поиска причины
почему выполнено только 2 из 4 сигналов
"""

# Поиск в логах всех ключевых моментов
with open('logs/trading_bot.log', 'r') as f:
    lines = f.readlines()

# Найти участок волны
wave_start = None
wave_end = None

for i, line in enumerate(lines):
    if '14:35:00' in line and 'Looking for wave' in line and '10:15' in line:
        wave_start = i
    if wave_start and '14:38:00' in line:  # Примерно конец волны
        wave_end = i
        break

if not wave_start:
    print("ERROR: Wave not found!")
    exit(1)

print(f"WAVE FOUND: lines {wave_start} to {wave_end}")
print("="*80)

# Анализ: собрать все ключевые события
events = []

for i in range(wave_start, wave_end + 1):
    line = lines[i]

    # Валидация
    if 'Parallel validation complete' in line:
        events.append(('VALIDATION', i, line.strip()))

    # Выполнение сигналов
    if 'Executing signal' in line and '/' in line:
        events.append(('EXEC_START', i, line.strip()))

    # Результаты
    if 'Signal' in line and 'executed' in line:
        events.append(('EXEC_SUCCESS', i, line.strip()))

    if 'Signal' in line and 'failed' in line:
        events.append(('EXEC_FAIL', i, line.strip()))

    # Открытие позиций
    if 'Position #' in line and 'opened' in line:
        events.append(('POSITION_OPENED', i, line.strip()))

    # Завершение волны
    if 'Wave' in line and 'complete:' in line:
        events.append(('WAVE_COMPLETE', i, line.strip()))

print("\nKEY EVENTS:")
print("="*80)
for event_type, line_num, content in events:
    print(f"{event_type:20} Line {line_num:6}: {content[:100]}")

print("\n" + "="*80)
print("ANALYSIS:")
print("="*80)

# Подсчет
validation_count = len([e for e in events if e[0] == 'VALIDATION'])
exec_start_count = len([e for e in events if e[0] == 'EXEC_START'])
exec_success_count = len([e for e in events if e[0] == 'EXEC_SUCCESS'])
exec_fail_count = len([e for e in events if e[0] == 'EXEC_FAIL'])
position_count = len([e for e in events if e[0] == 'POSITION_OPENED'])
wave_complete_count = len([e for e in events if e[0] == 'WAVE_COMPLETE'])

print(f"Validation events:    {validation_count}")
print(f"Execution started:    {exec_start_count}")
print(f"Execution succeeded:  {exec_success_count}")
print(f"Execution failed:     {exec_fail_count}")
print(f"Positions opened:     {position_count}")
print(f"Wave complete events: {wave_complete_count}")

print("\n" + "="*80)
print("HYPOTHESIS:")
print("="*80)

if exec_start_count == 2 and position_count == 1:
    print("✅ CONFIRMED: Only 2 signals were executed (started)")
    print("✅ CONFIRMED: Only 1 position was opened")
    print("❌ PROBLEM: Expected 4 signals to execute (from validation)")
    print("\n🔍 NEXT STEP: Find why final_signals list had only 2 elements")
    print("   instead of 4 after parallel validation")
elif wave_complete_count == 0:
    print("❌ PROBLEM: Wave did not complete normally")
    print("   Missing '🎯 Wave complete:' message")
