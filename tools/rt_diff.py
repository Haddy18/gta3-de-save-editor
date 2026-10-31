"""Round-trip diff: read_state -> apply_state on an untouched save.
Shows which bytes change and what they are (global name / stats index)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gta3_save_editor import (GTA3Save, apply_state, MISSIONS, RAMPAGES, USJS,
                              ST_PORTLAND_PASSED)

data = open("samples/referencia-sf1.sav", "rb").read()
sav = GTA3Save(data)
st = sav.read_state()
apply_state(sav, st)
rt = sav.to_bytes()

diff = [i for i in range(min(len(data), len(rt))) if rt[i] != data[i]]
print("bytes changed:", len(diff), " same length:", len(data) == len(rt))

# group consecutive offsets into runs
runs = []
for i in diff:
    if runs and i == runs[-1][1] + 1:
        runs[-1][1] = i
    else:
        runs.append([i, i])

rev = {}
for nm, idx in sav.names.items():
    rev.setdefault(sav.gbase + idx, nm)

for a, b in runs:
    nm = rev.get(a, "?")
    stats_idx = (a - sav.stats) / 4 if sav.stats is not None else None
    sdesc = ""
    if stats_idx is not None and stats_idx == int(stats_idx) and 0 <= stats_idx < 200:
        sdesc = " stats[%d]" % int(stats_idx)
    before = data[a:b + 1].hex()
    after = rt[a:b + 1].hex()
    print("  0x%06X-0x%06X  %-34s%s  %s -> %s" % (a, b, nm, sdesc, before, after))
