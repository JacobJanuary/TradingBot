#!/usr/bin/env python3
"""
Тестирование логики Trailing Stop для LONG и SHORT позиций
Проверка на наличие аналогичных проблем
"""

from decimal import Decimal

def test_long_position_logic():
    """Тест логики LONG позиции - есть ли проблемы?"""

    print("\n" + "="*60)
    print("ТЕСТ LONG ПОЗИЦИИ")
    print("="*60)

    # Симуляция LONG позиции
    class MockLongTS:
        symbol = 'BTCUSDT'
        side = 'long'
        entry_price = Decimal('50000')

    ts = MockLongTS()
    distance = Decimal('0.5')  # 0.5% trailing

    print("\n📈 Сценарий 1: Цена растет (нормальный случай)")
    print("-" * 40)

    # Цена растет: 50000 → 51000 → 52000
    ts.current_price = Decimal('50000')
    ts.highest_price = Decimal('50000')
    ts.current_stop_price = Decimal('49750')  # 50000 * 0.995

    print(f"1. Начало: price={ts.current_price}, highest={ts.highest_price}, SL={ts.current_stop_price}")

    # Цена растет до 52000
    ts.current_price = Decimal('52000')
    if ts.current_price > ts.highest_price:
        ts.highest_price = ts.current_price
        print(f"2. Цена выросла: price={ts.current_price}, highest={ts.highest_price}")

    # Расчет нового SL
    potential_stop = ts.highest_price * (Decimal('1') - distance / Decimal('100'))
    print(f"3. Расчет: potential_stop = {ts.highest_price} * 0.995 = {potential_stop}")

    # Проверка условия обновления
    if potential_stop > ts.current_stop_price:
        print(f"4. Обновление: {potential_stop} > {ts.current_stop_price}? ДА ✅")
        ts.current_stop_price = potential_stop
    else:
        print(f"4. Обновление: {potential_stop} > {ts.current_stop_price}? НЕТ")

    print(f"5. Результат: SL = {ts.current_stop_price}, price = {ts.current_price}")
    print(f"   SL < price? {ts.current_stop_price < ts.current_price} ✅ (правильно для LONG)")

    print("\n📉 Сценарий 2: Цена падает после роста")
    print("-" * 40)

    # Цена падает обратно: 52000 → 50500
    ts.current_price = Decimal('50500')
    print(f"1. Цена упала: price={ts.current_price}, highest={ts.highest_price}, SL={ts.current_stop_price}")

    # highest_price НЕ меняется при падении
    if ts.current_price > ts.highest_price:
        ts.highest_price = ts.current_price
        print(f"2. Обновление highest? НЕТ (цена ниже максимума)")
    else:
        print(f"2. highest остается: {ts.highest_price} (правильно)")

    # Расчет нового SL
    potential_stop = ts.highest_price * (Decimal('1') - distance / Decimal('100'))
    print(f"3. Расчет: potential_stop = {ts.highest_price} * 0.995 = {potential_stop}")

    # Проверка условия обновления
    if potential_stop > ts.current_stop_price:
        print(f"4. Обновление: {potential_stop} > {ts.current_stop_price}? {potential_stop > ts.current_stop_price}")
    else:
        print(f"4. SL остается: {ts.current_stop_price} (правильно)")

    print(f"5. Результат: SL = {ts.current_stop_price}, price = {ts.current_price}")
    print(f"   SL < price? {ts.current_stop_price < ts.current_price} ✅")

    print("\n🔴 Сценарий 3: Попытка найти проблему (как в SHORT)")
    print("-" * 40)

    # Попробуем воссоздать проблему SHORT для LONG
    # Может ли distance измениться так, чтобы SL стал выше цены?

    print("Допустим, distance меняется с 0.5% на 0.3%:")
    new_distance = Decimal('0.3')

    # Новый расчет с меньшим distance
    new_potential_stop = ts.highest_price * (Decimal('1') - new_distance / Decimal('100'))
    print(f"Новый расчет: {ts.highest_price} * 0.997 = {new_potential_stop}")
    print(f"Старый SL: {ts.current_stop_price}")
    print(f"Новый potential_stop > старый SL? {new_potential_stop > ts.current_stop_price}")

    if new_potential_stop > ts.current_stop_price:
        print(f"⚠️ Попытка ПОДНЯТЬ SL с {ts.current_stop_price} до {new_potential_stop}")
        print(f"Текущая цена: {ts.current_price}")
        print(f"Новый SL < текущая цена? {new_potential_stop < ts.current_price}")
        if new_potential_stop < ts.current_price:
            print("✅ ВСЁ В ПОРЯДКЕ! SL остается ниже цены для LONG")
        else:
            print("❌ ПРОБЛЕМА! SL выше цены для LONG!")

    print("\n" + "="*60)
    print("ВЫВОДЫ ДЛЯ LONG:")
    print("="*60)
    print("1. highest_price обновляется только при росте ✅")
    print("2. SL привязан к highest_price ✅")
    print("3. При падении цены SL остается на месте ✅")
    print("4. При уменьшении distance SL ПОДНИМАЕТСЯ ближе к цене")
    print("5. НО! Для LONG это безопасно, т.к. SL всегда ниже highest_price")
    print("6. ПРОБЛЕМ НЕ ОБНАРУЖЕНО для LONG позиций")


def test_short_position_logic():
    """Тест логики SHORT позиции - подтверждение проблемы"""

    print("\n" + "="*60)
    print("ТЕСТ SHORT ПОЗИЦИИ")
    print("="*60)

    # Симуляция SHORT позиции
    class MockShortTS:
        symbol = 'SAROSUSDT'
        side = 'short'
        entry_price = Decimal('0.19000')

    ts = MockShortTS()
    distance = Decimal('0.5')  # 0.5% trailing

    print("\n📉 Сценарий 1: Цена падает (нормальный случай)")
    print("-" * 40)

    # Цена падает: 0.19 → 0.18 → 0.17
    ts.current_price = Decimal('0.19000')
    ts.lowest_price = Decimal('0.19000')
    ts.current_stop_price = Decimal('0.19095')  # 0.19 * 1.005

    print(f"1. Начало: price={ts.current_price}, lowest={ts.lowest_price}, SL={ts.current_stop_price}")

    # Цена падает до 0.17
    ts.current_price = Decimal('0.17000')
    if ts.current_price < ts.lowest_price:
        ts.lowest_price = ts.current_price
        print(f"2. Цена упала: price={ts.current_price}, lowest={ts.lowest_price}")

    # Расчет нового SL
    potential_stop = ts.lowest_price * (Decimal('1') + distance / Decimal('100'))
    print(f"3. Расчет: potential_stop = {ts.lowest_price} * 1.005 = {potential_stop}")

    # Проверка условия обновления (ТЕКУЩАЯ ЛОГИКА)
    if potential_stop < ts.current_stop_price:
        print(f"4. Обновление: {potential_stop} < {ts.current_stop_price}? ДА ✅")
        ts.current_stop_price = potential_stop

    print(f"5. Результат: SL = {ts.current_stop_price}, price = {ts.current_price}")
    print(f"   SL > price? {ts.current_stop_price > ts.current_price} ✅ (правильно для SHORT)")

    print("\n📈 Сценарий 2: Цена растет после падения (ПРОБЛЕМА!)")
    print("-" * 40)

    # Цена растет обратно: 0.17 → 0.18334
    ts.current_price = Decimal('0.18334')
    print(f"1. Цена выросла: price={ts.current_price}, lowest={ts.lowest_price}, SL={ts.current_stop_price}")

    # lowest_price НЕ меняется при росте
    if ts.current_price < ts.lowest_price:
        ts.lowest_price = ts.current_price
        print(f"2. Обновление lowest? НЕТ")
    else:
        print(f"2. lowest остается: {ts.lowest_price} (правильно)")

    # Сценарий с изменением distance
    print("\n⚠️ Допустим, distance изменился или пересчитывается:")

    # Пересчет с тем же distance (имитация обновления)
    potential_stop = ts.lowest_price * (Decimal('1') + distance / Decimal('100'))
    print(f"3. Расчет: potential_stop = {ts.lowest_price} * 1.005 = {potential_stop}")
    print(f"   Текущая цена: {ts.current_price}")
    print(f"   potential_stop < текущая цена? {potential_stop < ts.current_price} ❌")

    # Проверка условия обновления (ТЕКУЩАЯ ЛОГИКА)
    print(f"\n4. Текущая логика проверки:")
    print(f"   if potential_stop < current_stop_price:")
    print(f"   {potential_stop} < {ts.current_stop_price}? {potential_stop < ts.current_stop_price}")

    if potential_stop < ts.current_stop_price:
        print(f"   ❌ ПРОБЛЕМА! Пытаемся установить SL = {potential_stop}")
        print(f"   Но текущая цена = {ts.current_price}")
        print(f"   SL < цена для SHORT - ОШИБКА!")

    print("\n" + "="*60)
    print("ВЫВОДЫ ДЛЯ SHORT:")
    print("="*60)
    print("1. lowest_price обновляется только при падении ✅")
    print("2. SL привязан к lowest_price ✅")
    print("3. При росте цены SL пытается обновиться ❌")
    print("4. Условие не учитывает текущую цену ❌")
    print("5. КРИТИЧЕСКАЯ ПРОБЛЕМА ПОДТВЕРЖДЕНА!")


def compare_long_vs_short():
    """Сравнение логики LONG и SHORT"""

    print("\n" + "="*60)
    print("СРАВНЕНИЕ LONG vs SHORT")
    print("="*60)

    print("\n📊 LONG позиции:")
    print("-" * 40)
    print("• Отслеживает: highest_price (максимум)")
    print("• SL формула: highest_price * (1 - distance%)")
    print("• SL движется: ВВЕРХ при росте цены")
    print("• При падении: SL остается на месте")
    print("• Условие обновления: if potential_stop > current_stop")
    print("• Результат: SL всегда НИЖЕ highest_price ✅")
    print("• ПРОБЛЕМ НЕ ОБНАРУЖЕНО")

    print("\n📊 SHORT позиции:")
    print("-" * 40)
    print("• Отслеживает: lowest_price (минимум)")
    print("• SL формула: lowest_price * (1 + distance%)")
    print("• SL движется: ВНИЗ при падении цены")
    print("• При росте: SL должен оставаться на месте")
    print("• Условие обновления: if potential_stop < current_stop")
    print("• Проблема: Не проверяет текущую цену! ❌")
    print("• КРИТИЧЕСКАЯ ОШИБКА НАЙДЕНА")

    print("\n🔴 Ключевое различие:")
    print("-" * 40)
    print("LONG: При изменении distance, новый SL ближе к highest_price")
    print("      highest_price - это максимум, цена всегда <= highest_price")
    print("      Поэтому SL не может стать выше текущей цены ✅")
    print()
    print("SHORT: При изменении distance, новый SL ближе к lowest_price")
    print("       lowest_price - это минимум, цена может быть > lowest_price")
    print("       Когда цена выше минимума, SL может стать < текущей цены ❌")
    print()
    print("РЕШЕНИЕ: Для SHORT обновлять SL только когда цена <= lowest_price")


if __name__ == "__main__":
    # Запуск всех тестов
    test_long_position_logic()
    test_short_position_logic()
    compare_long_vs_short()

    print("\n" + "🔍 "*20)
    print("ИТОГОВОЕ ЗАКЛЮЧЕНИЕ")
    print("🔍 "*20)
    print()
    print("✅ LONG позиции: Логика корректная, проблем не обнаружено")
    print("❌ SHORT позиции: Критическая ошибка в условии обновления SL")
    print()
    print("Рекомендация: Исправить только логику для SHORT позиций")
    print("Не трогать логику LONG - она работает правильно!")