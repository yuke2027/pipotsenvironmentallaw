"""Populate station latitude/longitude from the public Beijing monitoring
station catalog via the admin update API (audited path).

Coordinates are approximate public reference positions for the Beijing
ambient-air network; verify against the official station registry before
production acceptance.

Usage (inside an api container on the compose network):
    ESP_API=http://manual-web python /workspace/scripts/seed_station_coordinates.py
"""

import os
import sys

import httpx

BASE = os.environ.get("ESP_API", "http://manual-web")
USERNAME = os.environ.get("ESP_USER", "docshot")
PASSWORD = os.environ.get("ESP_PASS", "DocShot2026manual")

# name -> (longitude, latitude)
COORDS = {
    "东城东四": (116.434, 39.952), "东城天坛": (116.417, 39.875),
    "西城官园": (116.361, 39.942), "西城万寿西宫": (116.359, 39.878),
    "朝阳农展馆": (116.473, 39.942), "朝阳奥体中心": (116.407, 39.982),
    "海淀万柳": (116.287, 39.954), "海淀四季青": (116.265, 39.934),
    "丰台云岗": (116.146, 39.824), "丰台小屯": (116.273, 39.879),
    "石景山古城": (116.184, 39.914), "石景山老山": (116.222, 39.909),
    "大兴旧宫": (116.461, 39.806), "大兴黄村": (116.404, 39.718),
    "亦庄开发区": (116.506, 39.793), "通州东关": (116.663, 39.912),
    "通州永顺": (116.670, 39.917), "顺义北小营": (116.685, 40.197),
    "顺义新城": (116.663, 40.127), "昌平南邵": (116.286, 40.218),
    "昌平镇": (116.230, 40.217), "门头沟三家店": (116.106, 39.969),
    "门头沟双峪": (116.110, 39.943), "怀柔新城": (116.644, 40.328),
    "怀柔镇": (116.637, 40.317), "密云新城": (116.863, 40.361),
    "密云镇": (116.832, 40.378), "平谷新城": (117.121, 40.143),
    "平谷镇": (117.100, 40.143), "延庆夏都": (115.972, 40.453),
    "延庆石河营": (115.980, 40.459), "房山燕山": (115.995, 39.760),
    "房山良乡": (116.136, 39.742), "定陵(对照点)": (116.220, 40.289),
    "京东南区域点": (116.800, 39.700),
}


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30)
    r = client.post("/api/v2/auth/login", json={"username": USERNAME, "password": PASSWORD})
    r.raise_for_status()
    csrf = client.cookies.get("esp_csrf", "")
    stations = client.get("/api/v2/stations", params={"page_size": 200}).json()["items"]
    updated, skipped = 0, []
    for s in stations:
        coord = COORDS.get(s["name"])
        if coord is None:
            skipped.append(s["name"])
            continue
        lon, lat = coord
        if s.get("latitude") == lat and s.get("longitude") == lon:
            continue
        body = {"city_id": s["city_id"], "code": s["code"], "name": s["name"],
                "latitude": lat, "longitude": lon, "active": s["active"]}
        r = client.put(f"/api/v2/admin/stations/{s['id']}", json=body,
                       headers={"X-CSRF-Token": csrf})
        if r.status_code != 200:
            print(f"FAIL {s['name']}: {r.status_code} {r.text[:160]}")
            return 1
        updated += 1
    print(f"updated={updated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
