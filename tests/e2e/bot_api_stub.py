"""Fake Telegram Bot API for no-network e2e tests: an http.server on 127.0.0.1:<free port>,
run in a background thread. Endpoints: getUpdates, sendMessage, editMessageText,
pinChatMessage, getMe. Every call is recorded as (method, payload) in `.calls`.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class BotApiStub:
    def __init__(self, chat_id: int = 1):
        self.chat_id = chat_id
        self.calls: list[tuple[str, dict]] = []
        self._updates: list[dict] = []
        self._next_update_id = 1
        self._next_message_id = 1
        self._server = HTTPServer(("127.0.0.1", 0), _handler_for(self))
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def enqueue(self, text: str, update_id: int | None = None) -> int:
        uid = self._next_update_id if update_id is None else update_id
        if update_id is None:
            self._next_update_id += 1
        message = {"chat": {"id": self.chat_id}, "text": text, "date": int(time.time()), "message_id": uid}
        self._updates.append({"update_id": uid, "message": message})
        return uid

    def stop(self) -> None:
        self._server.shutdown()

    def handle(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == "getUpdates":
            offset = payload.get("offset", 0)
            return {"ok": True, "result": [u for u in self._updates if u["update_id"] >= offset]}
        if method == "getMe":
            return {"ok": True, "result": {"id": 1, "is_bot": True, "username": "stub_bot"}}
        if method in ("sendMessage", "sendPhoto"):
            msg_id = self._next_message_id
            self._next_message_id += 1
            return {"ok": True, "result": {"message_id": msg_id}}
        if method == "editMessageText":
            return {"ok": True, "result": {"message_id": payload.get("message_id")}}
        if method in ("pinChatMessage", "setMessageReaction", "sendChatAction"):
            return {"ok": True, "result": True}
        return {"ok": False, "error_code": 404, "description": f"unknown method {method}"}


def _handler_for(stub: BotApiStub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # keep test output quiet

        def do_POST(self):
            method = self.path.rsplit("/", 1)[-1]
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            is_json = self.headers.get("Content-Type", "").startswith("application/json")
            payload = json.loads(raw) if raw and is_json else {"_bytes": len(raw)}
            body = json.dumps(stub.handle(method, payload)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler
