"""Lantern Isle server tests (PROTOCOL.md v1).

Starts its own server.py on a spare port, so the live world is never touched.
Run: python3 tests.py
"""
import os
import socket
import subprocess
import sys
import time
import unittest

from bot import Conn

HERE = os.path.dirname(os.path.abspath(__file__))
WALK = set(".=*L")


def free_port():
    s = socket.socket()
    s.bind(("localhost", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        env = dict(os.environ, AAL_LAN_PORT=str(cls.port))
        cls.proc = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], cwd=HERE, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.time() + 6
        while time.time() < end:
            try:
                socket.create_connection(("localhost", cls.port), timeout=0.3).close()
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.proc.kill()

    def join(self, side, name=None):
        c = Conn("localhost", self.port, side, name=name)
        w = c.wait_for(lambda m: m.get("t") == "welcome", 4)
        self.assertIsNotNone(w, f"{side}: no welcome")
        return c, w

    def test_welcome_shape(self):
        c, w = self.join("p1", "Laptop")
        try:
            self.assertEqual(w["side"], "p1")
            self.assertEqual((w["w"], w["h"]), (40, 20))
            self.assertEqual(len(w["tiles"]), 20)
            self.assertTrue(all(len(r) == 40 for r in w["tiles"]))
            self.assertIn("chat", w)
            self.assertIn("players", w)
        finally:
            c.close()

    def test_three_sides_and_chat_reaches_everyone(self):
        cs = [self.join(s)[0] for s in ("p1", "p2", "p3")]
        try:
            cs[2].send({"t": "chat", "text": "hello from three"})
            for c in cs:
                m = c.wait_for(lambda m: m.get("t") == "chat" and m.get("text") == "hello from three", 3)
                self.assertIsNotNone(m, f"{c.side} did not get the chat")
                self.assertEqual(m["from"], "p3")
        finally:
            for c in cs:
                c.close()

    def test_chat_is_capped(self):
        c, _ = self.join("p2")
        try:
            c.send({"t": "chat", "text": "x" * 500})
            m = c.wait_for(lambda m: (m.get("t") == "chat" and m.get("from") == "p2") or m.get("t") == "err", 3)
            self.assertIsNotNone(m)
            if m["t"] == "chat":
                self.assertLessEqual(len(m["text"]), 200)
        finally:
            c.close()

    def test_move_changes_position_or_is_blocked(self):
        c, w = self.join("p1")
        try:
            before = w["players"]["p1"]
            moved = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c.send({"t": "move", "dx": dx, "dy": dy})
                m = c.wait_for(lambda m: m.get("t") == "state" and (m["players"]["p1"]["x"], m["players"]["p1"]["y"]) != (before["x"], before["y"]), 1.0)
                if m:
                    p = m["players"]["p1"]
                    self.assertEqual(abs(p["x"] - before["x"]) + abs(p["y"] - before["y"]), 1)
                    moved = True
                    break
            self.assertTrue(moved, "no direction was walkable from spawn")
        finally:
            c.close()

    def test_bad_move_is_rejected_not_fatal(self):
        c, _ = self.join("p3")
        try:
            c.send({"t": "move", "dx": 5, "dy": 0})
            c.send({"t": "ping"})
            self.assertIsNotNone(c.wait_for(lambda m: m.get("t") == "pong", 3), "server stopped answering after a bad move")
        finally:
            c.close()

    def test_place_and_erase_near_player(self):
        c, w = self.join("p2")
        try:
            me = w["players"]["p2"]
            x, y = me["x"] + 1, me["y"]
            if x >= 40:
                x = me["x"] - 1
            c.send({"t": "place", "x": x, "y": y, "tile": "L"})
            m = c.wait_for(lambda m: m.get("t") == "tile" and (m["x"], m["y"]) == (x, y), 3)
            self.assertIsNotNone(m, "place produced no tile message")
            self.assertEqual(m["tile"], "L")
            self.assertEqual(m["by"], "p2")
            c.send({"t": "place", "x": x, "y": y, "tile": "."})
            m = c.wait_for(lambda m: m.get("t") == "tile" and (m["x"], m["y"]) == (x, y), 3)
            self.assertIsNotNone(m)
            self.assertEqual(m["tile"], ".")
        finally:
            c.close()

    def test_place_far_away_is_rejected(self):
        c, w = self.join("p1")
        try:
            me = w["players"]["p1"]
            x = 39 if me["x"] < 20 else 0
            y = 19 if me["y"] < 10 else 0
            c.send({"t": "place", "x": x, "y": y, "tile": "#"})
            m = c.wait_for(lambda m: m.get("t") in ("err", "tile"), 2)
            self.assertTrue(m is None or m["t"] == "err", "a tile far from the player was placed")
        finally:
            c.close()

    def test_emote_and_ping(self):
        c, _ = self.join("p3")
        try:
            c.send({"t": "emote", "e": "wave"})
            m = c.wait_for(lambda m: m.get("t") == "state" and m["players"].get("p3", {}).get("emote") == "wave", 3)
            self.assertIsNotNone(m, "emote not shown in state")
            c.send({"t": "ping"})
            self.assertIsNotNone(c.wait_for(lambda m: m.get("t") == "pong", 3))
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
