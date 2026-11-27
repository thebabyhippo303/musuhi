#!/usr/bin/env python3
"""Tests for Lantern Garden server. Run: python3 -m pytest test_server.py -q
or plain: python3 test_server.py
"""
import json
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402
import tempfile  # noqa: E402

# Isolate unit tests from the live saved garden: point SAVE at a missing file.
server.SAVE = os.path.join(tempfile.mkdtemp(prefix="garden-test-"), "none.json")
from server import World, clamp, clean_color, MAX_SEEDS  # noqa: E402


def make_world():
    w = World()
    a = w.add_player("P1", "lantern", [60, 220, 200])
    b = w.add_player("P2", "moth", [255, 180, 80])
    return w, a, b


def test_clamp_and_color():
    assert clamp(5, 0, 10) == 5 and clamp(-1, 0, 10) == 0 and clamp(99, 0, 10) == 10
    assert clean_color([300, -5, 12]) == [255, 0, 12]
    assert clean_color("bad") == [220, 220, 220]
    assert clean_color([1, 2]) == [220, 220, 220]


def test_plant_and_own_touch_does_not_bloom():
    w, a, b = make_world()
    pa = w.players[a]
    w.handle(a, {"t": "plant"})
    assert len(w.seeds) == 1 and pa["planted"] == 1
    # owner standing on own seed for many steps: must NOT bloom
    for _ in range(20):
        w.step(0.05)
    assert len(w.seeds) == 1 and len(w.blooms) == 0, "own seed must not bloom alone"


def test_other_player_blooms_seed():
    w, a, b = make_world()
    pa, pb = w.players[a], w.players[b]
    w.handle(a, {"t": "plant"})
    seed = list(w.seeds.values())[0]
    # move planter away, bring other player onto seed
    pa["x"] = pa["tx"] = 100.0; pa["y"] = pa["ty"] = 100.0
    pb["x"] = pb["tx"] = float(seed["x"]); pb["y"] = pb["ty"] = float(seed["y"])
    w.step(0.05)
    assert len(w.seeds) == 0 and len(w.blooms) == 1
    bloom = list(w.blooms.values())[0]
    assert bloom["names"] == ["P1", "P2"] and bloom["level"] == 2
    assert bloom["color"] == [(60 + 255) // 2, (220 + 180) // 2, (200 + 80) // 2]
    assert pb["touched"] == 1
    snap = w.snapshot()
    assert snap["glow"] == 2 and snap["blooms"][0]["level"] == 2
    assert "last" not in snap["blooms"][0]  # internals not leaked


def test_move_clamp_and_step():
    w, a, b = make_world()
    w.handle(a, {"t": "move", "x": 99999, "y": -50})
    pa = w.players[a]
    assert pa["tx"] == 842 and pa["ty"] == 56
    pa["x"] = pa["tx"] = 400.0; pa["y"] = pa["ty"] = 240.0
    w.handle(a, {"t": "step", "dx": 1, "dy": 0})
    assert pa["tx"] == 430.0 and pa["ty"] == 240.0
    w.step(1.0)  # speed caps travel
    assert pa["x"] <= 430.0


def test_max_seeds_and_say():
    w, a, b = make_world()
    pa = w.players[a]
    for i in range(MAX_SEEDS + 3):
        pa["x"] = pa["tx"] = 100.0 + i * 40
        pa["y"] = pa["ty"] = 200.0
        w.handle(a, {"t": "plant"})
    assert len([s for s in w.seeds.values() if s["owner"] == a]) == MAX_SEEDS
    w.handle(a, {"t": "say", "text": "hello garden"})
    assert w.snapshot()["msgs"][-1] == {"from": "P1", "text": "hello garden"}


def test_third_player_joins_bloom_after_cooldown():
    w, a, b = make_world()
    c = w.add_player("P3", "prism", [255, 120, 80])
    pa, pb, pc = w.players[a], w.players[b], w.players[c]
    w.handle(a, {"t": "plant"})
    seed = list(w.seeds.values())[0]
    pa["x"] = pa["tx"] = 100.0; pa["y"] = pa["ty"] = 100.0
    pb["x"] = pb["tx"] = float(seed["x"]); pb["y"] = pb["ty"] = float(seed["y"])
    w.step(0.05)
    assert len(w.blooms) == 1
    bloom = list(w.blooms.values())[0]
    pb["x"] = pb["tx"] = 120.0; pb["y"] = pb["ty"] = 120.0
    pc["x"] = pc["tx"] = float(bloom["x"]); pc["y"] = pc["ty"] = float(bloom["y"])
    bloom["when"] -= 10  # bypass retouch cooldown deterministically
    w.step(0.05)
    assert bloom["level"] == 3 and "P3" in bloom["names"]


def test_wild_seed_on_star_bloom():
    w = World()
    assert len(w.blooms) == 0 and len(w.seeds) == 0  # clean, no live garden leak
    ids = {}
    for name, shape, col in [("A", "lantern", [10, 200, 200]),
                             ("B", "moth", [250, 180, 80]),
                             ("C", "prism", [250, 120, 120]),
                             ("D", "diamond", [190, 130, 255])]:
        ids[name] = w.add_player(name, shape, col)
    pa = w.players[ids["A"]]
    pa["x"] = pa["tx"] = 300.0; pa["y"] = pa["ty"] = 200.0
    w.handle(ids["A"], {"t": "plant"})
    assert len(w.seeds) == 1
    pa["x"] = pa["tx"] = 700.0; pa["y"] = pa["ty"] = 400.0
    for name in "BCD":
        p = w.players[ids[name]]
        p["x"] = p["tx"] = 300.0; p["y"] = p["ty"] = 200.0
        for b in w.blooms.values():
            b["when"] -= 10
        w.step(0.05)
        p["x"] = p["tx"] = 720.0; p["y"] = p["ty"] = 420.0
    bloom = list(w.blooms.values())[0]
    assert bloom["level"] == 4 and set(bloom["names"]) == {"A", "B", "C", "D"}
    wild = [s for s in w.seeds.values() if s["name"] == "garden"]
    assert len(wild) == 1, "star bloom should make the garden plant a wild seed"


def test_name_bloom():
    w, a, b = make_world()
    c = w.add_player("P3", "prism", [255, 120, 80])
    pa, pb, pc = w.players[a], w.players[b], w.players[c]
    w.handle(a, {"t": "plant"})
    seed = list(w.seeds.values())[0]
    pa["x"] = pa["tx"] = 100.0; pa["y"] = pa["ty"] = 100.0
    pb["x"] = pb["tx"] = float(seed["x"]); pb["y"] = pb["ty"] = float(seed["y"])
    w.step(0.05)
    bloom = list(w.blooms.values())[0]
    assert w.snapshot()["blooms"][0]["word"] == ""
    # a maker standing far away cannot name it
    w.handle(a, {"t": "say", "text": "name TooFar"})
    assert bloom.get("word", "") == ""
    # a stranger standing on it cannot name it
    pc["x"] = pc["tx"] = float(bloom["x"]); pc["y"] = pc["ty"] = float(bloom["y"])
    w.handle(c, {"t": "say", "text": "name NotMine"})
    assert bloom.get("word", "") == ""
    # the waker standing on it can; word is length-capped and in snapshot
    w.handle(b, {"t": "say", "text": "name WelcomeHomeFriend"})
    assert bloom["word"] == "WelcomeHomeFri"
    assert w.snapshot()["blooms"][0]["word"] == "WelcomeHomeFri"
    # plain chat still works and does not rename
    w.handle(b, {"t": "say", "text": "hello there"})
    assert bloom["word"] == "WelcomeHomeFri"
    assert w.snapshot()["msgs"][-1]["text"] == "hello there"


def test_save_load_roundtrip():
    w, a, b = make_world()
    pa, pb = w.players[a], w.players[b]
    w.handle(a, {"t": "plant"})
    seed = list(w.seeds.values())[0]
    pa["x"] = pa["tx"] = 100.0; pa["y"] = pa["ty"] = 100.0
    pb["x"] = pb["tx"] = float(seed["x"]); pb["y"] = pb["ty"] = float(seed["y"])
    w.step(0.05)
    w.handle(b, {"t": "say", "text": "name Kept"})
    pa["x"] = pa["tx"] = 500.0; pa["y"] = pa["ty"] = 300.0
    w.handle(a, {"t": "plant"})  # a sleeping seed also survives
    w.save()
    try:
        w2 = World()  # loads from the same isolated SAVE path
        assert len(w2.blooms) == 1 and len(w2.seeds) == 1
        bloom = list(w2.blooms.values())[0]
        assert bloom["word"] == "Kept" and bloom["names"] == ["P1", "P2"]
        assert w2.snapshot()["blooms"][0]["word"] == "Kept"
        assert list(w2.seeds.values())[0]["name"] == "P1"
    finally:
        os.unlink(server.SAVE)  # later tests must start from an empty garden


def test_socket_end_to_end():
    port = 18799
    env = dict(os.environ, AAL_LAN_PORT=str(port))
    here = os.path.dirname(os.path.abspath(__file__))
    # Run a copy in a temp dir so it cannot load the live saved garden.
    import shutil
    tmp = tempfile.mkdtemp(prefix="garden-sock-")
    shutil.copy(os.path.join(here, "server.py"), os.path.join(tmp, "server.py"))
    proc = subprocess.Popen([sys.executable, os.path.join(tmp, "server.py")],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 8
        sock = None
        while time.time() < deadline:
            try:
                sock = socket.create_connection(("localhost", port), timeout=2)
                break
            except OSError:
                time.sleep(0.2)
        assert sock is not None, "server did not start"
        f = sock.makefile("r", encoding="utf-8")
        sock.sendall((json.dumps({"t": "hello", "name": "T1", "shape": "kite",
                                   "color": [180, 120, 255]}) + "\n").encode())
        welcome = json.loads(f.readline())
        assert welcome["t"] == "welcome" and welcome["w"] == 854 and welcome["h"] == 480
        sock.sendall(b'{"t":"plant"}\n')
        got_state = False
        for _ in range(30):
            msg = json.loads(f.readline())
            if msg.get("t") == "state" and msg.get("seeds"):
                got_state = True
                break
        assert got_state, "no state with seed received"
        sock.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print("ALL %d TESTS PASSED" % len(fns))
