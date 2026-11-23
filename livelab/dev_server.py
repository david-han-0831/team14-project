"""로컬 개발 서버: python -m livelab.dev_server  (127.0.0.1:8787)

Vercel 함수(api/*.py)와 같은 livelab.http 핸들러를 쓴다.
  LIVE_MOCK=1            가짜 풀이자 (API 미사용)
  LIVE_MOCK_DELAY_MS=150 풀이 응답을 늦춰 화면의 진행 표시를 눈으로 확인할 때 (이 서버에서만 동작)
"""
from __future__ import annotations

import os
import time
from http.server import ThreadingHTTPServer

from .http import make_handler

HOST, PORT = "127.0.0.1", 8787


def _handler():
    base = make_handler()
    delay = int(os.environ.get("LIVE_MOCK_DELAY_MS") or 0) / 1000
    if delay <= 0:
        return base

    class Delayed(base):
        def do_POST(self):  # noqa: N802
            time.sleep(delay)
            super().do_POST()

    return Delayed


if __name__ == "__main__":
    print(f"live lab dev server → http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), _handler()).serve_forever()
