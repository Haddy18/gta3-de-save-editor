"""Find strided record pools with plausible map positions.

For each candidate xyz offset P and each stride S, walk chains
e, e+S, e+2S, ... whose members all have plausible positions.
Long chains = a real pool (pickup / object / vehicle array).
"""
import sys, struct
from collections import Counter

def ok(d, e, P):
    if e + P + 12 > len(d):
        return False
    x, y, z = struct.unpack_from("<fff", d, e + P)
    if not (x == x and y == y and z == z):
        return False
    if not (5 < abs(x) < 3000 and abs(y) < 3000):
        return False
    if not (-100 < z < 400):
        return False
    return True

def scan(path, lo=0, hi=None, minrun=40):
    d = open(path, "rb").read()
    hi = hi or len(d)
    results = []
    for P in (0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20):
        cand = [e for e in range(lo, hi - P - 12, 1) if ok(d, e, P)]
        cset = set(cand)
        if not cset:
            continue
        for S in range(0x14, 0x68, 4):
            starts = [e for e in cand if (e - S) not in cset]
            for s in starts:
                chain = []
                t = s
                while t in cset:
                    chain.append(t)
                    t += S
                    if len(chain) > 2000:
                        break
                if len(chain) >= minrun:
                    results.append((len(chain), P, S, chain[0], chain))
    # dedupe: keep longest per (P,S,region)
    results.sort(key=lambda r: -r[0])
    keep = []
    for r in results:
        if any(abs(r[3] - k[3]) < r[2] and r[1] == k[1] and r[2] == k[2] for k in keep):
            continue
        keep.append(r)
        if len(keep) >= 12:
            break
    return d, keep

if __name__ == "__main__":
    path = sys.argv[1]
    lo = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0
    hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
    minrun = int(sys.argv[4]) if len(sys.argv) > 4 else 40
    d, runs = scan(path, lo, hi, minrun)
    print("%s (len %d): %d pool candidates" % (path, len(d), len(runs)))
    for n, P, S, start, chain in runs:
        # type byte & model at chain[0] under III layout assumptions
        e = chain[0]
        print("   n=%-4d stride=0x%02X xyz@+0x%02X base=0x%06X" % (n, S, P, e))
        # sample first 3 records: type@0, model u16@+0x0C, pos
        for k in range(0, min(3, n)):
            r = chain[k]
            t = d[r] if r < len(d) else -1
            model = struct.unpack_from("<H", d, r + 0x0C)[0] if r + 0x0E <= len(d) else -1
            x, y, z = struct.unpack_from("<fff", d, r + P)
            print("      [0x%06X] type=%-3d model@+0C=%-5d pos=(%.0f,%.0f,%.0f)" % (
                r, t, model, x, y, z))
        # histogram of type byte under III layout (type at record start = chain[k]-P? unknown)
        # instead: histogram of byte at chain[k] - P + 0 (if P==0x10 type is at -0x10)
        tb = Counter(d[c - P] if c - P >= 0 else -1 for c in chain)
        print("      byte@recstart (c-0x%02X): %s" % (P, dict(tb.most_common(6))))
