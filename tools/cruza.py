#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cruza los 4 saves reales: busca variables cuyo valor correlacione
con paquetes (66/66/29/66), rampages (9/9/4/9) o misiones (68/60/3/60)."""
import os, sys

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
from gta3_save_editor import GTA3Save, _u32

FILES = ["referencia-sf1", "referencia-sf7", "GTA3sf8", "GTA3sf9"]
saves, datas = {}, {}
for n in FILES:
    p = os.path.join(here, "samples", n + ".sav")
    if os.path.exists(p):
        datas[n] = open(p, "rb").read()
        saves[n] = GTA3Save(datas[n])
names = [n for n in FILES if n in saves]
print("saves:", names)

def gval(n, var):
    i = saves[n].names.get(var)
    if i is None:
        return None
    return _u32(datas[n], saves[n].gbase + i)

# valores objetivo
TARGETS = {
    "paquetes":  {"referencia-sf1": 66, "referencia-sf7": 66,
                  "GTA3sf8": 29, "GTA3sf9": 66},
    "rampages":  {"referencia-sf1": 9, "referencia-sf7": 9,
                  "GTA3sf8": 4, "GTA3sf9": 9},
    "misiones":  {"referencia-sf1": 68, "referencia-sf7": 60,
                  "GTA3sf8": 3, "GTA3sf9": 60},
    "intentos":  {"referencia-sf1": 75, "referencia-sf7": 67,
                  "GTA3sf8": 6, "GTA3sf9": 67},
}

allnames = sorted(set().union(*[set(saves[n].names) for n in names]))
for label, tgt in TARGETS.items():
    print("\n=== globals que valen exactamente el patrón de %s ===" % label)
    for var in allnames:
        vals = {n: gval(n, var) for n in names}
        if all(vals[n] == tgt.get(n) for n in names):
            print("   %-40s %s" % (var, [vals[n] for n in names]))

# también: stats con ese patrón
print("\n=== stats con el patrón de paquetes (66/66/29/66) ===")
for idx in range(0, 140):
    try:
        vals = [saves[n].stat(idx) for n in names]
    except Exception:
        break
    if vals == [66, 66, 29, 66]:
        print("   stats[%d] = %s" % (idx, vals))

# teléfono: flags en los 4 saves
print("\n=== flags de misiones de teléfono / especiales por save ===")
interesting = [v for v in allnames if v.startswith("FLAG_") and
               any(k in v for k in ("DIABLO", "MEAT", "YARDIE", "HOOD",
                                    "TURISMO", "BLING", "RC"))]
for var in sorted(interesting):
    vals = [gval(n, var) for n in names]
    print("   %-40s %s" % (var, vals))
