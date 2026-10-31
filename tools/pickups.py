#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analiza el pool de Pickups (Block 7) de sf1 y sf8:
histórico de tipos/modelos, cuántos 'picked' por modelo, y alineación
de las entradas fijas (paquetes no se mueven)."""
import os, sys, struct, collections

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def find_pool(d, start=0x18CF0, end=None):
    """base del pool: última posición tal que las 28*400 primeras entradas
    sean (type<20, model<30000) coherentes con zeros al principio."""
    end = end or 0x22880
    best = None
    for base in range(start, end - 0x1C):
        # cuenta cuántas entradas seguidas tienen type<20 y model<30000
        run = 0
        while base + (run + 1) * 0x1C + 0x1C <= len(d):
            e = base + run * 0x1C
            if d[e] > 30:
                break
            run += 1
        if run >= 200 and (best is None or run > best[1]):
            best = (base, run)
    return best

def load(name):
    d = open(os.path.join(here, "samples", name + ".sav"), "rb").read()
    return d

def pool_entries(d, base, n):
    out = []
    for k in range(n):
        e = base + k * 0x1C
        typ, picked, ammo, obji, regen, model, flags = struct.unpack_from(
            "<BBHIIhH", d, e)
        x, y, z = struct.unpack_from("<fff", d, e + 0x10)
        out.append(dict(k=k, off=e, type=typ, picked=picked, ammo=ammo,
                        model=model, flags=flags, pos=(x, y, z)))
    return out

for name in ("referencia-sf1", "GTA3sf8"):
    d = load(name)
    b = find_pool(d)
    print("\n##### %s  pool @0x%X  (run=%s)" % (name, b[0], b[1]))
    ents = pool_entries(d, b[0], 336)
    hist = collections.Counter()
    picked_by = collections.Counter()
    types = collections.Counter()
    for x in ents:
        hist[x["model"]] += 1
        types[x["type"]] += 1
        if x["picked"]:
            picked_by[x["model"]] += 1
    print("  type histogram:", dict(sorted(types.items())))
    print("  modelos (model: total/picked):")
    for m in sorted(hist):
        print("    model %-5d : %3d / %3d" % (m, hist[m], picked_by[m]))
    tot = sum(1 for x in ents if x["picked"])
    print("  entradas con picked!=0: %d" % tot)

# ---- comparación directa por posición (paquetes fijos) -----------------
d1, d8 = load("referencia-sf1"), load("GTA3sf8")
b1 = find_pool(d1)[0]
b8 = find_pool(d8)[0]
e1 = pool_entries(d1, b1, 336)
e8 = pool_entries(d8, b8, 336)
print("\n=== alineación por posición (mismo model+pos en ambos) ===")
idx8 = {(round(x["model"]), round(x["pos"][0], 1), round(x["pos"][1], 1)): x
        for x in e8}
same = 0
diff_picked = collections.Counter()
for x in e1:
    key = (round(x["model"]), round(x["pos"][0], 1), round(x["pos"][1], 1))
    y = idx8.get(key)
    if y:
        same += 1
        if x["picked"] != y["picked"]:
            diff_picked[x["model"]] += 1
print("  entradas alineadas: %d" % same)
print("  modelos con 'picked' distinto entre sf1 y sf8:",
      dict(diff_picked))
