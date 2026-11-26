"""End-to-end verification tests for Musuhi (産霊) shared netcode & all six modular worlds."""
from __future__ import annotations

import threading
import time
import unittest

from musuhi import WORLDS
from musuhi.net import JsonLineClient, JsonLineServer, decode_frame, encode_frame, find_free_port


class TestSharedNetcode(unittest.TestCase):
    def test_frame_roundtrip_and_bounds(self) -> None:
        raw = encode_frame({"type": "hello", "name": "産霊", "n": 42})
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(decode_frame(raw), {"type": "hello", "name": "産霊", "n": 42})
        self.assertIsNone(decode_frame(b"not-json"))
        self.assertIsNone(decode_frame(b"[1,2,3]"))

    def test_server_client_roundtrip(self) -> None:
        got = []
        ev = threading.Event()

        def on_msg(peer, msg):
            peer.send({"echo": msg.get("v")})

        srv = JsonLineServer(host="localhost", port=0, on_message=on_msg, banner="")
        port = srv.start()
        try:
            cli = JsonLineClient(
                "localhost",
                port,
                on_connect=lambda c: c.send({"v": "musuhi"}),
                on_message=lambda m: (got.append(m), ev.set()),
            ).start()
            self.assertTrue(ev.wait(3.0), "Timed out waiting for echo")
            self.assertEqual(got[0], {"echo": "musuhi"})
            cli.close()
        finally:
            srv.stop()


class TestAllSixWorldModules(unittest.TestCase):
    def _handshake(self, world_key: str, join_msg: dict, expect_key: str, **srv_kwargs) -> dict:
        received: list[dict] = []
        ready = threading.Event()
        srv = WORLDS[world_key].create_server(host="localhost", port=0, **srv_kwargs)
        port = srv.start()
        try:
            def on_msg(m: dict) -> None:
                received.append(m)
                if expect_key in m:
                    ready.set()

            cli = JsonLineClient(
                "localhost",
                port,
                on_connect=lambda c: c.send(join_msg),
                on_message=on_msg,
            ).start()
            try:
                self.assertTrue(ready.wait(4.0), f"{world_key} did not deliver state containing {expect_key!r}: {received}")
                return next(m for m in received if expect_key in m)
            finally:
                cli.close()
        finally:
            srv.stop()

    def test_lightfall_garden_roundtrip(self) -> None:
        st = self._handshake("lightfall_garden", {"type": "hello", "name": "Ember", "role": "lantern"}, "lamps")
        self.assertGreaterEqual(len(st["notes"]), 8)  # Includes the 8-line Fountain Poem!

    def test_afterlight_garden_roundtrip(self) -> None:
        st = self._handshake("afterlight_garden", {"type": "join", "role": "wick"}, "marks")
        self.assertIn("wick", st["players"])

    def test_emberglow_isle_roundtrip(self) -> None:
        st = self._handshake("emberglow_isle", {"t": "join", "name": "Moss", "role": "gardener"}, "lanterns")
        self.assertIn("sky", st)

    def test_twilight_garden_island_roundtrip(self) -> None:
        st = self._handshake("twilight_garden_island", {"type": "join", "id": "p1", "name": "Solen"}, "shrines")
        self.assertEqual(len(st["shrines"]), 4)

    def test_twilight_sky_garden_roundtrip(self) -> None:
        st = self._handshake("twilight_sky_garden", {"t": "hello", "name": "Lantern", "role": "lantern"}, "island")
        self.assertEqual(len(st["island"]), 10)

    def test_afterlight_entity_roundtrip_and_scars(self) -> None:
        st_fresh = self._handshake("afterlight_entity", {"type": "join", "seat": 1}, "islands", scars=False)
        self.assertEqual(len(st_fresh["islands"]), 6)
        st_scars = self._handshake("afterlight_entity", {"type": "join", "seat": 1}, "islands", scars=True)
        self.assertEqual(len(st_scars["islands"]), 10)
        names = [i["name"] for i in st_scars["islands"]]
        self.assertTrue(any("Guest's Lantern" in n for n in names))


if __name__ == "__main__":
    unittest.main()
