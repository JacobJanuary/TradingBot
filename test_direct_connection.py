#!/usr/bin/env python3
"""Direct test of database connection using psql"""
import subprocess
import os
from dotenv import load_dotenv

load_dotenv()

host = os.getenv('DB_HOST')
port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')
user = os.getenv('DB_USER')
password = os.getenv('DB_PASSWORD')

print(f"Testing connection with:")
print(f"Host: {host}")
print(f"Port: {port}")
print(f"Database: {db_name}")
print(f"User: {user}")
print(f"Password: {'*' * len(password) if password else '(empty)'}")

# Set PGPASSWORD environment variable for psql
env = os.environ.copy()
env['PGPASSWORD'] = password

# Test with psql
cmd = f"psql -h {host} -p {port} -U {user} -d {db_name} -c 'SELECT version()'"
print(f"\nRunning: {cmd}")

try:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env, timeout=5)
    if result.returncode == 0:
        print("✅ Connection successful!")
        print(result.stdout)
    else:
        print("❌ Connection failed!")
        print(result.stderr)
except subprocess.TimeoutExpired:
    print("❌ Connection timeout - server might be unreachable")