import time
import subprocess
import sys
from datetime import datetime

def get_tail(file, lines=100):
    """Get last N lines from file"""
    try:
        result = subprocess.run(['tail', f'-{lines}', file], 
                              capture_output=True, text=True, timeout=5)
        return result.stdout
    except:
        return ""

def monitor():
    """Live monitoring of the bot"""
    print("\n" + "="*80)
    print("📊 LIVE MONITORING - Обновление каждые 15 секунд")
    print("="*80 + "\n")
    
    iteration = 0
    while True:
        iteration += 1
        now = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n🕐 [{now}] Итерация #{iteration}")
        print("-" * 80)
        
        # Проверка процессов
        ps_result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        bot_running = 'main.py --mode production' in ps_result.stdout
        gen_running = 'signal_generator' in ps_result.stdout
        
        print(f"🤖 Бот: {'✅ работает' if bot_running else '❌ остановлен'}")
        print(f"📡 Генератор: {'✅ работает' if gen_running else '❌ остановлен'}")
        
        if not bot_running:
            print("\n❌ БОТ ОСТАНОВЛЕН! Проверьте логи.")
            break
        
        # Последние события
        log = get_tail('tests/integration/bot_test_NEW.log', 200)
        
        # Волны
        waves = [line for line in log.split('\n') if 'Wave detected' in line or 'Wave.*complete' in line]
        if waves:
            print(f"\n🌊 Последняя волна:")
            print(f"   {waves[-1][-100:]}")
        
        # Позиции
        positions_opened = [line for line in log.split('\n') if 'Position opened:' in line]
        if positions_opened:
            recent = positions_opened[-5:]
            print(f"\n📈 Позиции открыто (всего {len(positions_opened)}, последние 5):")
            for pos in recent:
                symbol = pos.split('Position opened:')[1].split()[0] if 'Position opened:' in pos else '?'
                print(f"   • {symbol}")
        
        # SL ордера
        sl_created = len([line for line in log.split('\n') if 'Stop Loss order created' in line])
        sl_cancelled = len([line for line in log.split('\n') if 'Cancelled orphaned order' in line and 'STOP' in line])
        
        print(f"\n🛡️ SL ордера:")
        print(f"   Создано: {sl_created}")
        print(f"   Удалено: {sl_cancelled}")
        print(f"   Активно: {sl_created - sl_cancelled}")
        
        # Ошибки
        errors = [line for line in log.split('\n')[-50:] if 'ERROR' in line or 'Failed to open' in line]
        if errors:
            print(f"\n⚠️ Последние ошибки ({len(errors)}):")
            for err in errors[-3:]:
                print(f"   {err[-100:]}")
        
        # Следующая волна
        waiting = [line for line in log.split('\n') if 'Waiting' in line and 'until next wave' in line]
        if waiting:
            print(f"\n⏰ {waiting[-1].split('INFO - ')[1] if 'INFO - ' in waiting[-1] else waiting[-1][-80:]}")
        
        print("\n" + "="*80)
        print("Press Ctrl+C to stop monitoring")
        print("="*80)
        
        time.sleep(15)

if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n\n✅ Мониторинг остановлен")
        sys.exit(0)
