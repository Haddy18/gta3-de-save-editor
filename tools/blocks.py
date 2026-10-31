#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mapea la cadena de bloques del save DE (formato clásico III) y vuelca
Block 7 (Pickups) y Block 8 (Phone Info)."""
import os, sys, struct, re

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)

def u32(d, o):
    return struct.unpack_from("<I", d, o)[0] if 0 <= o + 4 <= len(d) else None

def mapa(path):
    d = open(path, "rb").read()
    print("\n##### %s (%d bytes)" % (os.path.basename(path), len(d)))
    # firmas conocidas -> nº de bloque
    known = {b"SCR\x00": 0, b"RST\x00": 9, b"RDR\x00": 10, b"ZNS\x00": 11,
             b"GNG\x00": 12, b"CGN\x00": 13, b"AUD\x00": 15, b"PTP\x00": 19}
    pos = {}
    for s, n in known.items():
        m = re.search(re.escape(s), d)
        if m:
            pos[n] = m.start()
    for n in sorted(pos):
        i = pos[n]
        print("  block %-2d firma @0x%06X  (sizes prev=%s next=%s)" %
              (n, i, u32(d, i - 4), u32(d, i + 4)))
    # volver atrás desde RST (block 9) para encontrar el final del block 8
    if 9 in pos:
        rst = pos[9]
        inner = u32(d, rst - 4)
        outer = u32(d, rst - 8)
        b9 = rst - 8
        print("\n  block 9 empieza @0x%06X (outer=%d inner=%d)" % (b9, outer, inner))
        # el bloque anterior termina en b9: leer su outer/inner
        in8 = u32(d, b9 - 4)
        out8 = u32(d, b9 - 8)
        b8 = b9 - 8 - in8
        print("  block 8 (Phone)  sizes @0x%06X (outer=%d inner=%d) -> data @0x%06X" %
              (b8, out8, in8, b8 + 8))
        n_phones = u32(d, b8 + 8)
        active = u32(d, b8 + 12)
        print("     phones=%s active=%s  (52 c/u => %d bytes)" %
              (n_phones, active, (n_phones or 0) * 52))
        # block 7 Pickups: termina en b8
        in7 = u32(d, b8 - 4)
        out7 = u32(d, b8 - 8)
        b7 = b8 - 8 - in7
        print("  block 7 (Pickups) sizes @0x%06X (outer=%d inner=%d) -> data @0x%06X" %
              (b7, out7, in7, b7 + 8))
        print("     inner=%d  => 336*28=%d + extra=%d" % (in7, 336 * 28, in7 - 336 * 28))
        return d, b7, b8, b9, pos
    return d, None, None, None, pos

d, b7, b8, b9, pos = mapa(os.path.join(here, "samples", "referencia-sf1.sav"))
if b7 is not None:
    print("\n=== Block 7 Pickups (primeras 12 entradas de 0x1C) ===")
    base = b7 + 8
    for k in range(12):
        e = base + k * 0x1C
        typ, picked, ammo, obji, regen, model, flags = struct.unpack_from(
            "<BBHIIhH", d, e)
        x, y, z = struct.unpack_from("<fff", d, e + 0x10)
        print("  #%3d type=%-3d picked=%d ammo=%-5d obj=%-6d regen=%-10d "
              "model=%-5d flags=0x%04x  pos=(%.1f, %.1f, %.1f)" %
              (k, typ, picked, ammo, obji, regen, model & 0xFFFF, flags,
               x, y, z))
