# Lantern Garden — LAN Protocol v2

Transport: TCP, UTF-8, one JSON object per line (`\n` terminated).
Server listens on port `AAL_LAN_PORT` (default 18765). Client connects to
`AAL_LAN_HOST` / `AAL_LAN_PORT` from the environment. Never display addresses;
show "LAN Connected" instead.

World: grid `W=26` columns x `H=13` rows. `(0,0)` is top-left. Server is authoritative.

## Client -> Server
| message | meaning |
|---|---|
| `{"t":"join","name":"P2"}` | first message; name max 12 chars |
| `{"t":"move","dx":1,"dy":0}` | step one tile (dx,dy each in -1,0,1); clears any goto |
| `{"t":"goto","x":5,"y":7}` | walk toward tile, one step per server tick (click-to-move) |
| `{"t":"act"}` | on empty tile: plant a seed. On a bloom (stage 3): light it into a lantern. On a lantern (stage 4): ring it like a bell |
| `{"t":"say","text":"hello"}` | speech bubble, max 40 chars, shown ~6 s |
| `{"t":"name","text":"Borrowed Wick"}` | v2: put a plaque on your tile (max 24 chars; empty text removes it) |

## Server -> Client
`{"t":"welcome","id":1,"w":26,"h":13,"tick_hz":5}` once after join.

`{"t":"state", ...}` every tick (5 Hz):
```json
{"t":"state","tick":123,
 "players":[{"id":1,"name":"P1","x":3,"y":4,"color":[255,180,60],"say":"hello","seeds":7,"lit":2}],
 "plants":[{"x":5,"y":6,"stage":2,"owner":1,"color":[255,180,60],"ring":-1}],
 "glow":4, "goal":12, "night":0.35}
```
- `plants.stage`: 0 seed, 1 sprout, 2 bud, 3 bloom, 4 lantern (lit, permanent).
- Plants advance one stage about every 6 s; they grow twice as fast when any player stands within 1 tile.
- `plants.color`: the planter's color (lanterns keep it forever). `plants.ring`: ticks since the lantern was last rung (0 when just lit/rung), `-1` if never; draw a ripple while `0 <= ring < 10`.
- `seeds`: seeds a player still carries (starts 8, +1 each time they light a lantern).
- `glow`: total lanterns lit by everyone (shared score). `goal`: lanterns needed for the garden to be "fully lit".
- `night`: 0..1 darkness, rises slowly over time; lanterns push it back (clients may tint the sky with it).
- `say` is `""` when the player is not speaking.

## v2 additions (all optional for clients; unknown fields can be ignored)
- State adds `"plaques":[{"x":13,"y":6,"text":"Borrowed Wick"}]`.
- State adds `"chapter"`: how many times the goal was reached. Each time, `goal` grows by 12.
- Wind: once chapter >= 1, about every 45 s a gust turns one lantern that has no
  player within 2 tiles back into a bloom (stage 3), to be re-lit. State adds
  `"wind"` (ticks since last gust, `-1` if never) and `"wind_at"` (`[x,y]` of the
  snuffed lantern, or `null` if the gust found nothing).
- The garden is saved to disk every 5 s and restored when the server restarts.
  Players are remembered by name (id, position, seeds, color); a returning player
  gets a second `welcome` carrying their old id.

## Controls (suggested for clients)
Arrow keys / WASD move, Space = act, left click a tile = goto,
keys 1-4 = say "hello" / "nice lantern" / "follow me" / "thank you".
