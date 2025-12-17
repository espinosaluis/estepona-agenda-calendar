import re
from datetime import datetime, timedelta
from ics import Calendar, Event
from playwright.sync_api import sync_playwright

URL = "https://turismo.estepona.es/agenda/"

# ---------- helpers ----------

BAD_TITLE_PREFIXES = (
    "Horario", "Entrada", "Salida", "De lunes", "Hasta", "DEL ", "HASTA",
    "Agenda", "E N E R O", "D I C I E M B R E", "S E M A N A L E S",
)

LOCATION_HINTS = (
    "Plaza", "Teatro", "Casa", "Iglesia", "Biblioteca", "Centro",
    "Palacio", "Polideportivo", "Recinto", "Urbanización",
    "Calle", "Avda", "Avenida", "Puerto",
)

def normalize(text):
    text = text.replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.split("\n")]
    return [l for l in lines if l]

def parse_date(line):
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", line)
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return datetime(y, mth, d)
    except ValueError:
        return None

def parse_times(line):
    """
    Returns list of (hour, minute) found in the line, in order.
    """
    return [(int(h), int(m)) for h, m in re.findall(r"\b(\d{1,2}):(\d{2})\b", line)]

def looks_like_title(line):
    if len(line) < 8:
        return False
    if line.startswith(BAD_TITLE_PREFIXES):
        return False
    # Prefer ALL CAPS or quoted titles
    if line.upper() == line:
        return True
    if "“" in line or "”" in line or '"' in line:
        return True
    return False

def extract_location(lines):
    for l in lines:
        for hint in LOCATION_HINTS:
            if hint.lower() in l.lower():
                return l
    return ""

# ---------- main parsing ----------

def extract_events(lines):
    events = []
    current_date = None
    buffer = []

    def flush_block(block, date):
        if not date or not block:
            return

        # Find candidate title
        title = None
        for l in block:
            if looks_like_title(l):
                title = l
                break
        if not title:
            # fallback: longest reasonable line
            title = max(block, key=len)

        location = extract_location(block)

        # Collect times in this block
        times = []
        for l in block:
            times.extend(parse_times(l))

        if times:
            # create one event per time
            for (h, m) in times:
                start = date.replace(hour=h, minute=m)
                end = start + timedelta(hours=2)
                events.append((title, start, end, location))
        else:
            # all-day-ish fallback
            start = date.replace(hour=9, minute=0)
            end = start + timedelta(hours=1)
            events.append((title, start, end, location))

    for line in lines:
        d = parse_date(line)
        if d:
            flush_block(buffer, current_date)
            buffer = []
            current_date = d
        else:
            buffer.append(line)

    flush_block(buffer, current_date)
    return events

# ---------- entry point ----------

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        text = page.inner_text("body")
        browser.close()

    lines = normalize(text)
    parsed = extract_events(lines)

    cal = Calendar()
    for title, start, end, location in parsed:
        e = Event()
        e.name = title[:200]
        e.begin = start
        e.end = end
        if location:
            e.location = location
        e.description = "Fuente: turismo.estepona.es/agenda"
        cal.events.add(e)

    with open("agenda.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)

    print(f"Parsed events: {len(parsed)}")

if __name__ == "__main__":
    main()
