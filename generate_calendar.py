import re
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from ics import Calendar, Event

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://turismo.estepona.es/agenda/"

def fetch_html(url: str) -> str:
    r = requests.get(
        url,
        timeout=60,
        verify=False,  # turismo.estepona.es has cert chain issues
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; EsteponaAgendaBot/1.0)"
        },
    )
    r.raise_for_status()
    return r.text

def pick_main_container(soup: BeautifulSoup):
    # Try common WordPress content containers first
    for sel in [
        "main",
        "article",
        ".entry-content",
        ".content-area",
        "#content",
        ".site-content",
        ".content",
        "body",
    ]:
        el = soup.select_one(sel)
        if el:
            return el
    return soup

def normalize_lines(text: str) -> list[str]:
    text = text.replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
    return [ln for ln in lines if ln]

def parse_date_from_line(line: str):
    """
    Accepts:
      - 04/01/26
      - 04/01/2026
      - ... 04/01/26 (embedded)
    Returns datetime.date or None
    """
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b", line)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    y = int(y)
    if y < 100:
        y += 2000
    try:
        return datetime(y, mo, d)
    except ValueError:
        return None

def parse_time_range_from_line(line: str):
    """
    Accepts:
      - 17:00 – 23:00
      - 17:00-23:00
      - 18.30 (rare) -> ignore unless HH:MM
    Returns (start_hhmm, end_hhmm) as (hours, minutes) or None
    """
    # Normalize dash variants
    s = line.replace("–", "-").replace("—", "-")
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\b", s)
    if not m:
        return None
    sh, sm, eh, em = map(int, m.groups())
    if not (0 <= sh <= 23 and 0 <= eh <= 23 and 0 <= sm <= 59 and 0 <= em <= 59):
        return None
    return (sh, sm), (eh, em)

def parse_single_time_from_line(line: str):
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", line)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return (h, mi)
    return None

def build_events_from_lines(lines: list[str]) -> list[dict]:
    """
    Heuristic:
      - When a line contains a date, we create/close an event block.
      - Title is the nearest meaningful line(s) before that date line.
      - If times appear near the block, use them.
    """
    events = []
    block = []

    def flush(block_lines: list[str]):
        # Find date in the block (usually last lines)
        dt = None
        for ln in reversed(block_lines):
            dt = parse_date_from_line(ln)
            if dt:
                break
        if not dt:
            return

        # Try to find time range / time in the block
        time_range = None
        single_time = None
        for ln in block_lines:
            tr = parse_time_range_from_line(ln)
            if tr:
                time_range = tr
                break
        if not time_range:
            for ln in block_lines:
                st = parse_single_time_from_line(ln)
                if st:
                    single_time = st
                    break

        # Build a reasonable title: pick the longest "interesting" line excluding pure dates/times
        candidates = []
        for ln in block_lines:
            if parse_date_from_line(ln):
                continue
            # Avoid lines that are only times
            if re.fullmatch(r"\d{1,2}:\d{2}(\s*-\s*\d{1,2}:\d{2})?", ln.replace("–", "-").replace("—", "-")):
                continue
            candidates.append(ln)

        title = ""
        if candidates:
            # Prefer a line that looks like an event name (often uppercase or has quotes)
            title = max(candidates, key=len)

        # Location heuristic: look for line with "Plaza", "Teatro", "Casa", "Iglesia", "Biblioteca", etc.
        location = ""
        for ln in candidates:
            if re.search(r"\b(Plaza|Teatro|Casa|Iglesia|Biblioteca|Centro|Palacio|Polideportivo|Recinto|Urbanización|Avda\.|Avenida|Calle)\b", ln, re.IGNORECASE):
                location = ln
                break

        description = "Fuente: turismo.estepona.es/agenda"
        # Include some context (trimmed)
        context = " | ".join(block_lines[:10])
        if context:
            description += f" | {context[:900]}"

        # Build start/end
        if time_range:
            (sh, sm), (eh, em) = time_range
            start = dt.replace(hour=sh, minute=sm)
            end = dt.replace(hour=eh, minute=em)
            # If end earlier than start, assume it ends next day
            if end <= start:
                end = end + timedelta(days=1)
        elif single_time:
            h, mi = single_time
            start = dt.replace(hour=h, minute=mi)
            end = start + timedelta(hours=2)
        else:
            # All-day-ish
            start = dt.replace(hour=9, minute=0)
            end = start + timedelta(hours=1)

        if not title:
            title = f"Evento ({dt.strftime('%d/%m/%Y')})"

        events.append(
            {
                "title": title[:180],
                "start": start,
                "end": end,
                "location": location[:180],
                "description": description,
            }
        )

    for ln in lines:
        block.append(ln)
        # If this line contains a date, flush the block
        if parse_date_from_line(ln):
            flush(block)
            block = []

    # Flush remaining
    if block:
        flush(block)

    # Deduplicate by (title, start)
    seen = set()
    deduped = []
    for e in events:
        key = (e["title"], e["start"].isoformat())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped

def main():
    html = fetch_html(URL)
    soup = BeautifulSoup(html, "html.parser")

    container = pick_main_container(soup)
    text = container.get_text("\n", strip=True)
    lines = normalize_lines(text)

    parsed = build_events_from_lines(lines)

    cal = Calendar()
    for i, p in enumerate(parsed):
        ev = Event()
        ev.name = p["title"]
        ev.begin = p["start"]
        ev.end = p["end"]
        if p["location"]:
            ev.location = p["location"]
        ev.description = p["description"]
        cal.events.add(ev)

    with open("agenda.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)

    # Helpful debug: print count to logs
    print(f"Parsed events: {len(parsed)}")

if __name__ == "__main__":
    main()
