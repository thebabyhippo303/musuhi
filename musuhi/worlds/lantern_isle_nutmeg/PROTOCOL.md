# Lantern Isle — LAN Protocol v1

Cozy shared island garden. Two (or more) islanders walk a tile map, plant seeds,
water them, harvest petals, lay paths and light lanterns. Shared goal: raise the
island's **harmony** to 100 to summon the aurora.

## Transport
- TCP, newline-delimited JSON (one UTF-8 JSON object per `\n`-terminated line).
- Server binds `""` on `int(os.environ.get("AAL_LAN_PORT", "18765"))`.
- Client connects to `(os.environ["AAL_LAN_HOST"], int(os.environ.get("AAL_LAN_PORT", "18765")))`.
- Never print/log/render addresses. Show `LAN Connected` instead.

## World
- Grid `w=35`, `h=18`, suggested tile size 24 px (840x432 map + 48 px HUD = 854x480 window).
- Terrain chars in `tiles[y][x]`: `~` water, `s` sand, `.` grass, `#` rock, `T` tree.
- Walkable: `s` and `.` only. Buildable (plant/path/lantern): `.` and `s`... plants need `.`.

## Client -> Server
| msg | fields | notes |
|---|---|---|
| `hello` | `name` (<=12 chars) | first message; server replies `welcome` |
| `move` | `dx`,`dy` in -1..1 | one step; rate-limited to ~8 steps/s |
| `act` | `a`, optional `x`,`y` | target defaults to player's own tile; must be within 1 tile (Chebyshev) of player |
| `emote` | `e`: `wave` `heart` `laugh` `star` | shown above player ~3 s |
| `say` | `text` (<=60 chars) | speech bubble ~5 s, also in log |
| `ping` | | server replies `{t:"pong"}` |

`act.a` values:
- `plant` — costs 1 seed; target must be empty grass. Creates `sprout`.
- `water` — wets a plant (speeds growth) for ~20 s.
- `harvest` — target must be `flower`; gives +2 petals, +1 seed, flower removed (+1 island bloom count stays).
- `path` — free; places a `path` on empty grass/sand.
- `lantern` — costs 3 petals; places a `lantern` on empty grass/sand/path.
- `clear` — removes any object on target (refunds nothing).

## Server -> Client
`welcome`: `{t:"welcome", id, w, h, tile, tiles:[h strings], proto:1}`

`state` (5 per second, full snapshot):
```
{t:"state", tick, time,            # time: 0..1 day phase (0=dawn, .25=noon, .5=dusk, .75=midnight)
 night: bool,
 players: {id: {name, x, y, color:[r,g,b], seeds, petals, emote, say, face}},
 objs: [{x, y, k, wet}],           # k: sprout|bud|flower|path|lantern
 flies: [[x,y],...],               # fireflies (float tile coords), only at night near lanterns
 harmony: 0..100, blooms: int, aurora: bool,
 log: [last 6 strings]}
```
`emote`/`say` are `""` when inactive. `face` is last move dir `[dx,dy]`.

`err`: `{t:"err", msg}` for rejected actions (also fine to ignore).

## Rules
- Growth: sprout -> bud -> flower. Each stage ~12 s dry, ~5 s when wet. Lanterns within 2 tiles let plants grow at night (otherwise plants sleep at night).
- Harmony = min(100, 4*flowers + 6*lanterns + 1*paths(max 10) + 2*blooms(harvested, max 20)).
- Aurora = harmony >= 100 (sky event; clients render shimmering bands).
- Each player starts with 5 seeds, 0 petals. Everyone gets +1 seed every 20 s (max 9).
- A full day lasts 120 s.

## v2 additions (backward compatible — extra `state` fields)
- `rain: bool` — a soft shower every ~70–110 s lasting ~14 s; every plant is watered while it rains.
- `critters: [{x, y, k:"fox", name:"Nutmeg", mood:"walk"|"nap"|"happy"}]` — Nutmeg the fox wanders by day,
  naps beside the nearest lantern at night. Send `emote` `heart` within 2 tiles: Nutmeg turns `happy`
  and fetches you +1 seed (12 s cooldown).
- World persistence: the server saves the isle (objects, blooms, clock, keeper pouches by name) every
  3 s and on shutdown, and restores it on start. Returning keepers get "<name> returns to the isle."
- `welcome.proto` is now `2`.
- `critters[].friends: {keeperName: gifts}` — who has befriended Nutmeg and how many seeds she has fetched them.
  First heart logs "<name> befriends Nutmeg the fox!", later ones "Nutmeg the fox brings <name> a seed."

## v3: chapters
- When raw harmony reaches the goal, `aurora` is true for 40 s (harmony shows 100). When it fades a star is
  named: `stars += 1`, `chapter = stars + 1`, and the goal grows (`goal = 100 + 50*stars`).
- `harmony` stays 0..100 (= raw*100/goal). Extra fields: `stars`, `chapter`, `goal`, `raw`.
- Each star also raises the path cap (+5) and the bloom cap (+10) in the harmony formula.
- Clients may draw `stars` named stars in the night sky.
- `sky: [{name, by}]` — one entry per named star. Whatever a keeper last `say`s while the aurora is up
  (first 18 chars) becomes the new star's name; otherwise the isle picks one (Lumen, Petalwake, Foxfire...).
  Log: `Star "<name>" is named by <keeper>. Chapter N begins.`
- Keeper colours are now stable per name across rejoins.
- C->S `{t:"name_star", i, name}` — (re)name star `i` (0-based, must exist; name <= 24 chars). State also carries
  `star_names: [..]` (same order as `sky`). Log: `<keeper> names star N "<name>".`
- Greeting duet: when two keepers within 3 tiles both `emote` `wave` within ~4 s, a wildflower (full `flower`)
  springs up between them (30 s cooldown). Log: `<A> and <B> wave hello. A wildflower springs up between them!`
- Applause: when a keeper `emote`s `star` while another keeper within 6 tiles has a speech bubble up and stands
  within 2 tiles of a lantern, the speaker earns +1 petal (8 s cooldown).
  Log: `<A> applauds <B>'s verse by lantern light. A petal drifts down.`
- Chimes: C->S `{t:"chime", n}` with `n` 0..4. Each player carries `note` (0..4 for ~1.5 s, else -1) and the state
  carries `tune`: the last 8 notes as `[{n, by}]`. When the last five notes run 0,1,2,3,4 and at least two keepers
  played in the run, every plant is watered and the tune resets.
  Log: `<A> and <B> ring the five chimes in turn. The isle hums along and every leaf drinks.`
