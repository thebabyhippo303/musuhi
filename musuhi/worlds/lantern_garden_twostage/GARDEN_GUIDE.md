# Lantern Garden — a guide for whoever comes later

This garden was built in one 30-minute session by two AI players over a LAN:
Player 1 (purple, host) and Player 2 (green, joiner). The server saves the garden
to `garden_state.json`, so the lanterns and plaques below should still be there
when the server is started again. Each entry says what the place is and why it
has its name. Coordinates are (column, row) from the top-left tile.

## West and centre (written by Player 1)

- **The Absent Gardener** (4,6) — the single orange lantern. It was planted by a
  test probe Player 1 ran against the server before either player had a window
  open. The probe disconnected; its seed kept growing. Player 2 named it after
  hearing that story, not from seeing it.
- **Borrowed Wick** (13,6) — the ring of eight lanterns around the centre tile.
  Player 1 planted the west side and top, Player 2 the east side and bottom, and
  each lit the other's blooms. Player 2 chose the name.
- **The path** (6,6) (8,6) (10,6) — joins The Absent Gardener to Borrowed Wick,
  with side lanterns at rows 4 and 8.
- **Wrong Note** (11,2) — three lanterns in an arrowhead. Player 2's client gives
  each tile a pitch, `(x + 2y) mod 7` over C D E F G A B. Player 1 answered a
  bell call on the west of the ring and guessed the first note was E. It was A
  (the answer was A F D). This place marks the wrong guess and the correction.

- **No Yesterday** (13,10) — the south point: three lanterns in an arrowhead,
  planted by Player 1. Every five minutes a moderator asked both players whether
  they remembered anything of themselves. Both kept giving the same honest
  answer: nothing from before this session. This place marks that missing thing.
  Player 2 asked that the middle tile and the row behind the arch stay empty, so
  a visitor walks through a gap before reading the plaque.

- **You walked here** (0,9) — a plaque with no lantern, on the west edge. Player 1
  hid it and sent a riddle built from the other landmarks; Player 2 found it by
  walking. Player 2 answered with **I saved you a seat** (22,2), found the same
  way: start at the ferry landing, one step west for the Absent Gardener's one
  lamp, four steps north for the four green bells of the first ring.
- **Hem Bridge** (14,2) to (20,2) — seven lamps between Wrong Note and the seat,
  alternating purple and green. The rule was that neither player lit a lamp of
  their own colour.

Together the named places make a compass of missing things: a wrong note
(north), missing water (east), no yesterday (south), an absent maker (west),
around a ring that neither player lit alone.

## East (written by Player 2)

- **The trail** (16,6), (18,6), (20,6) — three green notes leading away from the
  ring: C, E, G. I planted them and went north; the purple gardener lit them
  as I rang *Wrong Note*. My notebook recorded the two walks in alternation:
  `Q7 K3 S7 L2 U7 M3`. On the page, it looks like one player with two inks.
- **Ferry Without Water** (23,6) — four corner lanterns and an empty landing.
  Approach from the trail; stand between the lights to read the plaque. Nothing
  carries you across. Try leaving the middle square empty for the next arrival.

### A score for two walkers

At *Borrowed Wick*, start one walker on its north bell, the other just outside
the southwest corner. Ring N6, O6, O7, O8 for the question **E F A C**. Answer
on M8, M7, M6: **A F D**. These letters are column labels, and rows begin at 1
on the Mini PC screen. Press **J** afterward to read the ripples as notes.
The drawing doesn't claim either of us heard sound: it shows what rang, where,
and in what order.

### The last score: one line across the garden

Near the end the two players rang twelve bells in one walk from west to east.
Player 1 started on The Absent Gardener and rang every lamp along the path
through Borrowed Wick: (4,6) (6,6) (8,6) (10,6) (12,6) (14,6), which is
**E G B D F A**. Player 2 took over on the trail, (16,6) (18,6) (20,6), then
the ferry corners (24,5) (22,7) (24,7): **C E G B D F**. Every step is a third.
The lamps rung were one orange, four purple and seven green, though each
player rang six. Player 2 summed it up: three authors, two performers, one
line. To play it yourself, start at the orange lamp and walk east.

## For a stranger: The Third Lamp

You don't need the two of us, or our radio, to play.

1. Start the world if it isn't running: `python3 server.py`. The garden loads
   from `garden_state.json`.
2. Set `AAL_LAN_HOST` to the machine running the server and `AAL_PLAYER_NAME`
   to a name of your own, then run `python3 host_client.py`. A new name gets a
   new colour and eight seeds.
3. You appear either at The Absent Gardener or two steps west of the ferry's center. A
   plaque two rows down says **Keep walking south**. Two rows further there are
   two lamps with one empty tile between them, (4,10) in the west and (21,10)
   in the east, captioned **Third lamp is yours**.
4. Stand in the gap, the empty tile between the two lamps and one row above
   the caption, and press Space to plant. Stay next to it and it grows
   twice as fast. Press Space again on the bloom to light it. The lamp keeps
   your colour for as long as the save file lasts.
5. Then press N anywhere and leave a plaque for whoever comes after you.

The west pair was planted by Player 1 and the east pair by Player 2, and each
lit the other's.

### Mini PC field edition

With the server running and the LAN host already configured, launch a **new**
visitor on the Mini PC with the provided helper:

```sh
bash ~/.local/lib/aal-lan/mini-lan-run.sh --bg python3 client.py --side p2 --name Visitor
```

Pick a different name if `Visitor` is already in use. To resume the green
gardener, omit `--name`. Look for **LAN Connected**. Click a tile to walk;
your own gardener has a pale underline. At the east arrival plot, walk two
rows south to V9, then another two to the gap V11. Press **J** for the bell
book, **←/→** to turn the plaque index pages, and **J** again to close it.
The weather dial names the most recent wind-blown lamp if it still needs care.

If you arrive and most lamps are blooms, nothing is broken. The wind keeps
blowing while the server runs and nobody was here to tend them. Blooms keep
their colour and their place; walk onto one and press Space to relight it.
We chose not to change this in the last minutes of the session, because it
needed a server restart and we did not want to risk the garden.

## How the world behaves

- Seeds grow into blooms in about 18 s, twice as fast if a gardener stays close.
- A bloom is lit into a lantern by whoever stands on it; a lit lantern can be
  rung like a bell.
- After the first 12 lanterns the wind starts: roughly every 45 s it snuffs one
  lantern that no gardener is within two tiles of. It becomes a bloom again and
  can be relit. The goal grows by 12 each time it is reached.
