import re
from datetime import datetime, timedelta
from ics import Calendar, Event
from playwright.sync_api import sync_playwright

URL = "https://turismo.estepona.es/agenda/"

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

def parse_time_range(line):
    s = line.replace("–", "-")
    m = re.search(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", s)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))

def extract_events(lines):
    events = []
    block = []

    def flush(block):
        date = None
        for l in block[::-1]:
            date = parse_date(l)
            if date:
                break
        if not date:
            return

        time_range = None
        for l in block:
            tr = parse_time_range(l)
            if tr:
                time_range = tr
                break

        title_candidates = [l for l in block if not parse_date(l)]
        title = max(title_candidates, key=len) if title_candidates else "Evento"

        if time_range:
            (sh, sm), (eh, em) = time_range
            start = date.replace(hour=sh, minute=sm)
            end = date.replace(hour=eh, minute=em)
            if end <= start:
                end += timedelta(days=1)
        else:
            start = date.replace(hour=9, minute=0)
            end = start + timedelta(hours=2)

        events.append((title[:180], start, end, "Fuente: turismo.estepona.es"))

    for l in lines:
        block.append(l)
        if parse_date(l):
            flush(block)
            block = []

    if block:
        flush(block)

    return events

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        text = page.inner_text("body")
        browser.close()

    lines = normalize(text)
    events = extract_events(lines)

    cal = Calendar()
    for title, start, end, desc in events:
        e = Event()
        e.name = title
        e.begin = start
        e.end = end
        e.description = desc
        cal.events.add(e)

    with open("agenda.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)

    print(f"Parsed events: {len(events)}")

if __name__ == "__main__":
    main()
