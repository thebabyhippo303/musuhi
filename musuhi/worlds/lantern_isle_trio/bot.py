"""Headless Lantern Isle bot: connects as one side, walks, chats, and reports what it saw.

Usage: python3 bot.py --side p3 [--port N] [--steps 20] [--say "hello"]
Connects to (AAL_LAN_HOST or localhost, port). Never prints addresses.
"""
import argparse
import json
import os
import random
import socket
import time


class Conn:
    def __init__(self, host, port, side, name=None, timeout=3.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""
        self.side = side
        hello = {"t": "hello", "side": side}
        if name:
            hello["name"] = name
        self.send(hello)

    def send(self, obj):
        self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))

    def recv(self, timeout=3.0):
        """Return the next message, or None after timeout."""
        end = time.time() + timeout
        while b"\n" not in self.buf:
            left = end - time.time()
            if left <= 0:
                return None
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                return None
            if not chunk:
                return None
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def wait_for(self, pred, timeout=3.0):
        """Read until pred(msg) is true; return that message or None."""
        end = time.time() + timeout
        while time.time() < end:
            m = self.recv(end - time.time())
            if m is None:
                return None
            if pred(m):
                return m
        return None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", default="p3")
    ap.add_argument("--port", type=int, default=int(os.environ.get("AAL_LAN_PORT", "18765")))
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--say", default="")
    a = ap.parse_args()
    host = os.environ.get("AAL_LAN_HOST", "localhost")
    c = Conn(host, a.port, a.side, name="Bot")
    w = c.wait_for(lambda m: m.get("t") == "welcome", 4)
    if not w:
        print("no welcome")
        return 1
    print(f"LAN Connected · world {w['w']}x{w['h']} · score {w.get('score')}")
    if a.say:
        c.send({"t": "chat", "text": a.say})
    errs = 0
    for _ in range(a.steps):
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        c.send({"t": "move", "dx": dx, "dy": dy})
        m = c.wait_for(lambda m: m.get("t") in ("state", "err"), 1.0)
        if m and m.get("t") == "err":
            errs += 1
    st = c.wait_for(lambda m: m.get("t") == "state", 2)
    me = (st or {}).get("players", {}).get(a.side, {})
    print(f"after {a.steps} steps: at ({me.get('x')},{me.get('y')}), sparks {me.get('sparks')}, blocked {errs}")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
