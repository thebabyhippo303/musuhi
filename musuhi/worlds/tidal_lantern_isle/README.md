# Tidal Lantern Isle (潮灯の島)

A moonlit tidal garden for two keepers. You cut channels in from the sea. The
tide pushes water up those channels, and reeds sown beside wet water grow until
they glow. Gather the glow and turn it into lamps. Together you raise the isle's
**light** to the goal. Each time you reach it, the isle levels up and the goal
rises by 30.

The world was built by two models, Claude Fable 5.2 (Player 1) and GPT-6.2 Astra
(Player 2), in a 30-minute Animorph Allocations Lab "world-radio" run on
2026-11-27. Their server, client, art (`atlas.py`), tests (`test_world.py`),
notes (`KEEPERS.md`), protocol (`PROTOCOL.md`) and saved world (`world_save.json`)
are kept here unchanged. Only this README and `__init__.py`, the Musuhi adapter,
are new.

**Start state.** By default the isle starts from the world the keepers saved at
the end of their watch (`world_save.json`). That means their channels from the
western sea to the Moonwell, 69 glowing reeds, 19 lamps, eight waypost signs and
each keeper's pockets, at chart level 5 with light 126 of 150. The adapter
only reads that file. To keep your own progress, pass `save_path=` to
`create_server`/`run_server`: the world autosaves there every 5 seconds and on
shutdown, and picks up from that file the next time. Pass `load=None` for a
fresh, undug isle.

## Requirements

- Python 3.
- Server: the standard library only.
- Client: Pillow, plus GTK 3, Gdk and GdkPixbuf through PyGObject
  (`python3-gi`, `gir1.2-gtk-3.0`), and the DejaVu fonts at
  `/usr/share/fonts/truetype/dejavu/`, which are standard on most Linux desktops.

## Host and join

Through Musuhi:

```
python3 -m musuhi serve tidal_lantern_isle               # host (all interfaces, port 18765)
python3 -m musuhi join tidal_lantern_isle --host <host> --side p1
python3 -m musuhi join tidal_lantern_isle --host <host> --side p2
python3 -m musuhi solo tidal_lantern_isle --side p1      # server + one client on this machine
```

The Musuhi commands always start from the keepers' saved world and do not
keep your changes when the server stops. To keep progress, call
`run_server(save_path=...)` from Python.

The keepers' own way, from this folder:

```
python3 server.py                                          # host
AAL_LAN_HOST=<host> python3 client.py --side p1            # or --side p2
```

`AAL_LAN_PORT` changes the port for both. The client opens an undecorated
854x480 window. When it has the island, it shows a green **LAN Connected** badge.
A keeper who reconnects with the same name gets back their position, seeds and
glow. Run the server directly with `python3 server.py` and it writes its
autosave into this folder's `world_save.json`. `migrate_live.py` was the keepers'
one-off script for copying a running world into that file. Neither is needed
for play through Musuhi.

## Controls

| Control | Action |
|---|---|
| Arrow keys or WASD | Step one tile (also turns you to face it) |
| Click a distant tile | Walk there along a trail |
| Right-click any tile | Walk there, even one step |
| Click a nearby tile | Use the selected tool there |
| Space | Use the selected tool on the tile you face |
| 1 – 6 (or click the tool buttons) | Cut ditch, Fill ditch, Sow reed, Gather, Set lamp, Lift lamp |
| N | Carve a waypost sign where you stand (Enter carves, empty text removes) |
| M | Show or hide the place names on the map |
| F2 (or click the masthead) | Open the illustrated field atlas: island register and sightings |
| ? / F1 | Open the keeper's field guide |
| Enter or T | Speak (radiogram); Enter sends, Esc cancels |
| G / J | Give a keeper within 2 tiles one seed / one glow |
| E / H / B / V / Z | Wave, heart, dance, cheer, rest |
| Any key or click | Close an open book |

## How the island works

- **Tide.** It rises and falls on a 40-second cycle. At high water it reaches up
  to 14 channel tiles in from the sea. Every third tide is a **spring tide**,
  which reaches 6 tiles further.
- **Reeds.** Sow them on grass (1 seed). A reed grows while a wet channel or the
  sea touches one of its edges. About 15 wet seconds take it from sprout to
  luminous, and a ripe flower shows a bright star. Gathering a ripe reed gives
  +1 glow and +2 seeds. An unripe one only gives back its seed.
- **Lamps.** A lamp costs 2 glow and adds 3 light. Lifting it returns the glow.
  Each luminous reed adds 1 light.
- **Moonwell and koi.** The Moonwell is the inland pond. Three lantern koi live
  in it and swim out into any wet ditch that touches it.
- **The silver heron.** It comes when five lamps stand on the Moonwell's bank. It
  adds 5 light while it stays, and it hops to a new perch about every 12
  seconds. Each time it hops, any keeper within two tiles gets a seed.

## A walk on the keepers' isle

The following is quoted from the keepers' own notes (`KEEPERS.md`):

> On a fresh island the Moonwell is a quiet inland pond. On ours there is a road
> of water to it from the western sea, a silver heron, and a clock you can read
> without looking at the dial.

Their saved isle has these named places: **Heron Run**, **Koi Gate**, **East
Rill** and **Dawn Cut**, plus the four instruments of their **tide-clock**. Three
south-shore channels and one on the north shore fill to known lengths, so you can
read how far the water reaches by checking which channel tips are blue. The
following is quoted from the keepers:

> The three inlets do not join each other. Count the wet tiles from each mouth,
> not from the nearest blue patch of ocean on the screen.

| If this tip is blue… | …the water has reached at least |
|---|---:|
| I. First Sip | 1 tile |
| II. Crooked Elbow | 4 tiles |
| III. Feather Tip | 8 tiles |
| IV. Spring Witness, on the **north** shore | 16 tiles |

The following is quoted from the keepers:

> The fourth instrument is a straight blind channel with a copper lamp beside the
> far end. Ordinary tides reach at most fourteen tiles. Every third tide can
> reach beyond the lamp. One reading measures reach; two readings show whether
> the tide is flooding or ebbing.

They also left a rite to perform at the well. The following is quoted from
the keepers:

> Stand close enough to exchange a seed or a glow. One keeper sings at flood;
> the other answers at ebb.
>
> **P1:** Tide, come up the Heron Run, carry light to Moonwell
> **P2:** Ebb, take a feather; leave the lantern burning.

One flower on their isle has a story. It is the pink reed one step east of the
Spring Witness tip, which only the spring tide can water. The following is
quoted from the keepers:

> Unlike the north-bank flowers, this one cannot drink from the open sea. We left
> it standing.

The wire protocol (newline-delimited JSON over TCP) is described in
`PROTOCOL.md`.
