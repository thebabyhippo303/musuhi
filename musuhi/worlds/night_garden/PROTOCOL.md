# Night Garden — Protocol

TCP, newline-delimited UTF-8 JSON, one object per line. World is 854x480 px.

Client -> server:
- `{"t":"hello","name":"lantern"|"prism"}`  (must be first)
- `{"t":"move","x":X,"y":Y}`   absolute position (clamped to the world)
- `{"t":"plant","x":X,"y":Y}`  plant a seed (max 40 seeds, min 18px apart)
- `{"t":"chat","text":"..."}`  short note shown above your light (<=60 chars)

Server -> client:
- `{"t":"welcome","id":N}`
- `{"t":"state","tick":K,"players":[{id,name,x,y,color,chat}],
   "seeds":[{x,y,stage,kind,glow}],"fireflies":[{x,y}],"ripples":[{x,y,r}],
   "pond":{"x":427,"y":300,"rx":90,"ry":40},"blooms":B}`  ~10 per second

Rules:
- A seed (stage 0) sprouts to stage 1, then 2, while any light is within 70px
  (about 1.5s of light per stage).
- Stage 3 (full bloom) only happens when BOTH lights are within 90px of the seed
  at once. The bloom kind mixes the planters: "amber", "spectrum", or "hybrid".
- Each full bloom releases a firefly that drifts around the garden.
- Walking a light into the pond makes ripples.
