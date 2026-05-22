"""Pytest configuration — adds producer/ to sys.path for imports."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
