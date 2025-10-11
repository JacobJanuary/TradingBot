#!/usr/bin/env python3
"""
Модуль для обеспечения единственного экземпляра приложения.
Использует filelock для кроссплатформенной блокировки.

Features:
- 100% кроссплатформенность (Mac OS, Linux, Windows)
- Автоматическое восстановление после краха
- Проверка валидности PID
- Graceful shutdown
- Подробное логирование
"""

import os
import sys
import time
import atexit
import signal
import logging
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

try:
    from filelock import FileLock, Timeout
    import psutil
except ImportError as e:
    print(f"ERROR: Required dependencies not installed: {e}")
    print("Install with: pip install filelock psutil")
    sys.exit(1)

logger = logging.getLogger(__name__)


class SingleInstanceError(Exception):
    """Raised when another instance is already running"""
    pass


class SingleInstance:
    """
    Защита от множественного запуска приложения.

    Использует filelock для атомарной блокировки и psutil для проверки процессов.

    Usage:
        # Простое использование
        app = SingleInstance('my_app')

        # С контекстным менеджером
        with SingleInstance('my_app'):
            run_application()

        # С обработкой ошибок
        try:
            app = SingleInstance('my_app', timeout=5)
        except SingleInstanceError as e:
            print(f"Cannot start: {e}")
    """

    def __init__(
        self,
        app_id: str = "application",
        timeout: float = 0,
        auto_exit: bool = True,
        lock_dir: Optional[str] = None,
        cleanup_on_exit: bool = True
    ):
        """
        Initialize single instance protection.

        Args:
            app_id: Уникальный идентификатор приложения
            timeout: Время ожидания блокировки в секундах (0 = не ждать)
            auto_exit: Автоматически завершать при невозможности получить блокировку
            lock_dir: Директория для lock файла (None = системная temp)
            cleanup_on_exit: Автоматически освобождать блокировку при выходе
        """
        self.app_id = app_id
        self.timeout = timeout
        self.auto_exit = auto_exit
        self.cleanup_on_exit = cleanup_on_exit

        # Определяем директорию для lock файлов
        if lock_dir:
            self.lock_dir = Path(lock_dir)
        else:
            # Используем системную temp директорию
            import tempfile
            self.lock_dir = Path(tempfile.gettempdir())

        # Создаем директорию если не существует
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        # Пути к файлам
        self.lock_file = self.lock_dir / f"{app_id}.lock"
        self.pid_file = self.lock_dir / f"{app_id}.pid"
        self.info_file = self.lock_dir / f"{app_id}.info"

        # Объект блокировки
        self.lock: Optional[FileLock] = None
        self.acquired = False

        # Автоматическая попытка получить блокировку
        try:
            if not self.acquire():
                if self.auto_exit:
                    logger.error("❌ Another instance is already running")
                    self._show_running_instance_info()
                    sys.exit(1)
                else:
                    raise SingleInstanceError("Another instance is already running")
        except Timeout:
            if self.auto_exit:
                logger.error(f"❌ Failed to acquire lock within {timeout}s")
                self._show_running_instance_info()
                sys.exit(1)
            else:
                raise SingleInstanceError(f"Timeout acquiring lock ({timeout}s)")

    def acquire(self) -> bool:
        """
        Попытка получить блокировку.

        Returns:
            True если блокировка получена, False если уже заблокировано

        Raises:
            Timeout: Если не удалось получить блокировку за timeout секунд
        """
        try:
            # Проверяем существующую блокировку
            if self.lock_file.exists():
                if not self._is_lock_valid():
                    logger.warning("⚠️ Found stale lock file, cleaning up")
                    self._cleanup_stale_lock()

            # Создаем объект блокировки
            self.lock = FileLock(str(self.lock_file), timeout=self.timeout)

            # Пытаемся получить блокировку
            self.lock.acquire(timeout=self.timeout)

            # Сохраняем информацию о процессе
            self._write_pid_file()
            self._write_info_file()

            self.acquired = True

            # Регистрируем обработчики для cleanup
            if self.cleanup_on_exit:
                atexit.register(self.release)
                signal.signal(signal.SIGTERM, self._signal_handler)
                signal.signal(signal.SIGINT, self._signal_handler)

            logger.info(f"✅ Lock acquired for '{self.app_id}' (PID: {os.getpid()})")
            return True

        except Timeout:
            logger.error(f"❌ Lock timeout ({self.timeout}s)")
            raise

        except Exception as e:
            logger.error(f"❌ Failed to acquire lock: {e}", exc_info=True)
            return False

    def release(self):
        """Освобождение блокировки"""
        if not self.acquired:
            return

        try:
            # Освобождаем блокировку
            if self.lock:
                self.lock.release()

            # Удаляем файлы
            self._cleanup_files()

            self.acquired = False
            logger.info(f"✅ Lock released for '{self.app_id}'")

        except Exception as e:
            logger.error(f"Error releasing lock: {e}", exc_info=True)

    def _write_pid_file(self):
        """Записать PID в файл"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            logger.warning(f"Failed to write PID file: {e}")

    def _write_info_file(self):
        """Записать информацию о процессе"""
        try:
            info = {
                'pid': os.getpid(),
                'started': datetime.now().isoformat(),
                'executable': sys.executable,
                'argv': ' '.join(sys.argv),
                'cwd': os.getcwd(),
                'user': os.getenv('USER', os.getenv('USERNAME', 'unknown'))
            }

            with open(self.info_file, 'w') as f:
                for key, value in info.items():
                    f.write(f"{key}={value}\n")
        except Exception as e:
            logger.warning(f"Failed to write info file: {e}")

    def _is_lock_valid(self) -> bool:
        """
        Проверить валидность существующей блокировки.

        Returns:
            True если блокировка валидна (процесс жив), False если устарела
        """
        try:
            # Читаем PID из файла
            pid = self.get_running_pid()
            if pid is None:
                return False

            # Проверяем существование процесса
            return self.is_process_running(pid)

        except Exception as e:
            logger.warning(f"Error checking lock validity: {e}")
            return False

    def get_running_pid(self) -> Optional[int]:
        """
        Получить PID запущенного экземпляра.

        Returns:
            PID процесса или None если не найден
        """
        try:
            if not self.pid_file.exists():
                return None

            with open(self.pid_file, 'r') as f:
                pid_str = f.read().strip()
                return int(pid_str) if pid_str else None

        except (ValueError, FileNotFoundError):
            return None

    def is_process_running(self, pid: int) -> bool:
        """
        Проверить, запущен ли процесс с данным PID.

        Args:
            pid: ID процесса

        Returns:
            True если процесс запущен, False иначе
        """
        try:
            process = psutil.Process(pid)

            # Проверяем что процесс не зомби
            if process.status() == psutil.STATUS_ZOMBIE:
                return False

            # Опционально: проверяем что это наше приложение
            # (раскомментируйте если нужно)
            # cmdline = ' '.join(process.cmdline())
            # if 'main.py' not in cmdline:
            #     return False

            return True

        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            # Процесс существует но нет доступа - считаем что запущен
            return True
        except Exception as e:
            logger.warning(f"Error checking process {pid}: {e}")
            return False

    def _cleanup_stale_lock(self):
        """Удалить устаревшую блокировку"""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
            if self.pid_file.exists():
                self.pid_file.unlink()
            if self.info_file.exists():
                self.info_file.unlink()

            logger.info("Stale lock files cleaned up")
        except Exception as e:
            logger.warning(f"Failed to cleanup stale lock: {e}")

    def _cleanup_files(self):
        """Удалить все файлы блокировки"""
        try:
            for file in [self.pid_file, self.info_file]:
                if file.exists():
                    file.unlink()
        except Exception as e:
            logger.warning(f"Failed to cleanup files: {e}")

    def _show_running_instance_info(self):
        """Показать информацию о запущенном экземпляре"""
        try:
            pid = self.get_running_pid()
            if pid:
                logger.error(f"📍 Running instance PID: {pid}")

                if self.info_file.exists():
                    with open(self.info_file, 'r') as f:
                        logger.error("Instance details:")
                        for line in f:
                            logger.error(f"  {line.strip()}")

                # Дополнительная информация о процессе
                try:
                    process = psutil.Process(pid)
                    logger.error(f"  Process status: {process.status()}")
                    logger.error(f"  CPU: {process.cpu_percent()}%")
                    logger.error(f"  Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB")
                except:
                    pass

            logger.error(f"💡 To force start: rm {self.lock_file}")

        except Exception as e:
            logger.warning(f"Failed to show instance info: {e}")

    def _signal_handler(self, signum, frame):
        """Обработчик сигналов для graceful shutdown"""
        logger.info(f"Received signal {signum}, releasing lock...")
        self.release()
        sys.exit(0)

    def __enter__(self):
        """Контекстный менеджер: вход"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер: выход"""
        self.release()
        return False

    def __del__(self):
        """Деструктор: освобождение блокировки при удалении объекта"""
        if self.acquired:
            self.release()


def single_instance(app_id: str = "application", **kwargs):
    """
    Декоратор для защиты функции от множественного запуска.

    Usage:
        @single_instance('my_app')
        def main():
            run_application()
    """
    def decorator(func: Callable):
        def wrapper(*args, **func_kwargs):
            with SingleInstance(app_id, **kwargs):
                return func(*args, **func_kwargs)
        return wrapper
    return decorator


# CLI утилиты
def check_running(app_id: str) -> bool:
    """
    Проверить, запущено ли приложение.

    Returns:
        True если запущено, False иначе
    """
    import tempfile
    lock_dir = Path(tempfile.gettempdir())
    pid_file = lock_dir / f"{app_id}.pid"

    if not pid_file.exists():
        return False

    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        process = psutil.Process(pid)
        return process.status() != psutil.STATUS_ZOMBIE
    except:
        return False


def kill_running(app_id: str, force: bool = False) -> bool:
    """
    Завершить запущенный экземпляр.

    Args:
        app_id: Идентификатор приложения
        force: Использовать SIGKILL вместо SIGTERM

    Returns:
        True если успешно, False иначе
    """
    import tempfile
    lock_dir = Path(tempfile.gettempdir())
    pid_file = lock_dir / f"{app_id}.pid"

    if not pid_file.exists():
        print(f"Application '{app_id}' is not running")
        return False

    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())

        process = psutil.Process(pid)

        if force:
            process.kill()  # SIGKILL
            print(f"Killed process {pid} (SIGKILL)")
        else:
            process.terminate()  # SIGTERM
            print(f"Terminated process {pid} (SIGTERM)")

            # Ждем завершения
            try:
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                print("Process did not terminate, force killing...")
                process.kill()

        return True

    except psutil.NoSuchProcess:
        print(f"Process not found (stale PID file)")
        # Удаляем устаревший PID файл
        pid_file.unlink()
        return False
    except Exception as e:
        print(f"Error killing process: {e}")
        return False


if __name__ == "__main__":
    # Простой CLI интерфейс
    import argparse

    parser = argparse.ArgumentParser(description="Single Instance Manager")
    parser.add_argument('app_id', help='Application identifier')
    parser.add_argument('--check', action='store_true', help='Check if running')
    parser.add_argument('--kill', action='store_true', help='Kill running instance')
    parser.add_argument('--force', action='store_true', help='Force kill (SIGKILL)')

    args = parser.parse_args()

    if args.check:
        running = check_running(args.app_id)
        print(f"Application '{args.app_id}': {'RUNNING' if running else 'NOT RUNNING'}")
        sys.exit(0 if running else 1)

    elif args.kill:
        success = kill_running(args.app_id, force=args.force)
        sys.exit(0 if success else 1)

    else:
        parser.print_help()
