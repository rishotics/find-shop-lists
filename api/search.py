"""Vercel serverless function: POST /api/search"""
import os
import json
import time
import hashlib
import secrets
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import requests as http_requests

STABLEENRICH_BASE = "https://stableenrich.dev"

# In-memory cache (per lambda instance)
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
}


def api_post(url, payload):
    """Simple POST to stableenrich - no x402 payment (handled by Vercel proxy or future integration)"""
    try:
        resp = http_requests.post(
            url, json=payload,
            headers={"Content-Type": "application/json"},
            timeout=25
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"[API] {url} returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[API] error calling {url}: {e}")
    return None


def search_google_maps(text_query, lat, lng, radius=50000):
    url = f"{STABLEENRICH_BASE}/api/google-maps/text-search/full"
    payload = {
        "textQuery": text_query,
        "maxResultCount": 5,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius}},
        "languageCode": "en",
    }
    result = api_post(url, payload)
    return result.get("places", []) if result else []


def search_firecrawl(query, limit=10):
    url = f"{STABLEENRICH_BASE}/api/firecrawl/search"
    result = api_post(url, {"query": query, "limit": limit})
    return result.get("results", []) if result else []


def normalize_place(place):
    hours_list = place.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
    return {
        "name": place.get("displayName", {}).get("text", "Unknown"),
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


def normalize_web_result(result):
    return {
        "name": result.get("title", "Unknown"),
        "address": "", "phone": "",
        "website": result.get("url", ""),
        "rating": "", "reviews": "", "status": "", "hours": "", "maps_link": "",
        "source": "Web Search",
        "description": result.get("description", ""),
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


def json_response(handler, status, data):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


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

        # Check cache
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
            queries = [f"{keywords} {area['name']}", f"{keywords} shop dealer {area['name']}"]
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

            web_query = f"{keywords} {area['name']} justdial indiamart"
            for result in search_firecrawl(web_query, limit=5):
                normalized = normalize_web_result(result)
                normalized["area"] = area["name"]
                key = normalized["name"].lower().strip()
                if key not in seen_names and any(kw in key for kw in keywords.lower().split()[:2]):
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
