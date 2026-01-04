
import sys
import core.stop_loss_manager
import inspect

print("="*60)
print(f"Python Executable: {sys.executable}")
print(f"Core StopLossManager File: {core.stop_loss_manager.__file__}")
print("="*60)

try:
    source = inspect.getsource(core.stop_loss_manager.StopLossManager._set_binance_stop_loss_algo)
    print("Source code of _set_binance_stop_loss_algo loaded in memory:")
    print("-" * 40)
    # Print only lines 50-80 of the method (approx where logic is) or search for 'getattr'
    for line in source.split('\n'):
        if 'algo_method =' in line or 'getattr' in line or 'hasattr' in line:
            print(f">>> {line.strip()}")
    print("-" * 40)
except Exception as e:
    print(f"Could not get source: {e}")

print("="*60)
