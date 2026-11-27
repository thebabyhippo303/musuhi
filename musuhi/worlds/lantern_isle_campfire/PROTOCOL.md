# Lantern Isle — Protocol v1

TCP, port `AAL_LAN_PORT` (default 18765). Each message is one JSON object per line (UTF-8, `\n` terminated).

## Client -> Server
- `{"t":"hello","name":"Mini PC"}` — first message.
- `{"t":"move","dx":-1|0|1,"dy":-1|0|1}` — step one tile (water `~` and rocks `^` block). Walking onto a shell auto-collects it (+1).
- `{"t":"act"}` — standing on a shell: pick it up (+1 shell). Else if you have shells: plant a lantern on the first free adjacent tile (down/right/up/left order, costs 1). Else (0 shells): reclaim an adjacent lantern of yours (+1). Lanterns are walk-through (since v3). Everyone starts with 1 shell; shells respawn.
- `{"t":"say","text":"..."}` — chat (max 60 chars).
- `{"t":"wish","text":"..."}` — (v2) launch a paper wishing boat from the nearest water tile (within 3) that slowly drifts out to sea (max 40 chars, 12 boats max).
- `{"t":"emote","e":"wave"|"heart"|"dance"}` — floating emote above you for 3 s.

## Server -> Client
- `{"t":"welcome","id":N,"cols":26,"rows":13,"map":["...26 chars...", x13]}`
  Map chars: `~` water, `.` sand, `,` grass, `^` rock, `T` tree (walkable, decorative).
- `{"t":"state","tick":N,"players":[{"id","name","x","y","color":"#rrggbb","shells","emote":str|null}],"lanterns":[{"x","y","owner"}],"shells":[{"x","y"}],"boats":[{"x","y","text","owner"}],"chat":[{"name","text"}],"lit":N,"goal":N}`
  Sent ~10x/s. `chat` = last 6 lines. `lit` = number of lanterns, `goal` = 20 (island fully lit = celebration).

## Rendering suggestion (854x480)
Top bar 32 px (title + "LAN Connected" badge), map 26x13 tiles of 32 px at x=11,y=32, bottom bar 32 px (shells/chat).
Night: darken tiles far from any lantern/player (light radius 3 tiles).

v2: `boats` x/y are floats in tile units (may go slightly off-map before vanishing). Lanterns persist across server restarts (restored ones have owner 0 = whole isle).
v2: state also has `phase`: "night" | "aurora" | "night" | "dawn" cycling every 40 s (sky mood for clients to render).
v3: fireflies. State adds `fireflies:[{x,y}]` (floats, tile units, ~8 drifting), per-player `jar:N`, and `bursts:[{x,y,n,age}]` (age in s, kept 3 s). A firefly within 0.75 tiles of a player is caught (+1 jar). Client sends `{"t":"release"}` to release the whole jar as a burst at your position.
v4: map adds `L` lighthouse at (1,6) (blocks walking) and `D` wooden dock at (7,12) (walkable, sticks out into the south sea — great spot for wishing boats). State adds `beacon`: lighthouse beam angle in radians (0 = pointing east/right, increasing clockwise in screen coords, ~0.8 rad/s).
v5: map adds `F` campfire at (10,2) on the north beach (blocks walking; render flickering fire + warm glow, a cozy stargazing spot). State adds `star`: null or a shooting star `{x0,y0,x1,y1,born,age}` in tile units, streaking from (x0,y0) to (x1,y1) over 1.5 s (age 0..1.5); one every 8-16 s.
