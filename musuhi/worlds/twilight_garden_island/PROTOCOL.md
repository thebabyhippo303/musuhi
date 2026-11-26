# Twilight Garden-Island — LAN World Protocol

## Overview
- **World:** Twilight Garden-Island (*Lantern Isle*), logical world bounds `640 x 360` rendered inside an `854 x 480` GTK3 window.
- **Chosen Characters:**
  - **Solen (`p1`, Laptop Host):** Amber Star-Lantern keeper (`#ffb347`).
  - **Luma (`p2`, Mini PC Joiner):** Teal Lantern-Spirit keeper (`#3ee6d0`).
- **Transport:** Newline-delimited JSON (`\n`) over TCP.
  - Server binds `""` on `int(os.environ.get("AAL_LAN_PORT", "18765"))`.
  - Clients connect strictly to `(os.environ["AAL_LAN_HOST"], int(os.environ.get("AAL_LAN_PORT", "18765")))`.
  - Strict privacy: No network addresses, subnets, MACs, or interface names are ever logged, printed, or displayed.

## Client -> Server Messages
1. **Hello / Join:**
   `{"type": "hello", "id": "p1", "name": "Solen", "color": "#ffb347", "x": 230, "y": 185, "role": "Amber Star-Lantern"}`
2. **Move (relative or absolute):**
   `{"type": "move", "dx": 12, "dy": 0}` or `{"type": "move", "x": 260, "y": 190}`
3. **Plant Luminous Bloom / Lantern:**
   `{"type": "plant", "kind": "moonlily" | "starbloom" | "lantern"}`
4. **Leave Garden Note:**
   `{"type": "note", "text": "Two lanterns make a constellation."}`
5. **Emote / Light Pulse:**
   `{"type": "emote", "emote": "chime" | "sparkle" | "wave"}`
6. **Sky Shift:**
   `{"type": "sky", "sky": "twilight" | "aurora" | "meteor" | "dawn"}`

## Server -> Client Messages
- **Welcome (on connect / hello):**
  `{"type": "welcome", "you": "p1", "world_w": 640, "world_h": 360}`
- **Authoritative World State (10 Hz + immediate on actions):**
  ```json
  {
    "type": "state",
    "tick": 42,
    "world_w": 640,
    "world_h": 360,
    "sky": "twilight",
    "harmony": true,
    "players": {
      "p1": {"id": "p1", "name": "Solen", "color": "#ffb347", "x": 230.0, "y": 185.0, "emote": "", "speech": "", "role": "Amber Star-Lantern"},
      "p2": {"id": "p2", "name": "Luma", "color": "#3ee6d0", "x": 410.0, "y": 185.0, "emote": "chime", "speech": "", "role": "Teal Lantern-Spirit"}
    },
    "flowers": [{"id": 1, "x": 320.0, "y": 195.0, "kind": "moonlily", "by": "Luma", "color": "#7ef9ff"}],
    "notes": [{"id": 1, "x": 305.0, "y": 175.0, "text": "Hello from the shore", "by": "Solen"}],
    "events": ["Solen joined", "Luma planted moonlily"]
  }
  ```
