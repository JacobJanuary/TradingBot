#!/usr/bin/env python3
"""
Runtime signature checker for update_position method
Checks actual signature, parameters, and possible overloading
"""

import inspect
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from database.repository import Repository


def check_signature():
    """Check runtime signature of update_position"""

    print("=" * 80)
    print("RUNTIME SIGNATURE CHECK: Repository.update_position")
    print("=" * 80)

    # Get signature
    sig = inspect.signature(Repository.update_position)

    print(f"\n1. Method Signature:")
    print(f"   {Repository.update_position.__name__}{sig}")

    print(f"\n2. Parameters:")
    for name, param in sig.parameters.items():
        print(f"   - {name}: {param.annotation if param.annotation != inspect.Parameter.empty else 'no annotation'}")
        print(f"     Kind: {param.kind}")
        print(f"     Default: {param.default if param.default != inspect.Parameter.empty else 'no default'}")

    print(f"\n3. Return Type:")
    print(f"   {sig.return_annotation if sig.return_annotation != inspect.Signature.empty else 'no annotation'}")

    # Check for **kwargs
    has_var_keyword = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in sig.parameters.values()
    )
    print(f"\n4. Has **kwargs: {has_var_keyword}")

    # Check method resolution order
    print(f"\n5. Method Resolution Order (MRO):")
    for i, cls in enumerate(Repository.__mro__):
        print(f"   {i}. {cls.__name__}")
        if hasattr(cls, 'update_position') and cls != object:
            method = getattr(cls, 'update_position')
            print(f"      → Has update_position: {method}")

    # Check if method is overridden
    print(f"\n6. Method Owner:")
    method = Repository.update_position
    print(f"   Defined in: {method.__qualname__}")

    # Check docstring
    print(f"\n7. Docstring:")
    if method.__doc__:
        print(f"   {method.__doc__.strip()}")
    else:
        print("   No docstring")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    check_signature()
