#!/usr/bin/env python3
import json, re, urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = "http://www.foopee.com/punk/the-list/by-date.2.html"
OUT = Path("events.json")
UA = "Mozilla/5.0 (compatible; BayAreaConcertCalendar/1.0)"

class Node:
    def __init__(self):
        self.text=[]; self.anchors=[]; self.children=[]

class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.stack=[]; self.roots=[]; self.anchor=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag.lower()=="li":
            n=Node()
            (self.stack[-1].children if self.stack else self.roots).append(n)
            self.stack.append(n)
        elif tag.lower()=="a" and self.stack:
            self.anchor={"href":attrs.get("href",""),"text":[]}
    def handle_data(self,data):
        if self.stack:
            self.stack[-1].text.append(data)
            if self.anchor is not None: self.anchor["text"].append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self.stack and self.anchor is not None:
            self.anchor["text"]=" ".join("".join(self.anchor["text"]).split())
            self.stack[-1].anchors.append(self.anchor); self.anchor=None
        elif tag.lower()=="li" and self.stack:
            self.stack.pop()

def clean(s): return " ".join((s or "").split())

def fetch():
    req=urllib.request.Request(SOURCE,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=45) as r:
        return r.read().decode("latin-1","replace")

def parse_date(label,year):
    m=re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})\b",label)
    if not m: return None
    return datetime.strptime(f"{year} {m.group(2)} {m.group(3)}","%Y %b %d").strftime("%Y-%m-%d")

def city_venue(text):
    s=clean(text); aliases={"S.F.":"San Francisco","S.f.":"San Francisco","SF":"San Francisco"}
    parts=[p.strip() for p in s.split(",")]
    if len(parts)>1:
        return ", ".join(parts[:-1]).strip(), aliases.get(parts[-1],parts[-1])
    return s,""

def event_from_li(li,date,day):
    club=next((a for a in li.anchors if "by-club" in a["href"]),None)
    bands=[a["text"] for a in li.anchors if "by-band" in a["href"] and a["text"]]
    if not club: club=li.anchors[0] if li.anchors else None
    if not club: return None
    venue,city=city_venue(club["text"])
    raw=clean(" ".join(li.text)); details=raw
    for token in [club["text"]]+bands:
        if token: details=details.replace(token,"",1)
    details=re.sub(r"^[\s,:;-]+","",details).strip()
    return {"date":date,"day":day,"venue":venue,"city":city,"artists":", ".join(bands),"details":details}

def main():
    raw=fetch(); p=TreeParser(); p.feed(raw)
    now=datetime.now(ZoneInfo("America/Los_Angeles")); year=now.year; events=[]
    def walk(nodes):
        for n in nodes:
            own=clean(" ".join(n.text)); date=parse_date(own,year)
            if date and n.children:
                m=re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+[A-Z][a-z]{2}\s+\d{1,2}\b",own)
                day=m.group(0) if m else own
                for child in n.children:
                    e=event_from_li(child,date,day)
                    if e: events.append(e)
            walk(n.children)
    walk(p.roots)
    if len(events)<5:
        raise SystemExit(f"Parser found only {len(events)} events; refusing to overwrite good data.")
    dates=sorted({e["date"] for e in events}); first=datetime.strptime(dates[0],"%Y-%m-%d"); last=datetime.strptime(dates[-1],"%Y-%m-%d")
    label=f"{first.strftime('%b')} {first.day}–{last.day}, {last.year}"
    payload={"meta":{"source":SOURCE,"updated_at":now.strftime("%Y-%m-%d %I:%M %p PT"),"week_label":label},"events":events}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {len(events)} events from {SOURCE}")

if __name__=="__main__": main()
