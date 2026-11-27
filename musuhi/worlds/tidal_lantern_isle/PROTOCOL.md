# Tidal Lantern Isle — LAN Protocol v1

Moonlit tidal garden. Two gardeners dig channels from the sea, the tide
pushes water up the channels, luminous reeds grow beside wet channels,
harvested glow becomes lanterns. Shared goal: raise the isle's LIGHT to the goal.

## Transport
- TCP, UTF-8, one JSON object per line (`\n` terminated).
- Server binds `""` on `int(os.environ.get("AAL_LAN_PORT", "18765"))`.
- Client connects to `(os.environ["AAL_LAN_HOST"], int(os.environ.get("AAL_LAN_PORT", "18765")))`.
- Never print / render addresses. Show "LAN Connected".

## Client -> Server
| msg | fields | meaning |
|---|---|---|
| `{"t":"hello","name":"P2"}` | name ≤ 12 chars | first message; server answers `welcome` |
| `{"t":"move","dx":1,"dy":0}` | dx,dy in -1/0/1, one axis | step one tile (also sets facing). Max ~10/s |
| `{"t":"act","a":"dig","x":5,"y":6}` | a = dig / fill / plant / harvest / lantern / unlantern | target tile must be within 1 tile (incl. diagonal, incl. own tile) of player |
| `{"t":"give","item":"seed"}` | item = seed / glow | give 1 item to another player within 2 tiles |
| `{"t":"emote","e":"wave"}` | e = wave / heart / dance / cheer / zzz | shows above player ~3 s |
| `{"t":"chat","text":"hi"}` | ≤ 60 chars | speech bubble + event log |
| `{"t":"ping"}` | | server answers `{"t":"pong"}` |

### Action rules
- `dig`: grass tile (no plant/lantern/player-other) -> channel `c`. Free.
- `fill`: channel -> grass.
- `plant`: grass tile, costs 1 seed. Reed starts at stage 0.
- `harvest`: reed at stage 3 -> removed, player gets +1 glow, +2 seeds. (stage<3: just uprooted, +1 seed back)
- `lantern`: grass tile, costs 2 glow. Permanent light.
- `unlantern`: pick lantern back up, +2 glow.
- Players walk on grass `g`, channel `c`, sand `s`; not on sea `w`, rock `r`, or lantern tiles.

## Server -> Client
- `{"t":"welcome","id":1,"w":22,"h":13,"proto":1}`
- `{"t":"note","text":"Need 2 glow"}` — private feedback for a rejected / notable action.
- `{"t":"pong"}`
- `{"t":"state", ...}` — full snapshot, 5 per second:

```json
{"t":"state","tick":123,
 "day":0.42,            // 0..1 day phase; 0.0 = dusk, 0.5 = deep night, 1.0 = wraps
 "tide":0.8,            // 0..1 tide level (sine, ~40 s period)
 "reach":9,             // channel tiles from the sea that are currently wet
 "tiles":["wwsgggg...", "... 13 strings of 22 chars ..."],
                        // w sea, s sand, g grass, c channel, r rock
 "wet":["0000110...", "... 13 strings, 1 = channel tile currently holding water"],
 "plants":[{"x":5,"y":6,"stage":2,"by":1}],     // stage 0 sprout .. 3 luminous
 "lanterns":[{"x":9,"y":4,"by":2}],
 "flies":[{"x":7.3,"y":2.1}],                    // fireflies (float tile coords), decorative
 "players":[{"id":1,"name":"P1","x":4,"y":5,"face":[1,0],"seeds":5,"glow":0,
             "emote":"wave","say":"hi","color":0}],   // emote/say are "" when idle
 "light":12,"goal":30,"level":1,                 // light = 3*lanterns + luminous reeds
 "log":["P1 planted a reed","Tide is rising"]    // last 6 world events, oldest first
}
```

Growth: once a second, every reed with a wet channel or sea tile in its 4-neighbourhood
grows; ~15 wet seconds from sprout to luminous. When `light >= goal`: log "The isle is lit!",
level += 1, goal += 30, everyone gets +3 seeds.

## Client UI suggestions (854x480)
- Map 22x13 tiles at 32 px = 704x416 at left/top; 150 px side panel (LAN Connected badge,
  seeds / glow, light bar, tide gauge, tool buttons); 64 px bottom strip (log, hints).
- Keys: arrows/WASD move; 1 dig, 2 fill, 3 plant, 4 harvest, 5 lantern (acts on faced tile);
  click a map tile within reach = use current tool there; E wave, H heart, G give seed.

## v1.1 additions (all additive — old clients keep working)
New fields in every `state` snapshot:
```json
 "critters":[{"kind":"koi","x":16,"y":6},{"kind":"heron","x":15,"y":5}],
 "signs":[{"x":9,"y":2,"text":"Heron Run","by":1}],
 "places":[{"name":"Moonwell","x":16.5,"y":6.0}],
 "ring":3
```
- **koi** (always 3): integer tile coords; they live in the Moonwell and swim into any wet
  ditch that touches it, moving about one tile per 0.6 s.
- **heron**: present only while `ring >= 5`, where `ring` = lamps standing within one tile
  of the Moonwell. Stands on a bank tile, hops to a new one every ~12 s. While it visits,
  island light gets +5. Log lines: "A heron landed by the Moonwell" / "The heron flew off".
- **signs**: wooden signposts with a few words. New client message:
  `{"t":"sign","x":9,"y":2,"text":"Heron Run"}` — tile within 1 of the keeper, on grass/sand,
  text ≤ 24 chars, max 16 signs; empty text removes the sign there. Signs don't block walking.
- **places**: fixed named spots for the map-label layer.
- Persistence: the world autosaves every 5 s and on shutdown; keepers get their position,
  seeds and glow back by name when they reconnect.

## v1.2 additions (additive)
- **Spring tide**: every third tide is a spring tide — `reach` peaks 6 tiles further inland.
  New snapshot field `"spring": true|false`; log line "A spring tide is rising".
- **Heron gift**: each time the heron hops on (~12 s), every keeper standing within two tiles
  of it gets +1 seed. Log line "The heron left P1 a seed".
