#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vuelca el bloque player-info y STATS ampliado: sf1 (66 pkgs) vs sf8 (29)."""
import os, sys, struct

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
from gta3_save_editor import GTA3Save, _u32

d1 = open(os.path.join(here, "samples", "referencia-sf1.sav"), "rb").read()
d8 = open(os.path.join(here, "samples", "GTA3sf8.sav"), "rb").read()
s1, s8 = GTA3Save(d1), GTA3Save(d8)
print("playerinfo: sf1=0x%X sf8=0x%X ; stats: sf1=0x%X sf8=0x%X" %
      (s1.playerinfo, s8.playerinfo, s1.stats, s8.stats))

# ---- player-info completo --------------------------------------------
print("\n=== player-info (sf1 | sf8) ===")
p1, p8 = s1.playerinfo, s8.playerinfo
for off in range(0, 0x180, 16):
    a = d1[p1 + off:p1 + off + 16]
    b = d8[p8 + off:p8 + off + 16]
    mark = "  <<<" if a != b else ""
    print("  +%03X  %s | %s%s" %
          (off, a.hex(" "), b.hex(" "), mark))

# ---- STATS ampliado ----------------------------------------------------
print("\n=== STATS idx 140..300 (sf1 | sf8) ===")
for i in range(140, 300):
    try:
        a = s1.stat(i)
        b = s8.stat(i)
    except Exception:
        break
    if a or b:
        print("  [%3d] +0x%03X = %8d | %8d%s" %
              (i, i * 4, a, b, "   <<<" if a != b else ""))
