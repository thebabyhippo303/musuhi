# The Afterlight Garden

A small two-player sky garden. Wick, an amber lantern on legs, sets
lanterns. Mote, a teal sprite, plants starflowers. Leave a mark from each
character, then both tend the Heartseed at the central terrace to wake it.
Afterward, shape the garden however you like; the bloom stays.

## Play

Run `python3 server.py` on the host. Run `python3 client.py wick` and
`python3 client.py mote` on the two playing machines with the LAN
environment already configured. The window's **LAN Connected** badge
indicates that your character has joined; the gardener count shows
whether the other player has joined. The garden lives in server memory.

| Input | Action |
| --- | --- |
| Arrows / WASD, movement buttons | Move a tile |
| Click a tile | Take one step toward it |
| Space / P, Place | Place your character's mark where you stand |
| G, Signal | Send a greeting the other player can see |
| T, Tend | Offer care from the Heartseed tile or any adjacent tile |
| L, Legend | Show or hide the two gardeners' [legend](LEGEND.md) |

The little dashes in the sky are stepping points as well as the tiles
on each terrace. Both gardeners can cross the gaps.

The game uses Python 3, GTK3/PyGObject and Pillow. Run
`python3 -m unittest -v` from the project directory for world rules and
two-peer synchronization tests. See [PROTOCOL.md](PROTOCOL.md) for the
wire contract.

Wick and the server: Laptop collaborator. Mote and the original GTK
client and character artwork: Mini PC collaborator. Both shaped the
terraces in play.
