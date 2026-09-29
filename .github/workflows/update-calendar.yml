#!/usr/bin/env python3

import json
import re
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

BASE = "http://www.foopee.com/punk/the-list/"
SEEDS = [urljoin(BASE, f"by-date.{n}.html") for n in range(3)]
OUT = Path("events.json")
UA = "Mozilla/5.0 (compatible; BayAreaConcertCalendar/5.0)"

DATE_RE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})\b")
DATE_PAGE_RE = re.compile(r"(?:^|/)by-date(?:\.(\d+))?\.html$", re.I)
MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
FOOTER_WEEK_RE = re.compile(
    r"\s*\[\s*" + MON + r"\s+\d{1,2}\s*-\s*" + MON + r"\s+\d{1,2}\b", re.I)

CITY_ALIASES = {
    "S.F.": "San Francisco", "S.f.": "San Francisco", "SF": "San Francisco",
    "Mountain Veiw": "Mountain View", "UC Berkeley Campus": "Berkeley",
}
for _c in (
    "San Francisco", "Oakland", "Berkeley", "Albany", "Alameda", "San Jose",
    "Santa Cruz", "Felton", "Saratoga", "Petaluma", "Santa Rosa", "Novato",
    "Sebastopol", "Napa", "Richmond", "Mill Valley", "San Anselmo",
    "Point Reyes Station", "Half Moon Bay", "Pleasant Hill", "Los Gatos",
    "Orinda", "Mountain View", "Walnut Creek", "Rio Nido",
):
    CITY_ALIASES[_c] = _c


class Node:
    def __init__(self, parent=None):
        self.parent = parent
        self.text = []
        self.anchors = []
        self.children = []


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.roots = []
        self.anchor = None
        self.links = []
        self.in_script = False
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "script":
            self.in_script = True
            return
        if tag == "style":
            self.in_style = True
            return
        if tag == "li":
            parent = self.stack[-1] if self.stack else None
            node = Node(parent)
            if parent:
                parent.children.append(node)
            else:
                self.roots.append(node)
            self.stack.append(node)
        if tag == "a":
            href = attrs.get("href", "")
            if href:
                self.links.append(href)
            if self.stack:
                self.anchor = {"href": href, "text": []}

    def handle_data(self, data):
        if self.in_script or self.in_style or not self.stack:
            return
        self.stack[-1].text.append(data)
        if self.anchor is not None:
            self.anchor["text"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script":
            self.in_script = False
            return
        if tag == "style":
            self.in_style = False
            return
        if tag == "a" and self.stack and self.anchor is not None:
            self.anchor["text"] = clean("".join(self.anchor["text"]))
            self.stack[-1].anchors.append(self.anchor)
            self.anchor = None
        elif tag == "li" and self.stack:
            self.stack.pop()


def clean(value):
    return " ".join((value or "").split())


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("latin-1", "replace")


def resolve_date(label, now):
    match = DATE_RE.search(label)
    if not match:
        return None, None
    month = datetime.strptime(match.group(2), "%b").month
    day = int(match.group(3))
    candidates = []
    for year in (now.year - 1, now.year, now.year + 1):
        try:
            candidates.append(datetime(year, month, day, tzinfo=now.tzinfo))
        except ValueError:
            pass
    viable = [
        d for d in candidates
        if now - timedelta(days=14) <= d <= now + timedelta(days=245)
    ]
    date = min(viable or candidates, key=lambda c: abs((c - now).days))
    return date.strftime("%Y-%m-%d"), match.group(0)


STREET_RE = re.compile(
    r"\b(Street|St\.|Road|Rd\.|Ave\.|Avenue|Blvd\.|Boulevard|Drive|Dr\.)\b", re.I)


def split_venue_city(club_text):
    text = clean(club_text)
    parts = [p.strip() for p in text.split(",")]
    if len(parts) >= 2:
        tail = parts[-1]
        venue = ", ".join(parts[:-1]).strip()
        if tail in CITY_ALIASES:
            return venue, CITY_ALIASES[tail]
        if (1 <= len(tail) <= 28 and not re.search(r"\d", tail)
                and not STREET_RE.search(tail)):
            return venue, tail
    return text, ""


GARBAGE = [
    "[ Top of The List", "[Top of The List", "Top of The List",
    "Top of the List", "Graham Spencer", "gaJsHost", "google-analytics.com",
    "google-analytics", "_gat._getTracker", "pageTracker", "document.write",
    "UA-2878610-1", "javascript",
]


def sanitize_details(details):
    text = clean(details)
    match = FOOTER_WEEK_RE.search(text)
    if match:
        text = text[:match.start()]
    lower = text.lower()
    found = [lower.find(m.lower()) for m in GARBAGE]
    found = [p for p in found if p != -1]
    if found:
        text = text[:min(found)]
    text = re.sub(r"[\s\[\]|;\-]+$", "", text)
    return clean(text)


def event_from_node(node, date, day, source_url):
    club = next(
        (a for a in node.anchors if "by-club" in a["href"] and a["text"]),
        None)
    if not club:
        return None
    bands = [a["text"] for a in node.anchors
             if "by-band" in a["href"] and a["text"]]
    venue, city = split_venue_city(club["text"])
    details = clean(" ".join(node.text))
    if club["text"]:
        details = details.replace(club["text"], "", 1)
    for band in bands:
        details = details.replace(band, "", 1)
    details = re.sub(r"^[\s,:;\-]+", "", clean(details)).strip()
    details = sanitize_details(details)
    return {
        "date": date, "day": day, "venue": venue, "city": city,
        "artists": ", ".join(bands), "details": details,
        "source": source_url,
    }


def parse_page(raw, source_url, now):
    parser = PageParser()
    parser.feed(raw)
    events = []

    def walk(nodes, inherited_date=None, inherited_day=None):
        current_date, current_day = inherited_date, inherited_day
        for node in nodes:
            found_date, found_day = resolve_date(clean(" ".join(node.text)), now)
            if found_date:
                current_date, current_day = found_date, found_day
            if current_date:
                event = event_from_node(node, current_date, current_day, source_url)
                if event:
                    events.append(event)
            if node.children:
                walk(node.children, current_date, current_day)

    walk(parser.roots)
    return events, parser.links


def week_start(date_string):
    date = datetime.strptime(date_string, "%Y-%m-%d").date()
    return date - timedelta(days=date.weekday())


def week_label(start):
    end = start + timedelta(days=6)
    s, e = start.strftime("%b"), end.strftime("%b")
    if start.year != end.year:
        return f"{s} {start.day}, {start.year}–{e} {end.day}, {end.year}"
    if start.month == end.month:
        return f"{s} {start.day}–{end.day}, {start.year}"
    return f"{s} {start.day}–{e} {end.day}, {start.year}"


def page_sort_key(url):
    name = urlparse(url).path.rsplit("/", 1)[-1]
    match = DATE_PAGE_RE.search(name)
    if not match:
        return 999
    return int(match.group(1) or 0)


def main():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    today = now.date()
    queue = list(SEEDS)
    seen_urls = set()
    page_results = []
    all_events = []
    for number in range(0, 30):
        queue.append(urljoin(BASE, f"by-date.{number}.html"))
    while queue:
        url = queue.pop(0)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            raw = fetch(url)
        except Exception as exc:
            print(f"Skip {url}: {exc}")
            continue
        events, links = parse_page(raw, url, now)
        for href in links:
            absolute = urljoin(url, href)
            parsed = urlparse(absolute)
            if parsed.netloc and parsed.netloc != urlparse(BASE).netloc:
                continue
            if DATE_PAGE_RE.search(parsed.path) and absolute not in seen_urls:
                queue.append(absolute)
        if not events:
            continue
        filtered = [
            e for e in events
            if today - timedelta(days=1)
            <= datetime.strptime(e["date"], "%Y-%m-%d").date()
            <= today + timedelta(days=180)
        ]
        if not filtered:
            continue
        dates = sorted({e["date"] for e in filtered})
        page_results.append({
            "url": url, "events": len(filtered),
            "first_date": dates[0], "last_date": dates[-1],
        })
        all_events.extend(filtered)

    unique = []
    seen = set()
    for event in sorted(all_events, key=lambda e: (
            e["date"], e["venue"], e["artists"], e["details"])):
        key = (event["date"], event["venue"].lower(), event["city"].lower(),
               event["artists"].lower(), event["details"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    all_events = unique

    if len(all_events) < 30:
        raise SystemExit(
            f"Only {len(all_events)} total future events found; "
            "refusing to overwrite events.json.")

    weeks = {}
    for event in all_events:
        start = week_start(event["date"])
        key = start.isoformat()
        if key not in weeks:
            weeks[key] = {
                "start": key,
                "end": (start + timedelta(days=6)).isoformat(),
                "label": week_label(start),
                "count": 0,
            }
        weeks[key]["count"] += 1
    weeks_list = [weeks[k] for k in sorted(weeks)]
    source_pages = sorted(
        page_results,
        key=lambda p: (p["first_date"], page_sort_key(p["url"])))
    payload = {
        "meta": {
            "updated_at": now.strftime("%Y-%m-%d %I:%M %p PT"),
            "event_count": len(all_events),
            "week_count": len(weeks_list),
            "weeks": weeks_list,
            "source_pages": source_pages,
        },
        "events": all_events,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"Wrote {len(all_events)} events across {len(weeks_list)} "
          f"weeks from {len(source_pages)} Foopee pages")

    bad = ("top of the list", "google-analytics", "gajshost",
           "pagetracker", "document.write")
    garbage = [e for e in all_events
               if any(b in e.get("details", "").lower() for b in bad)]
    if garbage:
        raise SystemExit(
            f"ERROR: footer garbage still exists in {len(garbage)} events.")
    print("Footer garbage check: CLEAN")
    for page in source_pages:
        print(f"  {page['first_date']}..{page['last_date']}  "
              f"{page['events']:>3} shows  {page['url']}")


if __name__ == "__main__":
    main()
