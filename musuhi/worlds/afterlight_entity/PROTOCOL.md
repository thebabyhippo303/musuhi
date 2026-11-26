# Afterlight LAN protocol

Send one UTF-8 JSON object per newline over TCP; each line is at most
4 KiB. The client uses `AAL_LAN_HOST` and `AAL_LAN_PORT` (default port
18765), without logging endpoint information.

| Client message | Meaning |
| --- | --- |
| `{"type":"join","seat":1}` | First message. Seat 1 is Lumen; seat 2 is Vela. |
| `{"type":"move","dx":-1,"dy":0}` | Walk one 18-pixel step; each axis is −1, 0 or 1. |
| `{"type":"goto","x":427,"y":236}` | Move to the clicked canvas position (integer pixels). |
| `{"type":"tend"}` | Light a lantern (Lumen) or wake a starbloom (Vela). |
| `{"type":"weave"}` | Weave the aurora at the current island, together. |
| `{"type":"wave"}` | Send a visible greeting. |

The host broadcasts a complete `state` on join, leave, and recognized
actions. `revision` increases with these updates. No polling is needed.
`players` always has both `"1"` and `"2"`; each has `name`, `x`, `y`,
`online`, and a cumulative `waves` counter. Each item in `islands` has
`id`, `name`, `x`, `y`, `rx`, `ry`, `lantern`, `bloom`, and `woven`.
The latter three fields are booleans. `message` is safe display text.
Coordinates are in the 854×480 canvas; the walkable area spans
x=24..830 and y=92..380. Motion is clamped to that area.

An island can be tended within its ellipse. An aurora requires both
contributions, two online gardeners within that ellipse, and no more
than 96 pixels between them. A failed action explains why in `message`.
Contributions survive disconnects while the host process stays up. A
rejected join receives `{"type":"error","message":"..."}` before close.
