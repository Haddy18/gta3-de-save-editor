#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GTA III - The Definitive Edition :: 100% save editor

Loads a .sav, shows the GTASnP 100% checklist (missions, phones,
import/export, collectibles) with a checkbox per item, recalculates the
percentage (x/154), the missions done (x/73) and every derived counter,
and writes the file with a correct MD5 header seal (without it the game
shows an empty slot without any error).

Standard library only. No dependencies.

Format (verified against 4 saves written by the game itself):
  seal      = NOT(MD5( first 24 bytes zeroed + file[24:] )) at 0x08..0x17
  globals   = offset = base + Index,  base = position of b"SCR\\x00" + 0x14
              (Index comes from the two zlib name tables shipped by the
              save itself: "//Globalvariables V2 ...")
  stats:    block located by its constants (154 / 20 / 20 / 73)
  packages: "player info" block (found by walking the block chain
            backwards from stats): counter at +0x13, total at +0x17
  I/E garages = garage block: header +0x18 (Portland) and +0x1C
                (Shoreside), bits LSB first
  I/E crane    = crane block (4 blocks forward from garages),
                 dword at +0x04, 7 bits LSB first
  pickups:     Block 7 = [size=9492][Pickup[336] * 0x1C][84 B ring],
                 the phone block [2608][49] starts right after it.
                 Hidden packages = type 5 / model 1321, rampages =
                 type 3 / model 1392. Collecting one means the game
                 frees the slot (type=0, byte+1=1) and deletes its
                 object: there is NO per-item flag anywhere else,
                 which is why GTASnP keeps reporting them missing if
                 only the counter/flags are edited.
  objects:     Block 4 = [size = 4+n*84][n][CObject * 84], chained
                 between Vehicles and Path Find (its end + Path Find
                 has to land on the cranes block). Every live pickup
                 has its object here, so collecting drops both.

GUI:   python gta3_save_editor.py
Tests: python gta3_save_editor.py --selftest
"""

import hashlib
import math
import os
import re
import struct
import sys
import zlib

# ---------------------------------------------------------------- constantes

# Firefighter/vigilante/packages: GTASnP reads the script's GLOBALS (not
# the stats), and the I/E deliveries live in the per-car "SLOT" globals.
# The editor writes both so the game and the web agree:
#   NUMBER_OF_PACKAGES_COLLECTED       packages (0-100)
#   IND/COM/SUB_FIRES_EXTING           firefighter per island
#   IND/COM/SUB_COPCAR_KILLS           vigilante per island
#   INDUSTRIAL_SLOT1..16 (+_GARAGE_SLOTS_FILLED)   Portland Docks
#   SUBURBAN_SLOT1..16  (+_GARAGE_SLOTS_FILLED)    Shoreside Vale
#   EARNED_FREE_FLAMETHROWER           firefighter reward (>=20 on all 3)
#   CRAN_ACTIVATED_BEFORE              emergency crane completed
G_PKG = "NUMBER_OF_PACKAGES_COLLECTED"
G_FIRES = ("IND_FIRES_EXTING", "COM_FIRES_EXTING", "SUB_FIRES_EXTING")
G_VIG = ("IND_COPCAR_KILLS", "COM_COPCAR_KILLS", "SUB_COPCAR_KILLS")
G_IE = {
    "ie_pdx": ("INDUSTRIAL_SLOT%d", "INDUSTRIAL_GARAGE_SLOTS_FILLED"),
    "ie_ssv": ("SUBURBAN_SLOT%d", "SUBURBAN_GARAGE_SLOTS_FILLED"),
}
G_FLAME = "EARNED_FREE_FLAMETHROWER"
G_CRAN = "CRAN_ACTIVATED_BEFORE"

# --- Block 7 (Pickups) + Block 4 (Objects) -----------------------------
# Packages and rampages only exist physically: a Pickup entry plus its
# Object. "Collected" = the entry is freed (type=0, +1=1, rest zeroed)
# and the object is deleted, so both sides (game and GTASnP) have to be
# edited together. The rest of the entry has to be cleared too: a slot
# marked free that still names the package/rampage model is read back as
# uncollected (that is how the map kept showing the rampages).
PICKUP_BLOCK = 9492        # 336 * 0x1C + 84 (collected-index + ring)
PICKUP_SIZE = 0x1C
PICKUP_COUNT = 336
PHONE_BLOCK = 2608         # Block 8 size, follows the pickup block
PHONE_COUNT = 49
PKG_TYPE, PKG_MODEL = 5, 1321
RAMPAGE_TYPE, RAMPAGE_MODEL = 3, 1392
OBJECT_SIZE = 84

SEAL_OFF = 0x08          # 16-byte seal in the header
SEAL_LEN = 16

# 0-based indices into the stats block (byte offset = index * 4)
ST_PROGRESS       = 28   # 0x70  current progress
ST_PROGRESS_TOTAL = 29   # 0x74  total (154)
ST_ATTEMPTS       = 46   # 0xB8  attempts
ST_MISSIONS       = 47   # 0xBC  missions done
ST_TAXI           = 48   # 0xC0  taxi fares
ST_TURISMO        = 53   # 0xD4  best Turismo time (seconds)
ST_AMBULANCE      = 60   # 0xF0  people rescued (ambulance)
ST_VIGILANTE      = 61   # 0xF4  vigilante criminals
ST_PARAMEDIC      = 62   # 0xF8  max paramedic level
ST_FIRES          = 63   # 0xFC  fires extinguished
ST_JUMPS_FOUND    = 44   # 0xB0  unique jumps found
ST_JUMPS_TOTAL    = 45   # 0xB4
ST_RAMPAGES       = 66   # 0x108 rampages passed
ST_RAMPAGES_TOTAL = 67   # 0x10C
ST_MISSIONS_TOTAL = 68   # 0x110 total missions (73)
ST_BLING_SCORE    = 85   # 0x154 best Bling-Bling Scramble score
# "island story passed": the game keeps both a flag and this stat
ST_PORTLAND_PASSED   = 50   # 0x0C8
ST_STAUNTON_PASSED   = 51   # 0x0CC
ST_SHORESIDE_PASSED  = 52   # 0x0D0

# fires/vigilante per island: indices of the stats block itself
# (0x02a8ad and 0x02a8b9 over a base of 0x02a6f5 -> indices 110 and 113)
FIRE_STAT_I = 110
VIG_STAT_I = 113

# ---------------------------------------------------------------- missions
# 73 missions = the 73 "set_latest_mission_passed" calls of the script.
# FLAG = name in the save's own global variable table (zlib table).

F = lambda n: "FLAG_%s_PASSED" % n

MISSIONS = [
    # --- Portland (21) ---
    ("Story: Portland", "Luigi's Girls",                F("LUIGI_MISSION1")),
    ("Story: Portland", "Don't Spank Ma Bitch Up",      F("LUIGI_MISSION2")),
    ("Story: Portland", "Drive Misty For Me",           F("LUIGI_MISSION3")),
    ("Story: Portland", "Pump-Action Pimp",             F("LUIGI_MISSION4")),
    ("Story: Portland", "The Fuzz Ball",                F("LUIGI_MISSION5")),
    ("Story: Portland", "Mike Lips Last Lunch",         F("JOEY_MISSION1")),
    ("Story: Portland", "Farewell 'Chunky' Lee Chong",  F("JOEY_MISSION2")),
    ("Story: Portland", "Van Heist",                    F("JOEY_MISSION3")),
    ("Story: Portland", "Cipriani's Chauffeur",         F("JOEY_MISSION4")),
    ("Story: Portland", "Dead Skunk In The Trunk",      F("JOEY_MISSION5")),
    ("Story: Portland", "The Getaway",                  F("JOEY_MISSION6")),
    ("Story: Portland", "Taking Out The Laundry",       F("TONI_MISSION1")),
    ("Story: Portland", "The Pick-Up",                  F("TONI_MISSION2")),
    ("Story: Portland", "Salvatore's Called A Meeting", F("TONI_MISSION3")),
    ("Story: Portland", "Triads and Tribulations",      F("TONI_MISSION4")),
    ("Story: Portland", "Blow Fish",                    F("TONI_MISSION5")),
    ("Story: Portland", "Chaperone",                    F("FRANKIE_MISSION1")),
    ("Story: Portland", "Cutting The Grass",            F("FRANKIE_MISSION2")),
    ("Story: Portland", "Bomb Da Base: Act I",          F("FRANKIE_MISSION2.1")),
    ("Story: Portland", "Bomb Da Base: Act II",         F("FRANKIE_MISSION3")),
    ("Story: Portland", "Last Requests",                F("FRANKIE_MISSION4")),
    # --- Staunton (19) ---
    ("Story: Staunton", "Sayonara Salvatore",           F("ASUKA_MISSION1")),
    ("Story: Staunton", "Under Surveillance",           F("ASUKA_MISSION2")),
    ("Story: Staunton", "Paparazzi Purge",              F("ASUKA_MISSION3")),
    ("Story: Staunton", "Payday For Ray",               F("ASUKA_MISSION4")),
    ("Story: Staunton", "Two-Faced Tanner",             F("ASUKA_MISSION5")),
    ("Story: Staunton", "Kanbu Bust-Out",               F("KENJI_MISSION1")),
    ("Story: Staunton", "Grand Theft Auto",             F("KENJI_MISSION2")),
    ("Story: Staunton", "Deal Steal",                   F("KENJI_MISSION3")),
    ("Story: Staunton", "Shima",                        F("KENJI_MISSION4")),
    ("Story: Staunton", "Smack Down",                   F("KENJI_MISSION5")),
    ("Story: Staunton", "Silence The Sneak",            F("RAY_MISSION1")),
    ("Story: Staunton", "Arms Shortage",                F("RAY_MISSION2")),
    ("Story: Staunton", "Evidence Dash",                F("RAY_MISSION3")),
    ("Story: Staunton", "Gone Fishing",                 F("RAY_MISSION4")),
    ("Story: Staunton", "Plaster Blaster",              F("RAY_MISSION5")),
    ("Story: Staunton", "Marked Man",                   F("RAY_MISSION6")),
    ("Story: Staunton", "Liberator",                    F("LOVE_MISSION1")),
    ("Story: Staunton", "Waka-Gashira Wipeout",         F("LOVE_MISSION2")),
    ("Story: Staunton", "A Drop In The Ocean",          F("LOVE_MISSION3")),
    # --- Shoreside (8) ---
    ("Story: Shoreside", "Grand Theft Aero",            F("LOVE_MISSION4")),
    ("Story: Shoreside", "Escort Service",              F("LOVE_MISSION5")),
    ("Story: Shoreside", "Decoy",                       F("LOVE_MISSION6")),
    ("Story: Shoreside", "Love's Disappearance",        F("LOVE_MISSION7")),
    ("Story: Shoreside", "Bait",                        F("ASUKA_SUBURBAN_MISSION1")),
    ("Story: Shoreside", "Espresso-2-Go!",              F("ASUKA_SUBURBAN_MISSION2")),
    ("Story: Shoreside", "S.A.M. & Ransom",             F("ASUKA_SUBURBAN_MISSION3")),
    ("Story: Shoreside", "The Exchange",                F("CAT_MISSION1")),
    # --- Phone ---
    ("Phone: El Burro",  "Turismo",                     "@TURISMO"),
    ("Phone: El Burro",  "I Scream, You Scream",        F("DIABLO_MISSION2")),
    ("Phone: El Burro",  "Trial By Fire",               F("DIABLO_MISSION3")),
    ("Phone: El Burro",  "Big 'N Veiny",                F("DIABLO_MISSION4")),
    ("Phone: Marty",     "The Crook",                   F("MEAT_MISSION1")),
    ("Phone: Marty",     "The Thieves",                 F("MEAT_MISSION2")),
    ("Phone: Marty",     "The Wife",                    F("MEAT_MISSION3")),
    ("Phone: Marty",     "Her Lover",                   F("MEAT_MISSION4")),
    ("Phone: K. Courtney", "Bling-Bling Scramble",      "@BLING"),
    ("Phone: K. Courtney", "Uzi Rider",                 F("YARDIE_MISSION2")),
    ("Phone: K. Courtney", "Gangcar Round-Up",          F("YARDIE_MISSION3")),
    ("Phone: K. Courtney", "Kingdom Come",              F("YARDIE_MISSION4")),
    ("Phone: D-Ice",     "Uzi Money",                   F("HOOD_MISSION1")),
    ("Phone: D-Ice",     "Toyminator",                  F("HOOD_MISSION2")),
    ("Phone: D-Ice",     "Rigged To Blow",              F("HOOD_MISSION3")),
    ("Phone: D-Ice",     "Bullion Run",                 F("HOOD_MISSION4")),
    ("Phone: D-Ice",     "Rumble",                      F("HOOD_MISSION5")),
    # --- Off-Road ---
    ("Off-Road", "Patriot Playground",                     F("4X4_MISSION1")),
    ("Off-Road", "A Ride In The Park",                     F("4X4_MISSION2")),
    ("Off-Road", "Multistorey Mayhem",                     F("MAYHEM_MISSION1")),
    ("Off-Road", "Gripped",                                F("4X4_MISSION3")),
    # --- RC Cars ---
    ("RC Cars", "Diablo Destruction",                    "FLAG_RC1_PASSED"),
    ("RC Cars", "Mafia Massacre",                        "FLAG_RC2_PASSED"),
    ("RC Cars", "Rumpo Rampage",                         "FLAG_RC3_PASSED"),
    ("RC Cars", "Casino Calamity",                        "FLAG_RC4_PASSED"),
]
assert len(MISSIONS) == 73, len(MISSIONS)

RAMPAGES = [("Rampage %02d" % i, "RAMPAGE_%02d_FLAG" % i) for i in range(1, 21)]
USJS     = [("Unique jump %02d" % i, "FLAG_USJ%d_PASSED" % i) for i in range(1, 21)]

# Import/Export: emergency crane (7) + garages (16 + 16), order = GTASnP
IE_CRANE = ["Fire Truck", "Ambulance", "Enforcer", "FBI Car", "Rhino",
            "Barracks OL", "Police Car"]
IE_PORTLAND = ["Securicar", "Moonbeam", "Coach", "Flatbed", "Linerunner",
               "Trashmaster", "Patriot", "Mr Whoopee", "Blista", "Mule",
               "Yankee", "Bobcat", "Dodo", "Bus", "Rumpo", "Pony"]
IE_SHORESIDE = ["Sentinel", "Cheetah", "Banshee", "Idaho", "Infernus", "Taxi",
                "Kuruma", "Stretch", "Perennial", "Stinger", "Manana",
                "Landstalker", "Stallion", "BF Injection", "Cabbie", "Esperanto"]

# island flags the game does set when each island's story is complete
ISLAND_FLAGS = [
    ("FLAG_INDUSTRIAL_PASSED",   "Story: Portland"),
    ("FLAG_COMMERCIAL_PASSED",   "Story: Staunton"),
    ("FLAG_SUBURBAN_PASSED",     "Story: Shoreside"),
]
# Turismo and Bling-Bling have no _PASSED flag: they count through their
# record (stats[53] time in seconds, stats[85] score). GTASnP treats them
# as done when there is a record, just like the game's counter.
SPECIAL_TURISMO = "@TURISMO"
SPECIAL_BLING = "@BLING"

# Per-contact "all missions passed" flags. The game never sets them
# for the contacts whose first mission has no flag (El Burro/Turismo,
# King Courtney/Bling-Bling), and GTASnP and the phone chains can look
# at FLAG_ALL_<contact>_MISSIONS_PASSED, so keep them in sync: 1 only
# when every flag-based mission of that contact is ticked.
ALL_FLAG_GROUPS = {}
for _sec, _lbl, _f in MISSIONS:
    _m = re.match(r"FLAG_(\w+)_MISSION[\d.]+_PASSED$", _f)
    if _m:
        ALL_FLAG_GROUPS.setdefault(_m.group(1), []).append(_f)

# Off-road races keep a record (seconds) besides the flag, exactly like
# Turismo/Bling-Bling do (GTASnP accepts either one), so fill the record
# too when it is still 0. (flag, stat index, record in seconds)
RACE_RECORDS = [
    ("FLAG_4X4_MISSION1_PASSED", 56, 120),     # Patriot Playground
    ("FLAG_4X4_MISSION2_PASSED", 57, 102),     # A Ride In The Park
    ("FLAG_4X4_MISSION3_PASSED", 58, 218),     # Gripped!
    ("FLAG_MAYHEM_MISSION1_PASSED", 59, 140),  # Multistorey Mayhem
]

PARAMEDIC_MAX = 12   # level 12 = paramedic complete
FIRE_ISLAND_OK = 20  # fires per island for GTASnP
VIG_ISLAND_OK = 20   # vigilante per island for GTASnP
TAXI_MAX = 100

# ---------------------------------------------------------------- utilities


def compute_seal(data):
    """NOT(MD5(24 header bytes zeroed + rest))."""
    head = b"\x00" * 24 + data[24:]
    return bytes(b ^ 0xFF for b in hashlib.md5(head).digest())


def seal_ok(data):
    if len(data) < 0x20:
        return False
    return data[SEAL_OFF:SEAL_OFF + SEAL_LEN] == compute_seal(data)


def _u32(data, off):
    if off < 0 or off + 4 > len(data):
        raise IndexError(off)
    return struct.unpack_from("<I", data, off)[0]


def _set_u32(buf, off, value):
    struct.pack_into("<I", buf, off, value & 0xFFFFFFFF)


class SaveError(Exception):
    pass


# ---------------------------------------------------------------- the save file


class GTA3Save:
    """Parsing and writing of a GTA III Definitive Edition (1.1x) .sav."""

    def __init__(self, data, path=None):
        if len(data) < 0x1000:
            raise SaveError("The file is too small to be a save")
        self.data = bytes(data)
        self.path = path
        self.names = self._name_table()
        if not self.names:
            raise SaveError("No global variable name table found "
                            "(is this a GTA III DE save?)")
        self._locate()

    def _locate(self):
        """(Re)find every variable-size block. Called again after the
        objects array shrinks, because everything behind it moves."""
        self.gbase = self._globals_base()
        self.stats = self._find_stats()
        self.playerinfo = self._find_playerinfo()
        self.garages = self._find_garages()
        self.cranes = self._find_cranes()
        self.pickups = self._find_pickups()
        self.objects = self._find_objects()

    # ---- location ----------------------------------------------------
    def _name_table(self):
        names = {}
        for magic in (b"\x78\x01", b"\x78\x9c", b"\x78\xda", b"\x78\x5e"):
            pos = 0
            while True:
                i = self.data.find(magic, pos)
                if i < 0:
                    break
                try:
                    raw = zlib.decompress(self.data[i:])
                except zlib.error:
                    pos = i + 1
                    continue
                if b"Globalvariables" not in raw[:64]:
                    pos = i + 1
                    continue
                for line in raw.decode("utf-8", "replace").splitlines():
                    if not line or line.startswith("//"):
                        continue
                    parts = line.split(",")
                    if len(parts) >= 4:
                        try:
                            names.setdefault(parts[1], int(parts[3]))
                        except ValueError:
                            pass
                pos = i + 1
        return names

    def _flag_offset(self, name):
        if name not in self.names:
            return None
        off = self.gbase + self.names[name]
        return off if 0 <= off + 4 <= len(self.data) else None

    def _globals_base(self):
        """base = b"SCR\\x00" + 0x14; validated: the flags must read 0/1."""
        probes = [n for _, _, n in MISSIONS] + \
                 [n for _, n in RAMPAGES] + [n for _, n in USJS]
        best, best_score = None, -1.0
        pos = 0
        while True:
            i = self.data.find(b"SCR\x00", pos)
            if i < 0:
                break
            pos = i + 1
            base = i + 0x14
            ok = tot = 0
            for name in probes:
                idx = self.names.get(name)
                if idx is None:
                    continue
                tot += 1
                off = base + idx
                if 0 <= off < len(self.data) and self.data[off] in (0, 1):
                    ok += 1
            if tot and ok / tot > best_score:
                best, best_score = base, ok / tot
            if best_score == 1.0:
                break
        if best is None or best_score < 0.9:
            raise SaveError("Could not locate the save's global "
                            "variable space")
        return best

    def _find_stats(self):
        # the block is NOT 4-byte aligned (base 0x02a6f5, odd): look for
        # the 154 of the progress total byte by byte and validate the
        # surrounding fields
        n = len(self.data)
        needle = struct.pack("<I", 154)
        start = 0
        while True:
            i = self.data.find(needle, start)
            if i < 0:
                break
            start = i + 1
            if i + 0xA0 > n or i < 0x74:
                continue
            if _u32(self.data, i + 0x40) != 20:     # total jumps
                continue
            if _u32(self.data, i + 0x98) != 20:     # total rampages
                continue
            if _u32(self.data, i + 0x9C) != 73:     # total missions
                continue
            st = i - 0x74
            if _u32(self.data, st + 0x70) > 154:    # progress <= total
                continue
            mp = _u32(self.data, st + 0xBC)
            if mp <= 73 and _u32(self.data, st + 0xB8) >= mp:
                return st
        raise SaveError("Stats block not found")

    def _find_playerinfo(self):
        # the block chain: the player-info block ends where the size
        # field of the stats block begins
        target = self.stats - 4
        lo = max(0, target - 0x4000)
        for s in range(target - 4, lo, -1):
            if _u32(self.data, s) + 4 + s == target:
                pio = s + 4
                if pio + 0x1B < len(self.data) and _u32(self.data, pio + 0x17) == 100:
                    return pio
        # fallback: content search
        for p in range(lo, target):
            if _u32(self.data, p + 0x17) == 100 and _u32(self.data, p + 0x13) <= 100 \
                    and _u32(self.data, p) < 100_000_000:
                return p
        raise SaveError("Player info block not found (packages)")

    @staticmethod
    def _garage_predicate(data, p):
        """p = start of the garage block payload (classic wiki):
        [n][5 counters][3 I/E masks][ga21] + StoredCar[18] + Garage[n]."""
        if p + 0x2F8 + 140 > len(data):
            return False
        n = _u32(data, p)
        if not 10 <= n <= 30:
            return False
        if any(_u32(data, p + 4 * k) > 1000 for k in (1, 2, 3, 4, 5)):
            return False
        if any(_u32(data, p + off) > 0xFFFF for off in (0x18, 0x1C, 0x20)):
            return False
        if _u32(data, p + 0x28) > 500:        # StoredCar[0].model
            return False
        # Garage[n]: every entry with a valid type and ordered corners
        # (x1<x2, y1<y2, z1<z2) inside the map bounds
        base = p + 0x2F8
        if base + 140 * n > len(data):
            return False
        for i in range(n):
            b = base + 140 * i
            if data[b] > 20:
                return False
            try:
                f = struct.unpack_from("<ffffff", data, b + 0x1C)
            except struct.error:
                return False
            if not all(math.isfinite(v) and abs(v) < 3000 for v in f):
                return False
            if not (f[0] < f[1] and f[2] < f[3] and f[4] < f[5]):
                return False
        return True

    def _find_garages(self):
        hits = [p for p in range(0, len(self.data) - 0x2F8 - 140)
                if self._garage_predicate(self.data, p)]
        return hits[0] if len(hits) == 1 else (hits[0] if hits else None)

    def _find_cranes(self):
        """payload = [n][emergency mask][Crane[8] of 0x80]. The block has
        a fixed size: 8 + 8*0x80 = 1032, which makes it unique."""
        needle = struct.pack("<I", 1032)
        start = 0
        found = []
        while True:
            i = self.data.find(needle, start)
            if i < 0:
                break
            start = i + 1
            p = i + 4
            if p + 8 > len(self.data):
                continue
            n = _u32(self.data, p)
            mask = _u32(self.data, p + 4)
            if 1 <= n <= 12 and mask <= 0x7F and bin(mask).count("1") <= 7:
                found.append(p)
        if not found:
            # fallback: by content (the crane zones)
            for p in range(0, len(self.data) - 0x420, 4):
                n = _u32(self.data, p)
                mask = _u32(self.data, p + 4)
                if not (2 <= n <= 12 and mask <= 0x7F):
                    continue
                try:
                    x1, x2, y1, y2 = struct.unpack_from("<ffff", self.data,
                                                        p + 8 + 0xC)
                except struct.error:
                    continue
                if all(math.isfinite(v) and abs(v) < 5000 for v in (x1, x2, y1, y2)) \
                        and x1 != x2 and y1 != y2:
                    found.append(p)
        return found[0] if found else None

    # ---- Block 7 pickups + Block 4 objects ---------------------------
    def _find_pickups(self):
        """[size=9492][Pickup[336] * 0x1C][84-byte ring]; the phone
        block [2608][49] starts exactly at base + 9492."""
        want = struct.pack("<I", PICKUP_BLOCK)
        pos = 0
        while True:
            i = self.data.find(want, pos)
            if i < 0:
                return None
            pos = i + 1
            base = i + 4
            if _u32(self.data, base + PICKUP_BLOCK) != PHONE_BLOCK:
                continue
            if _u32(self.data, base + PICKUP_BLOCK + 4) != PHONE_COUNT:
                continue
            if base + 8 * PICKUP_SIZE > len(self.data):
                continue
            ok = True
            for k in range(8):
                e = base + k * PICKUP_SIZE
                if self.data[e] > 20:
                    ok = False
                    break
                x, y, z = struct.unpack_from("<fff", self.data, e + 0x10)
                if not (-2600 < x < 2600 and -2600 < y < 2600
                        and -100 < z < 300):
                    ok = False
                    break
            if ok:
                return base

    def _find_objects(self):
        """[size = 4 + n*84][n][CObject * 84]: objects end, then the
        Path Find block, have to land exactly on the cranes block."""
        if self.cranes is None:
            return None
        cranes_size = self.cranes - 4
        cands = []
        for p in range(0x1000, len(self.data) - 8):
            size = _u32(self.data, p)
            n = _u32(self.data, p + 4)
            if not (20 <= n <= 800) or size != 4 + n * OBJECT_SIZE:
                continue
            end = p + 4 + size
            if end + 8 > len(self.data):
                continue
            if end + 4 + _u32(self.data, end) != cranes_size:
                continue
            cands.append((p, n))
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0][0]
        # more than one candidate: the one whose package/rampage objects
        # match the live pickups is the real block
        want_pkg = self._live_slots(PKG_TYPE, PKG_MODEL)
        want_rmp = self._live_slots(RAMPAGE_TYPE, RAMPAGE_MODEL)
        best, best_score = cands[0][0], -1
        for p, n in cands:
            cnt_pkg = cnt_rmp = 0
            for k in range(n):
                m = struct.unpack_from("<H", self.data,
                                       p + 8 + k * OBJECT_SIZE)[0]
                if m == PKG_MODEL:
                    cnt_pkg += 1
                elif m == RAMPAGE_MODEL:
                    cnt_rmp += 1
            score = (cnt_pkg == len(want_pkg)) + (cnt_rmp == len(want_rmp))
            if score > best_score:
                best, best_score = p, score
        return best

    def _live_slots(self, ptype, pmodel):
        """Pool slots still holding this kind of live pickup."""
        if self.pickups is None:
            return []
        out = []
        for k in range(PICKUP_COUNT):
            e = self.pickups + k * PICKUP_SIZE
            if e + PICKUP_SIZE > len(self.data):
                break
            if self.data[e] == ptype and struct.unpack_from(
                    "<H", self.data, e + 0x0C)[0] == pmodel:
                out.append(k)
        return out

    def _stale_slots(self):
        """Indices of freed slots still carrying a package/rampage model."""
        if self.pickups is None:
            return []
        out = []
        for k in range(PICKUP_COUNT):
            e = self.pickups + k * PICKUP_SIZE
            if e + PICKUP_SIZE > len(self.data):
                break
            model = struct.unpack_from("<H", self.data, e + 0x0C)[0]
            if model not in (PKG_MODEL, RAMPAGE_MODEL):
                continue
            if not ((model == PKG_MODEL and self.data[e] == PKG_TYPE) or
                    (model == RAMPAGE_MODEL
                     and self.data[e] == RAMPAGE_TYPE)):
                out.append(k)
        return out

    def packages_alive(self):
        """Live hidden packages left in the pool (100 - collected)."""
        if self.pickups is None:
            return None
        return len(self._live_slots(PKG_TYPE, PKG_MODEL))

    def objects_count(self, model):
        """Objects with this model in Block 4 (None if not found)."""
        if self.objects is None:
            return None
        n = _u32(self.data, self.objects + 4) or 0
        start = self.objects + 8
        return sum(1 for k in range(n)
                   if struct.unpack_from("<H", self.data,
                                         start + k * OBJECT_SIZE)[0] == model)

    def _find_object(self, model, pos):
        """Address of the object with this model at this position."""
        if self.objects is None:
            return None
        n = _u32(self.data, self.objects + 4) or 0
        start = self.objects + 8
        for k in range(n):
            e = start + k * OBJECT_SIZE
            if e + OBJECT_SIZE > len(self.data):
                break
            if struct.unpack_from("<H", self.data, e)[0] != model:
                continue
            x, y, z = struct.unpack_from("<fff", self.data, e + 6)
            if (abs(x - pos[0]) < 0.01 and abs(y - pos[1]) < 0.01
                    and abs(z - pos[2]) < 0.01):
                return e
        return None

    def _remove_object_at(self, addr):
        """Delete one entry: n--, size = 4 + n*84, bytes moved down."""
        n = (_u32(self.data, self.objects + 4) or 1) - 1
        buf = bytearray(self.data)
        del buf[addr:addr + OBJECT_SIZE]
        struct.pack_into("<I", buf, self.objects + 4, n)
        _set_u32(buf, self.objects, 4 + n * OBJECT_SIZE)
        self.data = bytes(buf)

    def _collect_pickups(self, slots):
        """Free pool slots exactly like the game does when something is
        picked up (type=0, byte+1=1) and delete their objects."""
        if not slots or self.pickups is None:
            return
        drops = []
        buf = bytearray(self.data)
        for k in slots:
            e = self.pickups + k * PICKUP_SIZE
            if buf[e] not in (PKG_TYPE, RAMPAGE_TYPE):
                continue
            model = struct.unpack_from("<H", buf, e + 0x0C)[0]
            pos = struct.unpack_from("<fff", buf, e + 0x10)
            buf[e] = 0
            buf[e + 1] = 1
            buf[e + 2:e + PICKUP_SIZE] = bytes(PICKUP_SIZE - 2)
            drops.append((model, pos))
        self.data = bytes(buf)
        addrs = [a for a in (self._find_object(m, p) for m, p in drops)
                 if a is not None]
        # remove from the back so the addresses already computed stay valid
        for a in sorted(addrs, reverse=True):
            self._remove_object_at(a)
        if addrs:
            self._locate()

    def _purge_stale_slots(self):
        """A freed slot must not keep naming its pickup: the game's own
        saves never have a slot marked free (type 0) that still carries
        the package/rampage model, and anything reading the pool by
        model (GTASnP's map) would count it as uncollected."""
        if self.pickups is None:
            return
        buf = bytearray(self.data)
        changed = False
        for k in range(PICKUP_COUNT):
            e = self.pickups + k * PICKUP_SIZE
            if e + PICKUP_SIZE > len(buf):
                break
            model = struct.unpack_from("<H", buf, e + 0x0C)[0]
            if model not in (PKG_MODEL, RAMPAGE_MODEL):
                continue
            live = ((model == PKG_MODEL and buf[e] == PKG_TYPE) or
                    (model == RAMPAGE_MODEL and buf[e] == RAMPAGE_TYPE))
            if live:
                continue
            buf[e] = 0
            buf[e + 1] = 1
            buf[e + 2:e + PICKUP_SIZE] = bytes(PICKUP_SIZE - 2)
            changed = True
        if changed:
            self.data = bytes(buf)

    def collect_packages(self, target):
        """Leave exactly `target` packages uncollected: extra live
        entries are freed and their objects dropped. Only goes one way
        (the file forgets where a collected package was)."""
        if self.pickups is None:
            return
        self._purge_stale_slots()
        target = max(0, min(100, int(target)))
        live = self._live_slots(PKG_TYPE, PKG_MODEL)
        extra = len(live) - (100 - target)
        if extra > 0:
            self._collect_pickups(live[:extra])

    def collect_rampages(self, checked):
        """Mark rampage numbers (1-20) as passed in the pool. A rampage
        lives at slot `base + number`; base is derived from this save
        (pool and flags have to agree), or every live rampage is freed
        when all 20 are ticked."""
        if self.pickups is None:
            return
        self._purge_stale_slots()
        checked = set(checked)
        live = self._live_slots(RAMPAGE_TYPE, RAMPAGE_MODEL)
        if not live:
            return
        if set(range(1, 21)) <= checked:
            self._collect_pickups(live)
            return
        unchecked = sorted(set(range(1, 21)) - checked)
        if len(unchecked) != len(live):
            return          # pool and flags disagree and only some ticked
        base = None
        for cand in sorted({s - j for s in live for j in unchecked}):
            if {cand + j for j in unchecked} == set(live):
                base = cand
                break
        if base is None:
            return
        self._collect_pickups([s for s in live if (s - base) in checked])

    # ---- reads -------------------------------------------------------
    def global32(self, name, default=None):
        idx = self.names.get(name)
        if idx is None:
            return default
        off = self.gbase + idx
        if off + 4 > len(self.data):
            return default
        return _u32(self.data, off)

    def set_global(self, name, value):
        idx = self.names.get(name)
        if idx is None:
            return False
        off = self.gbase + idx
        if off + 4 > len(self.data):
            return False
        buf = bytearray(self.data)
        _set_u32(buf, off, value)
        self.data = bytes(buf)
        return True

    def flag(self, name):
        if name == SPECIAL_TURISMO:
            return 1 if self.stat(ST_TURISMO) else 0
        if name == SPECIAL_BLING:
            return 1 if self.stat(ST_BLING_SCORE) else 0
        off = self._flag_offset(name)
        if off is None:
            return 0
        return 1 if self.data[off] else 0

    def stat(self, index):
        return _u32(self.data, self.stats + 4 * index)

    def packages(self):
        v = self.global32(G_PKG)
        return v if v is not None and v <= 100 else \
            _u32(self.data, self.playerinfo + 0x13)

    def fire_islands(self):
        vals = [self.global32(n) for n in G_FIRES]
        if all(v is not None for v in vals):
            return vals
        return [self.stat(FIRE_STAT_I + k) for k in range(3)]

    def vig_islands(self):
        vals = [self.global32(n) for n in G_VIG]
        if all(v is not None for v in vals):
            return vals
        return [self.stat(VIG_STAT_I + k) for k in range(3)]

    def _phys32(self, off):
        return _u32(self.data, off) if off + 4 <= len(self.data) else 0

    def ie_crane(self):
        if self.cranes is None:
            return 0
        return self._phys32(self.cranes + 4) & 0x7F

    def ie_portland(self):
        tpl = G_IE["ie_pdx"][0]
        if any(self.global32(tpl % i) is not None for i in range(1, 17)):
            return sum(1 << (i - 1) for i in range(1, 17)
                       if self.global32(tpl % i, 0))
        if self.garages is None:
            return 0
        return self._phys32(self.garages + 0x18) & 0xFFFF

    def ie_shoreside(self):
        tpl = G_IE["ie_ssv"][0]
        if any(self.global32(tpl % i) is not None for i in range(1, 17)):
            return sum(1 << (i - 1) for i in range(1, 17)
                       if self.global32(tpl % i, 0))
        if self.garages is None:
            return 0
        return self._phys32(self.garages + 0x1C) & 0xFFFF

    # ---- writes ------------------------------------------------------
    def set_flag(self, name, value):
        off = self._flag_offset(name)
        if off is None:
            return False
        buf = bytearray(self.data)
        buf[off] = int(value) & 0xFF
        self.data = bytes(buf)
        return True

    def set_stat(self, index, value):
        buf = bytearray(self.data)
        _set_u32(buf, self.stats + 4 * index, value)
        self.data = bytes(buf)

    def _set_phys32(self, off, value):
        if off + 4 > len(self.data):
            return
        buf = bytearray(self.data)
        _set_u32(buf, off, value)
        self.data = bytes(buf)

    def set_packages(self, value):
        buf = bytearray(self.data)
        _set_u32(buf, self.playerinfo + 0x13, value)
        self.data = bytes(buf)

    def set_fire_islands(self, vals):
        for k, v in enumerate(vals):
            self.set_stat(FIRE_STAT_I + k, v)

    def set_vig_islands(self, vals):
        for k, v in enumerate(vals):
            self.set_stat(VIG_STAT_I + k, v)

    def set_ie_crane(self, bits):
        if self.cranes is not None:
            self._set_phys32(self.cranes + 4, bits & 0x7F)

    def set_ie_portland(self, bits):
        if self.garages is not None:
            self._set_phys32(self.garages + 0x18, bits & 0xFFFF)
        self._set_ie_slots("ie_pdx", bits)

    def set_ie_shoreside(self, bits):
        if self.garages is not None:
            self._set_phys32(self.garages + 0x1C, bits & 0xFFFF)
        self._set_ie_slots("ie_ssv", bits)

    def _set_ie_slots(self, key, bits):
        tpl, filled = G_IE[key]
        for i in range(1, 17):
            self.set_global(tpl % i, 1 if bits & (1 << (i - 1)) else 0)
        self.set_global(filled, bin(bits & 0xFFFF).count("1"))

    def reseal(self):
        buf = bytearray(self.data)
        buf[SEAL_OFF:SEAL_OFF + SEAL_LEN] = compute_seal(bytes(buf))
        self.data = bytes(buf)

    def to_bytes(self):
        return self.data

    # ---- full state (what the GUI models) ----------------------------
    def read_state(self):
        st = {}
        for sec, name, flag in MISSIONS:
            st[("mission", flag)] = self.flag(flag)
        for key, flag in RAMPAGES:
            st[("rampage", flag)] = self.flag(flag)
        for key, flag in USJS:
            st[("usj", flag)] = self.flag(flag)
        alive = self.packages_alive()
        st[("meta", "packages")] = (100 - alive) if alive is not None \
            else self.packages()
        st[("meta", "paramedic")] = min(self.stat(ST_PARAMEDIC), PARAMEDIC_MAX)
        st[("meta", "taxi")] = min(self.stat(ST_TAXI), TAXI_MAX)
        st[("meta", "fire")] = self.fire_islands()
        st[("meta", "vig")] = self.vig_islands()
        st[("meta", "ie_crane")] = self.ie_crane()
        st[("meta", "ie_pdx")] = self.ie_portland()
        st[("meta", "ie_ssv")] = self.ie_shoreside()
        return st


def compute_progress(st):
    """Progress points (154 max). Exactly reproduces the 4 real saves:
    91, 83, 83 and 17, as measured by the game itself."""
    total = sum(v for (kind, _), v in st.items() if kind == "mission")
    total += sum(v for (kind, _), v in st.items() if kind == "rampage")
    total += sum(v for (kind, _), v in st.items() if kind == "usj")
    total += st[("meta", "packages")] // 10
    if st[("meta", "paramedic")] >= PARAMEDIC_MAX:
        total += 1
    if all(v >= FIRE_ISLAND_OK for v in st[("meta", "fire")]):
        total += 1
    pdx, ssv = st[("meta", "ie_pdx")], st[("meta", "ie_ssv")]
    total += bin(pdx).count("1") + bin(ssv).count("1")
    return min(154, max(0, total))


def missions_done(st):
    return sum(v for (kind, _), v in st.items() if kind == "mission")


def apply_state(sav, st):
    """Write into the save all the GUI state + derived counters."""
    # 1. mission / rampage / jump flags
    for (kind, flag), v in st.items():
        if kind in ("mission", "rampage", "usj"):
            sav.set_flag(flag, 1 if v else 0)
    # 1b. physical collectibles: packages and rampages also live in the
    #     pickup pool (Block 7) + the objects array (Block 4); the game
    #     and GTASnP read those, not only the flags and counters.
    sav.collect_packages(st.get(("meta", "packages"), 0))
    sav.collect_rampages([j for j, (_lbl, f) in enumerate(RAMPAGES, 1)
                          if st.get(("rampage", f))])
    alive = sav.packages_alive()
    if alive is not None:
        # what is physically left is the truth: a collected package
        # cannot be resurrected (the file forgot where it was)
        st[("meta", "packages")] = 100 - alive
    # 2. island flags + the matching stats (whichever this save has)
    for i, (flag, section) in enumerate(ISLAND_FLAGS):
        need = [f for sec, _lbl, f in MISSIONS if sec == section]
        done = 1 if all(st.get(("mission", f), 0) for f in need) else 0
        sav.set_flag(flag, done)
        sav.set_stat(ST_PORTLAND_PASSED + i, done)
    # 2b. per-contact "all missions passed" flags
    for _pref, _flags in ALL_FLAG_GROUPS.items():
        _name = "FLAG_ALL_%s_MISSIONS_PASSED" % _pref
        if _name in sav.names:
            sav.set_global(_name, 1 if all(st.get(("mission", f), 0)
                                           for f in _flags) else 0)
    # 3. stats counters
    n_mis = missions_done(st)
    sav.set_stat(ST_MISSIONS, n_mis)
    sav.set_stat(ST_ATTEMPTS, max(sav.stat(ST_ATTEMPTS), n_mis))
    n_jumps = sum(v for (k, _), v in st.items() if k == "usj")
    n_ramp = sum(v for (k, _), v in st.items() if k == "rampage")
    sav.set_stat(ST_JUMPS_FOUND, n_jumps)
    sav.set_stat(ST_RAMPAGES, n_ramp)
    sav.set_flag("TOTAL_COMPLETED_USJ", n_jumps)
    sav.set_flag("TOTAL_RAMPAGES_PASSED", n_ramp)
    # the reward banked for the rampages: 5000 each in the saves
    # (4 passed -> 20000, 9 -> 45000)
    sav.set_global("RAMPAGE_REWARD", 5000 * n_ramp)
    # off-road races: besides the flag the game keeps a record (secs)
    for _flag, _idx, _secs in RACE_RECORDS:
        if st.get(("mission", _flag)) and not sav.stat(_idx):
            sav.set_stat(_idx, _secs)
    sav.set_packages(st[("meta", "packages")])
    sav.set_stat(ST_PARAMEDIC, st[("meta", "paramedic")])
    sav.set_stat(ST_TAXI, st[("meta", "taxi")])
    sav.set_flag("TAXI_PASSED", 100 if st[("meta", "taxi")] >= TAXI_MAX else 0)
    fire = st[("meta", "fire")]
    vig = st[("meta", "vig")]
    sav.set_fire_islands(fire)
    sav.set_vig_islands(vig)
    sav.set_stat(ST_FIRES, sum(fire))
    sav.set_stat(ST_VIGILANTE, sum(vig))
    # 4. script globals (what GTASnP and the script itself read)
    sav.set_global(G_PKG, st[("meta", "packages")])
    for name, v in zip(G_FIRES, fire):
        sav.set_global(name, v)
    for name, v in zip(G_VIG, vig):
        sav.set_global(name, v)
    sav.set_global(G_FLAME,
                   1 if all(v >= FIRE_ISLAND_OK for v in fire) else 0)
    # the emergency crane counts as done once all 7 are delivered
    sav.set_global(G_CRAN, 1 if st[("meta", "ie_crane")] == 0x7F else 0)
    # 4. Turismo / Bling-Bling: besides the flag they carry their record
    sav.set_stat(ST_TURISMO, 174 if st.get(("mission", SPECIAL_TURISMO), 0) else 0)
    sav.set_stat(ST_BLING_SCORE, 10 if st.get(("mission", SPECIAL_BLING), 0) else 0)
    # 5. I/E
    sav.set_ie_crane(st[("meta", "ie_crane")])
    sav.set_ie_portland(st[("meta", "ie_pdx")])
    sav.set_ie_shoreside(st[("meta", "ie_ssv")])
    # 6. progress
    sav.set_stat(ST_PROGRESS, compute_progress(st))
    sav.set_stat(ST_PROGRESS_TOTAL, 154)
    # 7. MD5 seal
    sav.reseal()
    return sav


# ---------------------------------------------------------------- GUI


def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    class Editor(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("GTA III Definitive Edition - 100% Save Editor")
            self.geometry("760x680")
            self.minsize(680, 560)
            self.sav = None
            self.st = {}
            self.vars = {}          # key -> Variable
            self.spinvars = {}      # key -> (StringVar, on_change)
            self._build_top()
            self._build_tabs()
            self._build_status()
            self._set_enabled(False)

        # ---------------- structure ----------------
        def _build_top(self):
            top = ttk.Frame(self, padding=(8, 8, 8, 4))
            top.pack(fill="x")
            ttk.Button(top, text="Open .sav...", command=self.open_file)\
                .pack(side="left")
            self.btn_save = ttk.Button(top, text="Save", command=self.save_file)
            self.btn_save.pack(side="left", padx=(6, 0))
            self.btn_saveas = ttk.Button(top, text="Save as...",
                                         command=self.save_file_as)
            self.btn_saveas.pack(side="left", padx=(6, 0))
            ttk.Button(top, text="Check all", command=lambda: self.set_all(True))\
                .pack(side="left", padx=(18, 0))
            ttk.Button(top, text="Uncheck all",
                       command=lambda: self.set_all(False)).pack(side="left", padx=(6, 0))
            self.path_var = tk.StringVar(value="No file loaded")
            ttk.Label(top, textvariable=self.path_var, foreground="#555")\
                .pack(side="left", padx=12)

        def _build_tabs(self):
            self.nb = ttk.Notebook(self)
            self.nb.pack(fill="both", expand=True, padx=8, pady=4)
            self.tab_hist = self._scroll_tab("Missions")
            self.tab_phone = self._scroll_tab("Phone")
            self.tab_side = self._scroll_tab("Off-Road / RC")
            self.tab_cat = self._scroll_tab("Rampages / Jumps")
            self.tab_veh = ttk.Frame(self.nb, padding=10)
            self.nb.add(self.tab_veh, text=" Vehicles ")
            self.tab_ie = self._scroll_tab("Import/Export")
            self.tab_pkg = ttk.Frame(self.nb, padding=10)
            self.nb.add(self.tab_pkg, text=" Packages ")

            # story missions
            root_h = self.tab_hist.inner
            for section in ("Story: Portland", "Story: Staunton",
                            "Story: Shoreside"):
                box = ttk.LabelFrame(root_h, text=" " + section + " ", padding=6)
                box.pack(fill="x", padx=6, pady=4)
                self._check_group(box, [("mission", f, n)
                                        for s2, n, f in MISSIONS if s2 == section])
            # phones
            for section in ("Phone: El Burro", "Phone: Marty",
                            "Phone: K. Courtney", "Phone: D-Ice"):
                box = ttk.LabelFrame(self.tab_phone.inner, text=" " + section + " ",
                                     padding=6)
                box.pack(fill="x", padx=6, pady=4)
                self._check_group(box, [("mission", f, n)
                                        for s2, n, f in MISSIONS if s2 == section])
            # offroad / rc
            for section in ("Off-Road", "RC Cars"):
                box = ttk.LabelFrame(self.tab_side.inner, text=" " + section + " ",
                                     padding=6)
                box.pack(fill="x", padx=6, pady=4)
                self._check_group(box, [("mission", f, n)
                                        for s2, n, f in MISSIONS if s2 == section])
            # rampages and jumps
            box = ttk.LabelFrame(self.tab_cat.inner, text=" Rampages (20) ", padding=6)
            box.pack(fill="x", padx=6, pady=4)
            self._check_group(box, [("rampage", f, n) for n, f in RAMPAGES])
            box = ttk.LabelFrame(self.tab_cat.inner, text=" Unique jumps (20) ",
                                 padding=6)
            box.pack(fill="x", padx=6, pady=4)
            self._check_group(box, [("usj", f, n) for n, f in USJS])

            self._build_vehicles(self.tab_veh)
            self._build_ie(self.tab_ie.inner)
            self._build_packages(self.tab_pkg)

        def _scroll_tab(self, title):
            tab = ttk.Frame(self.nb)
            self.nb.add(tab, text=" %s " % title)
            canvas = tk.Canvas(tab, highlightthickness=0)
            sb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas)
            inner.bind("<Configure>",
                       lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=sb.set)
            canvas.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            canvas.bind_all("<MouseWheel>",
                            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
            tab.inner = inner
            return tab

        def _check_group(self, parent, entries, columns=2):
            for i, (kind, flag, label) in enumerate(entries):
                key = (kind, flag)
                var = tk.IntVar(value=0)
                var.trace_add("write", lambda *_k, k=key: self._on_change(k))
                self.vars[key] = var
                cb = ttk.Checkbutton(parent, text=label, variable=var)
                cb.grid(row=i // columns, column=i % columns, sticky="w",
                        padx=6, pady=1)
            for c in range(columns):
                parent.columnconfigure(c, weight=1)

        def _build_vehicles(self, parent):
            box = ttk.LabelFrame(parent, text=" Vehicle missions ", padding=10)
            box.pack(fill="x")

            def spinner(row, text, key, maximum):
                ttk.Label(box, text=text).grid(row=row, column=0, sticky="w",
                                               pady=4)
                var = tk.StringVar()
                sp = ttk.Spinbox(box, from_=0, to=maximum, width=6,
                                 textvariable=var,
                                 command=lambda k=key, v=var: self._on_change(k))
                sp.grid(row=row, column=1, sticky="w", padx=8)
                sp.bind("<KeyRelease>", lambda _e, k=key, v=var: self._on_change(k))
                self.spinvars[key] = var
            spinner(0, "Paramedic - max level (12 = complete):",
                    ("meta", "paramedic"), PARAMEDIC_MAX)
            spinner(1, "Taxi - fares (100 = complete):", ("meta", "taxi"), TAXI_MAX)
            ttk.Label(box, text="Firefighter - fires per island:").grid(
                row=2, column=0, sticky="w", pady=4)
            fr = ttk.Frame(box)
            fr.grid(row=2, column=1, sticky="w")
            for k, name in enumerate(("Portland", "Staunton", "Shoreside")):
                v = tk.StringVar()
                ttk.Spinbox(fr, from_=0, to=100, width=5, textvariable=v).pack(
                    side="left", padx=3)
                ttk.Label(fr, text=name, foreground="#666").pack(side="left")
                self.spinvars[("meta", "fire", k)] = v
            ttk.Label(box, text="Vigilante - criminals per island:").grid(
                row=3, column=0, sticky="w", pady=4)
            fr2 = ttk.Frame(box)
            fr2.grid(row=3, column=1, sticky="w")
            for k, name in enumerate(("Portland", "Staunton", "Shoreside")):
                v = tk.StringVar()
                ttk.Spinbox(fr2, from_=0, to=100, width=5, textvariable=v).pack(
                    side="left", padx=3)
                ttk.Label(fr2, text=name, foreground="#666").pack(side="left")
                self.spinvars[("meta", "vig", k)] = v
            for r in range(4):
                box.columnconfigure(1, weight=1)

        def _build_ie(self, parent):
            def group(title, names, key):
                box = ttk.LabelFrame(parent, text=" " + title + " ", padding=6)
                box.pack(fill="x", padx=6, pady=4)
                for i, name in enumerate(names):
                    var = tk.IntVar(value=0)
                    var.trace_add("write",
                                  lambda *_k, k=key, b=i: self._on_bit(k, b))
                    self.vars[(key, i)] = var
                    cb = ttk.Checkbutton(box, text=name, variable=var)
                    cb.grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=1)
                box.columnconfigure(0, weight=1)
                box.columnconfigure(1, weight=1)

            group("Emergency crane (7)", IE_CRANE, "ie_crane")
            group("Portland Docks garage (16)", IE_PORTLAND, "ie_pdx")
            group("Shoreside Vale garage (16)", IE_SHORESIDE, "ie_ssv")
            ttk.Label(parent, text="The bit order is the same as "
                                   "GTASnP (LSB first).",
                      foreground="#666").pack(padx=8, pady=4)

        def _build_packages(self, parent):
            box = ttk.LabelFrame(parent, text=" Hidden packages ", padding=10)
            box.pack(fill="x")
            ttk.Label(box, text="Packages collected (0-100):").grid(
                row=0, column=0, sticky="w", pady=4)
            v = tk.StringVar()
            sp = ttk.Spinbox(box, from_=0, to=100, width=6, textvariable=v)
            sp.grid(row=0, column=1, sticky="w", padx=8)
            sp.bind("<KeyRelease>", lambda _e: self._on_change(("meta", "packages")))
            sp.configure(command=lambda: self._on_change(("meta", "packages")))
            self.spinvars[("meta", "packages")] = v
            ttk.Label(box, text="Every 10 packages are worth 1 progress point.",
                      foreground="#666").grid(row=1, column=0, columnspan=2,
                                              sticky="w", pady=(6, 0))

        def _build_status(self):
            bar = ttk.Frame(self, padding=(8, 2, 8, 6))
            bar.pack(fill="x", side="bottom")
            self.progress_var = tk.StringVar(value="Progress: -/154")
            self.mission_var = tk.StringVar(value="Missions: -/73")
            self.info_var = tk.StringVar(value="Open a GTA3sfN.sav to start")
            ttk.Label(bar, textvariable=self.progress_var,
                      font=("", 11, "bold")).pack(side="left")
            ttk.Label(bar, textvariable=self.mission_var,
                      font=("", 11, "bold")).pack(side="left", padx=14)
            ttk.Label(bar, textvariable=self.info_var,
                      foreground="#555").pack(side="right")

        # ---------------- logic ----------------
        def _set_enabled(self, state):
            for child in self.nb.winfo_children():
                for w in child.winfo_children():
                    pass  # the whole notebook is filled on open

        def _int(self, key):
            var = self.spinvars.get(key)
            if var is None:
                return 0
            try:
                return int(float(str(var.get()).replace(",", ".")))
            except ValueError:
                return 0

        def collect_state(self):
            st = {}
            for key, var in self.vars.items():
                st[key] = 1 if var.get() else 0
            st[("meta", "packages")] = max(0, min(100, self._int(("meta", "packages"))))
            st[("meta", "paramedic")] = max(0, min(PARAMEDIC_MAX,
                                                    self._int(("meta", "paramedic"))))
            st[("meta", "taxi")] = max(0, min(TAXI_MAX, self._int(("meta", "taxi"))))
            for grp in ("fire", "vig"):
                st[("meta", grp)] = [max(0, min(100, self._int(("meta", grp, k))))
                                     for k in range(3)]
            # I/E bits: rebuild from the checkboxes
            for key, names in (("ie_crane", IE_CRANE), ("ie_pdx", IE_PORTLAND),
                               ("ie_ssv", IE_SHORESIDE)):
                bits = 0
                for i in range(len(names)):
                    if self.vars.get((key, i), tk.IntVar(value=0)).get():
                        bits |= 1 << i
                st[("meta", key)] = bits
            return st

        def _refresh_labels(self):
            if not self.st:
                return
            st = self.collect_state()
            prog = compute_progress(st)
            n = missions_done(st)
            pct = prog * 100.0 / 154
            self.progress_var.set("Progress: %d/154 (%.1f%%)" % (prog, pct))
            self.mission_var.set("Missions: %d/73" % n)

        def _on_change(self, _key=None):
            self._refresh_labels()

        def _on_bit(self, _key, _bit):
            self._refresh_labels()

        def open_file(self):
            path = filedialog.askopenfilename(
                title="Open a GTA III DE save",
                filetypes=[("GTA III saves", "*.sav"), ("All", "*.*")])
            if not path:
                return
            try:
                with open(path, "rb") as fh:
                    sav = GTA3Save(fh.read(), path)
            except (OSError, SaveError) as exc:
                messagebox.showerror("Could not open", str(exc))
                return
            self.sav = sav
            self.st = sav.read_state()
            self._load_state_into_gui()
            self.path_var.set(os.path.basename(path))
            ok = seal_ok(sav.data)
            self.info_var.set(
                "MD5 seal: %s | original seal: %s"
                % ("OK" if ok else "recalculated on save",
                   "valid" if ok else "INVALID (the game will ignore "
                                       "it until you save)"))
            self._refresh_labels()

        def _load_state_into_gui(self):
            st = self.st
            for key, var in self.vars.items():
                if key[0] in ("ie_crane", "ie_pdx", "ie_ssv"):
                    i = key[1]
                    mask = ("meta", key[0])
                    var.set(1 if st.get(mask, 0) & (1 << i) else 0)
                else:
                    var.set(1 if st.get(key, 0) else 0)
            self.spinvars[("meta", "packages")].set(str(st[("meta", "packages")]))
            self.spinvars[("meta", "paramedic")].set(str(st[("meta", "paramedic")]))
            self.spinvars[("meta", "taxi")].set(str(st[("meta", "taxi")]))
            for grp in ("fire", "vig"):
                for k in range(3):
                    self.spinvars[("meta", grp, k)].set(str(st[("meta", grp)][k]))

        def set_all(self, value):
            if not self.sav:
                messagebox.showinfo("First", "Open a .sav first")
                return
            v = 1 if value else 0
            for var in self.vars.values():
                var.set(v)
            if value:
                self.spinvars[("meta", "packages")].set("100")
                self.spinvars[("meta", "paramedic")].set(str(PARAMEDIC_MAX))
                self.spinvars[("meta", "taxi")].set(str(TAXI_MAX))
                for grp in ("fire", "vig"):
                    for k in range(3):
                        self.spinvars[("meta", grp, k)].set("20")
            else:
                self.spinvars[("meta", "packages")].set("0")
                self.spinvars[("meta", "paramedic")].set("0")
                self.spinvars[("meta", "taxi")].set("0")
                for grp in ("fire", "vig"):
                    for k in range(3):
                        self.spinvars[("meta", grp, k)].set("0")
            self._refresh_labels()

        def _write(self, path):
            st = self.collect_state()
            apply_state(self.sav, st)
            with open(path, "wb") as fh:
                fh.write(self.sav.to_bytes())
            self.st = self.sav.read_state()
            self._load_state_into_gui()
            self._refresh_labels()
            prog = compute_progress(st)
            messagebox.showinfo(
                "Saved",
                "%s\n\nProgress: %d/154  |  Missions: %d/73\n"
                "MD5 seal recalculated: the game will load it without conflict.\n"
                "Tip: if the launcher reports a cloud conflict, pick LOCAL."
                % (os.path.basename(path), prog, missions_done(st)))

        def save_file(self):
            if not self.sav:
                messagebox.showinfo("First", "Open a .sav first")
                return
            self._write(self.sav.path)

        def save_file_as(self):
            if not self.sav:
                messagebox.showinfo("First", "Open a .sav first")
                return
            path = filedialog.asksaveasfilename(
                title="Save game as", defaultextension=".sav",
                initialfile=os.path.basename(self.sav.path),
                filetypes=[("GTA III saves", "*.sav")])
            if not path:
                return
            self._write(path)
            self.sav.path = path
            self.path_var.set(os.path.basename(path))

    app = Editor()
    app.mainloop()


# ---------------------------------------------------------------- selftest


def selftest():
    import shutil
    import tempfile

    here = os.path.dirname(os.path.abspath(__file__))
    ref = os.path.join(here, "samples", "referencia-sf1.sav")
    if not os.path.exists(ref):
        print("WARNING: samples/referencia-sf1.sav missing; partial selftest")
        ref = None
    checks = []

    def check(name, cond, extra=""):
        checks.append((name, bool(cond), extra))
        print("  [%s] %s %s" % ("OK" if cond else "FAIL", name, extra))

    # 1) the seal on saves written by the game
    prof = ("C:/Users/josep/Documents/Rockstar Games/GTA III Definitive Edition/"
            "Profiles/55D4E5B0")
    for n in (1, 7, 8, 9):
        p = os.path.join(prof, "GTA3sf%d.sav" % n)
        if os.path.exists(p):
            d = open(p, "rb").read()
            check("seal of GTA3sf%d.sav (written by the game)" % n, seal_ok(d))

    if ref:
        data = open(ref, "rb").read()
        sav = GTA3Save(data)
        st = sav.read_state()
        # 2) exact reproduction of the real progress
        check("computed progress == 91 (the game's value)",
              compute_progress(st) == 91, "-> %d" % compute_progress(st))
        check("computed missions == 68", missions_done(st) == 68,
              "-> %d" % missions_done(st))
        check("packages == 66", st[("meta", "packages")] == 66)
        check("rampages == 9", sum(v for (k, _), v in st.items()
                                   if k == "rampage") == 9)
        check("jumps == 7", sum(v for (k, _), v in st.items()
                                if k == "usj") == 7)
        check("firefighter per island == 80/0/0", st[("meta", "fire")] == [80, 0, 0])
        check("vigilante per island == 20/25/20", st[("meta", "vig")] == [20, 25, 20])
        check("I/E crane == 0x43 (Fire/Amb/Police)", st[("meta", "ie_crane")] == 0x43)
        check("I/E garages == 0/0", st[("meta", "ie_pdx")] == 0
              and st[("meta", "ie_ssv")] == 0)
        check("stats[47] missions == 68", sav.stat(ST_MISSIONS) == 68)

        # --- where the physical collectibles really live (Blocks 7+4)
        check("pickup pool found", sav.pickups is not None)
        check("objects block found", sav.objects is not None)
        check("34 live packages == 100 - 66", sav.packages_alive() == 34,
              "-> %s" % sav.packages_alive())
        check("11 live rampages == 20 - 9",
              len(sav._live_slots(RAMPAGE_TYPE, RAMPAGE_MODEL)) == 11)
        check("objects match live pickups",
              sav.objects_count(PKG_MODEL) == 34
              and sav.objects_count(RAMPAGE_MODEL) == 11)
        for nm2 in ("referencia-sf7", "GTA3sf8", "GTA3sf9"):
            p2 = os.path.join(here, "samples", nm2 + ".sav")
            if os.path.exists(p2):
                s2 = GTA3Save(open(p2, "rb").read())
                a2 = s2.packages_alive()
                r2 = len(s2._live_slots(RAMPAGE_TYPE, RAMPAGE_MODEL))
                exp_r = sum(1 for _, f2 in RAMPAGES if not s2.flag(f2))
                check("%s: pool agrees with counter/flags" % nm2,
                      a2 is not None and 100 - a2 == s2.packages()
                      and r2 == exp_r,
                      "(pkgs=%s ramp=%d)" % (a2, r2))

        # --- the island flags describe each island's own story and must be
        #     derived from it: a save with 3 missions keeps them at 0
        for nm2, want in (("referencia-sf1", 1), ("GTA3sf8", 0)):
            p2 = os.path.join(here, "samples", nm2 + ".sav")
            if not os.path.exists(p2):
                continue
            s2 = GTA3Save(open(p2, "rb").read())
            before = [s2.flag(f) for f, _ in ISLAND_FLAGS]
            t2 = apply_state(GTA3Save(open(p2, "rb").read()),
                             dict(s2.read_state()))
            after = [t2.flag(f) for f, _ in ISLAND_FLAGS]
            st_after = [t2.stat(ST_PORTLAND_PASSED + i)
                        for i in range(len(ISLAND_FLAGS))]
            check("%s: island flags stay %d" % (nm2, want),
                  before == [want] * 3 and after == [want] * 3
                  and st_after == [want] * 3,
                  "-> flags %s after %s stats %s" % (before, after, st_after))

        # 3) round-trip with no changes = byte for byte identical
        tmp = tempfile.mkdtemp(prefix="gta3ed_")
        try:
            p1 = os.path.join(tmp, "rt.sav")
            scrub = [range(sav.pickups + k * PICKUP_SIZE,
                           sav.pickups + (k + 1) * PICKUP_SIZE)
                     for k in sav._stale_slots()]
            apply_state(sav, st)
            with open(p1, "wb") as fh:
                fh.write(sav.to_bytes())
            rt = open(p1, "rb").read()
            # On an untouched save the only bytes apply_state can touch
            # are the per-contact FLAG_ALL_*_MISSIONS_PASSED flags (the
            # game never sets them for every contact, see ALL_FLAG_GROUPS)
            # plus the seal, which has to be recomputed for them.
            allowed = {sav.gbase + sav.names[nm] for nm in sav.names
                       if nm.startswith("FLAG_ALL_")
                       and nm.endswith("_MISSIONS_PASSED")}
            allowed.update(range(SEAL_OFF, SEAL_OFF + SEAL_LEN))
            # and the freed slots apply_state scrubs of their stale
            # package/rampage model (left over from older versions)
            for r in scrub:
                allowed.update(r)
            diff = [i for i in range(len(data))
                    if rt[i] != data[i]] if len(rt) == len(data) else None
            check("round-trip only touches FLAG_ALL_*",
                  diff is not None and all(i in allowed for i in diff),
                  "%d byte(s) changed" %
                  (len(diff) if diff is not None else -1))
            check("seal after round-trip", seal_ok(rt))

            # 4) check EVERYTHING
            sav2 = GTA3Save(data)
            st2 = sav2.read_state()
            for key in list(st2):
                kind = key[0]
                if kind in ("mission", "rampage", "usj"):
                    st2[key] = 1
            st2[("meta", "ie_crane")] = 0x7F
            st2[("meta", "ie_pdx")] = 0xFFFF
            st2[("meta", "ie_ssv")] = 0xFFFF
            st2[("meta", "packages")] = 100
            st2[("meta", "paramedic")] = PARAMEDIC_MAX
            st2[("meta", "taxi")] = TAXI_MAX
            st2[("meta", "fire")] = [20, 20, 20]
            st2[("meta", "vig")] = [20, 20, 20]
            alive0 = sav2.packages_alive()
            rmp0 = len(sav2._live_slots(RAMPAGE_TYPE, RAMPAGE_MODEL))
            apply_state(sav2, st2)
            out = sav2.to_bytes()
            # collecting frees pickup slots and drops their objects, so
            # the file shrinks by 84 bytes per package/rampage collected
            check("check all: size -84 per collected item",
                  len(out) == len(data) - (alive0 + rmp0) * OBJECT_SIZE,
                  "(%d vs %d)" % (len(out), len(data)))
            check("check all: valid seal", seal_ok(out))
            chk = GTA3Save(out)
            st3 = chk.read_state()
            check("check all: progress 154", compute_progress(st3) == 154,
                  "-> %d" % compute_progress(st3))
            check("check all: missions 73/73", chk.stat(ST_MISSIONS) == 73)
            check("check all: stats[29] == 154", chk.stat(ST_PROGRESS_TOTAL) == 154)
            check("check all: packages 100", chk.packages() == 100)
            check("check all: rampages 20", chk.stat(ST_RAMPAGES) == 20)
            check("check all: jumps 20", chk.stat(ST_JUMPS_FOUND) == 20)
            check("check all: firefighter 20/20/20", chk.fire_islands() == [20, 20, 20])
            check("check all: vigilante 20/20/20", chk.vig_islands() == [20, 20, 20])
            check("check all: pickup pool emptied",
                  chk.packages_alive() == 0
                  and not chk._live_slots(RAMPAGE_TYPE, RAMPAGE_MODEL))
            check("check all: package/rampage objects gone",
                  chk.objects_count(PKG_MODEL) == 0
                  and chk.objects_count(RAMPAGE_MODEL) == 0)
            check("check all: no freed slot names a package/rampage",
                  not chk._stale_slots(), "(%d)" % len(chk._stale_slots()))
            check("check all: rampage reward 100000",
                  chk.global32("RAMPAGE_REWARD") == 5000 * 20)
            check("check all: race records filled",
                  all(chk.stat(i) for i in (56, 57, 58, 59)))
            check("check all: FLAG_ALL_* set",
                  all(chk.global32(nm) == 1 for nm in chk.names
                      if nm.startswith("FLAG_ALL_")
                      and nm.endswith("_MISSIONS_PASSED")))
            check("check all: taxi 100", chk.stat(ST_TAXI) == 100)
            check("check all: paramedic 12", chk.stat(ST_PARAMEDIC) == 12)
            check("check all: I/E 0x7F/0xFFFF/0xFFFF",
                  chk.ie_crane() == 0x7F and chk.ie_portland() == 0xFFFF
                  and chk.ie_shoreside() == 0xFFFF)
            allflags = all(chk.flag(f) == 1 for _, _, f in MISSIONS)
            check("check all: the 73 flags == 1", allflags)
            check("check all: Turismo/Bling by record",
                  chk.stat(ST_TURISMO) > 0 and chk.stat(ST_BLING_SCORE) > 0)
            glok = (chk.global32(G_PKG) == 100
                    and [chk.global32(n) for n in G_FIRES] == [20, 20, 20]
                    and [chk.global32(n) for n in G_VIG] == [20, 20, 20]
                    and chk.global32(G_FLAME) == 1
                    and chk.global32(G_CRAN) == 1
                    and all(chk.global32(G_IE["ie_pdx"][0] % i) == 1
                            for i in range(1, 17))
                    and all(chk.global32(G_IE["ie_ssv"][0] % i) == 1
                            for i in range(1, 17))
                    and chk.global32(G_IE["ie_pdx"][1]) == 16
                    and chk.global32(G_IE["ie_ssv"][1]) == 16)
            check("check all: GTASnP globals (packages/fire/vig/"
                  "I/E slots/flame/crane)", glok)

            # 5) uncheck everything
            sav3 = GTA3Save(out)
            st4 = sav3.read_state()
            for key in list(st4):
                kind = key[0]
                if kind in ("mission", "rampage", "usj"):
                    st4[key] = 0
            st4[("meta", "ie_crane")] = 0
            st4[("meta", "ie_pdx")] = 0
            st4[("meta", "ie_ssv")] = 0
            st4[("meta", "packages")] = 0
            st4[("meta", "paramedic")] = 0
            st4[("meta", "taxi")] = 0
            st4[("meta", "fire")] = [0, 0, 0]
            st4[("meta", "vig")] = [0, 0, 0]
            apply_state(sav3, st4)
            out3 = sav3.to_bytes()
            chk3 = GTA3Save(out3)
            st5 = chk3.read_state()
            # flags and counters go back to 0, but the physical pool
            # cannot be resurrected: those packages stay collected,
            # which is worth 10 progress points
            check("uncheck all: progress == 10 (physical packages)",
                  compute_progress(st5) == 10,
                  "-> %d" % compute_progress(st5))
            check("uncheck all: missions 0", chk3.stat(ST_MISSIONS) == 0)
            check("uncheck all: rampages 0 (flags)",
                  chk3.stat(ST_RAMPAGES) == 0)
            check("uncheck all: valid seal", seal_ok(out3))

            # 6) the other profile saves parse with the same logic
            for n in (7, 8, 9):
                p = os.path.join(prof, "GTA3sf%d.sav" % n)
                if os.path.exists(p):
                    s = GTA3Save(open(p, "rb").read())
                    v = s.read_state()
                    check("GTA3sf%d: computed progress == stored" % n,
                          compute_progress(v) == s.stat(ST_PROGRESS),
                          "(%d vs %d)" % (compute_progress(v), s.stat(ST_PROGRESS)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    fails = [c for c in checks if not c[1]]
    print("\n%d checks, %d failures" % (len(checks), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    run_gui()
