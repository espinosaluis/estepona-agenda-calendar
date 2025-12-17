#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import html as html_mod
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional, Tuple, Iterable, Dict

from ics import Calendar, Event

# =========================
# CONFIG
# =========================
AGENDA_URL = "https://turismo.estepona.es/agenda/"
OUTPUT_ICS = "agenda.ics"
LOCAL_TZ = ZoneInfo("Europe/Madrid")

SOURCE_DESC = "Fuente: turismo.estepona.es/agenda"
EXCLUDE_TITLE_KEYWORDS = [
    "LOUIE LOUIE",  # remove always
]
# Some garbage strings that sometimes appear
GARBAGE_PREFIXES = [
    "Copyright ©",
]

# =========================
# HELPERS
# =========================

def _is_garbage_line(s: str) -> bool:
    s = s.strip()
    if not s:
        return True
    for p in GARBAGE_PREFIXES:
        if s.startswith(p):
            return True
    return False

def _contains_excluded_keyword(title: str) -> bool:
    up = title.upper()
    return any(k in up for k in EXCLUDE_TITLE_KEYWORDS)

def _clean_spaces(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def _strip_tags_to_lines(html: str) -> List[str]:
    # Remove scripts/styles
    html = re.sub(r"(?is)<script.*?>.*?</script>", "\n", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", "\n", html)
    # Replace <br> and block ends with newlines
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|li|h1|h2|h3|h4|tr|td|th)>", "\n", html)
    # Remove remaining tags
    text = re.sub(r"(?is)<[^>]+>", "\n", html)
    text = html_mod.unescape(text)
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ _clean_spaces(x) for x in text.split("\n") ]
    # Drop empties/garbage
    lines = [x for x in lines if x and not _is_garbage_line(x)]
    return lines

def _parse_dmy(s: str) -> Optional[date]:
    s = s.strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    return date(y, mo, d)

def _parse_until_or_range_header(line: str) -> Optional[Tuple[str, date, Optional[date]]]:
    """
    Detect:
      - "Hasta el 04/1/2026"
      - "HASTA 04/01/2026"
      - "DEL 18/12/25 HASTA 12/01/26"
    Returns: (kind, start_date, end_date)
      kind: "until" or "range"
    """
    l = line.strip()
    # DEL dd/mm/yy HASTA dd/mm/yy
    m = re.search(r"(?i)\bDEL\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+HASTA\s+(\d{1,2}/\d{1,2}/\d{2,4})\b", l)
    if m:
        d1 = _parse_dmy(m.group(1))
        d2 = _parse_dmy(m.group(2))
        if d1 and d2:
            return ("range", d1, d2)

    # Hasta el dd/mm/yy  OR HASTA dd/mm/yy
    m = re.search(r"(?i)\bHASTA(?:\s+EL)?\s+(\d{1,2}/\d{1,2}/\d{2,4})\b", l)
    if m:
        d2 = _parse_dmy(m.group(1))
        if d2:
            # start unknown here; we’ll set it when we create the event (today or month context)
            return ("until", date.today(), d2)

    return None

def _parse_date_set_header(line: str) -> Optional[List[date]]:
    """
    Detect things like:
      - "16/12/25"
      - "15 – 19/12/25"
      - "19-20 & 21/12/25"
      - "09 & 10/01/26"
      - "22-23 & 24" (we'll ignore incomplete because missing month/year)
    Returns list of dates, or None.
    """
    l = line.strip()

    # Exact date
    d = _parse_dmy(l)
    if d:
        return [d]

    # Range like "15 – 19/12/25" or "15-19/12/25"
    m = re.match(r"^(\d{1,2})\s*[–-]\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})$", l)
    if m:
        d1, d2, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        if y < 100:
            y += 2000
        start = date(y, mo, d1)
        end = date(y, mo, d2)
        if end < start:
            return None
        out = []
        cur = start
        while cur <= end:
            out.append(cur)
            cur += timedelta(days=1)
        return out

    # Multi like "19-20 & 21/12/25" or "09 & 10/01/26"
    # Capture rightmost "/mm/yy" and then days list on left
    m = re.match(r"^(.+?)\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})$", l)
    if m:
        left = m.group(1).strip()
        mo = int(m.group(2))
        y = int(m.group(3))
        if y < 100:
            y += 2000

        # extract day numbers from left: supports "19-20 & 21" or "09 & 10"
        day_nums: List[int] = []
        # first handle ranges like 19-20
        for rng in re.findall(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", left):
            a, b = int(rng[0]), int(rng[1])
            day_nums.extend(list(range(min(a, b), max(a, b) + 1)))
        # then individual numbers
        for n in re.findall(r"\b(\d{1,2})\b", left):
            day_nums.append(int(n))
        day_nums = sorted(set(day_nums))

        # sanity: must have at least 1
        if day_nums:
            out = []
            for dn in day_nums:
                try:
                    out.append(date(y, mo, dn))
                except ValueError:
                    pass
            return out if out else None

    return None

_TIME_RANGE_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2})\s*(?:[–-]|a|hasta)\s*(?P<end>\d{1,2}:\d{2})\s+(?P<title>.+)$",
    re.IGNORECASE
)
_TIME_START_RE = re.compile(r"^(?P<start>\d{1,2}:\d{2})\s+(?P<title>.+)$")

def _parse_time_and_title(line: str) -> Optional[Tuple[time, Optional[time], str]]:
    """
    Returns (start_time, end_time_or_None, title)
    Supports:
      "18:00 TITLE..."
      "12:00 – 18:00 TITLE..."
    """
    l = line.strip()
    m = _TIME_RANGE_RE.match(l)
    if m:
        sh, sm = map(int, m.group("start").split(":"))
        eh, em = map(int, m.group("end").split(":"))
        title = _clean_spaces(m.group("title"))
        return (time(sh, sm), time(eh, em), title)
    m = _TIME_START_RE.match(l)
    if m:
        sh, sm = map(int, m.group("start").split(":"))
        title = _clean_spaces(m.group("title"))
        return (time(sh, sm), None, title)
    return None

@dataclass
class PendingRangeEvent:
    kind: str               # "until" or "range"
    start: date
    end: date
    title: Optional[str] = None
    details: List[str] = None

def fetch_agenda_text_lines() -> List[str]:
    """
    Use Playwright to fetch and render the agenda page.
    This avoids Python SSL verification issues against that host.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright no está disponible. Asegúrate de instalarlo en el workflow.") from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(AGENDA_URL, wait_until="networkidle", timeout=90_000)
        html = page.content()
        browser.close()

    return _strip_tags_to_lines(html)

def build_calendar(lines: List[str]) -> Calendar:
    cal = Calendar()

    active_dates: List[date] = []
    pending_range: Optional[PendingRangeEvent] = None

    # We’ll store a small “buffer” for location/extra lines after a time/title line.
    last_event_ctx: Optional[Dict] = None

    # Helper to flush a multi-day ("Hasta"/"Del...hasta") event
    def flush_pending_range():
        nonlocal pending_range
        if not pending_range or not pending_range.title:
            pending_range = None
            return

        title = pending_range.title
        if _contains_excluded_keyword(title):
            pending_range = None
            return

        e = Event()
        e.name = title

        # Multi-day all-day spanning
        start_dt = datetime.combine(pending_range.start, time(0, 0), tzinfo=LOCAL_TZ)
        end_dt = datetime.combine(pending_range.end + timedelta(days=1), time(0, 0), tzinfo=LOCAL_TZ)
        e.begin = start_dt
        e.end = end_dt

        desc_lines = [SOURCE_DESC]
        if pending_range.details:
            for dline in pending_range.details:
                if dline and not _is_garbage_line(dline):
                    desc_lines.append(dline)
        e.description = "\n".join(desc_lines)

        cal.events.add(e)
        pending_range = None

    # Dedup set
    seen = set()

    def add_event(d: date, start_t: time, end_t: Optional[time], title: str, location: Optional[str], extra_desc: List[str]):
        title = _clean_spaces(title)
        if not title:
            return
        if _contains_excluded_keyword(title):
            return

        # If no end time, default to 2 hours
        if end_t is None:
            end_dt = datetime.combine(d, start_t, tzinfo=LOCAL_TZ) + timedelta(hours=2)
        else:
            end_dt = datetime.combine(d, end_t, tzinfo=LOCAL_TZ)
            start_dt_tmp = datetime.combine(d, start_t, tzinfo=LOCAL_TZ)
            # If end earlier than start, assume crosses midnight
            if end_dt <= start_dt_tmp:
                end_dt += timedelta(days=1)

        start_dt = datetime.combine(d, start_t, tzinfo=LOCAL_TZ)

        key = (title, start_dt.isoformat(), end_dt.isoformat(), (location or ""))
        if key in seen:
            return
        seen.add(key)

        ev = Event()
        ev.name = title
        ev.begin = start_dt
        ev.end = end_dt
        ev.description = SOURCE_DESC + ("\n" + "\n".join([x for x in extra_desc if x]) if extra_desc else "")
        if location:
            ev.location = location

        cal.events.add(ev)

    # Main parsing loop
    for raw in lines:
        line = _clean_spaces(raw)
        if not line:
            continue
        if _is_garbage_line(line):
            continue

        # Section headers we don't need
        if line.upper() in {"AGENDA", "DICIEMBRE", "ENERO", "BELENES", "SEMANALES", "EXPOSICIONES"}:
            continue

        # Detect range headers ("Hasta", "Del...hasta...")
        rng = _parse_until_or_range_header(line)
        if rng:
            # flush previous pending range if any
            flush_pending_range()
            kind, start_d, end_d = rng
            pending_range = PendingRangeEvent(kind=kind, start=start_d, end=end_d, title=None, details=[])
            active_dates = []  # range takes over until flushed
            last_event_ctx = None
            continue

        # If we are inside a pending range, the next non-empty lines usually are:
        #   - title line
        #   - maybe location/schedule lines
        if pending_range and pending_range.title is None:
            # First meaningful line after range header: treat as title
            pending_range.title = line
            continue
        if pending_range and pending_range.title is not None:
            # Collect some details until a new date header shows up
            # But if we hit an explicit date-set header, flush range.
            maybe_dates = _parse_date_set_header(line)
            if maybe_dates:
                flush_pending_range()
                active_dates = maybe_dates
                last_event_ctx = None
                continue
            # Otherwise store as detail (schedule/location/etc.)
            pending_range.details.append(line)
            continue

        # Date-set header?
        dates = _parse_date_set_header(line)
        if dates:
            active_dates = dates
            last_event_ctx = None
            continue

        # Time + title line?
        ttt = _parse_time_and_title(line)
        if ttt:
            st, et, title = ttt

            # Must have active_dates to place it; if not, skip
            if not active_dates:
                last_event_ctx = None
                continue

            # start new event context to capture location/extra lines after
            last_event_ctx = {
                "dates": list(active_dates),
                "start": st,
                "end": et,
                "title": title,
                "location": None,
                "extra": [],
            }
            # We won't add immediately; we add when we see next “time/title” or date header or end
            continue

        # If we have a last_event_ctx, treat this line as location/extra
        if last_event_ctx:
            # Heuristic: location-looking line (contains common place markers) => set location once
            if last_event_ctx["location"] is None and (
                "TEATRO" in line.upper()
                or "PLAZA" in line.upper()
                or "BIBLIOTECA" in line.upper()
                or "CASA" in line.upper()
                or "PALACIO" in line.upper()
                or "POLIDEPORTIVO" in line.upper()
                or "IGLESIA" in line.upper()
                or "CALLE" in line.upper()
                or "AVDA" in line.upper()
                or "URBANIZACIÓN" in line.upper()
                or "PUERTO" in line.upper()
                or "CENTRO" in line.upper()
            ):
                last_event_ctx["location"] = line
            else:
                last_event_ctx["extra"].append(line)
            continue

        # Otherwise: ignore line (or could be section text)
        continue

    # Flush pending range at end
    if pending_range:
        # if we had a pending range and we ended file, flush it
        # (in case title exists)
        if pending_range.title:
            e = Event()
            if not _contains_excluded_keyword(pending_range.title):
                e.name = pending_range.title
                start_dt = datetime.combine(pending_range.start, time(0, 0), tzinfo=LOCAL_TZ)
                end_dt = datetime.combine(pending_range.end + timedelta(days=1), time(0, 0), tzinfo=LOCAL_TZ)
                e.begin = start_dt
                e.end = end_dt
                desc_lines = [SOURCE_DESC]
                if pending_range.details:
                    desc_lines.extend([x for x in pending_range.details if x])
                e.description = "\n".join(desc_lines)
                cal.events.add(e)

    # IMPORTANT: We still need to flush the last_event_ctx into events
    # But since we delayed adding, do it now by re-scanning? Better: we should have flushed on transitions.
    # Simpler: add a final flush if last_event_ctx exists.
    if last_event_ctx:
        for d in last_event_ctx["dates"]:
            add_event(
                d=d,
                start_t=last_event_ctx["start"],
                end_t=last_event_ctx["end"],
                title=last_event_ctx["title"],
                location=last_event_ctx["location"],
                extra_desc=last_event_ctx["extra"],
            )

    # Sort events by begin (ics lib doesn't guarantee output order; but OK)
    # We'll rebuild a calendar in sorted order to make diffs cleaner.
    sorted_events = sorted(list(cal.events), key=lambda ev: ev.begin)
    new_cal = Calendar()
    for ev in sorted_events:
        new_cal.events.add(ev)

    return new_cal

def main():
    lines = fetch_agenda_text_lines()

    # Second pass: because we deferred adding events until we see “next block”,
    # we should improve flushing by doing it during loop. The current approach
    # adds only the LAST time/title block.
    #
    # So we do a controlled pass that flushes correctly:
    cal = Calendar()
    active_dates: List[date] = []
    pending_range: Optional[PendingRangeEvent] = None
    last_ctx: Optional[Dict] = None
    seen = set()

    def add_event_ctx(ctx: Dict):
        for d in ctx["dates"]:
            title = _clean_spaces(ctx["title"])
            if not title or _contains_excluded_keyword(title):
                continue

            st: time = ctx["start"]
            et: Optional[time] = ctx["end"]
            loc: Optional[str] = ctx.get("location")
            extra: List[str] = ctx.get("extra") or []

            if et is None:
                start_dt = datetime.combine(d, st, tzinfo=LOCAL_TZ)
                end_dt = start_dt + timedelta(hours=2)
            else:
                start_dt = datetime.combine(d, st, tzinfo=LOCAL_TZ)
                end_dt = datetime.combine(d, et, tzinfo=LOCAL_TZ)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)

            key = (title, start_dt.isoformat(), end_dt.isoformat(), (loc or ""))
            if key in seen:
                continue
            seen.add(key)

            ev = Event()
            ev.name = title
            ev.begin = start_dt
            ev.end = end_dt
            ev.description = SOURCE_DESC + ("\n" + "\n".join([x for x in extra if x]) if extra else "")
            if loc:
                ev.location = loc
            cal.events.add(ev)

    def flush_pending_range():
        nonlocal pending_range
        if not pending_range or not pending_range.title:
            pending_range = None
            return
        title = _clean_spaces(pending_range.title)
        if not title or _contains_excluded_keyword(title):
            pending_range = None
            return

        ev = Event()
        ev.name = title
        start_dt = datetime.combine(pending_range.start, time(0, 0), tzinfo=LOCAL_TZ)
        end_dt = datetime.combine(pending_range.end + timedelta(days=1), time(0, 0), tzinfo=LOCAL_TZ)
        ev.begin = start_dt
        ev.end = end_dt
        desc_lines = [SOURCE_DESC]
        if pending_range.details:
            desc_lines.extend([x for x in pending_range.details if x])
        ev.description = "\n".join(desc_lines)
        cal.events.add(ev)
        pending_range = None

    for raw in lines:
        line = _clean_spaces(raw)
        if not line or _is_garbage_line(line):
            continue

        if line.upper() in {"AGENDA", "DICIEMBRE", "ENERO", "BELENES", "SEMANALES", "EXPOSICIONES"}:
            continue

        # Date-set header flushes current event ctx
        dates = _parse_date_set_header(line)
        if dates:
            if last_ctx:
                add_event_ctx(last_ctx)
                last_ctx = None
            if pending_range:
                flush_pending_range()
            active_dates = dates
            continue

        rng = _parse_until_or_range_header(line)
        if rng:
            if last_ctx:
                add_event_ctx(last_ctx)
                last_ctx = None
            if pending_range:
                flush_pending_range()
            kind, start_d, end_d = rng
            pending_range = PendingRangeEvent(kind=kind, start=start_d, end=end_d, title=None, details=[])
            active_dates = []
            continue

        if pending_range and pending_range.title is None:
            pending_range.title = line
            continue
        if pending_range and pending_range.title is not None:
            # collect details
            pending_range.details.append(line)
            continue

        ttt = _parse_time_and_title(line)
        if ttt:
            # new timed event starts => flush previous ctx
            if last_ctx:
                add_event_ctx(last_ctx)
            st, et, title = ttt
            if not active_dates:
                last_ctx = None
                continue
            last_ctx = {
                "dates": list(active_dates),
                "start": st,
                "end": et,
                "title": title,
                "location": None,
                "extra": [],
            }
            continue

        if last_ctx:
            if last_ctx["location"] is None and (
                "TEATRO" in line.upper()
                or "PLAZA" in line.upper()
                or "BIBLIOTECA" in line.upper()
                or "CASA" in line.upper()
                or "PALACIO" in line.upper()
                or "POLIDEPORTIVO" in line.upper()
                or "IGLESIA" in line.upper()
                or "CALLE" in line.upper()
                or "AVDA" in line.upper()
                or "URBANIZACIÓN" in line.upper()
                or "PUERTO" in line.upper()
                or "CENTRO" in line.upper()
            ):
                last_ctx["location"] = line
            else:
                last_ctx["extra"].append(line)
            continue

    # flush at end
    if last_ctx:
        add_event_ctx(last_ctx)
    if pending_range:
        flush_pending_range()

    # Sort for stable output
    sorted_events = sorted(list(cal.events), key=lambda ev: ev.begin)
    out = Calendar()
    for ev in sorted_events:
        out.events.add(ev)

    with open(OUTPUT_ICS, "w", encoding="utf-8") as f:
        f.writelines(out.serialize_iter())

    print(f"Parsed events: {len(out.events)}")
    print(f"Wrote: {OUTPUT_ICS}")

if __name__ == "__main__":
    main()
