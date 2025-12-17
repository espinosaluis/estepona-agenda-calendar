import requests
from bs4 import BeautifulSoup
from datetime import datetime
from ics import Calendar, Event

URL = "https://turismo.estepona.es/agenda/"

html = requests.get(URL, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

cal = Calendar()

for item in soup.select(".agenda-item"):
    title = item.select_one(".agenda-title").get_text(strip=True)
    date_text = item.select_one(".agenda-date").get_text(strip=True)

    # You refine parsing here as needed
    date = datetime.strptime(date_text, "%d/%m/%Y")

    e = Event()
    e.name = title
    e.begin = date
    cal.events.add(e)

with open("agenda.ics", "w", encoding="utf-8") as f:
    f.writelines(cal)
