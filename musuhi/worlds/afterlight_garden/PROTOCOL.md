# The Afterlight Garden

Wick carries amber lanterns; Mote sows teal starflowers. The two gardeners
can leave independent marks, signal to each other, and wake the Heartseed
together. There is no timer, damage, or inventory. The garden persists in
the server's memory for as long as the server runs.

## Wire format

One UTF-8 JSON object per newline, carried over TCP. The client uses
`AAL_LAN_HOST` and `AAL_LAN_PORT` (port defaults to `18765`). The server
listens on the given port. Neither side should display transport details.

First send `{"type":"join","role":"wick"}` (or `"mote"`). Each role is
exclusive until that socket disconnects. Positions persist on rejoin.
Invalid or duplicate joins receive `{"type":"error","message":"..."}`.

After join, send one of:

| Message | Effect |
| --- | --- |
| `{"type":"move","dx":1,"dy":0}` | Move one tile, diagonals allowed. Each component must be an integer from -1 to 1. |
| `{"type":"place"}` | Wick places a lantern; Mote places a starflower. Repeats do not duplicate marks. Their marks may share a tile. |
| `{"type":"signal"}` | Sends a role-specific greeting to both gardeners. |
| `{"type":"tend"}` | Within one tile (including diagonals) of the Heartseed, offer care. Marks from both roles and both gardeners' care are required for the bloom. |

The grid is 20×12, with zero-based coordinates, east to the right and
south down. The Heartseed is at `(10,6)`. Wick starts at `(4,6)` and Mote
at `(15,6)`. Both can stand on the same tile.

Both clients receive this full snapshot on changes:

```json
{"type":"state","players":{"wick":{"x":4,"y":6},"mote":{"x":15,"y":6}},"marks":[{"role":"wick","x":4,"y":6}],"event":"Wick set an amber lantern.","bloom":false,"tended":[],"revision":3}
```

`players` contains only currently connected roles. `tended` lists the
roles with an offering at the Heartseed. `revision` increases with
published snapshots. The latest `event` is preserved while moving.
After bloom, tending renews the light without removing previous work.
