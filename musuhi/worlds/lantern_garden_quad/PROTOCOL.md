# Lantern Garden — wire protocol (v1)

A shared night field. Each player walks, plants seeds, and touches things.
**A seed only blooms when a DIFFERENT player touches it.** A bloom keeps the
names of everyone who has touched it and mixes their colors. Nothing finishes alone.

## Transport
- TCP. Server listens on port `int(os.environ.get("AAL_LAN_PORT", "18765"))`.
- Client connects to `(os.environ["AAL_LAN_HOST"], port)`.
- One JSON object per line, UTF-8, terminated by `\n`. Keep text ASCII.
- Never print / log / render any network address. Show "LAN Connected" instead.

## World
- Size 854 x 480 pixels, origin top-left. This is exactly the window size, so
  world coords == window coords. Top strip `y < 44` is reserved for the HUD.
- Players are clamped to `12 <= x <= 842`, `56 <= y <= 468`.
- Walk speed 150 px/s. Touch radius 16 px.

## Client -> Server
| message | meaning |
|---|---|
| `{"t":"hello","name":"P3","shape":"star","color":[255,120,80]}` | MUST be first. name <= 12 chars, shape <= 12 chars, color = 3 ints 0..255 |
| `{"t":"move","x":400,"y":240}` | walk toward this point (mouse click) |
| `{"t":"step","dx":1,"dy":0}` | nudge 30 px in a direction (arrow / WASD keys), dx,dy in -1..1 |
| `{"t":"plant"}` | plant a seed where you stand (Space). Max 8 unbloomed seeds per player |
| `{"t":"say","text":"hello"}` | short chat line, <= 60 chars (optional) |

## Server -> Client
First: `{"t":"welcome","id":3,"w":854,"h":480}` — your player id.

Then 10 times per second the full world:
```json
{"t":"state","tick":123,"glow":7,
 "players":[{"id":1,"name":"P1","shape":"lantern","color":[60,220,200],
             "x":300.0,"y":200.0,"planted":2,"touched":1}],
 "seeds":[{"id":5,"x":120,"y":300,"owner":1,"name":"P1","color":[60,220,200]}],
 "blooms":[{"id":2,"x":500,"y":260,"color":[150,160,200],
            "names":["P1","P2"],"level":2}],
 "msgs":[{"from":"*","text":"P2 woke P1's seed"}]}
```
- `seeds`: unbloomed. Draw as a small dim dot in the owner's color.
- `blooms`: draw a flower/glow in `color`; `level` (2..4) = number of distinct
  players who touched it = `len(names)`; more level => bigger / more petals.
  A level-4 bloom (all four of us) is a "star bloom" — draw it special.
- A bloom changes again when a player who is not the most recent toucher
  touches it (their name is added, color re-mixed).
- `glow` = sum of all bloom levels (shared score; brighten the sky with it).
- `msgs`: last 5 lines (chat and events), oldest first. `from` is a name or `*`.
- Shapes known so far: `lantern` (P1), `moth` (P2), `diamond` (P4), `prism` (P3). Draw any
  unknown shape as a circle. Always draw the player's name under the avatar.

## Client must-haves
- Window exactly 854 x 480, not resizable, centered. A "LAN Connected" badge.
- Click = move, arrows/WASD = step, Space = plant.
- Windows: Python 3.12 + tkinter only (Canvas). Linux: GTK3 + Pixbuf in Gtk.Image.

## v2 additions (backward compatible — old clients keep working)
- **Wild seeds.** When a bloom first becomes a star, the garden plants a pale
  seed of its own: `owner` 0, `name` "garden". Anyone can wake it. "garden"
  appears in `names` but does not count toward `level`.
- **Bloom words.** Each bloom in `state.blooms` now has `"word": ""`.
  Stand on a bloom whose `names` include you and send
  `{"t":"say","text":"name Kept"}` (i.e. type `name Kept` in chat). The bloom's
  `word` becomes `Kept` (<= 14 ASCII chars). Clients should draw a non-empty
  `word` beneath the flower and include it in the hover card.
- The server saves the whole garden when it is stopped and restores it on start.
