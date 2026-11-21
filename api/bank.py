"""Vercel 함수: /api/bank — 로직은 livelab/http.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from livelab.http import make_handler  # noqa: E402

handler = make_handler()
