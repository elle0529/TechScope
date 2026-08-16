from __future__ import annotations

import os
import selectors
import socket
import socketserver

TARGET_HOST = os.environ["TARGET_HOST"]
TARGET_PORT = int(os.environ.get("TARGET_PORT", "8000"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8000"))


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10)
        try:
            self.request.setblocking(False)
            upstream.setblocking(False)

            sel = selectors.DefaultSelector()
            sel.register(self.request, selectors.EVENT_READ, upstream)
            sel.register(upstream, selectors.EVENT_READ, self.request)

            while True:
                events = sel.select(timeout=60)
                if not events:
                    continue
                for key, _ in events:
                    source = key.fileobj
                    dest = key.data
                    try:
                        data = source.recv(65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        return
                    dest.sendall(data)
        finally:
            upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(("0.0.0.0", LISTEN_PORT), ProxyHandler) as server:
    print(
        f"TECHSCOPE_PROXY=LISTENING port={LISTEN_PORT} "
        f"target={TARGET_HOST}:{TARGET_PORT}",
        flush=True,
    )
    server.serve_forever()
