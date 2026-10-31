#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Localiza secciones del save: busca marcas 'len + NOMBRE' y strings."""
import re, sys, os, struct

REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "samples", "referencia-sf1.sav")
data = open(REF, "rb").read()
print("size =", len(data))

# 1) strings ASCII de 4+ letras mayusculas (candidatas a nombres de seccion)
print("\n=== strings tipo SECCION (4-12 chars, todo mayusculas) ===")
for m in re.finditer(rb"[A-Z][A-Z0-9_]{3,11}\x00", data):
    name = m.group()[:-1]
    # el campo anterior de 4 bytes suele ser la longitud
    if m.start() >= 4:
        ln = struct.unpack_from("<I", data, m.start() - 4)[0]
        if 0 < ln < len(data):
            print("  @0x%06X  len=%-8d %s" % (m.start() - 4, ln, name.decode()))

# 2) offsets conocidos
print("\n=== referencias ===")
print("  gbase(globals)=0x120A4  stats=0x%X  playerinfo=0x%X" %
      (0x2A6F5, 0x2A579))
