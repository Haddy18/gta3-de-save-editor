#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pool de Pickups localizado por posiciones plausibles (stride 0x1C)."""
import os, sys, struct, collections

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def plausible(d, o):
    if o + 0x1C > len(d):
        return False
    typ = d[e0] if False else None
    return True

def find_pool(d, start=0x18CF0, end=0x22880):
    best = None
    for base in range(start, end - 0x1C):
        run = 0
        while base + (run + 1) * 0x1C <= len(d):
            e = base + run * 0x1C
            if d[e] >= 20:
                break
            x, y, z = struct.unpack_from("<fff", d, e + 0x10)
            if not (-2600 < x < 2600 and -2600 < y < 2600 and -100 < z < 300
                    and abs(x) + abs(y) > 1):
                break
            run += 1
        if run >= 40 and (best is None or run > best[1]):
            best = (base, run)
    return best

def entries(d, base, n):
    out = []
    for k in range(n):
        e = base + k * 0x1C
        typ, picked, ammo, obji, regen, model, flags = struct.unpack_from(
            "<BBHIIhH", d, e)
        x, y, z = struct.unpack_from("<fff", d, e + 0x10)
        out.append(dict(k=k, off=e, type=typ, picked=picked, ammo=ammo,
                        model=model, flags=flags, pos=(x, y, z)))
    return out

def load(n):
    return open(os.path.join(here, "samples", n + ".sav"), "rb").read()

data = {n: load(n) for n in ("referencia-sf1", "referencia-sf7",
                             "GTA3sf8", "GTA3sf9")}
pools, allents = {}, {}
for n, d in data.items():
    b = find_pool(d)
    pools[n] = b
    allents[n] = entries(d, b[0], 340)
    print("%-16s pool base=0x%X run=%d" % (n, b[0], b[1]))

d = data["referencia-sf1"]
ents = allents["referencia-sf1"]
print("\n=== sf1: histograma model: total / picked (model>=100) ===")
hist = collections.Counter()
pk = collections.Counter()
typ = collections.Counter()
for x in ents:
    hist[x["model"]] += 1
    typ[(x["type"], x["model"])] += 1
    if x["picked"]:
        pk[x["model"]] += 1
for m in sorted(hist):
    if hist[m] > 1 or pk[m]:
        print("  model %-6d total=%-4d picked=%-4d" % (m, hist[m], pk[m]))
print("  type counts:", collections.Counter(x["type"] for x in ents))
print("  total picked:", sum(1 for x in ents if x["picked"]))

# ---- comparación por modelo/posición con sf8 ---------------------------
e8 = allents["GTA3sf8"]
key = lambda x: (x["model"], round(x["pos"][0], 1), round(x["pos"][1], 1),
                 round(x["pos"][2], 1))
idx8 = {}
for x in e8:
    idx8.setdefault(key(x), []).append(x)
print("\n=== sf1 vs sf8: entradas con la misma clave (model+pos) ===")
cnt = collections.Counter()
difs = collections.Counter()
for x in ents:
    ys = idx8.get(key(x))
    if ys:
        y = ys[0]
        cnt[x["model"]] += 1
        if x["picked"] != y["picked"]:
            difs[x["model"]] += 1
print("  modelos comunes con 'picked' distinto:", dict(difs))
for m in sorted(cnt):
    print("    model %-6d comunes=%-4d difieren=%d" % (m, cnt[m], difs[m]))
