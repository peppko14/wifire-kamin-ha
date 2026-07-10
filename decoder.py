#!/usr/bin/env python3
import json
from urllib.request import Request, urlopen
from config import REQUEST_TIMEOUT, WIFIRE_URL

PACKET_HEADER = bytes.fromhex("aacc3355")

def read_live_data() -> str:
    request = Request(WIFIRE_URL, headers={"Accept": "application/json", "Connection": "close"}, method="GET")
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        result = json.loads(response.read().decode("utf-8"))
    raw = result.get("raw")
    if not isinstance(raw, str):
        raise ValueError("Die Antwort enthält kein gültiges Feld 'raw'.")
    return raw

def decode_live_data(raw: str) -> dict:
    data = bytes.fromhex(raw)
    if len(data) < 19:
        raise ValueError(f"Antwort zu kurz: {len(data)} Bytes statt mindestens 19.")
    if data[0:4] != PACKET_HEADER:
        raise ValueError("Unbekannter Paketkopf.")
    door_open = bool(data[6] & 0x10)
    temperature_c = int.from_bytes(data[7:9], byteorder="big", signed=False)
    flap_raw = data[9]
    if flap_raw > 100:
        flap_percent = max(0, min(100, flap_raw - 150))
        flap_moving = True
    else:
        flap_percent = flap_raw
        flap_moving = False
    burn_hours = data[10]
    burn_minutes = data[11]
    burn_total_minutes = burn_hours * 60 + burn_minutes
    fan_raw = data[18]
    return {
        "temperature_c": temperature_c,
        "flap_percent": flap_percent,
        "flap_moving": flap_moving,
        "burn_hours": burn_hours,
        "burn_minutes": burn_minutes,
        "burn_total_minutes": burn_total_minutes,
        "burn_time": f"{burn_hours}:{burn_minutes:02d}",
        "door_open": door_open,
        "door_state": "offen" if door_open else "geschlossen",
        "fan_raw": fan_raw,
        "status_raw": data[6],
        "raw": raw,
    }

if __name__ == "__main__":
    decoded = decode_live_data(read_live_data())
    print("WiFire-Kamin Livedaten")
    print("----------------------")
    print(f"Temperatur:   {decoded['temperature_c']} °C")
    print(f"Luftklappe:   {decoded['flap_percent']} %")
    print(f"Abbrenndauer: {decoded['burn_time']}")
    print(f"Tür:          {decoded['door_state']}")
