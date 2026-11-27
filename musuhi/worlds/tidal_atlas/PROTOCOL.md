# Tidal Atlas - LAN Protocol

Night island, two lighthouse surveyors. One JSON object per line over TCP
(UTF-8, newline terminated). The server is authoritative. The client connects
to the host and port given by `AAL_LAN_HOST` / `AAL_LAN_PORT` (default port
18765). Never display the address; show "LAN Connected" instead.

## Client -> Server

| t       | fields            | effect                                               |
|---------|-------------------|------------------------------------------------------|
| `hello` | `name`, `color`   | must be first; server answers with `welcome`         |
| `move`  | `dx`, `dy`        | one step, each -1/0/1 (not both 0)                   |
| `plant` |                   | plant a signal garden on your tile (must be dry)     |
| `note`  | `text`            | bury a hidden note on your tile (max 80 chars, dry)  |
| `light` |                   | light a lighthouse within one tile of you            |
| `say`   | `text`            | chat line, appears in the shared log                 |

Unknown `t` values are ignored. Malformed lines get `{"t":"error","msg":...}`.

## Server -> Client

`welcome` (once): `id`, `w` (24), `h` (12), `elev` (list of `h` strings of
digits 0-3: 0 sea, 1 tidal flat, 2 shore, 3 high ground).

`state` (5 per second, full snapshot):

- `tick` - integer
- `tide` - float 0.5..2.5, 60 second cycle; a tile is flooded if `elev < tide`
- `players` - `[{id, name, color, x, y}]`
- `gardens` - `[{x, y, owner, stage}]`, stage 0..3, grows only while dry
- `notes` - `[{x, y, by, text}]` found notes only
- `lights` - `[{x, y, lit}]` the two lighthouses
- `charted` - percent of walkable tiles anyone has stepped on
- `chart` - `h` strings of 0/1, charted tiles
- `hum` - 0..3, how near you are to a hidden note that is not yours
  (3 = within 1 tile, 2 = within 3, 1 = within 6)
- `log` - last 5 event/chat strings

## Rules

- Sea (elev 0) is never walkable. Lighthouse tiles are solid.
- Dry feet cannot step onto a flooded tile. A surveyor caught by the tide may
  wade across flooded tiles to get out.
- Moves are rate limited (about 14 per second per player).
- A hidden note is found when a player other than its author steps exactly
  onto its tile. It then becomes visible to everyone.
