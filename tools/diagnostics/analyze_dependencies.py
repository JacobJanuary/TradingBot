#!/usr/bin/env python3
"""
Анализ зависимостей между модулями для безопасного рефакторинга

Цель: Понять какие файлы зависят от критичных модулей перед изменениями
"""
import ast
import os
from collections import defaultdict
from pathlib import Path

def analyze_imports(file_path):
    """Получить все импорты из файла"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except Exception as e:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports

def build_dependency_graph():
    """Построить граф зависимостей проекта"""
    project_root = Path('/Users/evgeniyyanvarskiy/PycharmProjects/TradingBot')

    dependencies = defaultdict(list)

    # Список критичных модулей для изменения
    critical_modules = [
        'database/repository.py',
        'database/models.py',
        'core/exchange_manager.py',
        'core/position_manager.py',
        'core/risk_manager.py',
        'utils/crypto_manager.py',
        'utils/decimal_utils.py',
        'protection/stop_loss_manager.py',
        'websocket/signal_client.py',
        'core/aged_position_manager.py',
    ]

    print("="*80)
    print("АНАЛИЗ ЗАВИСИМОСТЕЙ - ГРАФ КРИТИЧНЫХ МОДУЛЕЙ")
    print("="*80)
    print()
    print("Сканирую проект...")

    # Найти все файлы которые импортируют критичные модули
    for py_file in project_root.rglob('*.py'):
        if 'test' in str(py_file) or '.venv' in str(py_file):
            continue

        imports = analyze_imports(py_file)

        for critical in critical_modules:
            module_name = critical.replace('/', '.').replace('.py', '')
            if any(module_name in imp for imp in imports):
                dependencies[critical].append(str(py_file.relative_to(project_root)))

    # Вывести результат
    print("="*80)
    print("ГРАФ ЗАВИСИМОСТЕЙ - КТО ЗАВИСИТ ОТ КРИТИЧНЫХ МОДУЛЕЙ")
    print("="*80)

    total_dependencies = 0

    for module, dependents in sorted(dependencies.items()):
        print(f"\n📦 {module}")
        print(f"   Используется в {len(dependents)} файлах:")
        for dep in sorted(set(dependents))[:10]:  # Первые 10 уникальных
            print(f"   └─ {dep}")
        unique_deps = len(set(dependents))
        if unique_deps > 10:
            print(f"   └─ ... и еще {unique_deps - 10} файлов")
        total_dependencies += unique_deps

    print("\n" + "="*80)
    print(f"ИТОГО: {len(dependencies)} критичных модулей")
    print(f"       {total_dependencies} зависимостей найдено")
    print("="*80)

    return dependencies

def save_to_file(dependencies):
    """Сохранить граф в файл"""
    output_file = Path('DEPENDENCY_GRAPH.txt')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("ГРАФ ЗАВИСИМОСТЕЙ КРИТИЧНЫХ МОДУЛЕЙ\n")
        f.write("="*80 + "\n\n")

        f.write("Дата: 2025-10-09\n")
        f.write("Цель: Понять влияние изменений перед рефакторингом\n\n")

        for module, dependents in sorted(dependencies.items()):
            f.write(f"\n{'='*80}\n")
            f.write(f"МОДУЛЬ: {module}\n")
            f.write(f"{'='*80}\n")
            f.write(f"Используется в {len(set(dependents))} файлах:\n\n")
            for dep in sorted(set(dependents)):
                f.write(f"  - {dep}\n")

        f.write(f"\n{'='*80}\n")
        f.write(f"ИТОГО: {len(dependencies)} критичных модулей проанализировано\n")
        f.write(f"{'='*80}\n")

    print(f"\n✅ Граф сохранен в {output_file}")

def main():
    print("Начинаю анализ зависимостей...\n")

    deps = build_dependency_graph()

    if deps:
        save_to_file(deps)
        print("\n✅ Анализ завершен успешно!")
        print("\nЧто дальше:")
        print("  1. Прочитать DEPENDENCY_GRAPH.txt")
        print("  2. Понять влияние изменений")
        print("  3. Продолжить с Phase 0.2 (Backup)")
        return 0
    else:
        print("\n⚠️ Зависимости не найдены - проверьте критичные модули")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
