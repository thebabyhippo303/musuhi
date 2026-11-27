"""Host-side tests: plaques, persistence, chapters and wind."""
import unittest
from server import GOAL, WIND_TICKS, World


def join(w, name):
    p = w.add_player()
    w.handle(p, {"t": "join", "name": name})
    return p


class ServerTest(unittest.TestCase):
    def test_plaque_set_and_clear(self):
        w = World()
        p = join(w, "A")
        w.handle(p, {"t": "name", "text": "Borrowed Wick"})
        self.assertEqual(w.snapshot()["plaques"],
                         [{"x": p.x, "y": p.y, "text": "Borrowed Wick"}])
        w.handle(p, {"t": "name", "text": ""})
        self.assertEqual(w.snapshot()["plaques"], [])

    def test_save_and_restore_keeps_garden_and_player(self):
        w = World()
        p = join(w, "A")
        w.handle(p, {"t": "act"})
        w.handle(p, {"t": "move", "dx": 1, "dy": 0})
        w.handle(p, {"t": "name", "text": "Here"})
        saved = w.to_dict()
        w2 = World()
        w2.load_dict(saved)
        w2.add_player()            # a stranger takes the next fresh id first
        self.assertEqual(len(w2.plants), 1)
        self.assertEqual(list(w2.plaques.values()), ["Here"])
        q = join(w2, "A")
        self.assertEqual((q.id, q.x, q.y, q.seeds, q.color),
                         (p.id, p.x, p.y, p.seeds, p.color))

    def test_goal_grows_and_wind_snuffs_far_lantern(self):
        w = World()
        p = join(w, "A")
        for i in range(GOAL):
            w.plants[(i, 0)] = {"stage": 4, "owner": p.id, "age": 0,
                                "color": [1, 2, 3], "rung": None}
        p.x, p.y = 20, 10
        w.step()
        self.assertEqual((w.chapter, w.goal), (1, 2 * GOAL))
        while w.tick % WIND_TICKS:
            w.step()
        snap = w.snapshot()
        self.assertEqual(snap["glow"], GOAL - 1)
        self.assertEqual(snap["wind"], 0)
        x, y = snap["wind_at"]
        self.assertEqual(w.plants[(x, y)]["stage"], 3)

    def test_wind_spares_tended_lanterns(self):
        w = World()
        p = join(w, "A")
        w.chapter = 1
        w.plants[(p.x + 1, p.y)] = {"stage": 4, "owner": p.id, "age": 0,
                                    "color": [1, 2, 3], "rung": None}
        w._gust()
        self.assertEqual(w.glow(), 1)
        self.assertIsNone(w.wind_at)


if __name__ == "__main__":
    unittest.main()
