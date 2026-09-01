#!/usr/bin/env python3
"""CLI entrypoint for the podcast render worker. Logic lives in podcast_lane/.

Usage: python3 podcast_worker.py --limit 10
"""
from podcast_lane.worker import main

if __name__ == "__main__":
    main()
