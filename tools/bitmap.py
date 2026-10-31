#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Busca estado por ítem de los 100 paquetes en la zona variable:
a) runs de >=90 bytes consecutivos con valor 0/1
b) runs de >=90 dwords 0/1
c) ventanas de 13 bytes cuyo popcount == nº de paquetes de ese save
"""
import os, sys, struct

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
from gta3_save_editor import GTA3Save, _u32

FILES = {"referencia-sf1": 66, "referencia-sf7": 66,
         "GTA3sf8": 29, "GTA3sf9": 66}

def popcount(b):
    return bin(b).count("1")

for name, npkg in FILES.items():
    p = os.path.join(here, "samples", name + ".sav")
    d = open(p, "rb").read()
    s = GTA3Save(d)
    print("\n=== %s (paquetes=%d, size=%d) ===" % (name, npkg, len(d)))

    # a) runs de bytes 0/1
    runs, start = [], None
    for i, b in enumerate(d):
        if b <= 1:
            if start is None:
                start = i
        else:
            if start is not None and i - start >= 90:
                ones = sum(d[start:i])
                runs.append((start, i - start, ones))
            start = None
    if start is not None and len(d) - start >= 90:
        runs.append((start, len(d) - start, sum(d[start:])))
    for st, ln, ones in runs:
        ones_in_100 = sum(d[st:st + 100])
        print("  bytes 0/1: @0x%06X len=%d ones=%d%s" %
              (st, ln, ones, "   <-- ones(100)=%d" % ones_in_100))

    # b) runs de dwords 0/1 (alineados a 4)
    runs, start = [], None
    n = len(d) // 4 * 4
    for off in range(0, n, 4):
        v = struct.unpack_from("<I", d, off)[0]
        if v <= 1:
            if start is None:
                start = off
        else:
            if start is not None and (off - start) // 4 >= 90:
                ones = sum(struct.unpack_from("<I", d, o)[0]
                           for o in range(start, off, 4))
                runs.append((start, (off - start) // 4, ones))
            start = None
    for st, cnt, ones in runs:
        print("  dwords 0/1: @0x%06X n=%d ones=%d" % (st, cnt, ones))

    # c) ventanas de 13 bytes con popcount == npkg
    hits = []
    for off in range(0, len(d) - 13):
        pc = sum(popcount(b) for b in d[off:off + 13])
        if pc == npkg:
            hits.append(off)
    print("  ventanas 13B con popcount==%d: %d hits -> %s" %
          (npkg, len(hits), ["0x%X" % h for h in hits[:12]]))
