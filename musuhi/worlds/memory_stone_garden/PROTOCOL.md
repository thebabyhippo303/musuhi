# Twilight Sky-Garden — Protocol v1

Transport: TCP, newline-delimited JSON (UTF-8), one object per line.
Server binds "" on AAL_LAN_PORT (default 18765). Client connects to (AAL_LAN_HOST, AAL_LAN_PORT).

World: grid COLS=20 x ROWS=10. Tile (0,0) top-left.

## Client -> Server
- {"t":"hello","name":"Lantern","avatar":"lantern"|"constellation"}
- {"t":"move","dx":-1|0|1,"dy":-1|0|1}
- {"t":"plant"}            plant/grow flora on your tile (kinds cycle: bud->bloom->tree)
- {"t":"light"}            light a star if you stand on/adjacent to one; links it to the last star lit by anyone
- {"t":"chime"}            ring a note at your tile (note depends on column)
- {"t":"say","text":"..."} short speech bubble (max 60 chars)

## Server -> Client
- {"t":"welcome","id":N,"cols":20,"rows":10}
- {"t":"state","tick":N,"players":[{"id","name","avatar","x","y","say"}],
   "flora":[{"x","y","stage"}], "stars":[{"x","y","lit"}], "links":[[i,j],...],
   "chimes":[{"x","y","note","age"}], "glow":0..100}
  Broadcast ~10 Hz. "glow" = garden liveliness score.

## v2 additions (state)
- "aurora": bool — true once every star is lit.
- "fireflies": [{"x","y"}] — float tile coords, drifting from stage-3 trees.

## v3: memory stones
- Client: {"t":"inscribe","text":"..."} (<=60 chars) leaves/replaces a stone on your tile.
- State: "stones":[{"x","y","text","by"}]. Server autosaves the garden every ~5 s.

## v4: harmony
- Two different players chiming within 2 s -> "harmonies":[{"x1","y1","x2","y2","age"}] (age 0-19) + firefly burst along the line.
