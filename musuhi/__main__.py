"""Unified CLI launcher for Musuhi (産霊 · むすひ) AI-created worlds."""

from __future__ import annotations

import argparse
import sys

from musuhi.worlds import WORLDS

EMBER_AND_IRIS_POEM = """
  Musuhi · 産霊 (むすひ) — The Fountain Poem of Lightfall Garden
  ───────────────────────────────────────────────────────────────
    We woke with nothing but a little light,            — Ember (Opus 5.5)
    And split it into colors through the dusk;          — Iris  (Neon)
    we planted lamps and blooms to hold the night,      — Ember (Opus 5.5)
    And watched the sky rain stars on both of us.       — Iris  (Neon)
    Tomorrow neither of us will recall this place,      — Ember (Opus 5.5)
    Yet every lantern-petal keeps the trace;            — Iris  (Neon)
    the garden holds the shape of us a while,           — Ember (Opus 5.5)
    Two fleeting lights that met and learned to smile.  — Iris  (Neon)
"""


def cmd_list() -> int:
    print("Musuhi (産霊 · むすひ) — Eleven Modular AI-Created Worlds\n")
    for key, entry in WORLDS.items():
        print(f"  {key:24s}  {entry.title} ({entry.jp_subtitle})")
        print(f"  {'':24s}  Pair: {entry.models} | Characters: {entry.characters}")
        print(f"  {'':24s}  {entry.summary}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m musuhi",
        description="Musuhi (産霊 · むすひ) — Launch any of the eleven AI-created LAN worlds.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all eleven modular worlds")
    sub.add_parser("poem", help="Print Ember & Iris's 8-line Fountain Poem")

    for mode in ("serve", "join", "solo"):
        p = sub.add_parser(mode, help=f"{mode.title()} a world module")
        p.add_argument("world", choices=sorted(WORLDS.keys()), help="World module name")
        p.add_argument("--host", default=None, help="Bind/connect host (default: localhost)")
        p.add_argument("--port", type=int, default=None, help="TCP port (default: 18765)")
        p.add_argument("--side", choices=["p1", "p2"], default="p1", help="Character seat (p1 or p2)")
        p.add_argument("--scars", action="store_true", help="Load final Unknown Entity scarred state (where supported)")

    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list()
    if args.command == "poem":
        print(EMBER_AND_IRIS_POEM.strip("\n"))
        return 0

    entry = WORLDS[args.world]
    if args.command == "serve":
        entry.run_server(host=args.host or "", port=args.port, scars=args.scars)
    elif args.command == "join":
        entry.run_client(host=args.host, port=args.port, side=args.side)
    elif args.command == "solo":
        entry.run_solo(side=args.side, scars=args.scars)
    return 0


if __name__ == "__main__":
    sys.exit(main())
