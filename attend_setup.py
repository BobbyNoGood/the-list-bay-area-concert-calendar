#!/usr/bin/env python3
"""attend_setup.py - runs after rename_venues.py.
1) gives every show a stable id (used by the guitar counter);
2) hooks attend.js into index.html (safe to run every day; skips if already done)."""
import hashlib
import json
import re


def show_id(e):
    artists = re.sub(r"^\s*(CANCELLED|SOLD OUT)\s*:\s*", "", e.get("artists") or "", flags=re.I)
    headliner = re.sub(r"[^a-z0-9]+", " ", artists.split(",")[0].lower()).strip()
    city = re.sub(r"[^a-z0-9]+", " ", (e.get("city") or "").lower()).strip()
    return hashlib.sha1(("%s|%s|%s" % (e.get("date", ""), city, headliner)).encode()).hexdigest()[:12]


# (regex, replacement) - each must match exactly once in index.html
HOOKS = [
    (r"\.sort\(\s*\(a,b\)=>\s*a\.date\.localeCompare\(\s*b\.date\s*\)\s*\|\|\s*a\.venue\.localeCompare\(\s*b\.venue\s*\)\s*\)",
     ".sort(window.attendSort||((a,b)=>a.date.localeCompare(b.date)||a.venue.localeCompare(b.venue)))"),
    (r"!groups\.has\(\s*event\.date\s*\)", "!groups.has(window.attendKey?window.attendKey(event):event.date)"),
    (r"groups\.set\(\s*event\.date,", "groups.set(window.attendKey?window.attendKey(event):event.date,"),
    (r"groups\s*\.get\(\s*event\.date\s*\)", "groups.get(window.attendKey?window.attendKey(event):event.date)"),
    (r"\$\{esc\(list\[0\]\.day\)\}", "${esc(window.attendHead?window.attendHead():list[0].day)}"),
    (r'(<div class="city">\s*\$\{esc\(event\.city\)\}\s*</div>)', r"\1${window.attendBtn?window.attendBtn(event):''}"),
    (r"JSON\.stringify\(event\)", "JSON.stringify({...event,link:0,id:0})"),
    (r"</body>", '<script src="attend.js"></script>\n</body>'),
]


def patch_index():
    try:
        h = open("index.html", encoding="utf-8").read()
    except OSError:
        return "index.html not found"
    if "attend.js" in h:
        return "already hooked"
    for pat, rep in HOOKS:
        found = len(re.findall(pat, h))
        if found != 1:
            return "NOT hooked (pattern %r matched %d times, expected 1)" % (pat[:40], found)
    for pat, rep in HOOKS:
        h = re.sub(pat, rep, h, count=1)
    open("index.html", "w", encoding="utf-8").write(h)
    return "hooked"


def main():
    data = json.load(open("events.json", encoding="utf-8"))
    for e in data["events"]:
        e["id"] = show_id(e)
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("attend_setup: ids on %d shows; index.html: %s" % (len(data["events"]), patch_index()))


if __name__ == "__main__":
    main()
