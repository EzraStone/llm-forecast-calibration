"""Pytest path setup: make the repo root importable as `src.*`."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
