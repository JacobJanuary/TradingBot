#!/usr/bin/env python3
"""
Тесты для модуля single_instance.

Запуск:
    pytest test_single_instance.py -v
"""

import os
import sys
import time
import pytest
import tempfile
from pathlib import Path
import subprocess
import signal

# Добавляем путь к модулю
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.single_instance import SingleInstance, SingleInstanceError, check_running, kill_running


class TestSingleInstance:
    """Тесты базовой функциональности"""

    def test_basic_lock(self):
        """Тест базовой блокировки"""
        app_id = f"test_app_{os.getpid()}"

        # Первый экземпляр должен получить блокировку
        app1 = SingleInstance(app_id, auto_exit=False)
        assert app1.acquired is True

        # Второй экземпляр не должен получить блокировку
        with pytest.raises(SingleInstanceError):
            app2 = SingleInstance(app_id, auto_exit=False)

        # После освобождения можно получить снова
        app1.release()
        app3 = SingleInstance(app_id, auto_exit=False)
        assert app3.acquired is True
        app3.release()

    def test_context_manager(self):
        """Тест контекстного менеджера"""
        app_id = f"test_ctx_{os.getpid()}"

        # Внутри контекста блокировка активна
        with SingleInstance(app_id, auto_exit=False) as app:
            assert app.acquired is True

            # Второй экземпляр не может получить блокировку
            with pytest.raises(SingleInstanceError):
                SingleInstance(app_id, auto_exit=False)

        # После выхода блокировка освобождена
        app2 = SingleInstance(app_id, auto_exit=False)
        assert app2.acquired is True
        app2.release()

    def test_pid_tracking(self):
        """Тест отслеживания PID"""
        app_id = f"test_pid_{os.getpid()}"

        app = SingleInstance(app_id, auto_exit=False)

        # Проверяем что PID сохранен корректно
        pid = app.get_running_pid()
        assert pid == os.getpid()

        # Проверяем что процесс определяется как живой
        assert app.is_process_running(pid) is True

        # Проверяем что несуществующий PID определяется корректно
        assert app.is_process_running(999999) is False

        app.release()

    def test_stale_lock_cleanup(self):
        """Тест очистки устаревшей блокировки"""
        app_id = f"test_stale_{os.getpid()}"

        # Создаем первый экземпляр
        app1 = SingleInstance(app_id, auto_exit=False)
        pid_file = app1.pid_file

        # Подделываем PID несуществующего процесса
        with open(pid_file, 'w') as f:
            f.write("999999")

        # Освобождаем блокировку вручную (имитация краша)
        app1.lock.release()

        # Новый экземпляр должен определить устаревшую блокировку и очистить ее
        app2 = SingleInstance(app_id, auto_exit=False)
        assert app2.acquired is True

        app2.release()

    def test_timeout(self):
        """Тест таймаута"""
        app_id = f"test_timeout_{os.getpid()}"

        # Первый экземпляр
        app1 = SingleInstance(app_id, auto_exit=False)

        # Второй экземпляр с таймаутом должен бросить исключение
        from filelock import Timeout as FileLockTimeout

        with pytest.raises((SingleInstanceError, FileLockTimeout)):
            app2 = SingleInstance(app_id, timeout=0.1, auto_exit=False)

        app1.release()

    def test_custom_lock_dir(self):
        """Тест пользовательской директории для lock файлов"""
        app_id = f"test_custom_dir_{os.getpid()}"

        with tempfile.TemporaryDirectory() as tmpdir:
            app = SingleInstance(app_id, lock_dir=tmpdir, auto_exit=False)

            # Проверяем что файлы созданы в указанной директории
            assert app.lock_file.parent == Path(tmpdir)
            assert app.lock_file.exists()
            assert app.pid_file.exists()

            app.release()

    def test_info_file(self):
        """Тест файла с информацией о процессе"""
        app_id = f"test_info_{os.getpid()}"

        app = SingleInstance(app_id, auto_exit=False)

        # Проверяем что info файл создан
        assert app.info_file.exists()

        # Проверяем содержимое
        with open(app.info_file, 'r') as f:
            content = f.read()
            assert f"pid={os.getpid()}" in content
            assert "started=" in content
            assert "executable=" in content

        app.release()


class TestCLIFunctions:
    """Тесты CLI функций"""

    def test_check_running(self):
        """Тест проверки запущенного экземпляра"""
        app_id = f"test_check_{os.getpid()}"

        # Изначально не запущено
        assert check_running(app_id) is False

        # Запускаем
        app = SingleInstance(app_id, auto_exit=False)
        assert check_running(app_id) is True

        # Останавливаем
        app.release()
        assert check_running(app_id) is False

    def test_kill_running(self):
        """Тест завершения запущенного экземпляра"""
        app_id = f"test_kill_{os.getpid()}"

        # Создаем дочерний процесс
        script = f"""
import sys
import time
sys.path.insert(0, '{Path(__file__).parent.parent}')
from utils.single_instance import SingleInstance

app = SingleInstance('{app_id}', auto_exit=False)
time.sleep(10)  # Держим блокировку
"""

        # Запускаем процесс
        proc = subprocess.Popen(
            [sys.executable, '-c', script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Даем время на получение блокировки
        time.sleep(0.5)

        # Проверяем что запущен
        assert check_running(app_id) is True

        # Завершаем
        success = kill_running(app_id)
        assert success is True

        # Проверяем что завершен
        time.sleep(0.5)
        assert check_running(app_id) is False

        # Очищаем
        proc.wait(timeout=2)


class TestParallelExecution:
    """Тесты параллельного выполнения"""

    def test_parallel_attempts(self):
        """Тест множественных попыток запуска"""
        app_id = f"test_parallel_{os.getpid()}"

        # Скрипт для дочернего процесса
        script = f"""
import sys
sys.path.insert(0, '{Path(__file__).parent.parent}')
from utils.single_instance import SingleInstance, SingleInstanceError

try:
    app = SingleInstance('{app_id}', auto_exit=False)
    print("ACQUIRED")
    import time
    time.sleep(2)
    app.release()
except SingleInstanceError:
    print("BLOCKED")
    sys.exit(1)
"""

        # Запускаем несколько процессов одновременно
        processes = []
        for _ in range(5):
            proc = subprocess.Popen(
                [sys.executable, '-c', script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            processes.append(proc)

        # Собираем результаты
        results = []
        for proc in processes:
            stdout, _ = proc.communicate(timeout=5)
            output = stdout.decode().strip()
            results.append(output)

        # Только один процесс должен получить блокировку
        acquired_count = results.count("ACQUIRED")
        blocked_count = results.count("BLOCKED")

        assert acquired_count == 1, f"Expected 1 ACQUIRED, got {acquired_count}"
        assert blocked_count == 4, f"Expected 4 BLOCKED, got {blocked_count}"


def test_decorator():
    """Тест использования как декоратора"""
    from utils.single_instance import single_instance

    app_id = f"test_decorator_{os.getpid()}"
    executed = []

    @single_instance(app_id, auto_exit=False)
    def my_function():
        executed.append(True)
        return "success"

    # Первый вызов должен выполниться
    result = my_function()
    assert result == "success"
    assert len(executed) == 1

    # После завершения можно вызвать снова
    result2 = my_function()
    assert result2 == "success"
    assert len(executed) == 2


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v", "--tb=short"])
