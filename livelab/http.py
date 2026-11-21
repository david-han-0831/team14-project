"""HTTP 계층: (method, path, query, body) → (status, dict).

api/*.py (Vercel 함수) 와 livelab/dev_server.py (로컬) 가 같은 handle() 을 부른다.
오류 본문은 항상 {"error": "<문구>"}. 예상 못 한 예외의 원문은 내보내지 않는다.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl, urlsplit

from . import core

MAX_BODY = 4096


def _solve(query: dict, body: bytes) -> dict:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):  # 깊게 중첩된 본문도 400
        raise core.LiveError(400, "요청 본문이 JSON 이 아닙니다") from None
    if not isinstance(data, dict):
        raise core.LiveError(400, "요청 본문 형식이 잘못됐습니다")
    qid, condition = data.get("qid"), data.get("condition")
    if not isinstance(qid, str) or not isinstance(condition, str):
        raise core.LiveError(400, "qid 와 condition 이 필요합니다")
    return core.solve(qid, condition)


ROUTES = {
    "/api/health": ("GET", lambda q, b: core.health()),
    "/api/bank": ("GET", lambda q, b: core.bank(q.get("set", "week09"))),
    "/api/reports": ("GET", lambda q, b: {"reports": core.reports()}),
    "/api/solve": ("POST", _solve),
}


def handle(method: str, path: str, query: dict, body: bytes) -> tuple[int, dict]:
    route = ROUTES.get(path.rstrip("/") or "/")
    if route is None:
        return 404, {"error": "없는 경로입니다"}
    want, fn = route
    if method != want:
        return 405, {"error": "허용되지 않는 메서드입니다"}
    try:
        return 200, fn(query, body)
    except core.LiveError as e:
        return e.status, {"error": e.message}
    except Exception:  # noqa: BLE001  원문은 내보내지 않는다
        return 500, {"error": "서버 오류"}


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _respond(self, method: str):
            url = urlsplit(self.path)
            try:
                length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
            except ValueError:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            status, payload = handle(method, url.path, dict(parse_qsl(url.query)), body)
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            self._respond("GET")

        def do_POST(self):  # noqa: N802
            self._respond("POST")

        def log_message(self, *args):  # 요청 로그를 남기지 않는다
            pass

    return Handler
