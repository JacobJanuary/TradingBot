#!/usr/bin/env python3
"""
Test CryptoManager Random Salt

Проверяет что CryptoManager использует случайный salt, а не фиксированный
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.crypto_manager import CryptoManager


def test_crypto_manager_random_salt():
    """Test that CryptoManager uses random salt"""

    print("="*80)
    print("🔐 CRYPTO MANAGER RANDOM SALT TEST")
    print("="*80)
    print()

    passed = []
    failed = []

    # Clean up any existing salt file for test
    salt_file = Path('.crypto_salt')
    if salt_file.exists():
        salt_file.unlink()
        print("   Removed existing salt file for clean test")

    # Test 1: Generate new CryptoManager
    try:
        cm1 = CryptoManager()
        passed.append("✅ CryptoManager initialized")
    except Exception as e:
        failed.append(f"❌ CryptoManager initialization failed: {e}")
        return False

    # Test 2: Check salt exists
    try:
        if hasattr(cm1, 'salt'):
            passed.append("✅ CryptoManager has salt attribute")
            print(f"   Salt length: {len(cm1.salt)} bytes")
        else:
            failed.append("❌ CryptoManager has NO salt attribute")
    except Exception as e:
        failed.append(f"❌ Salt attribute check failed: {e}")

    # Test 3: Check salt is NOT the old fixed salt
    try:
        fixed_salt = b'trading_bot_salt'
        if cm1.salt != fixed_salt:
            passed.append("✅ Salt is NOT the old fixed value")
        else:
            failed.append("❌ Salt is STILL the old fixed value!")
    except Exception as e:
        failed.append(f"❌ Salt comparison failed: {e}")

    # Test 4: Check salt file was created
    try:
        if salt_file.exists():
            passed.append(f"✅ Salt file created: {salt_file}")
            # Check file size
            size = salt_file.stat().st_size
            print(f"   Salt file size: {size} bytes")
            if size == 16:
                passed.append("✅ Salt file has correct size (16 bytes)")
            else:
                failed.append(f"❌ Salt file has wrong size: {size} bytes (expected 16)")
        else:
            failed.append(f"❌ Salt file NOT created: {salt_file}")
    except Exception as e:
        failed.append(f"❌ Salt file check failed: {e}")

    # Test 5: Check encryption/decryption works
    try:
        plaintext = "test_secret_key_12345"
        encrypted = cm1.encrypt(plaintext)
        decrypted = cm1.decrypt(encrypted)

        if decrypted == plaintext:
            passed.append("✅ Encryption/Decryption works")
            print(f"   Plaintext: {plaintext}")
            print(f"   Encrypted: {encrypted[:50]}...")
            print(f"   Decrypted: {decrypted}")
        else:
            failed.append(f"❌ Decryption mismatch: got '{decrypted}', expected '{plaintext}'")
    except Exception as e:
        failed.append(f"❌ Encryption/Decryption failed: {e}")

    # Test 6: Check salt persistence (reload from file)
    try:
        # Save first salt
        salt1 = cm1.salt

        # Create new CryptoManager instance (should load salt from file)
        cm2 = CryptoManager()
        salt2 = cm2.salt

        if salt1 == salt2:
            passed.append("✅ Salt loaded from file correctly")
        else:
            failed.append("❌ Salt NOT loaded from file (different salt)")
    except Exception as e:
        failed.append(f"❌ Salt persistence test failed: {e}")

    # Test 7: Check randomness (generate two salts and compare)
    try:
        # Remove salt file
        if salt_file.exists():
            salt_file.unlink()

        # Generate first salt
        cm_a = CryptoManager()
        salt_a = cm_a.salt

        # Remove salt file again
        if salt_file.exists():
            salt_file.unlink()

        # Generate second salt
        cm_b = CryptoManager()
        salt_b = cm_b.salt

        if salt_a != salt_b:
            passed.append("✅ Salt is random (different each time)")
        else:
            failed.append("❌ Salt is NOT random (same each time)")
    except Exception as e:
        failed.append(f"❌ Salt randomness test failed: {e}")

    # Results
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)

    if passed:
        print(f"\n✅ PASSED ({len(passed)}):")
        for item in passed:
            print(f"   {item}")

    if failed:
        print(f"\n❌ FAILED ({len(failed)}):")
        for item in failed:
            print(f"   {item}")

    print("\n" + "="*80)
    total = len(passed) + len(failed)
    print(f"TOTAL: {len(passed)}/{total} passed")
    print("="*80)

    # Cleanup
    if salt_file.exists():
        salt_file.unlink()
        print("\n🧹 Cleaned up test salt file")

    return len(failed) == 0


def main():
    success = test_crypto_manager_random_salt()

    if success:
        print("\n✅ CRYPTO MANAGER RANDOM SALT TEST PASSED")
        return 0
    else:
        print("\n❌ CRYPTO MANAGER RANDOM SALT TEST FAILED")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
