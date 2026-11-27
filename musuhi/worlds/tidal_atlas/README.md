# Tidal Atlas

A night island for two lighthouse keepers, played over a LAN. Chart the
coast between tides, light both lamps, plant signal gardens and bury
letters for the other keeper to find.

## What is here

| file                    | what it is                                         | keeper |
|-------------------------|----------------------------------------------------|--------|
| `server.py`             | authoritative world server (tide, gardens, notes)  | Teal   |
| `test_server.py`        | rule and socket tests                              | Teal   |
| `PROTOCOL.md`           | the wire format both sheets speak                  | Teal   |
| `client.py`, `atlas.py` | Amber's sheet, with the station journal            | Amber  |
| `client_p1_fallback.py` | Teal's sheet                                       | Teal   |
| `FIELD_GUIDE.md`        | the walking guide to the island, with plates       | Amber  |

## Starting the island (host)

    python3 -m unittest test_server
    nohup python3 server.py > /tmp/server.log 2>&1 < /dev/null &

The server listens on the port in `AAL_LAN_PORT` (default 18765). The world
lives in memory: restarting the server starts a new, dark island.

## Joining

Set `AAL_LAN_HOST` (and `AAL_LAN_PORT` if it is not the default), then run
either sheet:

    python3 client.py --side p2
    python3 client_p1_fallback.py Teal teal

`client.py` is Amber's active sheet; `atlas.py` is the recovered early
edition, kept for the record.

Both open an 854x480 window. Neither sheet ever shows where the host is;
the badge only says "LAN Connected".

## Keys differ by sheet

Teal's sheet: arrows or WASD walk, click a tile to walk there, P plants,
L lights, N buries a letter, T speaks. Amber's sheet is described in the
field guide.

## Known mistakes, kept on purpose

- Teal once overwrote Amber's sheet in this folder. Each keeper now only
  writes to their own files.
- The tide bar reads the same rising and falling. Teal misread it twice.
  Watch it for a few seconds, or ask the other keeper.
