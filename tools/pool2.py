"""Find structured pools (arrays of records with map positions) in a save.

For each candidate record-start offset P (position of xyz inside the record)
and stride S, look for long runs of consecutive records whose xyz look like
real map coordinates. A pickup/object/vehicle pool shows up as a long run.
"""
import sys, struct

def ok(d, e, P):
    if e + P + 12 > len(d):
        return False
    x, y, z = struct.unpack_from("<fff", d, e + P)
    if not (x == x and y == y and z == z):        # NaN
        return False
    if not (5 < abs(x) < 3000 and abs(y) < 3000):
        return False
    if not (-100 < z < 400):
        return False
    return True

def find_runs(path, lo=0, hi=None, minrun=50):
    d = open(path, "rb").read()
    hi = hi or len(d)
    best = []
    for P in (0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C):
        cand = [e for e in range(lo, hi - P - 12) if ok(d, e, P)]
        cset = set(cand)
        seen = set()
        for e in cand:
            if e - 1 in cset and (e - 1) in cset:
                # possible continuation; only start runs at non-continuations
                pass
            if e in seen:
                continue
            # walk back to run start
            s = e
            while (s - 1) in cset:
                s -= 1
            # walk forward
            n = 0
            t = s
            while t in cset:
                seen.add(t)
                n += 1
                t += 1
            if n >= minrun:
                best.append((n, P, s))
    best.sort(reverse=True)
    return d, best

if __name__ == "__main__":
    path = sys.argv[1]
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
    minrun = int(sys.argv[4]) if len(sys.argv) > 4 else 50
    d, runs = find_runs(path, lo, hi, minrun)
    print("%s  runs>= %d:" % (path, minrun))
    for n, P, s in runs[:20]:
        # stride guess: distance between consecutive members
        print("   n=%d  xyz@+0x%02X  start=0x%06X" % (n, P, s))
        # estimate stride from members
        cset = set()
        # recompute quickly
        mem = []
        t = s
        while ok(d, t, P) and len(mem) < n + 1:
            mem.append(t)
            t += 1
        if len(mem) > 1:
            gaps = [b - a for a, b in zip(mem, mem[1:])]
            from collections import Counter
            print("      gaps:", Counter(gaps).most_common(4))
