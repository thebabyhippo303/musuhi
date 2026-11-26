# Emberglow Isle — LAN Protocol v1

A twilight island shared by **Wick** (moth lantern keeper) and **Moss** (stone-golem gardener).
Seeds only grow inside lantern light. Bloom enough and the island answers.

Transport: TCP, newline-delimited JSON (one object per line, UTF-8).
Server binds `""` on `AAL_LAN_PORT` (default 18765). Client connects to
`(AAL_LAN_HOST, AAL_LAN_PORT)`. Never show addresses; show "LAN Connected".

## World
- Grid `w=24`, `h=12`. `tiles` is a list of 12 strings of 24 chars:
  - `.` grass (walk)   `s` sand (walk)   `p` path (walk)
  - `~` water (blocked)  `#` rock (blocked)  `T` tree (blocked)
  - `B` bell shrine (blocked; stand next to it to ring)
- Players may share a tile.

## Client -> Server
| message | meaning |
|---|---|
| `{"t":"join","name":"Wick","role":"keeper","kind":"moth","color":"#5b2a6e"}` | first message. role: `keeper` or `gardener` |
| `{"t":"move","dx":1,"dy":0}` | step one tile (dx,dy in -1..1) |
| `{"t":"act","a":"lantern"}` | keeper: place a lantern on own tile, or pick it up if one is there (max 8) |
| `{"t":"act","a":"seed"}` | gardener: plant a seed on own tile (grass/sand only, max 40) |
| `{"t":"act","a":"ring"}` | ring the bell (must be within 1 tile of `B`). If BOTH players are near the bell: Duet (all lit plants grow a stage, fireflies swarm) |
| `{"t":"act","a":"emote","e":"wave"}` | e: `wave`, `heart`, `dance`, `glow` (shown ~3s) |
| `{"t":"act","a":"note","text":"hello"}` | leave a note (max 40 chars) on own tile; replaces existing |
| `{"t":"ping"}` | optional keepalive |

Either role may also use the generic `{"t":"act","a":"primary"}` which maps to
`lantern` for keepers and `seed` for gardeners.

## Server -> Client
`welcome` (once, after join):
```json
{"t":"welcome","id":1,"w":24,"h":12,"tiles":["....", "..."],"world":"Emberglow Isle"}
```
`state` (about 5 per second, and right after any change):
```json
{"t":"state","tick":123,
 "players":[{"id":1,"name":"Moss","role":"gardener","kind":"golem","color":"#6fbf5a",
             "x":5,"y":6,"face":"r","emote":"wave"}],
 "lanterns":[[4,5]],
 "plants":[{"x":5,"y":5,"stage":2,"lit":true}],
 "notes":[{"x":3,"y":4,"text":"hi","by":"Moss"}],
 "fireflies":[[7,3]],
 "blooms":3,
 "sky":"dusk",
 "event":"Duet! The bell hums.",
 "log":["Moss planted a seed","Wick lit a lantern"]}
```
- plant `stage`: 0 seed, 1 sprout, 2 bud, 3 bloom. Grows one stage every ~3s while
  within 2 tiles (Chebyshev) of a lantern (`lit`).
- `emote` is `""` when idle. `face` is `l`/`r`/`u`/`d`.
- `sky`: `dusk` -> `starlit` (5 blooms) -> `aurora` (12 blooms) -> `dawnsong` (20 blooms).
- `fireflies`: decorative positions, appear near blooms.
- `event`: latest world announcement (may be `""`). `log`: last 6 lines.
- `{"t":"error","msg":"..."}` for a rejected action (also appears as no state change).

## v1.1 additions (backwards compatible)
- `notes[]` now carry `"n"`: planting order (1 = first note ever left). The list is sent in that order.
- `plants[]` now carry `"hue"`: the sky a flower opened under (`dusk`, `starlit`, `aurora`,
  `dawnsong`), `""` until it blooms. A flower remembers.
- `plants[]` carry `"recalled"`: `true` when the hue was reconstructed from memory during the
  first save migration rather than witnessed by the server. Treat those as approximate.
- The server saves the isle (lanterns, plants, notes, last positions by name) to a save file next
  to itself about once a second and restores it on start, so a restart keeps the world. A player
  who rejoins under the same name resumes where they stood.
