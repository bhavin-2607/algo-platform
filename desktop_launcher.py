#!/usr/bin/env python3
"""Algo Platform - Native Standalone Desktop Executable Launcher."""

import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from launcher.app import main

if __name__ == "__main__":
    main()
