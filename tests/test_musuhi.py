"""End-to-end verification tests for Musuhi (産霊) shared netcode & all modular worlds."""
from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
import time
import unittest

from musuhi import WORLDS

WORLDS_DIR = Path(__file__).resolve().parent.parent / "musuhi" / "worlds"
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


class TestAllWorldModules(unittest.TestCase):
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


    def _save_copy(self, world_key: str, filename: str) -> str:
        """Copy a world's save into a temp dir so tests load it without ever writing to it."""
        tmp = tempfile.mkdtemp(prefix="musuhi-test-")
        self.addCleanup(shutil.rmtree, tmp, True)
        dst = Path(tmp) / filename
        shutil.copy(WORLDS_DIR / world_key / filename, dst)
        return str(dst)

    def test_night_garden_roundtrip(self) -> None:
        st = self._handshake("night_garden", {"t": "hello", "name": "lantern"}, "seeds")
        self.assertEqual([p["name"] for p in st["players"]], ["lantern"])
        self.assertEqual(st["pond"]["x"], 427)

    def test_memory_stone_garden_roundtrip(self) -> None:
        save = self._save_copy("memory_stone_garden", "garden_save.json")
        st = self._handshake("memory_stone_garden", {"t": "hello", "name": "Lantern", "avatar": "lantern"}, "stones", save_path=save)
        self.assertEqual(len(st["stars"]), 10)
        self.assertGreaterEqual(len(st["stones"]), 1)  # Their memory stones survive

    def test_lantern_isle_campfire_roundtrip(self) -> None:
        save = self._save_copy("lantern_isle_campfire", "world_save.json")
        st = self._handshake("lantern_isle_campfire", {"t": "hello", "name": "Laptop"}, "lanterns", save_path=save)
        self.assertEqual(st["goal"], 20)
        self.assertGreaterEqual(st["lit"], 20)  # Restored lanterns light the whole isle

    def test_lantern_isle_nutmeg_roundtrip(self) -> None:
        save = self._save_copy("lantern_isle_nutmeg", "world.json")
        st = self._handshake("lantern_isle_nutmeg", {"t": "hello", "name": "Bram"}, "critters", save_path=save)
        self.assertEqual(st["critters"][0]["name"], "Nutmeg")
        self.assertGreaterEqual(len(st["sky"]), 1)  # Named stars restored from the save

    def test_lantern_isle_trio_roundtrip(self) -> None:
        st = self._handshake("lantern_isle_trio", {"t": "hello", "side": "p3", "name": "Lilac"}, "tiles")
        self.assertEqual((st["w"], st["h"]), (40, 20))
        chart = __import__("json").loads((WORLDS_DIR / "lantern_isle_trio" / "lantern-chart.json").read_text())
        self.assertEqual(st["tiles"], chart["tiles"])  # The keepers' saved isle, tile for tile

    def test_tidal_lantern_isle_roundtrip(self) -> None:
        st = self._handshake("tidal_lantern_isle", {"t": "hello", "name": "P1"}, "signs")
        save = __import__("json").loads((WORLDS_DIR / "tidal_lantern_isle" / "world_save.json").read_text())
        self.assertEqual(st["tiles"], save["tiles"])  # The keepers' dug channels, tile for tile
        self.assertEqual((st["level"], st["goal"]), (5, 150))
        self.assertGreaterEqual(st["ring"], 5)  # Enough lamps on the Moonwell bank to call the heron
        self.assertIn("IV. Spring Witness", [s["text"] for s in st["signs"]])
        p1 = next(p for p in st["players"] if p["name"] == "P1")
        self.assertEqual((p1["x"], p1["y"], p1["seeds"]), (16, 2, 10))  # P1's pockets restored by name

    def test_tidal_atlas_roundtrip(self) -> None:
        st = self._handshake("tidal_atlas", {"t": "hello", "name": "Amber", "color": "amber"}, "chart")
        self.assertEqual((len(st["chart"]), len(st["chart"][0])), (12, 24))
        self.assertTrue(0.5 <= st["tide"] <= 2.5)
        self.assertEqual(sorted((l["x"], l["y"], l["lit"]) for l in st["lights"]), [(4, 5, False), (19, 6, False)])
        self.assertEqual((st["gardens"], st["notes"]), ([], []))  # A fresh, dark island: no saved state
        self.assertEqual(st["chart"][5][5], "1")  # Amber's first footprint, beside the west light
        self.assertEqual(st["players"][0]["color"], "amber")

    def test_lantern_garden_twostage_roundtrip(self) -> None:
        save = self._save_copy("lantern_garden_twostage", "garden_state.json")
        shipped = (WORLDS_DIR / "lantern_garden_twostage" / "garden_state.json").read_bytes()
        st = self._handshake("lantern_garden_twostage", {"t": "join", "name": "P2"}, "plaques", save_path=save)
        self.assertEqual(len(st["plaques"]), 12)
        texts = {(q["x"], q["y"]): q["text"] for q in st["plaques"]}
        self.assertEqual(texts[(13, 6)], "Borrowed Wick")  # The gardeners' saved garden, plaque for plaque
        self.assertEqual(texts[(4, 6)], "The Absent Gardener")
        self.assertEqual((st["chapter"], st["goal"]), (3, 48))
        self.assertGreaterEqual(st["glow"], 36)  # 37 lanterns lit when they left; the wind may snuff one
        self.assertEqual((WORLDS_DIR / "lantern_garden_twostage" / "garden_state.json").read_bytes(), shipped)

    def test_lantern_garden_quad_roundtrip(self) -> None:
        save = Path(tempfile.mkdtemp(prefix="lantern-garden-")) / "garden_state.json"
        try:
            st = self._handshake("lantern_garden_quad", {"t": "hello", "name": "P4", "shape": "diamond", "color": [190, 130, 255]}, "blooms", save=save)
            words = {b["word"]: b for b in st["blooms"] if b["word"]}
            self.assertEqual([words[w]["x"] < words[n]["x"] for w, n in (("Someone", "left"), ("left", "room"), ("room", "here"))], [True] * 3)  # The arc, read left to right
            self.assertEqual(sorted(words["Before"]["names"])[-2:], ["tA", "tB"])  # The test players, kept
            self.assertEqual([s["name"] for s in st["seeds"]], ["garden"] * 3)  # Three pale seeds still asleep
            me = next(p for p in st["players"] if p["name"] == "P4")
            self.assertEqual((me["x"], me["y"]), (426.0, 224.0))  # The diamond returns where it last stood
            self.assertTrue(save.exists())  # Written down on stop, beside nothing in the repo
        finally:
            shutil.rmtree(save.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
