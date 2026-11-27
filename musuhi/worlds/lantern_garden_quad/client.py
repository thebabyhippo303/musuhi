#!/usr/bin/env python3
"""Lantern Garden launcher: picks the right window toolkit per platform.

Windows -> tkinter client (client_tk.py)
Linux   -> GTK client (client_gtk.py)
Usage: python client.py --side p1|p2|p3|p4
"""
import sys


def main():
    if sys.platform.startswith("win"):
        from client_tk import main as tk_main
        tk_main()
    else:
        from client_gtk import main as gtk_main
        gtk_main()


if __name__ == "__main__":
    main()
