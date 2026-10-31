"""Round-trip check: read_state -> apply_state -> compare bytes."""
import sys, os, importlib.util

here = os.path.dirname(os.path.abspath(__file__))
main, = sys.argv[1:2]
spec = importlib.util.spec_from_file_location("ed", os.path.join(here, main))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

for fn in sorted(os.listdir(os.path.join(here, "samples"))):
    p = os.path.join(here, "samples", fn)
    data = open(p, "rb").read()
    sav = m.GameSave(data, p)
    st = sav.read_state()
    m.apply_state(sav, st)
    out = sav.to_bytes()
    diff = [i for i in range(min(len(data), len(out))) if data[i] != out[i]]
    print("%-16s len %d->%d  changed=%d" % (fn, len(data), len(out), len(diff)))
    if diff:
        runs = []
        s = diff[0]; prev = diff[0]
        for i in diff[1:]:
            if i == prev + 1:
                prev = i
            else:
                runs.append((s, prev)); s = i; prev = i
        runs.append((s, prev))
        for a, b in runs[:25]:
            print("    0x%06X-0x%06X (%d bytes)  %r -> %r" % (
                a, b, b - a + 1, data[a:b + 1][:24], out[a:b + 1][:24]))
        if len(runs) > 25:
            print("    ... %d more runs" % (len(runs) - 25))
