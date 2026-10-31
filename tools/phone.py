"""Cruza el bloque 8 (Phone Info, 49 x 52 B) de los 4 saves con las
banderas de misiones de telefono para ver que representa cada estado."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gta3_save_editor import GTA3Save, PICKUP_BLOCK, PHONE_BLOCK, PHONE_COUNT

PHONE_MISSIONS = [
    ("@TURISMO", "FLAG_DIABLO_MISSION2_PASSED"),
    ("DIABLO2",  "FLAG_DIABLO_MISSION2_PASSED"),
    ("DIABLO3",  "FLAG_DIABLO_MISSION3_PASSED"),
    ("DIABLO4",  "FLAG_DIABLO_MISSION4_PASSED"),
    ("MEAT1",    "FLAG_MEAT_MISSION1_PASSED"),
    ("MEAT2",    "FLAG_MEAT_MISSION2_PASSED"),
    ("MEAT3",    "FLAG_MEAT_MISSION3_PASSED"),
    ("MEAT4",    "FLAG_MEAT_MISSION4_PASSED"),
    ("@BLING",   "FLAG_YARDIE_MISSION2_PASSED"),
    ("YARDIE2",  "FLAG_YARDIE_MISSION2_PASSED"),
    ("YARDIE3",  "FLAG_YARDIE_MISSION3_PASSED"),
    ("YARDIE4",  "FLAG_YARDIE_MISSION4_PASSED"),
    ("HOOD1",    "FLAG_HOOD_MISSION1_PASSED"),
    ("HOOD2",    "FLAG_HOOD_MISSION2_PASSED"),
    ("HOOD3",    "FLAG_HOOD_MISSION3_PASSED"),
    ("HOOD4",    "FLAG_HOOD_MISSION4_PASSED"),
    ("HOOD5",    "FLAG_HOOD_MISSION5_PASSED"),
]

files = ["referencia-sf1", "referencia-sf7", "GTA3sf8", "GTA3sf9"]
saves = {}
for nm in files:
    p = "samples/%s.sav" % nm
    if os.path.exists(p):
        saves[nm] = GTA3Save(open(p, "rb").read())

# locate the phone block: right after the pickup block
for nm, sav in saves.items():
    assert sav.pickups is not None, nm
    base = sav.pickups + PICKUP_BLOCK
    n = struct.unpack_from("<I", sav.data, base + 4)[0]
    print("%s: phone block @0x%06X  n=%d" % (nm, base, n))
    for k in range(n):
        e = base + 8 + k * 52
        rec = sav.data[e:e + 52]
        # state byte seems at +0x2C (per localiza.py); dump non-zero words
        state = rec[0x2C]
        other = [b for b in rec[:0x2C] if b]
        print("   [%2d] state=%d  rest=%s" % (k, state, other[:10]))
    print()

# cross-reference: which flags are set in each save (phone missions only)
print("=== flags de misiones de telefono por save ===")
hdr = "%-10s" % "flag" + "".join("%-14s" % nm for nm in saves)
print(hdr)
seen = set()
for _, f in PHONE_MISSIONS:
    if f in seen:
        continue
    seen.add(f)
    row = "%-10s" % f.replace("FLAG_", "").replace("_PASSED", "")
    for nm, sav in saves.items():
        row += "%-14s" % sav.flag(f)
    print(row)
