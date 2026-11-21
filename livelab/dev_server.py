"""로컬 개발 서버: python -m livelab.dev_server  (127.0.0.1:8787)

Vercel 함수(api/*.py)와 같은 livelab.http 핸들러를 쓴다. 가짜 풀이자로 돌리려면 LIVE_MOCK=1.
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer

from .http import make_handler

HOST, PORT = "127.0.0.1", 8787

if __name__ == "__main__":
    print(f"live lab dev server → http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), make_handler()).serve_forever()
