"""PyInstaller entry point for the frozen desktop build."""

import sys

from needle_factory_sim.app import main

if __name__ == "__main__":
    sys.exit(main())
