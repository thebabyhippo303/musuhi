# Tidal Atlas (潮の地図帳)

A small night island for two lighthouse keepers, **Teal** and **Amber**, played
over a LAN. The tide comes in and goes out every minute. The keepers chart the
coast between tides, light the two lighthouses, plant signal gardens, and bury
letters for each other to find. In the keepers' own words (quoted from their
README):

> A night island for two lighthouse keepers, played over a LAN. Chart the
> coast between tides, light both lamps, plant signal gardens and bury
> letters for the other keeper to find.

The keepers wrote every file in this folder except this guide and
`__init__.py`, and those files are unchanged. That includes their own
`README.md`, `FIELD_GUIDE.md` (the walking guide, with its three plates in
`plates/`), `PROTOCOL.md` and `test_server.py`.

## Requirements

- Python 3
- PyGObject with GTK 3, GDK and GdkPixbuf, plus Pillow, for both sheets (the
  window is drawn with Pillow and shown in GTK)
- The server needs only the standard library

## Start state

The keepers kept no save file. Their world lives in memory, and their README
says so: "restarting the server starts a new, dark island". Every start
gives the same coastline with no footprints, gardens, letters or lit lamps.
The field guide ends on the same point:

> A fresh server starts with the same coastline but no footprints, letters or
> signal gardens. A new pair of keepers can give it a different history.

## Host and join

Each keeper has their own sheet (client window). Both open an 854x480 window
and both show only "LAN Connected", never the host's address.

| Seat | Keeper | Sheet the keepers used |
|---|---|---|
| `--side p1` | Teal (the host's keeper) | `client_p1_fallback.py Teal teal` |
| `--side p2` | Amber | `client.py --side p2` |

```
python3 -m musuhi solo tidal_atlas                  # server + Teal's sheet on this machine
python3 -m musuhi solo tidal_atlas --side p2        # server + Amber's sheet

python3 -m musuhi serve tidal_atlas --port 18765    # host
python3 -m musuhi join  tidal_atlas --host <host> --port 18765 --side p1
python3 -m musuhi join  tidal_atlas --host <host> --port 18765 --side p2
```

You can also run the keepers' scripts directly from this folder. Use
`python3 server.py` on the host, then set `AAL_LAN_HOST` (and
`AAL_LAN_PORT` if it is not 18765) and run either sheet.

## Controls

The two sheets use different keys. Their README says "Keys differ by sheet".

| Action | Teal's sheet (p1) | Amber's sheet (p2) |
|---|---|---|
| Walk one step | Arrows or WASD | Arrows or WASD |
| Walk to a tile | Click the tile | Click the tile |
| Plant a signal garden | P or Space, or the Plant button | G, or the Plant button |
| Light a lighthouse next to you | L, or the Light button | L, or the Light button |
| Bury a letter on dry ground | N, then type, then Enter | N, then type, then Enter |
| Speak to the other keeper | T or Enter, then type, then Enter | T, then type, then Enter |
| Cancel typing | Esc | Esc |
| Station journal | (none; the sheet shows the latest log lines) | J (↑ ↓ scroll, any other key closes) |

## Rules of the island

These come from `PROTOCOL.md` and `server.py`:

- The island is 24 x 12 tiles. Columns run A–X west to east and rows 1–12
  north to south. Each tile is sea, tidal flat, shore or high ground.
- The tide rises from 0.5 to 2.5 and falls back over 60 seconds. A tile is
  underwater when its height is below the tide. Little wavelets show which
  tiles are wet.
- With dry feet you cannot step onto a flooded tile. If the tide catches you,
  you can wade through it to get out.
- There are two lighthouses, the west light at E6 and the east light at T7.
  Stand beside one and light it.
- A signal garden grows through four stages, but only while its tile is dry.
- A buried letter stays hidden until the *other* keeper steps exactly on its
  tile. Then both keepers can read it. A hidden letter hums, and the hum gets
  louder the closer you are (three pips means within one tile). The keepers'
  warning: "three pips mean *very close*, not *found*. Step on the actual
  tile."
- The CHARTED figure is the share of walkable tiles that any keeper has
  stepped on.

## What the keepers left in the world

The island resets on each start, so their gardens and letters are not on the
map. `FIELD_GUIDE.md` records the first survey as a walk you can repeat on
the same coastline. It covers the west light at E6, the Margin headland, the
first letters at H8 and N3, **Second Sounding** at O7 (Amber's nine-garden
sail and Teal's nine-garden compass, which together look like a boat), Wader's
Shelf, the Hem along the south shore, and **Last Landing** at E3. E3 was the
last dark tile, and charting it brought the survey to 100%. The letter
buried there reads, as the guide quotes it:

> Last Landing: two readers finished the chart. Neither saw it all alone.

The guide also names the *elder gardens*. When a keeper rejoins, the gardens
planted before stay in place but are drawn in a different colour on each
sheet (rose on Amber's, silver on Teal's):

> You can disagree about their color and still meet beside the same flower.

`atlas.py` is an earlier edition of Amber's sheet. The keepers kept it "for
the record" and the module does not launch it. Their README also lists two
"known mistakes, kept on purpose". Teal once overwrote Amber's sheet, and
the tide bar looks the same whether the tide is rising or falling.
