# Lantern Isle — Protocol v1

Transport: TCP, UTF-8, one JSON object per line (`\n` terminated).
Server binds `""` on `AAL_LAN_PORT` (default 18765). Client connects to
`(AAL_LAN_HOST, AAL_LAN_PORT)`. Never show addresses anywhere — show "LAN Connected".

World: grid `W=40` x `H=20` tiles. Rows are strings, one char per tile:

| char | tile    | walkable |
|------|---------|----------|
| `.`  | grass   | yes |
| `=`  | path    | yes |
| `*`  | flower  | yes |
| `L`  | lantern | yes |
| `~`  | water   | no  |
| `#`  | wall    | no  |
| `T`  | tree    | no  |
| `^`  | rock    | no  |

Sides: `p1`, `p2`, `p3` (one connection per side; a reconnect replaces the old one).

## Client -> Server

- `{"t":"hello","side":"p1","name":"Laptop"}` — must be first. `name` optional.
- `{"t":"move","dx":1,"dy":0}` — one tile step (dx,dy in -1..1, not both 0). Server validates.
- `{"t":"place","x":5,"y":7,"tile":"#"}` — set a tile (any tile char above) within 3 tiles
  of the player. Cannot place on a tile occupied by a player unless walkable. `"."` = erase.
- `{"t":"chat","text":"hello"}` — in-world chat, max 200 chars. Broadcast to everyone.
- `{"t":"emote","e":"wave"}` — one of `wave`, `heart`, `dance`, `sleep`, `!`, `?`. Shown ~4s.
- `{"t":"ping"}` -> `{"t":"pong"}`

## Server -> Client

- `{"t":"welcome","side":"p1","w":40,"h":20,"tiles":["....","..."],"players":{...},
   "sparks":[[x,y],...],"score":0,"chat":[<last 30 chat msgs>],"clock":0.25}`
- `{"t":"state","players":{"p1":{"x":3,"y":4,"name":"Laptop","online":true,
   "emote":"wave","sparks":2}, ...},"sparks":[[x,y],...],"score":7,"clock":0.31,"goal":25}`
  — broadcast ~5x/sec and right after any change. `clock` is 0..1 day cycle
  (0.0 = dawn, 0.5 = dusk, >0.5 = night; lanterns glow at night). `score` = team sparks.
- `{"t":"tile","x":5,"y":7,"tile":"#","by":"p1"}` — a tile changed.
- `{"t":"chat","from":"p1","name":"Laptop","text":"hello","n":12}` — `from` may be `"sys"`
  for system notices (joins, leaves, goals). `n` is a rising message number.
- `{"t":"err","text":"..."}` — rejected action (non fatal).

## Rules

- Sparks appear on random walkable tiles (max 6). Walking onto one collects it:
  +1 to player `sparks` and team `score`. Each time team score hits a multiple of
  `goal` (25) the server announces it in chat and a ring of flowers blooms.
- Everything is authoritative on the server; clients just render state and send intents.
- Client suggested layout (854x480): map 40x20 tiles at 20px = 800x400, HUD strip on top
  with "LAN Connected" badge, chat log + text entry at the bottom.
- Suggested keys: arrows/WASD move; 1-8 pick tile; click map = place picked tile;
  right-click = erase; Enter focuses chat entry; F1-F6 emotes.
