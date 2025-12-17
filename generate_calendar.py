import re
from datetime import datetime, timedelta
from ics import Calendar, Event
from playwright.sync_api import sync_playwright

URL = "https://turismo.estepona.es/agenda/"

# ---------- filters ----------

SECTION_KEYWORDS = (
    "AGENDA", "DICIEMBRE", "ENERO", "FEBRERO", "MARZO",
    "BELENES", "EXPOSICIONES", "SEMANALES"
)

BLACKLIST_KEYWORDS = (
    "LOUIE LOUIE",  # permanently excluded
)

BAD_PREFIXES = (
    "Horario", "Entrada", "Salida", "De lunes", "Agenda",
)

LOCATION_HINTS = (
    "Plaza", "Teatro", "Casa", "Iglesia", "Biblioteca",
    "Centro", "Palacio", "Polideportivo", "Recinto",
    "Urbanización", "Calle", "Avda", "Avenida", "Puerto",
)

# ---------- helpers ----------

def normalize(text):
    text = text.replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.split("\n")]
    return [l for l in lines if l]

def is_section(line):
    u = line.upper()
    return any(k in u for k in SECTION_KEYWORDS)

def is_blacklisted(line):
    u = line.upper()
    return any(k in u for k in BLACKLIST_KEYWORDS)

def parse_date(line):
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", line)
    if not m:
        return None
    d, mth, y = map(int, m.groups())
    if y < 100:
        y += 2000
    try:
        return datetime(y, mth, d)
    except ValueError:
        return None

def parse_until_date(lines):
    for l in lines:
        if "HASTA" in l.upper():
            d = parse_date(l)
            if d:
                return d
    return None

def looks_like_title(line):
    if len(line) < 8:
        return False
    if line.startswith(BAD_PREFIXES):
        return False
    if line.upper() == line:
        return True
    if "“" in line or "”" in line or '"' in line:
        return True
    return False

def extract_location(lines):
    for l in lines:
        for h in LOCATION_HINTS:
            if h.lower() in l.lower():
                return l
    return ""

def extract_time(lines):
    for l in lines:
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", l)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None

# ---------- parsing ----------

def extract_events(lines):
    events = []
    block = []
    current_date = None

    def flush(block, date):
        if not block or not date:
            return

        text = " ".join(block).upper()
        if is_blacklisted(text):
            return

        title = None
        for l in block:
            if looks_like_title(l):
                title = l
                break
        if not title:
            return

        until = parse_until_date(block)
        location = extract_location(block)
        time = extract_time(block)

        if until:
            start = date.replace(hour=9, minute=0)
            end = until.replace(hour=18, minute=0)
        else:
            if time:
                h, m = time
                start = date.replace(hour=h, minute=m)
            else:
                start = date.replace(hour=9, minute=0)
            end = start + timedelta(hours=2)

        events.append((title, start, end, location))

    for line in lines:
        if is_section(line):
            continue

        d = parse_date(line)
        if d:
            flush(block, current_date)
            block = []
            current_date = d
        else:
            block.append(line)

    flush(block, current_date)
    return events

# ---------- main ----------

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
