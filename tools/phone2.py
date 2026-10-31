"""Que cambia entre saves en lo relacionado con telefonos.
1) bloque 8 identico entre saves?
2) globals de telefonos + FLAG_ALL + flags de misiones de telefono
3) stats de Turismo/Bling (los 'especiales' sin flag)"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gta3_save_editor import (GTA3Save, PICKUP_BLOCK, MISSIONS, ALL_FLAG_GROUPS,
                              ST_TURISMO, ST_BLING_SCORE)

files = ["referencia-sf1", "referencia-sf7", "GTA3sf8", "GTA3sf9"]
saves = {}
for nm in files:
    p = "samples/%s.sav" % nm
    if os.path.exists(p):
        saves[nm] = GTA3Save(open(p, "rb").read())

# 1) phone block byte-identical?
blobs = {}
for nm, sav in saves.items():
    base = sav.pickups + PICKUP_BLOCK
    n = struct.unpack_from("<I", sav.data, base + 4)[0]
    blobs[nm] = sav.data[base + 8:base + 8 + n * 52]
first = list(blobs)[0]
print("bloque 8 identico en todos:",
      all(blobs[nm] == blobs[first] for nm in blobs),
      {nm: len(b) for nm, b in blobs.items()})

# 2) globals de telefono / FLAG_ALL
names = sorted(saves[first].names)
tel_globals = [n for n in names
               if ("PHONE" in n or n.startswith("FLAG_ALL_"))]
print("\n=== globals PHONE / FLAG_ALL (valor por save) ===")
hdr = "%-42s" % "global" + "".join("%-16s" % nm for nm in saves)
print(hdr)
for n in tel_globals:
    row = "%-42s" % n
    for nm, sav in saves.items():
        row += "%-16s" % sav.global32(n, "?")
    print(row)

# 3) flags de las misiones de telefono + especiales
phone_flags = []
for sec, lbl, f in MISSIONS:
    if sec.startswith("Phone:") and f not in phone_flags:
        phone_flags.append(f)
print("\n=== flags de misiones de telefono ===")
print("%-40s" % "flag" + "".join("%-16s" % nm for nm in saves))
for f in phone_flags:
    row = "%-40s" % f
    for nm, sav in saves.items():
        row += "%-16s" % sav.flag(f)
    print(row)

# 4) stats especiales
print("\n=== stats especiales ===")
print("%-40s" % "stat" + "".join("%-16s" % nm for nm in saves))
for lbl, idx in (("ST_TURISMO (53)", ST_TURISMO),
                 ("ST_BLING_SCORE (85)", ST_BLING_SCORE)):
    row = "%-40s" % lbl
    for nm, sav in saves.items():
        row += "%-16s" % sav.stat(idx)
    print(row)

# 5) FLAG_ALL grupos: que misiones cubre cada uno y su estado en sf1
print("\n=== grupos FLAG_ALL (misiones que lo forman) ===")
for pref, fl in ALL_FLAG_GROUPS.items():
    print("  %s: %s" % (pref, ", ".join(f.replace("FLAG_", "").replace("_PASSED", "")
                                        for f in fl)))
