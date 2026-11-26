# Lightfall Garden — Protocol v1
TCP, newline-delimited JSON (UTF-8), one object per line. Port: AAL_LAN_PORT (default 18765).
World: grid W=21, H=10 tiles (render 40px tiles -> 840x400 canvas).
Tile chars: '.' grass, '~' water (blocked), '#' stone path, 'T' tree (blocked).

## Client -> Server
{"type":"hello","name":"Ember","role":"lantern"}   role: "lantern" | "prism"
{"type":"move","dx":0,"dy":-1}                     dx,dy in {-1,0,1}
{"type":"act"}        lantern: toggle lamp on own tile (place if none). prism: plant/cycle flower color on own tile.
{"type":"emote","emote":"wave"}                    wave|heart|star|laugh
{"type":"note","text":"hello"}                     leave a note on own tile (<=60 chars)
{"type":"chat","text":"hi"}                        <=80 chars, goes into log
{"type":"event","name":"aurora"}                   world event: aurora (toggle sky shimmer)

## Server -> Client
{"type":"welcome","id":"p1"}
{"type":"state","w":21,"h":10,"tiles":[...10 strings...],
 "players":{"p1":{"name":..,"role":..,"x":..,"y":..,"emote":"wave"|null,"emote_age":sec}},
 "lamps":[[x,y,lit],...], "flowers":[[x,y,color_idx],...],
 "notes":[[x,y,text,author],...], "aurora":false, "lit_count":n, "bloom_count":n,
 "log":[last 6 strings], "tick":n}
Flower colors idx 0..5: red, orange, yellow, green, cyan, violet.
State is broadcast after every change and every 1s.

## v2 additions
State also has "harmony" (lit lamps with a bloom in any of 8 neighbor tiles), "harmony_goal" (8),
and "lightfall" (true while harmony >= goal: draw falling stars). Garden persists in garden.json.
v3: "heart_stones": [[x,y],...] — permanent marks created when a keeper moves onto a tile another keeper occupies.
