#!/usr/bin/env python3
"""Convert Instagram numeric media ids to shortcodes.
Usage: python3 -I shortcode.py 4020836893606321669 [more ids...]
Verified: 4020836893606321669 -> DfM4dn3MJ4F
"""
import sys

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def shortcode(media_id):
    n, s = int(media_id), ""
    while n:
        n, r = divmod(n, 64)
        s = ALPHABET[r] + s
    return s


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(arg, shortcode(arg.split("_")[0]))
