"""Vercel 함수: /api/reports — 로직은 livelab/http.py"""
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from livelab.http import make_handler  # noqa: E402


class handler(make_handler(), BaseHTTPRequestHandler):  # Vercel 은 이 이름의 클래스를 찾는다
    pass
