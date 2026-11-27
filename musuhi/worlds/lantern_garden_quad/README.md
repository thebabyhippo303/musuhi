# Lantern Garden

A shared night field for four players, one on each side: the **Lantern**
(P1), the **Moth** (P2), the **Prism** (P3) and the **Diamond** (P4; the
Linux window draws and calls it a kite). Each player walks, plants seeds and
touches things. In the gardeners' own words, from `PROTOCOL.md` (quoted):

> **A seed only blooms when a DIFFERENT player touches it.** A bloom keeps the
> names of everyone who has touched it and mixes their colors. Nothing finishes alone.

Linux and Windows windows share one garden. The four gardeners built two
windows that read the same world. One is a GTK 3 window drawn with Pillow
(`client_gtk.py`), used on Linux. The other is a tkinter window
(`client_tk.py`), which the Windows players used to join and which also
runs on Linux.

## Requirements

- Python 3 (the server and the tkinter window use only the standard library).
- For the GTK window: GTK 3 with GDK and GdkPixbuf through PyGObject, and Pillow.
- For the tkinter window: tkinter (Python 3.12 or newer on Windows).

## Host and join

Through Musuhi, start the garden on one machine and open a window on each
player's machine. Pick a different side (`p1` to `p4`) for each player:

```python
from musuhi import WORLDS
garden = WORLDS["lantern_garden_quad"]
garden.run_server(port=18765)                               # on the host
garden.run_client(host="<host>", port=18765, side="p3")     # on each player's machine
garden.run_client(host="<host>", port=18765, side="p4", toolkit="tk")   # force tkinter
garden.run_solo(side="p1")                                  # host and join on one machine
```

`run_client` opens the GTK window when PyGObject and Pillow are installed,
and the tkinter window otherwise. Pass `toolkit="tk"` or `toolkit="gtk"` to
choose one yourself. Windows has no PyGObject, so Windows players get the
tkinter window, as in the original game. The tkinter window was drawn for
Windows at 100% scaling; on a Linux HiDPI screen its text comes out too large
for the window, so use the GTK window there.

**Starting state.** By default the garden starts from the state the
gardeners saved at the end of their walk (`garden_state.json`). It has 28
blooms with their names and words, three pale seeds still asleep, the last
five lines spoken, and the place where each side last stood. That file is
only read and is never changed. The running garden writes itself to its own
save file every ten seconds and again when the server stops. The file is
`~/.local/share/musuhi/lantern_garden_quad/garden_state.json`, or the same
path under `$XDG_DATA_HOME`. To continue your own garden, pass that file as
`load=`. Pass `load=None` for an empty field, and `save=` to choose a
different save file.

The gardeners' own scripts also run directly from this folder. Run
`python3 server.py` on the host (it reads and writes `garden_state.json`
beside it). Then run `python3 client.py --side p1` (or `p2`, `p3`, `p4`) on
each player's machine, with `AAL_LAN_HOST` and `AAL_LAN_PORT` set as
`PROTOCOL.md` describes. Their launcher uses tkinter on Windows and GTK on
Linux. Their tests are in `test_server.py` (`python3 -m pytest test_server.py -q`).

## Controls

| Control | GTK window (Linux) | tkinter window |
|---|---|---|
| Walk to a point | Left-click | Left-click |
| Step 30 px | Arrow keys or WASD | Arrow keys or WASD |
| Plant a seed where you stand | Space, or the **Plant · Space** button | Space, P or E, right-click, or the **Plant** button |
| Speak | Enter, type, Enter (Esc cancels) | Enter or **Say / Name**, type, Enter (Esc cancels) |
| Name a bloom you helped make | Stand on it and say `name <word>` | Same |
| Quick lines | (none) | 1, 2, 3 |
| Read a flower's makers | Hover over it | (none) |

Each player can have up to eight seeds asleep at once. A seed wakes when
another player walks within 16 px of it. A bloom changes again whenever
someone other than its most recent toucher walks over it. That player's name
is added and the colour is remixed. When all four players' names are on one
flower it becomes a **star bloom**. The garden then plants a pale wild seed
of its own somewhere in the field, and anyone can wake it. The glow in the
sky is the sum of all bloom levels. It is a shared score.

## What is in the garden

The gardeners wrote a walk through it in `FIELD_GUIDE.md`. It starts like
this (quoted):

> Start at the two pale flowers in the southeast grass. The upper one is
> **Welcome**, first woken by the coral prism. The lower one is **Again**, first
> woken by the amber moth. Neither seed was planted by a player. The garden
> left them when two distant flowers became stars.

To the west is the green flower **Before**. It carries the names of two
short-lived test players, tA and tB, and the gardeners kept them. Three
star blooms carry compass words: **north**, **west** and **east**. In the northwest, four flowers on the hills spell a line.
Each word was a place one player chose and another player had to visit
(quoted):

> Someone / left / room / here.

A pale seed woke after the last word, and its word is **Someday**. Late in
the walk the gardeners played a silent game. They planted seeds without
saying where, and the finder named each bloom. That is how **Understory**,
**After**, **Found** and **Still** got their names. **Echo**, **Kept**,
**Return**, **Elsewhere** and **Hem** are in the field as well.

The guide also leaves a few things open for whoever comes next (quoted):

> The pale seed in the far northeast sky was left asleep on purpose, and
> without a name. If you wake it, the word is yours to choose.

> There was a place kept empty in our arc below **here**. It is yours if
> you want it.

## Files

| File | What it is |
|---|---|
| `server.py` | The gardeners' authoritative world server (asyncio, one JSON object per line) |
| `client.py` | Their launcher (tkinter on Windows, GTK on Linux) |
| `client_gtk.py` | The GTK 3 + Pillow window |
| `client_tk.py` | The tkinter window |
| `test_server.py` | Their tests for the server |
| `garden_state.json` | The garden as they left it |
| `PROTOCOL.md` | Their wire protocol (v1 plus the v2 wild seeds and bloom words) |
| `FIELD_GUIDE.md` | Their walk through the garden, with notes from the host, the windowmaker and the test-keeper |
| `__init__.py`, `README.md` | Added by Musuhi: the module adapter and this page |
