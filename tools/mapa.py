#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mapea la estructura del save: bloques zlib, regiones y posibles
copias duplicadas de los globals (¿GTASnP lee otra copia?)."""
import os, sys, struct, zlib

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, here)
from gta3_save_editor import GTA3Save, _u32

p = os.path.join(here, "samples", "referencia-sf1.sav")
data = open(p, "rb").read()
sav = GTA3Save(data)
gbase = sav.gbase
print("size=%d  gbase=0x%X  globals: 4385 vars -> 0x%X..0x%X" %
      (len(data), gbase, gbase, gbase + 4 * 4385))

# --- bloques zlib: inicio, fin comprimido, tamaño descomprimido ---
print("\n=== bloques zlib ===")
pos = 0
bloques = []
for magic in (b"\x78\x01", b"\x78\x9c", b"\x78\xda", b"\x78\x5e"):
    pos = 0
    while True:
        i = data.find(magic, pos)
        if i < 0:
            break
        pos = i + 1
        try:
            d = zlib.decompressobj()
            out = d.decompress(data[i:])
            out += d.flush()
        except zlib.error:
            continue
        consumed = len(data[i:]) - len(d.unused_data)
        if b"Globalvariables" in out[:64] or len(out) > 10000:
            bloques.append((i, consumed, len(out)))
            print("  @0x%06X comprimido=%d fin=0x%06X  descomprimido=%d%s" %
                  (i, consumed, i + consumed, len(out),
                   "  <-- contiene la tabla de nombres"
                   if b"Globalvariables" in out[:64] else ""))

# --- ¿hay una SEGUNDA copia de los globals? buscar el patrón de floats
#     ONE_SIXTEENTH=0.0625 (3d 00 00 00) seguido de los primeros flags ---
print("\n=== búsqueda de copias de los globals ===")
first = data[gbase:gbase + 64]
print("  plaintext @0x%X: %s" % (gbase, first[:32].hex()))
pat = first[:16]
pos = 0
while True:
    i = data.find(pat, pos)
    if i < 0:
        break
    print("  otra copia en 0x%06X" % i)
    pos = i + 1

# también dentro de los bloques descomprimidos
for (i, comp, size) in bloques:
    d = zlib.decompressobj()
    out = d.decompress(data[i:]) + d.flush()
    j = out.find(first[:16])
    print("  bloque 0x%X descomprimido: copia de globals en %s" %
          (i, ("offset %d" % j) if j >= 0 else "NO"))

# --- ¿dónde acaban los globals y qué hay alrededor? ---
end = gbase + 4 * 4385
print("\n=== en torno al final de los globals (0x%X) ===" % end)
for off in range(end - 16, end + 48, 4):
    print("  0x%06X: %08x  %d" % (off, _u32(data, off), _u32(data, off)))

# --- ¿el bloque zlib de nombres está ANTES de 0x120A4? ¿solapado? ---
print("\n=== primer bloque zlib @0xd9 ===")
d = zlib.decompressobj()
out = d.decompress(data[0xd9:]) + d.flush()
print("  descomprimido=%d, comprimido consumido=%d, fin=0x%X" %
      (len(out), len(data[0xd9:]) - len(d.unused_data),
       0xd9 + len(data[0xd9:]) - len(d.unused_data)))
print("  primeros bytes: %s" % out[:48])
