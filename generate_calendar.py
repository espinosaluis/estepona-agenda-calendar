import re
import uuid
import requests
import urllib3
from datetime import datetime
from ics import Calendar, Event

# Disable SSL warnings (the site has a broken cert chain)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

AGENDA_URL = "https://turismo.estepona.es/agenda/"
OUTPUT_FILE = "agenda.ics"

# Always ignore this garbage event
BLACKLIST = ["LOUIE"]

def clean(text: str) -> str:
    text = re.sub(r"<.*?>", "", text)
    return re.sub(r"\s+", " ", text).strip()

def main():
    response = requests.get(
        AGENDA_URL,
        timeout=30,
        verify=False   # ← THIS is what makes it work again
    )
    response.raise_for_status()

    html = response.text

    cal = Calendar()
    seen = set()

    # Very conservative extraction: title + date + time if present
    blocks = re.findall(
        r'<h3.*?>(.*?)</h3>.*?(?:Fecha|Date).*?(\d{2}/\d{2}/\d{4}).*?(?:Hora|Time).*?(\d{1,2}:\d{2})?',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    for raw_title, date_str, time_str in blocks:
        title = clean(raw_title)

        if any(bad in title.upper() for bad in BLACKLIST):
            continue

        try:
            start_date = datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            continue

        time_str = time_str or "09:00"
        start = datetime.strptime(
            f"{start_date.strftime('%Y-%m-%d')} {time_str}",
            "%Y-%m-%d %H:%M"
        )

        key = (title, start)
        if key in seen:
            continue
        seen.add(key)

        event = Event()
        event.uid = f"{uuid.uuid4()}@estepona"
        event.name = title
        event.begin = start
        event.end = start.replace(hour=min(start.hour + 2, 23))
        event.description = "Fuente: turismo.estepona.es/agenda"

        cal.events.add(event)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

    print(f"Generated {len(cal.events)} events")

if __name__ == "__main__":
    main()
