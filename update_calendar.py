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

SEEDS = [
    urljoin(BASE, "by-date.0.html"),
    urljoin(BASE, "by-date.1.html"),
    urljoin(BASE, "by-date.2.html"),
]

OUT = Path("events.json")

UA = "Mozilla/5.0 (compatible; BayAreaConcertCalendar/5.0)"

DATE_RE = re.compile(
    r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"([A-Z][a-z]{2})\s+"
    r"(\d{1,2})\b"
)

DATE_PAGE_RE = re.compile(
    r"(?:^|/)by-date(?:\.(\d+))?\.html$",
    re.I
)

#
# THIS is the important footer fix.
#
# Foopee puts navigation like:
#
# [ Aug 24 - Aug 30 ] [ Aug 31 - Sep 6 ] ...
#
# inside the final concert listing on each page.
# As soon as one of those week ranges appears,
# everything after it is page navigation/footer junk.
#

FOOTER_WEEK_RE = re.compile(
    r"\s*\[\s*"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+\d{1,2}"
    r"\s*-\s*"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+\d{1,2}"
    r"\s*\]",
    re.I
)


CITY_ALIASES = {
    "S.F.": "San Francisco",
    "S.f.": "San Francisco",
    "SF": "San Francisco",
    "San Francisco": "San Francisco",

    "Oakland": "Oakland",
    "Berkeley": "Berkeley",
    "Albany": "Albany",
    "Alameda": "Alameda",
    "San Jose": "San Jose",
    "Santa Cruz": "Santa Cruz",
    "Felton": "Felton",
    "Saratoga": "Saratoga",
    "Petaluma": "Petaluma",
    "Santa Rosa": "Santa Rosa",
    "Novato": "Novato",
    "Sebastopol": "Sebastopol",
    "Napa": "Napa",
    "Richmond": "Richmond",
    "Mill Valley": "Mill Valley",
    "San Anselmo": "San Anselmo",
    "Point Reyes Station": "Point Reyes Station",
    "Half Moon Bay": "Half Moon Bay",
    "Pleasant Hill": "Pleasant Hill",
    "Los Gatos": "Los Gatos",
    "Orinda": "Orinda",
    "Mountain View": "Mountain View",
    "Mountain Veiw": "Mountain View",
    "Walnut Creek": "Walnut Creek",
    "Rio Nido": "Rio Nido",

    "UC Berkeley Campus": "Berkeley",
}


class Node:

    def __init__(self, parent=None):

        self.parent = parent
        self.text = []
        self.anchors = []
        self.children = []


class PageParser(HTMLParser):

    def __init__(self):

        super().__init__(
            convert_charrefs=True
        )

        self.stack = []
        self.roots = []

        self.anchor = None

        self.links = []

        self.in_script = False
        self.in_style = False


    def handle_starttag(
        self,
        tag,
        attrs
    ):

        attrs = dict(attrs)

        tag = tag.lower()

        if tag == "script":

            self.in_script = True
            return

        if tag == "style":

            self.in_style = True
            return

        if tag == "li":

            parent = (
                self.stack[-1]
                if self.stack
                else None
            )

            node = Node(
                parent
            )

            if parent:

                parent.children.append(
                    node
                )

            else:

                self.roots.append(
                    node
                )

            self.stack.append(
                node
            )

        if tag == "a":

            href = attrs.get(
                "href",
                ""
            )

            if href:

                self.links.append(
                    href
                )

            if self.stack:

                self.anchor = {
                    "href": href,
                    "text": []
                }


    def handle_data(
        self,
        data
    ):

        if (
            self.in_script
            or
            self.in_style
        ):

            return

        if not self.stack:

            return

        self.stack[-1].text.append(
            data
        )

        if self.anchor is not None:

            self.anchor["text"].append(
                data
            )


    def handle_endtag(
        self,
        tag
    ):

        tag = tag.lower()

        if tag == "script":

            self.in_script = False
            return

        if tag == "style":

            self.in_style = False
            return

        if (
            tag == "a"
            and
            self.stack
            and
            self.anchor is not None
        ):

            self.anchor["text"] = clean(
                "".join(
                    self.anchor["text"]
                )
            )

            self.stack[-1].anchors.append(
                self.anchor
            )

            self.anchor = None

        elif (
            tag == "li"
            and
            self.stack
        ):

            self.stack.pop()


def clean(
    value
):

    return " ".join(
        (value or "").split()
    )


def fetch(
    url
):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=45
    ) as response:

        return response.read().decode(
            "latin-1",
            "replace"
        )


def resolve_date(
    label,
    now
):

    match = DATE_RE.search(
        label
    )

    if not match:

        return None, None

    month = datetime.strptime(
        match.group(2),
        "%b"
    ).month

    day = int(
        match.group(3)
    )

    candidates = []

    for year in (
        now.year - 1,
        now.year,
        now.year + 1
    ):

        try:

            candidates.append(
                datetime(
                    year,
                    month,
                    day,
                    tzinfo=now.tzinfo
                )
            )

        except ValueError:

            pass

    viable = [
        date
        for date in candidates
        if (
            now - timedelta(days=14)
            <=
            date
            <=
            now + timedelta(days=245)
        )
    ]

    possible = (
        viable
        or
        candidates
    )

    date = min(
        possible,
        key=lambda candidate:
            abs(
                (
                    candidate
                    -
                    now
                ).days
            )
    )

    return (
        date.strftime(
            "%Y-%m-%d"
        ),
        match.group(0)
    )


def split_venue_city(
    club_text
):

    text = clean(
        club_text
    )

    parts = [
        part.strip()
        for part in text.split(",")
    ]

    if len(parts) >= 2:

        tail = parts[-1]

        if tail in CITY_ALIASES:

            venue = ", ".join(
                parts[:-1]
            ).strip()

            city = CITY_ALIASES[
                tail
            ]

            return (
                venue,
                city
            )

    if len(parts) >= 2:

        tail = parts[-1]

        looks_like_city = (
            1
            <=
            len(tail)
            <=
            28

            and

            not re.search(
                r"\d",
                tail
            )

            and

            not re.search(
                r"\b("
                r"Street|St\.|"
                r"Road|Rd\.|"
                r"Ave\.|Avenue|"
                r"Blvd\.|Boulevard|"
                r"Drive|Dr\."
                r")\b",
                tail,
                re.I
            )
        )

        if looks_like_city:

            venue = ", ".join(
                parts[:-1]
            ).strip()

            return (
                venue,
                tail
            )

    return (
        text,
        ""
    )


def sanitize_details(
    details
):

    text = clean(
        details
    )

    #
    # PRIMARY FIX:
    #
    # Cut off the first Foopee weekly
    # navigation range and EVERYTHING
    # following it.
    #
    # Example:
    #
    # a/a $20 7pm
    # [ Aug 24 - Aug 30 ]
    # [ Aug 31 - Sep 6 ]
    # [ Top of The List ]
    # javascript garbage...
    #
    # becomes simply:
    #
    # a/a $20 7pm
    #

    match = FOOTER_WEEK_RE.search(
        text
    )

    if match:

        text = text[
            :match.start()
        ]


    #
    # Backup hard stops in case Foopee
    # changes the footer format.
    #

    garbage_markers = [
        "[ Top of The List",
        "[Top of The List",
        "Top of The List",
        "Top of the List",
        "Graham Spencer",
        "gaJsHost",
        "google-analytics.com",
        "google-analytics",
        "_gat._getTracker",
        "pageTracker",
        "document.write",
        "UA-2878610-1",
        "javascript",
    ]

    lower_text = (
        text.lower()
    )

    earliest = None

    for marker in garbage_markers:

        position = lower_text.find(
            marker.lower()
        )

        if position == -1:

            continue

        if (
            earliest is None
            or
            position < earliest
        ):

            earliest = position

    if earliest is not None:

        text = text[
            :earliest
        ]


    #
    # Clean leftover separators.
    #

    text = re.sub(
        r"[\s\[\]|;\-]+$",
        "",
        text
    )

    return clean(
        text
    )


def event_from_node(
    node,
    date,
    day,
    source_url
):

    club = next(
        (
            anchor

            for anchor in node.anchors

            if (
                "by-club"
                in
                anchor["href"]

                and

                anchor["text"]
            )
        ),
        None
    )

    if not club:

        return None

    bands = [
        anchor["text"]

        for anchor in node.anchors

        if (
            "by-band"
            in
            anchor["href"]

            and

            anchor["text"]
        )
    ]

    venue, city = split_venue_city(
        club["text"]
    )

    raw = clean(
        " ".join(
            node.text
        )
    )

    details = raw

    if club["text"]:

        details = details.replace(
            club["text"],
            "",
            1
        )

    for band in bands:

        details = details.replace(
            band,
            "",
            1
        )

    details = re.sub(
        r"^[\s,:;\-]+",
        "",
        clean(
            details
        )
    ).strip()

    details = sanitize_details(
        details
    )

    return {
        "date": date,
        "day": day,
        "venue": venue,
        "city": city,
        "artists": ", ".join(
            bands
        ),
        "details": details,
        "source": source_url,
    }


def parse_page(
    raw,
    source_url,
    now
):

    parser = PageParser()

    parser.feed(
        raw
    )

    events = []


    def walk(
        nodes,
        inherited_date=None,
        inherited_day=None
    ):

        current_date = (
            inherited_date
        )

        current_day = (
            inherited_day
        )

        for node in nodes:

            own_text = clean(
                " ".join(
                    node.text
                )
            )

            found_date, found_day = resolve_date(
                own_text,
                now
            )

            if found_date:

                current_date = (
                    found_date
                )

                current_day = (
                    found_day
                )

            if current_date:

                event = event_from_node(
                    node,
                    current_date,
                    current_day,
                    source_url
                )

                if event:

                    events.append(
                        event
                    )

            if node.children:

                walk(
                    node.children,
                    current_date,
                    current_day
                )


    walk(
        parser.roots
    )

    return (
        events,
        parser.links
    )


def week_start(
    date_string
):

    date = datetime.strptime(
        date_string,
        "%Y-%m-%d"
    ).date()

    return (
        date
        -
        timedelta(
            days=date.weekday()
        )
    )


def week_label(
    start
):

    end = (
        start
        +
        timedelta(
            days=6
        )
    )

    if (
        start.year
        !=
        end.year
    ):

        return (
            f"{start.strftime('%b')} "
            f"{start.day}, "
            f"{start.year}"
            f"–"
            f"{end.strftime('%b')} "
            f"{end.day}, "
            f"{end.year}"
        )

    if (
        start.month
        ==
        end.month
    ):

        return (
            f"{start.strftime('%b')} "
            f"{start.day}"
            f"–"
            f"{end.day}, "
            f"{start.year}"
        )

    return (
        f"{start.strftime('%b')} "
        f"{start.day}"
        f"–"
        f"{end.strftime('%b')} "
        f"{end.day}, "
        f"{start.year}"
    )


def page_sort_key(
    url
):

    name = urlparse(
        url
    ).path.rsplit(
        "/",
        1
    )[-1]

    match = DATE_PAGE_RE.search(
        name
    )

    if not match:

        return 999

    return int(
        match.group(1)
        or
        0
    )


def main():

    now = datetime.now(
        ZoneInfo(
            "America/Los_Angeles"
        )
    )

    today = now.date()

    queue = list(
        SEEDS
    )

    seen_urls = set()

    page_results = []

    all_events = []


    #
    # Probe future Foopee weekly pages.
    #

    for number in range(
        0,
        30
    ):

        queue.append(
            urljoin(
                BASE,
                f"by-date.{number}.html"
            )
        )


    while queue:

        url = queue.pop(0)

        if url in seen_urls:

            continue

        seen_urls.add(
            url
        )


        try:

            raw = fetch(
                url
            )

        except Exception as exc:

            print(
                f"Skip {url}: {exc}"
            )

            continue


        events, links = parse_page(
            raw,
            url,
            now
        )


        for href in links:

            absolute = urljoin(
                url,
                href
            )

            parsed = urlparse(
                absolute
            )

            if (
                parsed.netloc
                and
                parsed.netloc
                !=
                urlparse(BASE).netloc
            ):

                continue

            if (
                DATE_PAGE_RE.search(
                    parsed.path
                )

                and

                absolute
                not in
                seen_urls
            ):

                queue.append(
                    absolute
                )


        if not events:

            continue


        filtered = [

            event

            for event in events

            if (
                today
                -
                timedelta(
                    days=1
                )

                <=

                datetime.strptime(
                    event["date"],
                    "%Y-%m-%d"
                ).date()

                <=

                today
                +
                timedelta(
                    days=180
                )
            )
        ]


        if not filtered:

            continue


        dates = sorted(
            {
                event["date"]

                for event in filtered
            }
        )


        page_results.append(
            {
                "url": url,

                "events": len(
                    filtered
                ),

                "first_date": dates[0],

                "last_date": dates[-1],
            }
        )


        all_events.extend(
            filtered
        )


    #
    # Remove duplicates.
    #

    unique = []

    seen = set()


    for event in sorted(
        all_events,
        key=lambda e: (
            e["date"],
            e["venue"],
            e["artists"],
            e["details"]
        )
    ):

        key = (
            event["date"],
            event["venue"].lower(),
            event["city"].lower(),
            event["artists"].lower(),
            event["details"].lower(),
        )


        if key in seen:

            continue


        seen.add(
            key
        )

        unique.append(
            event
        )


    all_events = unique


    #
    # Safety check.
    #

    if len(all_events) < 30:

        raise SystemExit(
            f"Only "
            f"{len(all_events)} "
            f"total future events found; "
            f"refusing to overwrite "
            f"events.json."
        )


    weeks = {}


    for event in all_events:

        start = week_start(
            event["date"]
        )

        key = start.isoformat()


        if key not in weeks:

            weeks[key] = {

                "start": key,

                "end": (
                    start
                    +
                    timedelta(
                        days=6
                    )
                ).isoformat(),

                "label": week_label(
                    start
                ),

                "count": 0,
            }


        weeks[key]["count"] += 1


    weeks_list = [
        weeks[key]

        for key in sorted(
            weeks
        )
    ]


    source_pages = sorted(
        page_results,

        key=lambda page: (
            page["first_date"],
            page_sort_key(
                page["url"]
            )
        )
    )


    payload = {

        "meta": {

            "updated_at": now.strftime(
                "%Y-%m-%d %I:%M %p PT"
            ),

            "event_count": len(
                all_events
            ),

            "week_count": len(
                weeks_list
            ),

            "weeks": weeks_list,

            "source_pages": source_pages,
        },

        "events": all_events,
    }


    OUT.write_text(

        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        )

        +

        "\n",

        encoding="utf-8"
    )


    print(
        f"Wrote "
        f"{len(all_events)} events "
        f"across "
        f"{len(weeks_list)} weeks "
        f"from "
        f"{len(source_pages)} "
        f"Foopee pages"
    )


    #
    # EXTRA TEST:
    #
    # If any footer garbage somehow remains,
    # report it prominently in the workflow.
    #

    garbage = []

    for event in all_events:

        combined = (
            event.get(
                "details",
                ""
            )
        ).lower()

        if (
            "top of the list"
            in combined

            or

            "google-analytics"
            in combined

            or

            "gajshost"
            in combined

            or

            "pagetracker"
            in combined

            or

            "document.write"
            in combined
        ):

            garbage.append(
                event
            )


    if garbage:

        raise SystemExit(
            f"ERROR: footer garbage "
            f"still exists in "
            f"{len(garbage)} events. "
            f"events.json was generated "
            f"but this run is being "
            f"marked failed so the "
            f"problem cannot go unnoticed."
        )


    print(
        "Footer garbage check: CLEAN"
    )


    for page in source_pages:

        print(
            f"  "
            f"{page['first_date']}"
            f".."
            f"{page['last_date']}  "
            f"{page['events']:>3} shows  "
            f"{page['url']}"
        )


if __name__ == "__main__":

    main()
