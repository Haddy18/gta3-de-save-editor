#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compara los 4 saves reales: globals relevantes + diffs por regiones."""
import os, sys, struct

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
from gta3_save_editor import GTA3Save, _u32

saves = {}
for n in ("referencia-sf1", "referencia-sf7", "GTA3sf8", "GTA3sf9"):
    p = os.path.join(here, "samples", n + ".sav")
    if os.path.exists(p):
        saves[n] = open(p, "rb").read()

print("=== globals clave por save ===")
keys = ["NUMBER_OF_PACKAGES_COLLECTED", "TOTAL_RAMPAGES_PASSED",
        "TOTAL_COMPLETED_USJ", "PASSED_USJ_COUNTER", "USJ_NUMBER",
        "DIABLO_PHONE", "MEAT_PHONE", "YARDIE_PHONE", "HOOD_PHONE",
        "RAY_PHONE1", "RAY_PHONE2", "RAY_PHONE3", "RAY_PHONE4",
        "PACKAGES_COLLECTED", "PACKAGE_NUMBERS",
        "FLAG_YARDIE1_PASSED", "FLAG_DIABLO1_PASSED",
        "FLAG_HOOD1_PASSED", "FLAG_MEAT1_PASSED"]
parsed = {}
for name, d in saves.items():
    s = GTA3Save(d)
    parsed[name] = s
    vals = []
    for k in keys:
        i = s.names.get(k)
        v = _u32(d, s.gbase + i) if i is not None else None
        vals.append("%s=%s" % (k.split("_")[0] if k not in ("NUMBER_OF_PACKAGES_COLLECTED",
                 "TOTAL_RAMPAGES_PASSED", "TOTAL_COMPLETED_USJ") else k, v))
    print("\n%s: pkgs_global=%s playerinfo+0x13=%d stats[28]=%d stats[47]=%d" %
          (name, s.global32("NUMBER_OF_PACKAGES_COLLECTED"),
           _u32(d, s.playerinfo + 0x13), s.stat(28), s.stat(47)))
    for k in keys:
        i = s.names.get(k)
        if i is not None:
            print("    %-32s = %s" % (k, _u32(d, s.gbase + i)))

# ---- diffs por regiones de 4KB ---------------------------------------
print("\n=== regiones con diferencias entre sf1 y sf7 ===")
names = list(saves)
a, b = saves[names[0]], saves[names[1]]
print("(%s vs %s, size %d/%d)" % (names[0], names[1], len(a), len(b)))
if len(a) == len(b):
    blocks = {}
    for off in range(0, len(a)):
        if a[off] != b[off]:
            blocks.setdefault(off // 0x1000, 0)
            blocks[off // 0x1000] += 1
    for blk in sorted(blocks):
        print("  0x%05X-0x%05X : %d bytes distintos" %
              (blk * 0x1000, blk * 0x1000 + 0xFFF, blocks[blk]))
