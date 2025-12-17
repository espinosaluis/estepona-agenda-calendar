import re
import uuid
import requests
from datetime import datetime
from ics import Calendar, Event

AGENDA_URL = "https://turismo.estepona.es/agenda/"
OUTPUT_FILE = "agenda.ics"

# Events you never want
BLACKLIST = [
    "LOUIE LOUIE",
    "LOUIE",
    "ROCK BAR",
]

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def is_blacklisted(text: str) -> bool:
    upper = text.upper()
    return any(bad in upper for bad in BLACKLIST)

def parse_events(html: str):
    """
    Very defensive parsing: extract blocks that look like events.
    This matches what the site actually outputs and avoids garbage.
    """
    events = []

    blocks = re.findall(
        r'<div class="agenda-item">(.*?)</div>\s*</div>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    for block in blocks:
        title_match = re.search(r"<h3.*?>(.*?)</h3>", block, re.DOTALL)
        date_match = re.search(r"(\d{2}/\d{2}/\d{2,4})", block)
        time_match = re.search(r"(\d{1,2}:\d{2})", block)

        if not title_match or not date_match:
            continue

        title = clean_text(re.sub("<.*?>", "", title_match.group(1)))

        if is_blacklisted(title):
            continue

        date_str = date_match.group(1)
        time_str = time_match.group(1) if time_match else "09:00"

        try:
            date = datetime.strptime(date_str, "%d/%m/%y")
        except ValueError:
            date = datetime.strptime(date_str, "%d/%m/%Y")

        start = datetime.strptime(
            f"{date.strftime('%Y-%m-%d')} {time_str}",
            "%Y-%m-%d %H:%M",
        )

        events.append((title, start))

    return events

def main():
    response = requests.get(AGENDA_URL, timeout=30)
    response.raise_for_status()

    html = response.text

    cal = Calendar()
    seen = set()

    events = parse_events(html)

    for title, start in events:
        key = (title, start)
        if key in seen:
            continue
        seen.add(key)

        e = Event()
        e.uid = f"{uuid.uuid4()}@estepona"
        e.name = title
        e.begin = start
        e.end = start.replace(hour=start.hour + 2)
        e.description = "Fuente: turismo.estepona.es/agenda"

        cal.events.add(e)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

    print(f"Parsed events: {len(cal.events)}")

if __name__ == "__main__":
    main()
