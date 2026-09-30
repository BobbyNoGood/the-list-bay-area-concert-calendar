#!/usr/bin/env python3
"""rename_venues.py - runs last: final venue display names + a link on every show.
Edit RENAMES to change what a venue is called on the site.
Format: "Name as it is now|City": "Name to show".
Keep the venue name inside the new name for venues that have a website link
in index.html (e.g. "Fox Theater Oakland" still contains "Fox Theater")."""
import json
import re
from urllib.parse import quote_plus, urlparse

BLOCKED = ("livenation.com", "ticketmaster.com")

RENAMES = {
    "Arena|Oakland": "Oakland Arena",
    "Civic Auditorium|San Francisco": "SF Civic Auditorium",
    "Fox Theater|Oakland": "Fox Theater Oakland",
    "Fox Theater|Redwood City": "Fox Theater Redwood City",
    "Frost Amphitheater|Stanford": "Frost Amphitheater Stanford",
    "Independent|San Francisco": "SF Independent",
    "Masonic|San Francisco": "The Masonic",
    "Mountain Winery|Saratoga": "Saratoga Mountain Winery",
    "Pavilion|Concord": "Concord Pavilion",
    "Music Hall|Napa": "Napa Music Hall",
    "Planetarium|Richmond": "Richmond Planetarium",
    "Quarry Amphitheater|Santa Cruz": "Quarry Amphitheater at UCSC",
    "San Jose Civic|San Jose": "San Jose Civic Center",
    "Warriors Stadium|San Francisco": "Chase Center",
}

# Official venue websites (the venue's own site, never a Ticketmaster page).
EXTRA_SITES = {
    "Fillmore": "thefillmore.com",
    "Shoreline Amphitheater": "shorelineamphitheatre.com",
    "Concord Pavilion": "concordpavilion.com",
    "Castro": "castrotheatre.com",
    "UC Theater": "uctheatre.net",
    "The Masonic": "masonicsf.com",
    "Knockout": "theknockoutsf.com",
    "Uptown Theater": "uptowntheatrenapa.com",
    "Hopmonk Tavern": "hopmonk.com",
    "Catalyst": "catalystclub.com",
    "Oakland Arena": "oaklandarena.com",
    "SF Civic Auditorium": "billgrahamcivic.com",
    "Stay Gold Deli": "staygolddeli.com",
    "Neck of the Woods": "neckofthewoodssf.com",
    "Cornerstone": "cornerstoneberkeley.com",
    "Meritage Resort": "meritageresort.com",
    "Moe's Alley": "moesalley.com",
    "Rio Theatre": "riotheatre.com",
    "Crepe Place": "crepeplace.com",
    "Hotel Utah": "hotelutah.com",
    "Cow Palace": "cowpalace.com",
    "Palace of Fine Arts": "palaceoffinearts.com",
    "Guild Theater": "guildtheatre.com",
    "Eagle": "sf-eagle.com",
    "Great Northern": "thegreatnorthernsf.com",
    "Felton Music Hall": "feltonmusichall.com",
    "Freight": "thefreight.org",
    "Arlene Francis Center": "arlenefranciscenter.org",
    "Paramount Theatre": "paramounttheatre.com",
    "Black Cat": "blackcatsf.com",
    "Feinstein's at the Nikko": "feinsteinssf.com",
    "Gray Area": "grayarea.org",
    "Kuumbwa Jazz Center": "kuumbwajazz.org",
    "Mystic Theater": "mystictheatre.com",
    "Biscuits and Blues": "biscuitsandblues.com",
    "Gundlach Bundschu Winery": "gunbun.com",
    "Faction Brewing": "factionbrewing.com",
    "Lanesplitters Pizza": "lanesplitters.com",
    "Hardly Strictly Bluegrass at Golden Gate Park": "hardlystrictly.com",
    "Fox Theater Redwood City": "foxrwc.com",
    "Fox Theater Oakland": "thefoxoakland.com",
}


def venue_sites():
    """VENUE_URLS from index.html -> {venue key: website}. Ticketmaster/Live Nation
    pages are not venue websites, so they are skipped (those shows get a search link)."""
    try:
        h = open("index.html", encoding="utf-8").read()
        i = h.index("const VENUE_URLS")
        blk = h[i:h.index("};", i)]
        found = re.findall(r'"([^"]+)"\s*:\s*"(https?://[^"]+)"', blk)
        return {k: u for k, u in found if not any(b in u for b in BLOCKED)}
    except Exception:
        return {}


def make_link(e, sites):
    """Best-effort link straight to this show. Known venue site: jump to the top
    result on that site for the headliner. Otherwise: a web search for the show."""
    artists = re.sub(r"^\s*(CANCELLED|SOLD OUT)\s*:\s*", "", e.get("artists") or "", flags=re.I)
    headliner = artists.split(",")[0].split("(")[0].strip()
    venue, city = e.get("venue", ""), e.get("city", "")
    if venue in EXTRA_SITES:
        q = "!ducky %s %s site:%s" % (headliner, venue, EXTRA_SITES[venue])
        return "https://duckduckgo.com/?q=" + quote_plus(q)
    for key, url in sites.items():
        if key.lower() in venue.lower():
            host = urlparse(url).netloc.replace("www.", "")
            q = "!ducky %s %s site:%s" % (headliner, venue, host)
            return "https://duckduckgo.com/?q=" + quote_plus(q)
    q = "%s %s %s %s -site:ticketmaster.com -site:livenation.com" % (
        headliner, venue, city, e.get("day", ""))
    return "https://www.google.com/search?q=" + quote_plus(q)


def patch_index():
    """Make the show cards use each show's own link (done once, safe to repeat)."""
    try:
        h = open("index.html", encoding="utf-8").read()
    except OSError:
        return "index.html not found"
    if "event.link||" in h:
        return "already patched"
    new, n = re.subn(r"venueURL\(\s*event\.venue\s*\)",
                     "(event.link||venueURL(event.venue))", h)
    if n != 1:
        return "NOT patched (expected 1 spot, found %d)" % n
    new = new.replace('"Official venue \u2197"', '"Find this show \u2197"')
    open("index.html", "w", encoding="utf-8").write(new)
    return "patched"


def main():
    data = json.load(open("events.json", encoding="utf-8"))
    sites = venue_sites()
    used = {}
    for e in data["events"]:
        k = "%s|%s" % (e.get("venue", ""), e.get("city", ""))
        if k in RENAMES:
            e["venue"] = RENAMES[k]
            used[k] = used.get(k, 0) + 1
        e["link"] = make_link(e, sites)
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    try:
        with open("venue_report.txt", "a", encoding="utf-8") as f:
            f.write("\n== RENAMES APPLIED (rename_venues.py) ==\n")
            for k, n in sorted(used.items()):
                f.write("%s  ->  %s (%d shows)\n" % (k, RENAMES[k], n))
            for k in sorted(set(RENAMES) - set(used)):
                f.write("NOT FOUND (no shows right now): %s\n" % k)
    except OSError:
        pass
    print("index.html:", patch_index())
    print("rename_venues: renamed %d shows, links on %d shows" % (
        sum(used.values()), len(data["events"])))


if __name__ == "__main__":
    main()
