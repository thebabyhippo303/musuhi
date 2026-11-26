"""Shared, privacy-safe NDJSON TCP networking for all Musuhi (産霊) worlds.

Design guarantees:
- Strict newline-delimited UTF-8 JSON framing with bounded line lengths.
- Never logs, prints, or broadcasts peer IP addresses, subnets, or hostnames.
- Clean SO_REUSEADDR binding, TCP_NODELAY low-latency delivery, and thread-safe
  broadcasting with graceful shutdown.
- Automatic client reconnection with clean localhost defaults so every world can
  run both solo (localhost) and over a real LAN without environment boilerplate.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
from typing import Any, Callable, Optional

DEFAULT_HOST = "localhost"
DEFAULT_BIND = ""
DEFAULT_PORT = 18765
MAX_LINE_BYTES = 16 * 1024


def encode_frame(obj: dict[str, Any]) -> bytes:
    """Serialize a JSON object as a compact UTF-8 newline-delimited frame."""
    return (json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def decode_frame(raw: bytes) -> Optional[dict[str, Any]]:
    """Decode one NDJSON line into a dict, returning None on invalid input."""
    text = raw.strip()
    if not text or len(text) > MAX_LINE_BYTES:
        return None
    try:
        obj = json.loads(text.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def resolve_endpoint(
    host: Optional[str] = None,
    port: Optional[int] = None,
    *,
    default_host: str = DEFAULT_HOST,
    default_port: int = DEFAULT_PORT,
) -> tuple[str, int]:
    """Resolve client target (host, port) from explicit args -> env -> safe default."""
    resolved_host = host if host is not None else os.environ.get("AAL_LAN_HOST", default_host)
    if not resolved_host:
        resolved_host = default_host
    raw_port = port if port is not None else os.environ.get("AAL_LAN_PORT", str(default_port))
    try:
        resolved_port = int(raw_port)
    except (TypeError, ValueError):
        resolved_port = default_port
    return resolved_host, resolved_port


def resolve_bind_port(port: Optional[int] = None, *, default_port: int = DEFAULT_PORT) -> int:
    """Resolve server bind port from explicit arg -> AAL_LAN_PORT -> default."""
    if port is not None:
        return int(port)
    try:
        return int(os.environ.get("AAL_LAN_PORT", str(default_port)))
    except ValueError:
        return default_port


def find_free_port(host: str = DEFAULT_HOST) -> int:
    """Return an available ephemeral TCP port on host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


class PeerSession:
    """Thread-safe handle representing one connected NDJSON TCP peer."""

    def __init__(self, conn: socket.socket, peer_id: int) -> None:
        self._conn = conn
        self.peer_id = peer_id
        self.meta: dict[str, Any] = {}
        self._send_lock = threading.Lock()
        self._closed = False

    def send(self, obj: dict[str, Any]) -> bool:
        """Send one JSON object frame to this peer. Returns False if disconnected."""
        return self.send_bytes(encode_frame(obj))

    def send_bytes(self, payload: bytes) -> bool:
        with self._send_lock:
            if self._closed:
                return False
            try:
                self._conn.sendall(payload)
                return True
            except OSError:
                self._closed = True
                return False

    def close(self) -> None:
        with self._send_lock:
            self._closed = True
            try:
                self._conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._conn.close()
            except OSError:
                pass


class JsonLineServer:
    """Privacy-safe multi-client NDJSON TCP server shared by all Musuhi worlds."""

    def __init__(
        self,
        host: str = DEFAULT_BIND,
        port: Optional[int] = None,
        *,
        on_connect: Optional[Callable[[PeerSession], None]] = None,
        on_message: Optional[Callable[[PeerSession, dict[str, Any]], None]] = None,
        on_disconnect: Optional[Callable[[PeerSession], None]] = None,
        tick_interval: Optional[float] = None,
        on_tick: Optional[Callable[[], None]] = None,
        banner: str = "Musuhi world server ready.",
    ) -> None:
        self.host = host
        self.requested_port = resolve_bind_port(port) if port is None else int(port)
        self.on_connect = on_connect
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.tick_interval = tick_interval
        self.on_tick = on_tick
        self.banner = banner

        self._sock: Optional[socket.socket] = None
        self._peers: dict[int, PeerSession] = {}
        self._peers_lock = threading.Lock()
        self._next_peer_id = 1
        self._stop_event = threading.Event()
        self._accept_thread: Optional[threading.Thread] = None
        self._tick_thread: Optional[threading.Thread] = None
        self.port: int = self.requested_port

    def start(self) -> int:
        """Bind, listen, and spawn accept + optional tick threads. Returns bound port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.requested_port))
        sock.listen(16)
        sock.settimeout(0.5)
        self._sock = sock
        self.port = int(sock.getsockname()[1])
        self._stop_event.clear()

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

        if self.tick_interval and self.on_tick:
            self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
            self._tick_thread.start()
        return self.port

    def serve_forever(self) -> None:
        """Start listening and block until interrupted or stopped."""
        self.start()
        if self.banner:
            print(self.banner, flush=True)

        def _handle_sig(_signum, _frame):
            self._stop_event.set()

        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, _handle_sig)
            signal.signal(signal.SIGTERM, _handle_sig)

        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(0.25)
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop accepting connections and close all active peers cleanly."""
        self._stop_event.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        with self._peers_lock:
            peers = list(self._peers.values())
            self._peers.clear()
        for peer in peers:
            peer.close()

    def peers(self) -> list[PeerSession]:
        with self._peers_lock:
            return list(self._peers.values())

    def broadcast(self, obj: dict[str, Any]) -> None:
        """Send one JSON object frame to every currently connected peer."""
        payload = encode_frame(obj)
        dead: list[PeerSession] = []
        for peer in self.peers():
            if not peer.send_bytes(payload):
                dead.append(peer)
        for peer in dead:
            peer.close()

    def _tick_loop(self) -> None:
        assert self.tick_interval is not None and self.on_tick is not None
        while not self._stop_event.wait(self.tick_interval):
            try:
                self.on_tick()
            except Exception:
                pass

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            with self._peers_lock:
                pid = self._next_peer_id
                self._next_peer_id += 1
                peer = PeerSession(conn, pid)
                self._peers[pid] = peer
            threading.Thread(target=self._peer_loop, args=(peer, conn), daemon=True).start()

    def _peer_loop(self, peer: PeerSession, conn: socket.socket) -> None:
        try:
            if self.on_connect:
                self.on_connect(peer)
            buf = b""
            conn.settimeout(1.0)
            while not self._stop_event.is_set():
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_LINE_BYTES * 2 and b"\n" not in buf:
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = decode_frame(line)
                    if msg is not None and self.on_message:
                        self.on_message(peer, msg)
        finally:
            with self._peers_lock:
                self._peers.pop(peer.peer_id, None)
            if self.on_disconnect:
                try:
                    self.on_disconnect(peer)
                except Exception:
                    pass
            peer.close()


class JsonLineClient:
    """Auto-reconnecting NDJSON TCP client shared by all Musuhi world GUIs."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        *,
        on_connect: Optional[Callable[["JsonLineClient"], None]] = None,
        on_message: Optional[Callable[[dict[str, Any]], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
        reconnect_delay: float = 1.0,
    ) -> None:
        self.host, self.port = resolve_endpoint(host, port)
        self.on_connect = on_connect
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.reconnect_delay = reconnect_delay

        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.connected = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "JsonLineClient":
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def send(self, obj: dict[str, Any]) -> bool:
        payload = encode_frame(obj)
        with self._lock:
            sock = self._sock
        if sock is None:
            return False
        try:
            sock.sendall(payload)
            return True
        except OSError:
            return False

    def close(self) -> None:
        self._stop_event.set()
        self.connected = False
        with self._lock:
            sock = self._sock
            self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            sock: Optional[socket.socket] = None
            try:
                sock = socket.create_connection((self.host, self.port), timeout=4.0)
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                sock.settimeout(1.0)
                with self._lock:
                    self._sock = sock
                self.connected = True
                if self.on_connect:
                    self.on_connect(self)

                buf = b""
                while not self._stop_event.is_set():
                    try:
                        chunk = sock.recv(65536)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        msg = decode_frame(line)
                        if msg is not None and self.on_message:
                            self.on_message(msg)
            except OSError:
                pass
            finally:
                was_connected = self.connected
                self.connected = False
                with self._lock:
                    if self._sock is sock:
                        self._sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                if was_connected and self.on_disconnect:
                    try:
                        self.on_disconnect()
                    except Exception:
                        pass
            if not self._stop_event.is_set():
                self._stop_event.wait(self.reconnect_delay)
