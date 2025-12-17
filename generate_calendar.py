import re
import requests
from datetime import datetime, timedelta
from ics import Calendar, Event

AGENDA_URL = "https://turismo.estepona.es/agenda/"

# Keywords that indicate long-running events
LONG_EVENTS = [
    "EXPOSICIÓN",
    "BELÉN",
    "PARQUE",
    "FERIA",
]

# Keywords / garbage to ignore completely
IGNORE_KEYWORDS = [
    "LOUIE LOUIE",
    "ROCK BAR",
    "Copyright",
    "Powered by WordPress",
    "Supreme Directory",
]

TIME_REGEX = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
DATE_REGEX = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")


def normalize_title(text: str) -> str:
    """Remove leading times and normalize spacing"""
    text = TIME_REGEX.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def is_long_event(title: str) -> bool:
    return any(k in title.upper() for k in LONG_EVENTS)


def should_ignore(text: str) -> bool:
    return any(k.lower() in text.lower() for k in IGNORE_KEYWORDS)


def parse_date(date_str: str) -> datetime:
    d, m, y = date_str
    if len(y) == 2:
        y = "20" + y
    return datetime(int(y), int(m), int(d))


def extract_events(page_text: str):
    events = []
    seen = set()

    current_date = None

    lines = [l.strip() for l in page_text.splitlines() if l.strip()]

    for line in lines:

        if should_ignore(line):
            break

        # Date line
        date_match = DATE_REGEX.search(line)
        if date_match:
            current_date = parse_date(date_match.groups())
            continue

        if not current_date:
            continue

        # Skip lines with no letters
        if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", line):
            continue

        title = normalize_title(line)

        if should_ignore(title):
            continue

        key = (current_date.date(), title.upper())
        if key in seen:
            continue

        seen.add(key)

        ev = Event()
        ev.name = title
        ev.begin = current_date

        # Long events: 1-day placeholder
        if is_long_event(title):
            ev.end = current_date + timedelta(hours=2)
        else:
            ev.end = current_date + timedelta(hours=2)

        ev.description = "Fuente: turismo.estepona.es/agenda"
        events.append(ev)

    return events


def main():
    response = requests.get(AGENDA_URL, timeout=30)
    response.raise_for_status()

    calendar = Calendar()
    events = extract_events(response.text)

    print(f"Parsed events: {len(events)}")

    for ev in events:
        calendar.events.add(ev)

    with open("agenda.ics", "w", encoding="utf-8") as f:
        f.writelines(calendar)


if __name__ == "__main__":
    main()
