#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Análisis rápido del save de referencia: globals + bloque STATS."""
import struct, sys, os, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gta3_save_editor import GTA3Save, _u32

REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "samples", "referencia-sf1.sav")

data = open(REF, "rb").read()
sav = GTA3Save(data)
gbase = sav.gbase
print("gbase = 0x%X  stats = 0x%X  playerinfo = 0x%X" %
      (gbase, sav.stats, sav.playerinfo))

# ---- globals con valor, filtrados por patrón -------------------------
pat = sys.argv[1] if len(sys.argv) > 1 else None

def gval(name):
    idx = sav.names.get(name)
    if idx is None:
        return None
    off = gbase + idx
    if off + 4 > len(data):
        return None
    return _u32(data, off)

if pat:
    rx = re.compile(pat, re.I)
    for name in sorted(sav.names, key=lambda n: sav.names[n]):
        if rx.search(name):
            print("%-45s idx=%-6d off=0x%06X  val=%d" %
                  (name, sav.names[name], gbase + sav.names[name], gval(name)))

# ---- bloque STATS entero ---------------------------------------------
print("\n=== STATS (idx: valor) ===")
for i in range(0, 140):
    try:
        v = sav.stat(i)
    except Exception:
        break
    print("  [%3d] +0x%03X = %d" % (i, i * 4, v))
