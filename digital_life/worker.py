"""Stable process entry point; implementation lives in entrypoints/."""
from digital_life.entrypoints.worker import main

if __name__=='__main__': raise SystemExit(main())
