import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

INPUT_FILE = "agenda.txt"      # aquí pegas el texto plano de la agenda
OUTPUT_FILE = "agenda.ics"

TIMEZONE = "Europe/Madrid"

def dt(date_str, time_str="00:00"):
    return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%y %H:%M")

def format_dt(d):
    return d.strftime("%Y%m%dT%H%M%S")

def vevent(summary, start, end, location=""):
    uid = str(uuid.uuid4())
    return f"""BEGIN:VEVENT
UID:{uid}
DTSTART:{format_dt(start)}
DTEND:{format_dt(end)}
SUMMARY:{summary}
LOCATION:{location}
DESCRIPTION:Fuente: turismo.estepona.es/agenda
END:VEVENT
"""

def main():
    text = Path(INPUT_FILE).read_text(encoding="utf-8")

    events = []

    blocks = re.split(r"\n\s*\n", text)

    current_date = None

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # ❌ quitar LOUIE
        if "LOUIE LOUIE" in block.upper():
            continue

        # detectar fecha tipo 17/12/25
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{2})\b", block)
        if date_match:
            current_date = date_match.group(1)

        if not current_date:
            continue

        # detectar hora
        time_match = re.search(r"\b(\d{1,2}:\d{2})\b", block)
        start_time = time_match.group(1) if time_match else "00:00"

        try:
            start = dt(current_date, start_time)
            end = start + timedelta(hours=2)
        except Exception:
            continue

        lines = block.splitlines()
        summary = lines[0][:120]
        location = ""
        if len(lines) > 1:
            location = lines[-1][:120]

        events.append(vevent(summary, start, end, location))

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Estepona Agenda//ES
CALSCALE:GREGORIAN
""" + "\n".join(events) + "\nEND:VCALENDAR\n"

    Path(OUTPUT_FILE).write_text(ics, encoding="utf-8")

    print(f"Eventos generados: {len(events)}")

if __name__ == "__main__":
    main()
