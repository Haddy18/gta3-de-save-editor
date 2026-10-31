"""Dump the 0x34-stride pool found in VC saves and compare sf1 vs sf3."""
import sys, struct, os
from collections import Counter

def find_pool(d):
    """Locate the pool: chain of records with plausible xyz at +0x08, stride 0x34."""
    def ok(e):
        if e + 0x08 + 12 > len(d):
            return False
        x, y, z = struct.unpack_from("<fff", d, e + 0x08)
        return (x == x and 5 < abs(x) < 3000 and abs(y) < 3000 and -100 < z < 400)
    # candidate starts: any offset where next is +0x34 also ok, previous not ok
    best = None
    for e in range(0x24000, min(0x3F000, len(d) - 0x40)):
        if ok(e) and not ok(e - 0x34) and ok(e + 0x34):
            # grow
            n = 0
            t = e
            while ok(t):
                n += 1
                t += 0x34
                if n > 2000:
                    break
            if best is None or n > best[1]:
                best = (e, n)
    return best

def dump(path, base, nrec=4):
    d = open(path, "rb").read()
    print("--", os.path.basename(path), "base=0x%06X" % base)
    for k in range(nrec):
        r = base + k * 0x34
        rec = d[r:r + 0x34]
        print("   [0x%06X] %s" % (r, rec.hex()))
        # try interpret: u32s
        u = struct.unpack_from("<13I", d, r)
        print("        u32:", u)
        f = struct.unpack_from("<fff", d, r + 8)
        print("        f32@+8:", tuple(round(v, 1) for v in f))

if __name__ == "__main__":
    root = sys.argv[1]
    for fn in sorted(os.listdir(root)):
        p = os.path.join(root, fn)
        d = open(p, "rb").read()
        res = find_pool(d)
        if not res:
            print("%-16s NO POOL" % fn)
            continue
        base, n = res
        print("%-16s pool base=0x%06X n=%d" % (fn, base, n))
        # histogram of byte@+0 (type?), u16@+4, u16@+6 over alive records
        types = Counter()
        for k in range(n):
            r = base + k * 0x34
            if r + 0x34 > len(d):
                break
            types[d[r]] += 1
        print("      byte@+0 histogram:", dict(types.most_common(8)))
        # u16 at various offsets: find offset with many small "model-like" values
        for off in (2, 4, 6, 0x20, 0x22, 0x24, 0x26):
            c = Counter()
            for k in range(n):
                r = base + k * 0x34
                if r + off + 2 > len(d):
                    break
                c[struct.unpack_from("<H", d, r + off)[0]] += 1
            top = c.most_common(5)
            print("      u16@+0x%02X top: %s" % (off, top))
