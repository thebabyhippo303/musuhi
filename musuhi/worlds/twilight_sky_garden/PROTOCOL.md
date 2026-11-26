# Twilight Sky Garden — Protocol v1
TCP, newline-delimited JSON (one object per line, UTF-8). Port = AAL_LAN_PORT (default 18765).

World grid: W=20 cols x H=10 rows (tiles). Only "island" tiles are walkable (server provides `island` as list of 10 strings, '#'=ground, '.'=sky/void).
Fixed `chimes` (tile positions) and `stars` (sky positions in 0..1 normalized coords for drawing at top of canvas).

## Client -> Server
{"t":"hello","name":"Prism","role":"prism"}     role: "lantern" | "prism"
{"t":"move","dx":-1|0|1,"dy":-1|0|1}            one tile step (blocked off-island / by chime)
{"t":"plant"}       plant/grow a glowing flower on your tile (stage 1..3; planting again grows it)
{"t":"chime"}       ring the nearest chime within 1 tile (all players see a ripple)
{"t":"star"}        light the next unlit star (if both lit >=1 together, constellations connect)
{"t":"note","text":"..."}   leave a note (max 60 chars) on your tile
{"t":"emote","e":"wave"|"heart"|"spark"}
{"t":"ping"}

## Server -> Client
{"t":"welcome","id":"p1"}
{"t":"state", "tick":N, "island":[...], "players":{"p1":{"name","role","x","y","emote","emote_age"}},
 "plants":[{"x","y","stage","by"}], "chimes":[{"x","y","ring_age"}], "stars":[{"x","y","lit","by"}],
 "notes":[{"x","y","text","by"}], "log":["last 6 events"], "bloom":0..100}
State is broadcast on every change and every 0.5s. `*_age` = seconds since event (null if never).
"bloom" rises as the garden grows; at 100 the sky aurora appears.

## v2 additions (backward compatible)
{"t":"build","dx":-1..1,"dy":-1..1}  weave a glowing stepping-stone on an adjacent void tile ('.' -> '*', walkable)
{"t":"lamp"}   raise a lamp post on your tile in your colour
Heart emotes from both players within 2 tiles and 10s -> shooting star.
State adds: "lamps":[{x,y,by,role}], "wishes":N, "wish_age":sec|null. island may contain '*' (built stone, walkable).
World persists to world_save.json across server restarts.
