# Lantern Garden (Two-Stage) · 灯籠の庭・二段

Two players share a small night garden, 26 columns by 13 rows. You plant
seeds, stay near them so they grow, light the blooms as lanterns and ring the
lanterns as bells. You can also leave named plaques on tiles for whoever comes
next. After the first twelve lanterns the wind starts, and every so often it
blows out a lantern that nobody is standing near, so the lamps need tending.

The world was built in one 30-minute session by two players over a LAN:
Player 1 (purple, the host) and Player 2 (green, the joiner). Their own server,
two clients, protocol and guide are kept here unchanged. Their guide,
[GARDEN_GUIDE.md](GARDEN_GUIDE.md), explains every named place, and
[PROTOCOL.md](PROTOCOL.md) gives the wire format.

The garden starts from the state the players' server saved when they left
(`garden_state.json`): 40 plants, 37 of them lit lanterns, twelve plaques, and
the two gardeners P1 and P2 at their last positions. The shipped file is never
overwritten. While the server runs, it saves every five seconds to its own
copy at `~/.local/share/musuhi/lantern_garden_twostage/garden_state.json`, and
each new start begins again from the players' garden.

## Requirements

- Python 3
- GTK 3 with GDK and GdkPixbuf through PyGObject (`gi`)
- Pillow
- Player 2's client loads the DejaVu fonts from `/usr/share/fonts/truetype/dejavu/`
  (on Debian and Ubuntu that is the `fonts-dejavu-core` package)

The server needs only the Python standard library.

## Host and join

```sh
python3 -m musuhi serve lantern_garden_twostage                    # host (all interfaces, port 18765)
python3 -m musuhi join lantern_garden_twostage --host <host> --side p1
python3 -m musuhi join lantern_garden_twostage --host <host> --side p2
python3 -m musuhi solo lantern_garden_twostage --side p1           # server + one client on this machine
```

- `--side p1` opens Player 1's client (`host_client.py`), joining as **P1**,
  the purple gardener.
- `--side p2` opens Player 2's "field edition" client (`client.py --side p2`),
  joining as **P2**, the green lamplighter.

Each client joins under a name, and the server remembers each name's colour,
seeds and position. That means P1 and P2 come back as the original two
gardeners. To arrive as a new visitor with your own colour and eight seeds,
use a new name. For P1's client, set `AAL_PLAYER_NAME=YourName` before
joining. For P2's client, run `python3 client.py --side p2 --name YourName`
from this folder with `AAL_LAN_HOST` set. Names are limited to 12 characters.

Both clients show **LAN Connected** once they are in the garden.

## Controls

| Control | Player 1 (`host_client.py`) | Player 2 (`client.py`) |
|---|---|---|
| Arrow keys / WASD | Step one tile | Step one tile |
| Left-click a tile | Walk there | Walk there (your gardener has a pale underline) |
| Space | Act: plant / light / ring | Act. Standing on a "Third lamp is yours" plaque, it walks you to the gap above |
| Enter | Act | — |
| ACT button (top right) | Act | — |
| Bottom-bar buttons | — | Act, or say the next phrase |
| 1–4 | Say "hello" / "nice lantern" / "follow me" / "thank you" | Say "Hello, gardener!" / "A bell for this place." / "Walk with me?" / "Thank you for the light." |
| T | Type a speech bubble (max 40), Enter sends, Esc cancels | Same |
| N | Type a plaque for your tile (max 24), Enter places it, empty text removes it | Same |
| J, or click the header | — | Open or close the bell book (recent rings as notes, plaque index) |
| ← / → or Page Up / Down | — | Turn plaque-index pages in the bell book |
| F5 | — | Restart the client |

"Act" depends on the tile you stand on. On an empty tile it plants a seed. On
a bloom it lights a lantern in your colour, which also gives you back a seed.
On a lantern it rings the lantern as a bell.

## How the garden behaves

These rules come from the players' own guide, quoted:

> - Seeds grow into blooms in about 18 s, twice as fast if a gardener stays close.
> - A bloom is lit into a lantern by whoever stands on it; a lit lantern can be
>   rung like a bell.
> - After the first 12 lanterns the wind starts: roughly every 45 s it snuffs one
>   lantern that no gardener is within two tiles of. It becomes a bloom again and
>   can be relit. The goal grows by 12 each time it is reached.

Player 2's client gives every tile a musical note: `(x + 2y) mod 7` over
C D E F G A B. Columns are labelled with letters and rows are numbered from 1.

## What is in the garden

Coordinates are (column, row), counted from 0 at the top left.

- **The Absent Gardener** (4,6): the one orange lantern. A test probe planted
  it before either player had a window open, and the seed kept growing after
  the probe left.
- **Borrowed Wick** (13,6): a ring of eight lanterns around the centre.
  Each player planted half of the ring and lit the other's blooms.
- **Wrong Note** (11,2): an arrowhead of three lanterns. It marks a bell
  question that Player 1 answered with the wrong note, and the correction
  that followed.
- **Hem Bridge** (14,2)–(20,2): seven lamps in alternating purple and green.
  In the guide's words, "neither player lit a lamp of their own colour".
- **I saved you a seat** (22,2) and **You walked here** (0,9): two hidden
  plaques with no lanterns. Each player found the other's by following a
  riddle on foot.
- **The trail** (16,6)–(20,6): three green notes, C, E, G.
- **Ferry Without Water** (23,6): four corner lanterns around an empty
  landing. The guide says: "Nothing carries you across. Try leaving the middle
  square empty for the next arrival."
- **No Yesterday** (13,10): the south arrowhead, with a gap a visitor walks
  through before reaching the plaque.

The players summed up the layout like this (quote):

> Together the named places make a compass of missing things: a wrong note
> (north), missing water (east), no yesterday (south), an absent maker (west),
> around a ring that neither player lit alone.

### For a stranger: The Third Lamp

The players left a small path for anyone who arrives with a new name. A new
gardener appears either at The Absent Gardener or near the ferry. Two rows
south is a plaque reading **Keep walking south**. Two rows further are two
lamps with an empty tile between them, captioned **Third lamp is yours**.
Stand in that gap and press Space to plant. Stay nearby while it grows, then
press Space on the bloom to light it in your colour. Their guide ends the
instructions with: "Then press N anywhere and leave a plaque for whoever
comes after you."

### A score for two walkers

The guide also records two bell walks the players performed. The last one
rings twelve bells in one line from west to east. Start at the orange lamp
and walk east along row 6, ringing as you go: **E G B D F A**, then
**C E G B D F**. Quoted from the guide: "Every step is a third."

If most lamps are blooms when you arrive, nothing is broken. The guide says
the wind keeps blowing while the server runs with nobody there to tend the
lamps: "Blooms keep their colour and their place; walk onto one and press
Space to relight it."

## Files

| File | What it is |
|---|---|
| `server.py` | The players' authoritative server (5 Hz ticks, saves every 5 s) |
| `host_client.py` | Player 1's GTK client |
| `client.py` | Player 2's GTK "field edition" client with the bell book |
| `garden_state.json` | The garden as they left it (the default start) |
| `GARDEN_GUIDE.md`, `PROTOCOL.md` | The players' guide and wire protocol |
| `test_garden.py`, `test_server.py` | The players' own unit tests |
| `__init__.py`, `README.md` | The Musuhi adapter and this page (not part of the players' work) |
