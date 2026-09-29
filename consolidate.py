#!/usr/bin/env python3
"""consolidate.py - merge hand-typed duplicate venues/events in events.json.

Run AFTER update_calendar.py (needs venue_tools.py next to it). Rewrites
events.json and writes venue_report.txt. Names are compared fuzzily, cities must
agree, and shaky matches are only merged when the calendar itself proves it
(same date + same artists). Everything merged, and everything left for a human
to check, is listed in venue_report.txt.
"""
import json
import re
import sys
from collections import Counter, defaultdict

from venue_tools import *

EVENTS_FILE = "events.json"
REPORT_FILE = "venue_report.txt"


def main():
    data = json.load(open(EVENTS_FILE, encoding="utf-8"))
    events = data["events"]
    before_events = len(events)
    rep_city, rep_manual = [], []

    # -------- 1. clean each event's venue/city text
    lock = {key_tokens(k): v for k, v in VENUE_CITY_LOCK.items()}
    lock_core = {core_and_tail(k)[0]: v for k, v in lock.items()}
    alias_raw = {k.lower(): v for k, v in MANUAL_ALIASES.items()}
    work = []
    for e in events:
        base, addr = split_venue(e.get("venue"))
        city, note = canon_city(e.get("city"))
        for ak in ((base + "|" + city), base):
            if ak.lower() in alias_raw:
                target = alias_raw[ak.lower()]
                rep_manual.append("%s -> %s" % (ak, target))
                base = target
                break
        c0 = core_and_tail(key_tokens(base))[0]
        if c0 in lock_core and city != lock_core[c0]:
            note = "%s [%s]: %s -> %s (locked)" % (base, e.get("date"), city or "blank", lock_core[c0])
            city = lock_core[c0]
        if note:
            rep_city.append(note)
        work.append((e, base, addr, city, e.get("city", "")))

    # -------- 2. groups (venue text + city), plus the site's known venue names
    groups, gidx = [], {}
    for e, base, addr, city, oc in work:
        k = (base, city)
        if k not in gidx:
            gidx[k] = len(groups)
            groups.append(Group(base, city))
        g = groups[gidx[k]]
        g.count += 1
        g.dates[e["date"]].append(bands(e.get("artists")))
    for u in url_keys():
        groups.append(Group(u, "", phantom=True))

    # -------- 3. merge
    cl = Clusters(groups)
    pairs, review, weak = [], [], []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            a, b = groups[i], groups[j]
            if a.phantom and b.phantom:
                continue
            res = compare(a, b)
            if not res:
                continue
            if a.city and b.city and a.city != b.city:
                if res[0] >= 2 and min(a.count, b.count) < 3 and not (a.phantom or b.phantom):
                    review.append("SAME NAME, DIFFERENT CITY: '%s' (%s, %d shows) vs '%s' (%s, %d shows)" % (
                        a.name, a.city, a.count, b.name, b.city, b.count))
                continue
            strength, why = res
            if strength == 0:
                n = shared_shows(a, b)
                if n:
                    strength, why = 1, "%s; PROVEN by calendar: %d show(s) listed under both names" % (why, n)
            pairs.append((-strength, -(a.count + b.count), i, j, why))
    pairs.sort()
    merged_why = {}
    for negs, _, i, j, why in pairs:
        if -negs >= 1:
            if cl.union(i, j):
                merged_why[(i, j)] = why
        elif not (groups[i].phantom or groups[j].phantom):
            weak.append((i, j, why))

    # -------- 4. canonical name/city per cluster
    members = defaultdict(list)
    for i in range(len(groups)):
        members[cl.find(i)].append(i)
    info = {}  # root -> [name, city, has_phantom, total_count]
    for r, idx in members.items():
        gs = [groups[i] for i in idx]
        real_gs = [g for g in gs if not g.phantom]
        if not real_gs:
            continue
        ph = [g for g in gs if g.phantom]
        name = (ph[0].name if ph else
                max(real_gs, key=lambda g: (g.count, -len(g.name))).name)
        cc = Counter()
        for g in real_gs:
            if g.city:
                cc[g.city] += g.count
        info[r] = [name, cc.most_common(1)[0][0] if cc else "", bool(ph),
                   sum(g.count for g in real_gs)]
    # same venue in two cities must use ONE spelling (e.g. Hopmonk Tavern)
    votes = defaultdict(Counter)
    for r, (name, city, has_ph, n) in info.items():
        if not has_ph:
            votes[core_and_tail(key_tokens(name))[0]][name] += n
    for r, v in info.items():
        if not v[2]:
            v[0] = max(votes[core_and_tail(key_tokens(v[0]))[0]].items(),
                       key=lambda kv: (kv[1], -len(kv[0])))[0]
    canon, merge_lines = {}, []
    for r, idx in members.items():
        if r not in info:
            continue
        name, city = info[r][0], info[r][1]
        real_gs = [groups[i] for i in idx if not groups[i].phantom]
        for g in real_gs:
            canon[(g.name, g.city)] = (name, city)
        for g in real_gs:
            if (g.name, g.city) == (name, city):
                continue
            reason = "same venue, city was blank" if g.name == name else ""
            for (i, j), w in merged_why.items():
                if groups[i] is g or groups[j] is g:
                    reason = w
                    break
            merge_lines.append("%s | %s   <=   %s (%s, %d shows)\n      why: %s" % (
                name, city or "no city", g.name, g.city or "no city", g.count,
                reason or "same venue as the rest of its group"))
    for i, j, why in weak:
        ri, rj = cl.find(i), cl.find(j)
        if ri != rj and ri in info and rj in info:
            x, y = sorted([ri, rj], key=lambda r: info[r][0])
            review.append("CHECK: '%s' (%s, %d shows) vs '%s' (%s, %d shows) - %s" % (
                info[x][0], info[x][1] or "no city", info[x][3],
                info[y][0], info[y][1] or "no city", info[y][3], why))
    merge_lines_sorted = sorted(merge_lines)

    # -------- 5. rewrite events
    for e, base, addr, city, oc in work:
        name, ncity = canon[(base, city)]
        if not oc.strip() and ncity:
            e["details"] = re.sub(r"\s+", " ", re.sub(
                r"(?<![\w.])S\.F\.(?!\w)", "", e.get("details") or "")).strip() \
                if ncity == "San Francisco" else e.get("details", "")
        e["venue"], e["city"] = name, ncity
        if addr:
            e["address"] = addr

    # -------- 6. duplicate shows
    buckets = defaultdict(list)
    for n, e in enumerate(events):
        buckets[(e["date"], e["venue"], e["city"])].append(n)
    drop, dup_lines, maybe = set(), [], []
    for k, ns in buckets.items():
        for x in range(len(ns)):
            for y in range(x + 1, len(ns)):
                a, b = events[ns[x]], events[ns[y]]
                if ns[x] in drop or ns[y] in drop:
                    continue
                if band_overlap(bands(a.get("artists","")), bands(b.get("artists",""))) < 1.0:
                    continue
                ta, tb = times(a.get("details")), times(b.get("details"))
                if ta and tb and not (ta & tb):
                    maybe.append("%s %s: '%s' listed twice with different times (%s vs %s) - kept both" % (
                        k[0], k[1], (a.get("artists") or "")[:50], "/".join(sorted(ta)), "/".join(sorted(tb))))
                    continue
                keep, gone = (ns[x], ns[y]) if len(a.get("details") or "") >= len(b.get("details") or "") else (ns[y], ns[x])
                drop.add(gone)
                dup_lines.append("%s %s: '%s' | '%s'  (kept longer listing)" % (
                    k[0], k[1], (events[keep].get("artists") or "")[:45], (events[gone].get("artists") or "")[:45]))
    kept = [e for n, e in enumerate(events) if n not in drop]

    # -------- 7. safety + write
    venues_before = len({(b, oc) for _, b, _, _, oc in work})
    venues_after = len({(e["venue"], e["city"]) for e in kept})
    ok = len(kept) >= 0.95 * before_events
    lines = ["VENUE CLEANUP REPORT (data from %s)" % data.get("meta", {}).get("updated_at", "?"),
             "Shows: %d -> %d   Venues: %d -> %d" % (before_events, len(kept), venues_before, venues_after), ""]
    if not ok:
        lines += ["!! Cleanup would remove more than 5% of shows - NOT APPLIED. Check the lists below.", ""]
    lines += ["== MERGED VENUES (%d) ==" % len(merge_lines),
              "Shown as: KEPT NAME | city   <=   name that was folded into it"]
    lines += merge_lines_sorted or ["(none)"]
    lines += ["", "== CITY FIXES (%d) ==" % len(rep_city)] + (sorted(set(rep_city)) or ["(none)"])
    if rep_manual:
        lines += ["", "== MANUAL ALIASES USED =="] + sorted(set(rep_manual))
    lines += ["", "== DUPLICATE SHOWS REMOVED (%d) ==" % len(dup_lines)] + (dup_lines or ["(none)"])
    lines += ["", "== PLEASE CHECK - NOT MERGED (%d) ==" % (len(set(review)) + len(maybe)),
              "If two of these are really the same place, add a line to MANUAL_ALIASES in venue_tools.py."]
    lines += sorted(set(review)) + sorted(set(maybe)) or ["(none)"]
    known = {c.lower() for c in KNOWN_CITIES}
    odd = sorted({e["city"] for e in kept if e["city"] and e["city"].lower() not in known})
    lines += ["", "== CITIES NOT ON THE KNOWN LIST (check spelling) ==", ", ".join(odd) or "(none)"]
    nocity = sorted({e["venue"] for e in kept if not e["city"]})
    lines += ["", "== VENUES WITH NO CITY ==", ", ".join(nocity) or "(none)"]
    open(REPORT_FILE, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    if ok:
        data["events"] = kept
        data.setdefault("meta", {})["event_count"] = len(kept)
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print("consolidate: shows %d -> %d, venues %d -> %d, applied=%s" % (
        before_events, len(kept), venues_before, venues_after, ok))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
