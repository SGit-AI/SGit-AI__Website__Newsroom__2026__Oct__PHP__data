#!/usr/bin/env python3
"""Kept for the chain's command line: the import is tools/sync_v1.py import (v1 -> here, never over a change made here)."""
import os, subprocess, sys
sys.exit(subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'sync_v1.py'), 'import', *sys.argv[1:]]).returncode)
