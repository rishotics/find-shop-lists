"""
Shop Finder API Server
Searches Google Maps, JustDial, and IndiaMART for shops matching user criteria.
"""
import os
import json
import csv
import io
import time
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder="static")
CORS(app)

STABLEENRICH_BASE = "https://stableenrich.dev"

# x402 payment config - set via environment variables
# The server acts as a proxy, handling x402 payments on behalf of the frontend
WALLET_PRIVATE_KEY = os.environ.get("WALLET_PRIVATE_KEY", "")
WALLET_ADDRESS = os.environ.get("WALLET_ADDRESS", "")

# Cache results to avoid repeat API calls
search_cache = {}


def get_cache_key(query_params):
    raw = json.dumps(query_params, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def search_google_maps(text_query, lat, lng, radius=50000):
    """Search Google Maps via stableenrich.dev"""
    url = f"{STABLEENRICH_BASE}/api/google-maps/text-search/full"
    payload = {
        "textQuery": text_query,
        "maxResultCount": 5,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius,
            }
        },
        "languageCode": "en",
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("places", [])
        elif resp.status_code == 402:
            return {"error": "payment_required", "message": "API payment required"}
    except Exception as e:
        print(f"Google Maps search error: {e}")
    return []


def search_firecrawl(query, limit=10):
    """Search the web via Firecrawl on stableenrich.dev"""
    url = f"{STABLEENRICH_BASE}/api/firecrawl/search"
    payload = {"query": query, "limit": limit}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("results", [])
    except Exception as e:
        print(f"Firecrawl search error: {e}")
    return []


def normalize_place(place):
    """Normalize a Google Maps place into our standard format"""
    name = place.get("displayName", {}).get("text", "Unknown")
    address = place.get("formattedAddress", "")
    phone = place.get("nationalPhoneNumber", "") or place.get(
        "internationalPhoneNumber", ""
    )
    website = place.get("websiteUri", "")
    rating = place.get("rating", "")
    reviews = place.get("userRatingCount", "")
    status = place.get("businessStatus", "")
    maps_link = place.get("googleMapsUri", "")

    hours_list = (
        place.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
    )
    hours = "; ".join(hours_list) if hours_list else ""

    return {
        "name": name,
        "address": address,
        "phone": phone,
        "website": website,
        "rating": rating,
        "reviews": reviews,
        "status": status,
        "hours": hours,
        "maps_link": maps_link,
        "source": "Google Maps",
    }


def normalize_web_result(result):
    """Normalize a Firecrawl/web result"""
    return {
        "name": result.get("title", "Unknown"),
        "address": "",
        "phone": "",
        "website": result.get("url", ""),
        "rating": "",
        "reviews": "",
        "status": "",
        "hours": "",
        "maps_link": "",
        "source": "Web Search",
        "description": result.get("description", ""),
    }


AREA_COORDS = {
    "fatehpur": {"lat": 25.93, "lng": 80.81},
    "khaga": {"lat": 25.74, "lng": 81.00},
    "kaushambi": {"lat": 25.53, "lng": 81.37},
    "manjhanpur": {"lat": 25.53, "lng": 81.37},
    "prayagraj": {"lat": 25.43, "lng": 81.84},
    "allahabad": {"lat": 25.43, "lng": 81.84},
    "kanpur": {"lat": 26.45, "lng": 80.35},
    "lucknow": {"lat": 26.85, "lng": 80.95},
    "agra": {"lat": 27.18, "lng": 78.02},
    "varanasi": {"lat": 25.32, "lng": 83.01},
    "banda": {"lat": 25.48, "lng": 80.34},
}


def parse_areas(area_text):
    """Parse area text into coordinates list"""
    areas = []
    area_lower = area_text.lower().strip()
    for name, coords in AREA_COORDS.items():
        if name in area_lower:
            areas.append({"name": name.title(), **coords})
    if not areas:
        areas.append({"name": area_text.strip(), "lat": 25.93, "lng": 80.81})
    return areas


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)


@app.route("/api/search", methods=["POST"])
def search_shops():
    data = request.json
    keywords = data.get("keywords", "").strip()
    areas = data.get("areas", "").strip()
    comments = data.get("comments", "").strip()

    if not keywords or not areas:
        return jsonify({"error": "Keywords and area are required"}), 400

    cache_key = get_cache_key({"keywords": keywords, "areas": areas, "comments": comments})
    if cache_key in search_cache:
        cached = search_cache[cache_key]
        if time.time() - cached["time"] < 3600:
            return jsonify(cached["data"])

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
            places = search_google_maps(query, area["lat"], area["lng"])
            if isinstance(places, dict) and places.get("error"):
                return jsonify(places), 402
            for place in places:
                normalized = normalize_place(place)
                normalized["area"] = area["name"]
                key = normalized["name"].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    all_results.append(normalized)

        web_query = f"{keywords} {area['name']} Uttar Pradesh justdial indiamart"
        web_results = search_firecrawl(web_query, limit=5)
        for result in web_results:
            normalized = normalize_web_result(result)
            normalized["area"] = area["name"]
            key = normalized["name"].lower().strip()
            if key not in seen_names and keywords.lower().split()[0] in key:
                seen_names.add(key)
                all_results.append(normalized)

    response_data = {
        "results": all_results,
        "count": len(all_results),
        "search": {"keywords": keywords, "areas": areas, "comments": comments},
        "timestamp": datetime.now().isoformat(),
    }

    search_cache[cache_key] = {"data": response_data, "time": time.time()}

    return jsonify(response_data)


@app.route("/api/export/csv", methods=["POST"])
def export_csv():
    data = request.json
    results = data.get("results", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Shop Name", "Address", "Area", "Phone", "Website",
        "Rating", "Reviews", "Status", "Hours", "Maps Link", "Source",
    ])
    for r in results:
        writer.writerow([
            r.get("name", ""),
            r.get("address", ""),
            r.get("area", ""),
            r.get("phone", ""),
            r.get("website", ""),
            r.get("rating", ""),
            r.get("reviews", ""),
            r.get("status", ""),
            r.get("hours", ""),
            r.get("maps_link", ""),
            r.get("source", ""),
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"shop_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
