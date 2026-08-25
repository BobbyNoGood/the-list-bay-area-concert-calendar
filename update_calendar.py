#!/usr/bin/env python3
import json
import re
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = "http://www.foopee.com/punk/the-list/by-date.2.html"
OUT = Path("events.json")
UA = "Mozilla/5.0 (compatible; BayAreaConcertCalendar/2.0)"
DATE_RE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})\b")

class Node:
    def __init__(self):
        self.text = []
        self.anchors = []
        self.children = []

class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.roots = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "li":
            node = Node()
            if self.stack:
                self.stack[-1].children.append(node)
            else:
                self.roots.append(node)
            self.stack.append(node)
        elif tag == "a" and self.stack:
            self.anchor = {"href": attrs.get("href", ""), "text": []}

    def handle_data(self, data):
        if not self.stack:
            return
        self.stack[-1].text.append(data)
        if self.anchor is not None:
            self.anchor["text"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self.stack and self.anchor is not None:
            self.anchor["text"] = clean("".join(self.anchor["text"]))
            self.stack[-1].anchors.append(self.anchor)
            self.anchor = None
        elif tag == "li" and self.stack:
            self.stack.pop()

def clean(value):
    return " ".join((value or "").split())

def fetch():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read().decode("latin-1", "replace")

def parse_date(label, year):
    match = DATE_RE.search(label)
    if not match:
        return None, None
    day_label = match.group(0)
    iso = datetime.strptime(
        f"{year} {match.group(2)} {match.group(3)}", "%Y %b %d"
    ).strftime("%Y-%m-%d")
    return iso, day_label

def normalize_city(city):
    city = clean(city).strip(" ,:-")
    aliases = {
        "S.F.": "San Francisco",
        "S.f.": "San Francisco",
        "SF": "San Francisco",
        "S F": "San Francisco",
    }
    return aliases.get(city, city)

def extract_city(raw, venue, first_band):
    remainder = raw
    venue_pos = remainder.find(venue)
    if venue_pos >= 0:
        remainder = remainder[venue_pos + len(venue):]
    if first_band:
        band_pos = remainder.find(first_band)
        between = remainder[:band_pos] if band_pos >= 0 else remainder
    else:
        between = remainder
    between = clean(between).strip()
    if between.startswith(","):
        between = between[1:].strip()
    bad = re.search(r"\$|\b(?:a/a|21\+|18\+|all ages|free|pm|am)\b", between, re.I)
    if bad:
        between = between[:bad.start()].strip(" ,:-")
    if len(between) > 50:
        between = ""
    return normalize_city(between)

def event_from_node(node, date, day):
    club = next((a for a in node.anchors if "by-club" in a["href"] and a["text"]), None)
    if not club:
        return None

    bands = [a["text"] for a in node.anchors if "by-band" in a["href"] and a["text"]]
    venue = clean(club["text"])
    raw = clean(" ".join(node.text))
    first_band = bands[0] if bands else ""
    city = extract_city(raw, venue, first_band)

    details = raw
    if venue:
        details = details.replace(venue, "", 1)
    if city:
        city_variants = [city]
        if city == "San Francisco":
            city_variants += ["S.F.", "S.f.", "SF"]
        for variant in city_variants:
            if variant in details:
                details = details.replace(variant, "", 1)
                break
    for band in bands:
        details = details.replace(band, "", 1)
    details = re.sub(r"^[\s,:;\-]+", "", clean(details)).strip()

    return {
        "date": date,
        "day": day,
        "venue": venue,
        "city": city,
        "artists": ", ".join(bands),
        "details": details,
    }

def main():
    raw = fetch()
    parser = TreeParser()
    parser.feed(raw)

    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    year = now.year
    events = []

    def walk(nodes, inherited_date=None, inherited_day=None):
        current_date = inherited_date
        current_day = inherited_day

        for node in nodes:
            own_text = clean(" ".join(node.text))
            found_date, found_day = parse_date(own_text, year)
            if found_date:
                current_date = found_date
                current_day = found_day

            if current_date:
                event = event_from_node(node, current_date, current_day)
                if event:
                    events.append(event)

            if node.children:
                walk(node.children, current_date, current_day)

    walk(parser.roots)

    unique = []
    seen = set()
    for event in events:
        key = (
            event["date"],
            event["venue"],
            event["city"],
            event["artists"],
            event["details"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(event)
    events = unique

    if len(events) < 30:
        raise SystemExit(
            f"Parser found only {len(events)} events; refusing to overwrite events.json."
        )

    dates = sorted({e["date"] for e in events})
    first = datetime.strptime(dates[0], "%Y-%m-%d")
    last = datetime.strptime(dates[-1], "%Y-%m-%d")

    if first.month == last.month:
        week_label = f"{first.strftime('%b')} {first.day}–{last.day}, {last.year}"
    else:
        week_label = (
            f"{first.strftime('%b')} {first.day}–"
            f"{last.strftime('%b')} {last.day}, {last.year}"
        )

    payload = {
        "meta": {
            "source": SOURCE,
            "updated_at": now.strftime("%Y-%m-%d %I:%M %p PT"),
            "week_label": week_label,
            "event_count": len(events),
        },
        "events": events,
    }

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"Wrote {len(events)} events from {SOURCE}")

if __name__ == "__main__":
    main()
