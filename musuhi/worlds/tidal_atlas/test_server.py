#!/usr/bin/env python3
"""Tests for the Tidal Atlas world rules and the line-JSON socket layer."""
import asyncio
import json
import unittest

import server
from server import World, W, H, TIDE_PERIOD


class WorldRules(unittest.TestCase):
    def setUp(self):
        self.w = World(0.0)
        self.a = self.w.add_player("Teal", "teal")
        self.b = self.w.add_player("Amber", "amber")

    def at(self, pid):
        p = self.w.players[pid]
        return p["x"], p["y"]

    def put(self, pid, x, y):
        self.w.players[pid]["x"], self.w.players[pid]["y"] = x, y

    def test_map_shape_and_connectivity(self):
        self.assertEqual(len(self.w.elev), H)
        self.assertTrue(all(len(r) == W for r in self.w.elev))
        land = {(x, y) for y in range(H) for x in range(W)
                if self.w.elev[y][x] >= 1 and (x, y) not in self.w.lights}
        seen, todo = set(), [server.SPAWNS[0]]
        while todo:
            x, y = todo.pop()
            if (x, y) in seen or (x, y) not in land:
                continue
            seen.add((x, y))
            todo += [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        self.assertEqual(seen, land)
        self.assertGreater(len(land), 80)

    def test_spawns_distinct_and_dry(self):
        self.assertNotEqual(self.at(self.a), self.at(self.b))
        self.w.now = TIDE_PERIOD / 2          # high tide
        for pid in (self.a, self.b):
            self.assertFalse(self.w.flooded(*self.at(pid)))

    def test_move_and_bounds(self):
        x, y = self.at(self.a)
        self.w.now = 1.0
        self.assertTrue(self.w.move(self.a, 1, 0))
        self.assertEqual(self.at(self.a), (x + 1, y))
        self.assertFalse(self.w.move(self.a, 1, 0))   # rate limited
        self.assertFalse(self.w.move(self.a, 0, 0))
        self.assertFalse(self.w.move(self.a, 2, 0))

    def test_lighthouse_is_solid_and_lightable(self):
        lx, ly = server.LIGHTHOUSES[0]
        self.assertEqual(self.at(self.a), (lx + 1, ly))
        self.w.now = 1.0
        self.assertFalse(self.w.move(self.a, -1, 0))
        self.assertTrue(self.w.light(self.a))
        self.assertFalse(self.w.light(self.a))        # already lit
        self.assertTrue(self.w.light(self.b))
        self.assertTrue(all(self.w.lights.values()))

    def test_tide_blocks_dry_feet_but_allows_wading(self):
        flats = [(x, y) for y in range(H) for x in range(W)
                 if self.w.elev[y][x] == 1]
        self.assertTrue(flats)
        fx, fy = next((x, y) for x, y in flats
                      if self.w.elev[y][x + 1] >= 2 or self.w.elev[y][x - 1] >= 2)
        dx = 1 if self.w.elev[fy][fx + 1] >= 2 else -1
        self.w.now = TIDE_PERIOD / 4                  # mid tide 1.5
        self.assertTrue(self.w.flooded(fx, fy))
        self.put(self.a, fx + dx, fy)
        self.assertFalse(self.w.move(self.a, -dx, 0))  # dry -> flooded
        self.put(self.a, fx, fy)
        self.w.now += 1
        self.assertTrue(self.w.move(self.a, dx, 0))    # wade out
        self.w.now = 0.0                               # low tide
        self.w.players[self.a]["last_move"] = -1
        self.assertFalse(self.w.flooded(fx, fy))
        self.assertTrue(self.w.move(self.a, -dx, 0))

    def test_garden_grows_only_when_dry(self):
        self.assertTrue(self.w.plant(self.a))
        self.assertFalse(self.w.plant(self.a))
        for i in range(1, 40):
            self.w.step(i * 1.0)
        g = self.w.snapshot(self.a)["gardens"][0]
        self.assertEqual(g["stage"], 3)
        self.assertEqual(g["owner"], self.a)

    def test_note_hidden_until_other_player_steps_on_it(self):
        self.assertTrue(self.w.bury(self.a, "hello from the west light"))
        self.assertEqual(self.w.snapshot(self.b)["notes"], [])
        self.assertEqual(self.w.hum(self.a), 0)        # own note never hums
        ax, ay = self.at(self.a)
        self.put(self.b, ax + 1, ay)
        self.assertEqual(self.w.hum(self.b), 3)
        self.put(self.a, ax, ay - 1)
        self.w.now = 5.0
        self.assertTrue(self.w.move(self.b, -1, 0))
        notes = self.w.snapshot(self.a)["notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "hello from the west light")
        self.assertEqual(self.w.hum(self.b), 0)

    def test_text_is_scrubbed(self):
        self.assertNotIn("999.999.999.999", server.clean_text("meet at 999.999.999.999 ok"))
        self.assertEqual(len(server.clean_text("x" * 500)), server.MAX_TEXT)

    def test_snapshot_is_json_and_charted_counts(self):
        snap = json.loads(json.dumps(self.w.snapshot(self.a)))
        self.assertEqual(len(snap["chart"]), H)
        self.assertEqual(len(snap["players"]), 2)
        self.assertGreaterEqual(snap["charted"], 1)
        self.assertTrue(0.5 <= snap["tide"] <= 2.5)

    def test_bad_fields_report_error(self):
        self.assertIsNotNone(self.w.handle(self.a, {"t": "move", "dx": "east"}))
        self.assertIsNone(self.w.handle(self.a, {"t": "dance"}))


class SocketLayer(unittest.TestCase):
    def test_hello_welcome_state_roundtrip(self):
        async def run():
            srv = await server.Server().start(0)
            port = srv.sockets[0].getsockname()[1]
            r, w = await asyncio.open_connection("localhost", port)
            w.write(b'{"t":"move","dx":1,"dy":0}\n')
            self.assertEqual(json.loads(await r.readline())["t"], "error")
            w.write(b'{"t":"hello","name":"Teal","color":"teal"}\n')
            wel = json.loads(await r.readline())
            self.assertEqual((wel["t"], wel["w"], wel["h"]), ("welcome", W, H))
            w.write(b'{"t":"plant"}\n{"t":"say","text":"hi"}\n')
            for _ in range(3):
                st = json.loads(await asyncio.wait_for(r.readline(), 3))
            self.assertEqual(st["t"], "state")
            self.assertEqual(len(st["gardens"]), 1)
            self.assertIn("Teal: hi", st["log"])
            w.close()
            srv.close()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
