import json
import requests

r = requests.get(
    "https://archive-api.open-meteo.com/v1/archive",
    params={
        "latitude":30.5926, "longitude":114.3055,
        "start_date": "2026-11-01", "end_date": "2026-11-03",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
    },
    timeout=(5,10)
)
print(r.status_code, len(r.content), "bytes")
d = r.json()
print("top keys:", list(d))
print("daily keys:", list(d["daily"]))
print("days:", len(d["daily"]["time"]))
print("time:", d["daily"]["time"])
print("tmax:", d["daily"]["temperature_2m_max"])
print("tz:", d["timezone"], d["utc_offset_seconds"], "elev:", d["elevation"])