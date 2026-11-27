#!/usr/bin/env python3
"""One-off: copy the running world into world_save.json (used once to hot-upgrade the server)."""
import json
import os
import socket

import server

s = socket.create_connection(("localhost", int(os.environ.get("AAL_LAN_PORT", "18765"))), timeout=3)
s.sendall(b'{"t":"hello","name":"scribe"}\n')
f = s.makefile("r")
while True:
    m = json.loads(f.readline())
    if m["t"] == "state":
        break
s.close()
save = {
    "v": 1, "t": m["day"] * server.DAY_PERIOD, "level": m["level"], "goal": m["goal"],
    "tiles": m["tiles"],
    "plants": [[p["x"], p["y"], p["stage"] * server.GROW_PER_STAGE, p["by"]] for p in m["plants"]],
    "lanterns": [[l["x"], l["y"], l["by"]] for l in m["lanterns"]],
    "signs": [],
    "stash": {p["name"]: {"x": p["x"], "y": p["y"], "seeds": p["seeds"], "glow": p["glow"]}
              for p in m["players"] if p["name"] != "scribe"},
    "log": [l for l in m["log"] if "scribe" not in l],
}
with open(server.SAVE_PATH, "w") as out:
    json.dump(save, out)
print("saved: %d plants, %d lanterns, keepers %s" % (len(save["plants"]), len(save["lanterns"]), sorted(save["stash"])))
