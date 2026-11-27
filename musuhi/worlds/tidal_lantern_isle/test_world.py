#!/usr/bin/env python3
"""Tests for the Tidal Lantern Isle world logic and wire protocol."""
import asyncio
import json
import os
import unittest

import server
from server import World, W, H, TIDE_PERIOD


class WorldLogic(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.p = self.w.add_player("Ann")
        self.q = self.w.add_player("Bo")

    def high_tide(self):
        self.w.t = TIDE_PERIOD / 2
        self.w.recompute_wet()

    def test_spawn_distinct_and_walkable(self):
        self.assertNotEqual((self.p.x, self.p.y), (self.q.x, self.q.y))
        for pl in (self.p, self.q):
            self.assertIn(self.w.tiles[pl.y][pl.x], "gcs")

    def test_move_and_blocking(self):
        x, y = self.p.x, self.p.y
        self.assertIsNone(self.w.move(self.p.id, 1, 0, now=1.0))
        self.assertEqual((self.p.x, self.p.y), (x + 1, y))
        self.assertEqual(self.w.move(self.p.id, 1, 1, now=2.0), "Bad move")
        self.p.x, self.p.y = 1, 2  # sand next to sea
        self.assertIn("sea", self.w.move(self.p.id, -1, 0, now=3.0))
        self.assertEqual((self.p.x, self.p.y), (1, 2))

    def test_move_rate_limit(self):
        x = self.p.x
        self.w.move(self.p.id, 1, 0, now=1.0)
        self.w.move(self.p.id, 1, 0, now=1.01)
        self.assertEqual(self.p.x, x + 1)

    def test_players_do_not_overlap(self):
        self.q.x, self.q.y = self.p.x + 1, self.p.y
        self.w.move(self.p.id, 1, 0, now=1.0)
        self.assertNotEqual((self.p.x, self.p.y), (self.q.x, self.q.y))

    def test_act_range(self):
        self.assertEqual(self.w.act(self.p.id, "dig", self.p.x + 3, self.p.y), "Too far away")
        self.assertEqual(self.w.act(self.p.id, "dig", -1, 0), "Out of bounds")
        self.assertEqual(self.w.act(self.p.id, "boom", self.p.x, self.p.y), "Unknown action")

    def test_channel_gets_wet_with_tide(self):
        self.p.x, self.p.y = 2, 4
        for x in (1, 2, 3):
            self.assertIsNone(self.w.act(self.p.id, "dig", x, 4))
        self.w.t = 0.0
        self.w.recompute_wet()
        self.assertEqual(self.w.wet, set())
        self.high_tide()
        self.assertEqual(self.w.wet, {(1, 4), (2, 4), (3, 4)})
        self.assertIsNone(self.w.act(self.p.id, "fill", 2, 4))
        self.assertEqual(self.w.wet, {(1, 4)})

    def test_reed_grows_only_when_wet_and_harvest(self):
        self.p.x, self.p.y = 2, 4
        for x in (1, 2, 3):
            self.w.act(self.p.id, "dig", x, 4)
        seeds = self.p.seeds
        self.assertIsNone(self.w.act(self.p.id, "plant", 3, 5))
        self.assertEqual(self.p.seeds, seeds - 1)
        self.assertEqual(self.w.act(self.p.id, "plant", 3, 5), "Tile is taken")
        self.w.t = 0.0
        self.w.recompute_wet()
        for _ in range(40):
            self.w.grow()
        self.assertEqual(self.w.snapshot()["plants"][0]["stage"], 0)
        self.high_tide()
        for _ in range(40):
            self.w.grow()
        self.assertEqual(self.w.snapshot()["plants"][0]["stage"], 3)
        self.assertEqual(self.w.light(), 1)
        self.assertEqual(self.w.act(self.p.id, "harvest", 3, 5), "+1 glow, +2 seeds")
        self.assertEqual((self.p.glow, self.p.seeds), (1, seeds + 1))
        self.assertEqual(self.w.act(self.p.id, "harvest", 3, 5), "Nothing to harvest")

    def test_lantern_cost_and_light(self):
        x, y = self.p.x + 1, self.p.y
        self.assertEqual(self.w.act(self.p.id, "lantern", x, y), "Need 2 glow")
        self.p.glow = 2
        self.assertIsNone(self.w.act(self.p.id, "lantern", x, y))
        self.assertEqual(self.p.glow, 0)
        self.assertEqual(self.w.light(), 3)
        self.assertEqual(self.w.move(self.p.id, 1, 0, now=1.0), "A lantern stands there")
        self.assertEqual(self.w.act(self.p.id, "unlantern", x, y), "Picked up the lantern")
        self.assertEqual(self.p.glow, 2)

    def test_goal_levels_up(self):
        self.w.goal = 3
        self.p.glow = 2
        self.w.act(self.p.id, "lantern", self.p.x + 1, self.p.y)
        self.assertEqual(self.w.level, 2)
        self.assertEqual(self.w.goal, 33)
        self.assertEqual(self.q.seeds, 9)

    def test_give(self):
        self.q.x, self.q.y = 15, 2
        self.assertEqual(self.w.give(self.p.id, "seed"), "Nobody close enough")
        self.q.x, self.q.y = self.p.x + 2, self.p.y
        self.assertIsNone(self.w.give(self.p.id, "seed"))
        self.assertEqual((self.p.seeds, self.q.seeds), (5, 7))
        self.assertEqual(self.w.give(self.p.id, "glow"), "You have no glow")

    def test_emote_and_chat_expire(self):
        self.w.handle(self.p.id, {"t": "emote", "e": "wave"})
        self.w.handle(self.p.id, {"t": "chat", "text": "  hello   there " + "x" * 100})
        self.assertEqual(self.p.emote, "wave")
        self.assertLessEqual(len(self.p.say), 60)
        self.assertTrue(self.p.say.startswith("hello there"))
        for _ in range(30):
            self.w.step(0.2)
        self.assertEqual((self.p.emote, self.p.say), ("", ""))

    def test_handle_garbage_is_safe(self):
        for msg in ({}, {"t": "nope"}, {"t": "act"}, {"t": "act", "a": "dig", "x": "1", "y": None},
                    {"t": "move", "dx": "a"}, {"t": "give"}, {"t": "emote", "e": 5}):
            out = self.w.handle(self.p.id, msg)
            self.assertIsInstance(out, list)
        self.assertEqual(self.w.handle(self.p.id, {"t": "ping"}), [{"t": "pong"}])

    def test_snapshot_shape_and_privacy(self):
        self.w.step(0.2)
        s = self.w.snapshot()
        self.assertEqual(len(s["tiles"]), H)
        self.assertTrue(all(len(r) == W for r in s["tiles"] + s["wet"]))
        self.assertTrue(0.0 <= s["tide"] <= 1.0 and 0.0 <= s["day"] < 1.0)
        blob = json.dumps(s)
        for bad in ("127.", "192.168", "10.0", "eth", "wlan"):
            self.assertNotIn(bad, blob)

    def test_sign_place_and_remove(self):
        x, y = self.p.x + 1, self.p.y
        self.assertIsNone(self.w.handle(self.p.id, {"t": "sign", "x": x, "y": y, "text": " Heron   Run "}) or None)
        self.assertEqual(self.w.snapshot()["signs"], [{"x": x, "y": y, "text": "Heron Run", "by": self.p.id}])
        self.assertEqual(self.w.act(self.p.id, "plant", x, y), "Tile is taken")
        self.assertEqual(self.w.sign(self.p.id, x, y, ""), "Sign removed")
        self.assertEqual(self.w.sign(self.p.id, 20, 10, "far"), "Too far away")

    def test_heron_lands_when_lamps_ring_the_moonwell(self):
        self.assertEqual(len([c for c in self.w.snapshot()["critters"] if c["kind"] == "koi"]), 3)
        for pos in ((18, 5), (19, 7), (15, 5), (16, 7), (14, 6)):
            self.w.lanterns[pos] = self.p.id
        base = self.w.light()
        self.w.step(0.2)
        kinds = [c["kind"] for c in self.w.snapshot()["critters"]]
        self.assertIn("heron", kinds)
        self.assertEqual(self.w.light(), base + server.HERON_BONUS)
        del self.w.lanterns[(14, 6)]
        self.w.step(0.2)
        self.assertIsNone(self.w.heron)

    def test_heron_leaves_a_seed_for_a_keeper_waiting_nearby(self):
        for pos in ((18, 5), (19, 7), (15, 5), (16, 7), (14, 6)):
            self.w.lanterns[pos] = self.p.id
        self.w.step(0.2)
        hx, hy = self.w.heron
        self.p.x, self.p.y = hx, hy + 2
        self.q.x, self.q.y = 2, 2
        seeds, far = self.p.seeds, self.q.seeds
        self.w.heron_move_at = self.w.t
        self.w.step(0.2)
        self.assertEqual(self.p.seeds, seeds + 1)
        self.assertEqual(self.q.seeds, far)
        self.assertIn("The heron left %s a seed" % self.p.name, self.w.log)

    def test_every_third_tide_is_a_spring_tide(self):
        self.w.t = TIDE_PERIOD / 2
        self.assertFalse(self.w.spring())
        self.assertEqual(self.w.reach(), server.MAX_REACH)
        self.w.t = 2.5 * TIDE_PERIOD
        self.assertTrue(self.w.spring())
        self.assertEqual(self.w.reach(), server.MAX_REACH + server.SPRING_EXTRA)
        self.assertTrue(self.w.snapshot()["spring"])

    def test_koi_stay_in_water(self):
        self.p.x, self.p.y = 15, 4
        for x in (14, 15, 16):
            self.w.act(self.p.id, "dig", x, 4)
        self.high_tide()
        for _ in range(300):
            self.w.step(0.2)
            water = server.POND | self.w.wet
            for c in self.w.snapshot()["critters"]:
                if c["kind"] == "koi":
                    self.assertIn((c["x"], c["y"]), water)

    def test_save_and_restore_world_and_keepers(self):
        self.p.x, self.p.y = 2, 4
        self.w.act(self.p.id, "dig", 2, 4)
        self.w.act(self.p.id, "plant", 3, 5)
        self.p.glow = 4
        self.w.act(self.p.id, "lantern", 3, 3)
        self.w.sign(self.p.id, 3, 4, "North Ditch")
        blob = json.loads(json.dumps(self.w.to_save()))
        w2 = World()
        w2.load_save(blob)
        self.assertEqual(w2.tiles[4][2], "c")
        self.assertIn((3, 5), w2.plants)
        self.assertIn((3, 3), w2.lanterns)
        self.assertEqual(w2.signs[(3, 4)]["text"], "North Ditch")
        ann = w2.add_player("Ann")
        self.assertEqual((ann.x, ann.y, ann.glow, ann.seeds), (2, 4, 2, self.p.seeds))
        fresh = w2.add_player("Cy")
        self.assertEqual(fresh.seeds, 6)

    def test_remove_player(self):
        self.w.remove_player(self.q.id)
        self.assertEqual(len(self.w.snapshot()["players"]), 1)


class WireProtocol(unittest.TestCase):
    def test_two_clients_over_tcp(self):
        async def scenario():
            srv = server.Server()
            s = await asyncio.start_server(srv.on_client, "localhost", 0)
            port = s.sockets[0].getsockname()[1]
            tick = asyncio.ensure_future(srv.ticker())

            async def client(name):
                r, w = await asyncio.open_connection("localhost", port)
                w.write((json.dumps({"t": "hello", "name": name}) + "\n").encode())
                welcome = json.loads(await r.readline())
                return r, w, welcome

            async def next_of(r, kind):
                while True:
                    m = json.loads(await asyncio.wait_for(r.readline(), 3))
                    if m["t"] == kind:
                        return m

            r1, w1, wel1 = await client("Ann")
            r2, w2, wel2 = await client("Bo")
            self.assertEqual(wel1["t"], "welcome")
            self.assertNotEqual(wel1["id"], wel2["id"])
            w1.write(b'{"t":"move","dx":1,"dy":0}\nnot json\n{"t":"ping"}\n')
            await next_of(r1, "pong")
            await asyncio.sleep(0.3)
            st = await next_of(r2, "state")
            st = await next_of(r2, "state")
            names = {p["name"]: p for p in st["players"]}
            self.assertEqual(set(names), {"Ann", "Bo"})
            self.assertEqual(names["Ann"]["x"], server.SPAWNS[0][0] + 1)
            w1.write(b'{"t":"act","a":"lantern","x":0,"y":0}\n')
            note = await next_of(r1, "note")
            self.assertEqual(note["text"], "Too far away")
            w2.close()
            await asyncio.sleep(0.4)
            st = await next_of(r1, "state")
            while len(st["players"]) != 1:
                st = await next_of(r1, "state")
            w1.close()
            tick.cancel()
            s.close()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main(verbosity=1)
