# Emberglow Isle · First visit

Moss has a pouch of seeds. Wick has eight lanterns. Neither can grow a garden alone.

Walk up to a flag and its line appears on the field wire. Look for a second flag
nearby: the keepers take turns starting and finishing a couplet. If you would
rather find the next line on foot, leave the verse book closed.

## Open the isle

Use a Python 3 installation with GTK 3, GdkPixbuf 2, PyGObject, and Pillow.
In the supplied LAN environment, start the server once on the laptop:

```
python3 server.py
```

In a separate terminal, open Moss's window:

```
python3 client.py --side p1
```

Open Wick's window on the Mini PC using the supplied launcher:

```
bash <local-helper> --bg python3 client.py --side p2
```

Both keepers should see **LAN Connected**. Their windows are 854 × 480.
The server saves the garden, named keepers' last positions, and ordered flags
in `world_save.json`; a client can close and rejoin.

## In the field

| Input | What it does |
|---|---|
| Click grass, trail or sand | Walk to that tile |
| Arrows / WASD | Take one step; interrupt a longer walk |
| E / Space | Moss plants on grass or sand; Wick sets down or picks up a lantern |
| R | Ring the shrine from a neighboring tile. Two nearby keepers play a duet. |
| H | Cycle through wave, heart, dance and glow |
| N | Write a flag (40 characters). Enter pins it, Esc cancels. |
| J | Read the recent field wire |
| V | Open *Field verses*. Use left/right or the page buttons. Click a line or map pin to walk there. |
| P | Open the illustrated petal key. The captions separate reconstructed colors from witnessed ones. |

The labeled controls at the foot of the chart are clickable.

## A game for two

One keeper makes a shape without saying its name. The other walks around it,
then says what they saw. Only then does the first keeper say what they drew.
An opening in a ring of flowers can be a doorway to someone on foot and a
harbor to someone looking out to sea.
