#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agrupa los nombres de variables por familia (prefijo + sufijo numérico).
Busca familias de ~100 (paquetes), ~20 (rampages/saltos), ~14 (teléfonos)."""
import os, re, collections

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = open(os.path.join(here, "tools", "globales.tsv"),
            encoding="utf-8", errors="replace").read().splitlines()[2:]
fams = collections.defaultdict(list)
for line in rows:
    p = line.rstrip("\r").split(",")
    if len(p) < 4:
        continue
    name = p[1]
    m = re.match(r"^(.*?)(\d+)$", name)
    if m:
        fams[m.group(1)].append(int(m.group(2)))
    else:
        fams[name].append(None)

print("=== familias con >= 12 miembros numerados ===")
for pref, idxs in sorted(fams.items()):
    nums = sorted(i for i in idxs if i is not None)
    if len(nums) >= 12:
        print("  %-38s n=%-4d %s..%s" %
              (pref, len(nums), nums[0], nums[-1]))
