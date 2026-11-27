"""Two-player tending: the lighter can differ from the planter."""
import unittest
from server import GROW_TICKS, World


class GardenTest(unittest.TestCase):
    def test_cooperative_bell(self):
        w=World()
        grower, guest=w.add_player(),w.add_player()
        pos=grower.x,grower.y
        w.handle(grower,{"t":"act"})
        w.handle(guest,{"t":"goto","x":pos[0],"y":pos[1]})
        for _ in range(3*GROW_TICKS//2):
            w.step()
        self.assertEqual((guest.x,guest.y),pos)
        self.assertEqual(w.snapshot()["plants"][0]["stage"],3)
        w.handle(guest,{"t":"act"})
        w.step()
        snap=w.snapshot()
        self.assertEqual((snap["glow"],guest.lit), (1,1))
        self.assertEqual(snap["plants"][0]["color"],list(grower.color))
        self.assertEqual(snap["plants"][0]["ring"],1)
        w.handle(grower,{"t":"act"})
        self.assertEqual(w.snapshot()["plants"][0]["ring"],0)
        self.assertEqual(w.glow(),1)
