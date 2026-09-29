#!/usr/bin/env python3
"""venue_tools.py - helper rules for consolidate.py (venue name/city matching).
The lists at the top (MANUAL_ALIASES etc.) are the ones to edit by hand."""
import difflib
import re
from collections import Counter, defaultdict

INDEX_FILE = "index.html"

# ---- Edit these by hand when the report shows a call the script can't make ----
# "name as typed on Foopee": "name you want shown"
# (write "Name|City" to limit an alias to one city)
MANUAL_ALIASES = {
    "Shoreline Theater": "Shoreline Amphitheater",
    "Civic|San Jose": "San Jose Civic",
    "Civic Center|San Jose": "San Jose Civic",
}
# venue (any spelling) -> city it is ALWAYS in
VENUE_CITY_LOCK = {
    "924 Gilman Street": "Berkeley",
}
CITY_FIX = {
    "s.f.": "San Francisco", "sf": "San Francisco", "s.f. aa": "San Francisco",
    "golden gate park": "San Francisco", "stanford campus": "Stanford",
    "stanford university": "Stanford",
}
KNOWN_CITIES = [c.strip() for c in """
San Francisco, Oakland, Berkeley, San Jose, Santa Cruz,
Daly City, Alameda, Menlo Park, Palo Alto, Stanford, Fairfax,
La Honda, Santa Rosa, Petaluma, Novato, Sebastopol,
Mill Valley, Napa, Vallejo, Richmond, Emeryville, Albany,
El Cerrito, Orinda, Walnut Creek, Concord, Pacifica, Fremont,
Hayward, San Leandro, Redwood City, Mountain View, Santa Clara,
Sunnyvale, Cupertino, Saratoga, Los Gatos, Campbell, Felton,
Crockett, Rohnert Park, Sonoma, San Rafael, Larkspur,
San Mateo, Burlingame, San Carlos, San Bruno, Half Moon Bay,
Pleasanton, Livermore, Dublin, Martinez, Benicia, Woodside,
Aptos, Capitola, Scotts Valley, Cotati, Healdsburg,
Guerneville, Point Reyes, Sausalito, Belmont, San Anselmo,
Ross, Corte Madera, Tiburon, Lafayette, Danville, Pittsburg,
Antioch, Vacaville, Davis, Sacramento, Monterey
""".replace("\n", " ").split(",") if c.strip()]
TOKEN_MAP = {"st": "street", "ave": "avenue", "theatre": "theater",
             "amphitheatre": "amphitheater", "amptheater": "amphitheater",
             "amptheatre": "amphitheater", "gillman": "gilman"}
GENERIC = {"street", "avenue", "theater", "amphitheater", "tavern", "saloon",
           "center", "centre", "hall", "club", "lounge", "bar", "room",
           "auditorium", "brewing", "brewery", "pub", "cafe", "stadium",
           "ballroom", "pavilion"}
DROP_TAIL = {"co", "inc", "llc", "company"}


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


# ------------------------------------------------------------------ cities
def canon_city(c):
    """returns (city, note)"""
    c = (c or "").strip().strip(",").strip()
    if not c:
        return "", None
    k = c.lower()
    if k in CITY_FIX:
        return CITY_FIX[k], None if CITY_FIX[k] == c else "%s -> %s" % (c, CITY_FIX[k])
    for kc in KNOWN_CITIES:
        if kc.lower() == k:
            return kc, None if kc == c else "%s -> %s" % (c, kc)
    best = max(KNOWN_CITIES, key=lambda x: ratio(k, x.lower()))
    if ratio(k, best.lower()) >= 0.86:
        return best, "%s -> %s (typo)" % (c, best)
    return c, None


# ------------------------------------------------------------------ venue names
def split_venue(raw):
    """'Hub, 2650 Broadway' -> ('Hub', '2650 Broadway')"""
    raw = (raw or "").strip()
    base, _, rest = raw.partition(",")
    base = base.strip().rstrip(".,; ") or raw.strip(",. ")
    rest = rest.strip().strip(",").strip()
    return base, (rest if rest[:1].isdigit() else "")


def key_tokens(base):
    s = re.split(r" at | @ ", base.lower())[0].replace("&", " and ")
    s = re.sub(r"['\u2019`.]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    t = [TOKEN_MAP.get(w, w) for w in s.split()]
    if len(t) > 1 and t[0] == "the":
        t = t[1:]
    while len(t) > 1 and t[-1] in DROP_TAIL:
        t = t[:-1]
    return tuple(t)


def core_and_tail(t):
    core = list(t)
    tail = []
    while len(core) > 1 and core[-1] in GENERIC:
        tail.insert(0, core.pop())
    return tuple(core), tuple(tail)


def contiguous(small, big):
    n = len(small)
    return n > 0 and n < len(big) and any(
        big[i:i + n] == small for i in range(len(big) - n + 1))


# ------------------------------------------------------------------ artists / times
def bands(artists):
    out = []
    for b in (artists or "").split(","):
        b = re.sub(r"\(.*?\)", " ", b.lower())
        b = re.sub(r"[^a-z0-9 ]", " ", b)
        b = " ".join(b.split())
        if b:
            out.append(b)
    return out


def band_overlap(x, y):
    """share of the smaller band list found in the other one (fuzzy)"""
    if not x or not y:
        return 0.0
    small, big = (x, y) if len(x) <= len(y) else (y, x)
    hit = sum(1 for s in small if any(ratio(s, b) >= 0.9 for b in big))
    return hit / len(small)


def times(details):
    d = (details or "").lower()
    ts = set(re.findall(r"\b\d{1,2}(?::\d{2})?\s*[ap]m\b", d))
    if "noon" in d:
        ts.add("noon")
    return {t.replace(" ", "") for t in ts}


# ------------------------------------------------------------------ groups
class Group:
    def __init__(self, name, city, phantom=False):
        self.name, self.city, self.phantom = name, city, phantom
        self.key = key_tokens(name)
        self.core, self.tail = core_and_tail(self.key)
        self.count = 0
        self.dates = defaultdict(list)  # date -> [band lists]


def shared_shows(a, b):
    n = 0
    for d in set(a.dates) & set(b.dates):
        if any(band_overlap(x, y) >= 0.5 for x in a.dates[d] for y in b.dates[d]):
            n += 1
    return n


def compare(a, b):
    """-> (strength, reason) ; strength 3/2 = auto, 0 = needs calendar proof / human"""
    if a.key == b.key:
        return 3, "same name after fixing case/punctuation/St.-Street"
    if a.core == b.core:
        ta, tb = set(a.tail), set(b.tail)
        if not ta or not tb or ta <= tb or tb <= ta:
            extra = " ".join(sorted(ta ^ tb)) or "word"
            return 2, "same name, only a generic word added (%s)" % extra
        return 0, "same name but different type word (%s vs %s)" % (
            " ".join(a.tail), " ".join(b.tail))
    if [w for w in a.key if w.isdigit()] != [w for w in b.key if w.isdigit()] \
            and any(w.isdigit() for w in a.key + b.key):
        digits_differ = True
    else:
        digits_differ = False
    ja, jb = " ".join(a.key), " ".join(b.key)
    rc = ratio(" ".join(a.core), " ".join(b.core))
    r = max(ratio(ja, jb), rc)
    if not digits_differ and r >= 0.88 and min(len(ja), len(jb)) >= 8 and ja[0] == jb[0]:
        return 2, "spelling typo (%d%% alike)" % round(r * 100)
    if contiguous(a.core, b.core) or contiguous(b.core, a.core):
        return 0, "one name is inside the other"
    for x, y in ((a, b), (b, a)):
        if "and" in x.key:
            parts = " ".join(x.key).split(" and ")
            if any(tuple(p.split()) and core_and_tail(tuple(p.split()))[0] == y.core
                   for p in parts):
                return 0, "'and' listing that includes the other venue"
    if rc >= 0.75 and not digits_differ:
        return 0, "names look similar (%d%% alike)" % round(rc * 100)
    return None


class Clusters:
    def __init__(self, groups):
        self.p = list(range(len(groups)))
        self.cities = [({g.city} if g.city else set()) for g in groups]

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i, j):
        ri, rj = self.find(i), self.find(j)
        if ri == rj:
            return True
        ci, cj = self.cities[ri], self.cities[rj]
        if ci and cj and ci != cj:
            return False  # different cities => different venues
        self.p[rj] = ri
        self.cities[ri] = ci | cj
        return True


def url_keys():
    """venue names the website already has links for (keys of VENUE_URLS)"""
    try:
        h = open(INDEX_FILE, encoding="utf-8").read()
        i = h.index("const VENUE_URLS")
        blk = h[i:h.index("};", i)]
        return re.findall(r'^\s*"([^"]+)"\s*:', blk, re.M)
    except Exception:
        return []
