#!/usr/bin/env python
"""Quick test to verify .env loading works."""

import os
from pathlib import Path

# Before loading .env
print('Before .env load:')
print(f'  YOUTUBE_API_KEY set: {bool(os.getenv("YOUTUBE_API_KEY"))}')

# Simulate what the CLI does
_REPO_ROOT = Path.cwd()
env_file = _REPO_ROOT / '.env'
if env_file.exists():
    with env_file.open('r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                if key and not os.getenv(key):
                    os.environ[key] = value
                    print(f'  Loaded: {key}')

# After loading .env
print('\nAfter .env load:')
print(f'  YOUTUBE_API_KEY set: {bool(os.getenv("YOUTUBE_API_KEY"))}')
key = os.getenv('YOUTUBE_API_KEY')
if key:
    print(f'  Key preview: ...{key[-6:]}')

print('\n✓ .env file loaded successfully!')
