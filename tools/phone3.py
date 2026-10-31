"""Diff byte a byte del bloque 8 (Phone Info) entre los 4 saves.
Busca que bytes cambian y con que correlacionan (misiones de telefono)."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gta3_save_editor import GTA3Save, PICKUP_BLOCK

files = ["referencia-sf1", "referencia-sf7", "GTA3sf8", "GTA3sf9"]
saves = {}
for nm in files:
    p = "samples/%s.sav" % nm
    if os.path.exists(p):
        saves[nm] = GTA3Save(open(p, "rb").read())

blocks = {}
for nm, sav in saves.items():
    base = sav.pickups + PICKUP_BLOCK
    n = struct.unpack_from("<I", sav.data, base + 4)[0]
    blocks[nm] = sav.data[base + 8:base + 8 + n * 52]

names = list(blocks)
ref = blocks[names[0]]
print("registro = 52 B, 49 registros")
for nm in names[1:]:
    b = blocks[nm]
    diffs = [i for i in range(len(ref)) if ref[i] != b[i]]
    print("\n%s vs %s: %d bytes distintos" % (names[0], nm, len(diffs)))
    for i in diffs:
        rec, off = divmod(i, 52)
        print("   rec[%2d] +0x%02X: %s -> %s" % (
            rec, off, "%02x" % ref[i], "%02x" % b[i]))

# vuelco completo de registros que difieren, para ver el layout
print("\n=== registros que difieren (hex) ===")
seen = set()
for nm in names[1:]:
    b = blocks[nm]
    for i in range(len(ref)):
        if ref[i] != b[i]:
            rec = i // 52
            if rec in seen:
                continue
            seen.add(rec)
            r1 = ref[rec * 52:(rec + 1) * 52]
            r2 = b[rec * 52:(rec + 1) * 52]
            print("rec[%d] sf1 : %s" % (rec, r1.hex()))
            print("rec[%d] %-6s: %s" % (rec, nm, r2.hex()))
            # floats a 0,4,8 (posicion), 12,16,20 (rot?) y enteros
            f = struct.unpack_from("<6f", r1)
            print("   floats sf1: %s" % (["%.1f" % v for v in f],))
