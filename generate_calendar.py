import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from ics import Calendar, Event

# Disable SSL warnings (site has broken cert chain)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://turismo.estepona.es/agenda/"

# Fetch page with relaxed SSL + user agent
response = requests.get(
    URL,
    timeout=30,
    verify=False,
    headers={
        "User-Agent": "Mozilla/5.0 (compatible; EsteponaAgendaBot/1.0)"
    }
)

response.raise_for_status()
html = response.text

soup = BeautifulSoup(html, "html.parser")

cal = Calendar()

# NOTE:
# This is a generic parser that will be refined once HTML is stabilized.
# It intentionally avoids crashing if structure changes.

items = soup.find_all("article")

for item in items:
    title_tag = item.find("h3")
    time_tag = item.find("time")

    if not title_tag or not time_tag:
        continue

    title = title_tag.get_text(strip=True)

    # Try to extract ISO date from <time datetime="YYYY-MM-DD">
    date_attr = time_tag.get("datetime", "")
    if not date_attr:
        continue

    date_str = date_attr.split("T")[0]

    try:
        start = datetime.fromisoformat(date_str)
    except ValueError:
        continue

    e = Event()
    e.name = title
    e.begin = start
    e.duration = timedelta(hours=2)
    e.description = "Fuente: turismo.estepona.es/agenda"
    cal.events.add(e)

# Write calendar file
with open("agenda.ics", "w", encoding="utf-8") as f:
    f.writelines(cal)
