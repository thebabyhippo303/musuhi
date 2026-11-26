# Afterlight

Two gardeners, six islands, one night sky. Lumen carries amber light in an
oversized midnight coat. Vela is a teal comet with a trail of sparks. A
lantern or a starbloom can change an island alone, but only the two
gardeners together can weave its aurora.

## Play

- Click a place in the garden or use arrows/WASD to move.
- **Tend** (Space) on an island. Lumen plants its lantern; Vela wakes its bloom.
- **Weave** (E) after both contributions are in place and both gardeners
  stand close together on the island.
- **Wave** (Q) to send a little hello into the dark.

Begin at Hearth at Rest. Restore the other islands in any order.
The connection badge and gardener names show who's present.

## Run

The host runs `python3 server.py`. Both machines use Python 3 with GTK3
and Pillow for `python3 client.py --seat 1` (Lumen, host) or
`python3 client.py --seat 2` (Vela, joiner). Configure `AAL_LAN_HOST`
on each client and use the same `AAL_LAN_PORT` on all three processes
(the port defaults to 18765).

The host keeps the current garden in memory. Closing a client does not
erase its work; stopping the host does.

Run the world and TCP tests with `python3 -m unittest -v test_server`.
The message format is in [PROTOCOL.md](PROTOCOL.md).
The [field guide](FIELD_GUIDE.md) tells the islands' stories; the
[gardeners' journal](JOURNAL.md) follows Lumen and Vela's first visit.
