"""Vercel serverless: POST /api/search
Uses Google Maps Places API (New) + SerpAPI for web results.

Env vars:
  GOOGLE_MAPS_API_KEY - Google Cloud API key with Places API enabled
"""
import os
import json
import time
import hashlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import urllib.error

GOOGLE_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

search_cache = {}
CACHE_TTL = 3600

AREA_COORDS = {
    "fatehpur": {"lat": 25.93, "lng": 80.81},
    "khaga": {"lat": 25.74, "lng": 81.00},
    "kaushambi": {"lat": 25.53, "lng": 81.37},
    "manjhanpur": {"lat": 25.53, "lng": 81.37},
    "sirathu": {"lat": 25.63, "lng": 81.34},
    "prayagraj": {"lat": 25.43, "lng": 81.84},
    "allahabad": {"lat": 25.43, "lng": 81.84},
    "kanpur": {"lat": 26.45, "lng": 80.35},
    "lucknow": {"lat": 26.85, "lng": 80.95},
    "agra": {"lat": 27.18, "lng": 78.02},
    "varanasi": {"lat": 25.32, "lng": 83.01},
    "banda": {"lat": 25.48, "lng": 80.34},
    "delhi": {"lat": 28.61, "lng": 77.23},
    "noida": {"lat": 28.57, "lng": 77.32},
    "ghaziabad": {"lat": 28.67, "lng": 77.42},
    "jaipur": {"lat": 26.91, "lng": 75.79},
    "patna": {"lat": 25.60, "lng": 85.10},
    "bhopal": {"lat": 23.26, "lng": 77.41},
    "indore": {"lat": 22.72, "lng": 75.86},
    "mumbai": {"lat": 19.08, "lng": 72.88},
    "pune": {"lat": 18.52, "lng": 73.86},
    "hyderabad": {"lat": 17.39, "lng": 78.49},
    "bangalore": {"lat": 12.97, "lng": 77.59},
    "chennai": {"lat": 13.08, "lng": 80.27},
    "kolkata": {"lat": 22.57, "lng": 88.36},
    "ahmedabad": {"lat": 23.02, "lng": 72.57},
    "surat": {"lat": 21.17, "lng": 72.83},
    "burhanpur": {"lat": 21.31, "lng": 76.23},
    "nagpur": {"lat": 21.15, "lng": 79.09},
    "raipur": {"lat": 21.25, "lng": 81.63},
    "meerut": {"lat": 28.98, "lng": 77.71},
    "bareilly": {"lat": 28.37, "lng": 79.42},
    "gorakhpur": {"lat": 26.76, "lng": 83.37},
}


def api_request(url, payload=None, method="POST"):
    """Make HTTP request using urllib (no external deps)."""
    try:
        data = json.dumps(payload).encode() if payload else None
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[API] HTTP {e.code}: {url}")
        return None
    except Exception as e:
        print(f"[API] Error: {e}")
        return None


def search_google_maps(text_query, lat, lng, radius=50000):
    """Google Maps Places API (New) - Text Search."""
    if not GOOGLE_API_KEY:
        return []

    url = f"https://places.googleapis.com/v1/places:searchText"
    payload = {
        "textQuery": text_query,
        "maxResultCount": 10,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius,
            }
        },
        "languageCode": "en",
    }

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Goog-Api-Key", GOOGLE_API_KEY)
        req.add_header("X-Goog-FieldMask",
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.internationalPhoneNumber,"
            "places.websiteUri,places.rating,places.userRatingCount,"
            "places.businessStatus,places.regularOpeningHours,"
            "places.googleMapsUri"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode())
            return result.get("places", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"[Google Maps] HTTP {e.code}: {body[:200]}")
        return []
    except Exception as e:
        print(f"[Google Maps] Error: {e}")
        return []


def normalize_place(place):
    dn = place.get("displayName", {})
    hours_obj = place.get("regularOpeningHours", {})
    hours_list = hours_obj.get("weekdayDescriptions", [])
    return {
        "name": dn.get("text", "Unknown"),
        "address": place.get("formattedAddress", ""),
        "phone": place.get("nationalPhoneNumber", "") or place.get("internationalPhoneNumber", ""),
        "website": place.get("websiteUri", ""),
        "rating": place.get("rating", ""),
        "reviews": place.get("userRatingCount", ""),
        "status": place.get("businessStatus", ""),
        "hours": "; ".join(hours_list) if hours_list else "",
        "maps_link": place.get("googleMapsUri", ""),
        "source": "Google Maps",
    }


def parse_areas(area_text):
    areas = []
    area_lower = area_text.lower().strip()
    for name, coords in AREA_COORDS.items():
        if name in area_lower:
            areas.append({"name": name.title(), **coords})
    if not areas:
        areas.append({"name": area_text.strip(), "lat": 25.93, "lng": 80.81})
    return areas


def json_response(h, status, data):
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.end_headers()
    h.wfile.write(json.dumps(data).encode())


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body) if body else {}

        keywords = data.get("keywords", "").strip()
        areas = data.get("areas", "").strip()
        comments = data.get("comments", "").strip()

        if not keywords or not areas:
            return json_response(self, 400, {"error": "Keywords and area are required"})

        if not GOOGLE_API_KEY:
            return json_response(self, 503, {
                "error": "no_key",
                "message": "Server not configured. Set GOOGLE_MAPS_API_KEY env variable."
            })

        # Cache
        cache_key = hashlib.md5(
            json.dumps({"k": keywords, "a": areas, "c": comments}, sort_keys=True).encode()
        ).hexdigest()
        if cache_key in search_cache:
            cached = search_cache[cache_key]
            if time.time() - cached["time"] < CACHE_TTL:
                return json_response(self, 200, cached["data"])

        area_list = parse_areas(areas)
        all_results = []
        seen_names = set()

        for area in area_list:
            queries = [
                f"{keywords} {area['name']}",
                f"{keywords} shop dealer {area['name']}",
            ]
            if comments:
                queries.append(f"{keywords} {comments} {area['name']}")

            for query in queries:
                for place in search_google_maps(query, area["lat"], area["lng"]):
                    normalized = normalize_place(place)
                    normalized["area"] = area["name"]
                    key = normalized["name"].lower().strip()
                    if key not in seen_names:
                        seen_names.add(key)
                        all_results.append(normalized)

        response_data = {
            "results": all_results,
            "count": len(all_results),
            "search": {"keywords": keywords, "areas": areas, "comments": comments},
            "timestamp": datetime.now().isoformat(),
        }

        search_cache[cache_key] = {"data": response_data, "time": time.time()}
        return json_response(self, 200, response_data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
