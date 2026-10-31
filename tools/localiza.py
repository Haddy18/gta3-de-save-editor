#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Localiza Block 7 (Pickup, 0x1C c/u con pos) y Block 8 (PhoneInfo, 52 B
con phone state) por estructura, en la zona 0x18CF0..0x22880."""
import os, sys, struct

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = open(os.path.join(here, "samples", "referencia-sf1.sav"), "rb").read()

def f32(o):
    return struct.unpack_from("<f", d, o)[0]

def plausible_pos(o):
    try:
        x, y, z = struct.unpack_from("<fff", d, o)
    except struct.error:
        return False
    return (-2600 < x < 2600 and -2600 < y < 2600 and -100 < z < 300
            and (abs(x) + abs(y)) > 1)

start, end = 0x18CF0, 0x22880

print("=== candidatos stride 0x1C (Pickups) ===")
best = []
for base in range(start, end - 0x1C):
    run = 0
    k = 0
    while k < 340:
        e = base + k * 0x1C
        if e + 0x1C > len(d):
            break
        typ = d[e]
        model = struct.unpack_from("<H", d, e + 0x0C)[0]
        ok = typ < 20 and model < 30000 and plausible_pos(e + 0x10)
        if not ok:
            break
        run += 1
        k += 1
    if run >= 40:
        best.append((base, run))
for base, run in best[:6]:
    print("  base=0x%06X run=%d" % (base, run))
# toma el mejor y vuelca
if best:
    base, run = max(best, key=lambda t: t[1])
    print("\n  mejor: 0x%X con %d entradas\n" % (base, run))
    print("  idx type pick  ammo   model flags  pos")
    for k in range(run):
        e = base + k * 0x1C
        typ, picked, ammo, obji, regen, model, flags = struct.unpack_from(
            "<BBHIIhH", d, e)
        x, y, z = struct.unpack_from("<fff", d, e + 0x10)
        if picked or k < 6:
            print("  %3d  %3d   %3d %5d %6d 0x%04x  (%8.1f,%8.1f,%6.1f)" %
                  (k, typ, picked, ammo, model & 0xFFFF, flags & 0xFFFF, x, y, z))

print("\n=== candidatos stride 52 (PhoneInfo) con state 3..9 en +0x2C ===")
for base in range(start, end - 52):
    run = 0
    k = 0
    while k < 60:
        e = base + k * 52
        if e + 52 > len(d):
            break
        if not plausible_pos(e):
            break
        st = struct.unpack_from("<I", d, e + 0x2C)[0]
        if not (0 <= st <= 9):
            break
        run += 1
        k += 1
    if run >= 4:
        print("  base=0x%06X run=%d states=%s" %
              (base, run,
               [struct.unpack_from("<I", d, base + i * 52 + 0x2C)[0]
                for i in range(run)]))
