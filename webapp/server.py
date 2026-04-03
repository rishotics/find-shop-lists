"""
Shop Finder API Server (DukaanKhoj)
Searches Google Maps, JustDial, and IndiaMART for shops via stableenrich.dev x402 APIs.

Environment variables:
  WALLET_PRIVATE_KEY  - Your EVM wallet private key (hex, with or without 0x prefix)
                        Get this from your agentcash wallet or any EVM wallet.

To run:
  export WALLET_PRIVATE_KEY="your_private_key_here"
  python3 server.py
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
import requests as http_requests
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

app = Flask(__name__, static_folder="static")
CORS(app)

STABLEENRICH_BASE = "https://stableenrich.dev"

# --- x402 Wallet Setup ---
WALLET_PRIVATE_KEY = os.environ.get("WALLET_PRIVATE_KEY", "")
wallet_account = None
if WALLET_PRIVATE_KEY:
    key = WALLET_PRIVATE_KEY if WALLET_PRIVATE_KEY.startswith("0x") else "0x" + WALLET_PRIVATE_KEY
    wallet_account = Account.from_key(key)
    print(f"[x402] Wallet loaded: {wallet_account.address}")
else:
    print("[x402] WARNING: No WALLET_PRIVATE_KEY set. API calls will fail with 402.")
    print("[x402] Set it via: export WALLET_PRIVATE_KEY='your_key_here'")

# Cache results to avoid repeat API calls (saves money!)
search_cache = {}
CACHE_TTL = 3600  # 1 hour


def get_cache_key(query_params):
    raw = json.dumps(query_params, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def x402_post(url, payload, max_usd=0.10):
    """Make a POST request with x402 payment handling.

    Flow:
    1. Send request normally
    2. If 402 returned, parse payment requirements from response
    3. Sign payment authorization
    4. Retry with payment header
    """
    headers = {"Content-Type": "application/json"}

    # First attempt
    resp = http_requests.post(url, json=payload, headers=headers, timeout=30)

    if resp.status_code == 200:
        return resp.json()

    if resp.status_code != 402 or not wallet_account:
        return None

    # Parse 402 payment requirements
    try:
        payment_req = resp.json()

        # The x402 protocol returns payment details in the response
        # We need to create a signed payment and retry
        x_payment = resp.headers.get("X-PAYMENT-REQUIRED") or resp.headers.get("x-payment-required")

        if x_payment:
            payment_details = json.loads(x_payment)
        else:
            payment_details = payment_req

        # Create payment signature
        # Sign a message authorizing the payment
        price = payment_details.get("maxAmountRequired", payment_details.get("price", "0"))

        payment_payload = {
            "x402Version": 2,
            "scheme": "exact",
            "network": "eip155:8453",  # Base chain
            "payload": {
                "signature": "",
                "authorization": {
                    "from": wallet_account.address,
                    "to": payment_details.get("payTo", ""),
                    "value": str(price),
                    "validAfter": "0",
                    "validBefore": str(int(time.time()) + 3600),
                    "nonce": Web3.keccak(text=str(time.time())).hex(),
                }
            }
        }

        # Sign the authorization
        message = json.dumps(payment_payload["payload"]["authorization"], sort_keys=True)
        msg = encode_defunct(text=message)
        signed = wallet_account.sign_message(msg)
        payment_payload["payload"]["signature"] = signed.signature.hex()

        # Retry with payment
        headers["X-PAYMENT"] = json.dumps(payment_payload)
        resp2 = http_requests.post(url, json=payload, headers=headers, timeout=30)

        if resp2.status_code == 200:
            return resp2.json()
        else:
            print(f"[x402] Payment retry failed: {resp2.status_code} {resp2.text[:200]}")
            return None

    except Exception as e:
        print(f"[x402] Payment error: {e}")
        return None


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
    result = x402_post(url, payload)
    if result:
        return result.get("places", [])
    return []


def search_firecrawl(query, limit=10):
    """Search the web via Firecrawl on stableenrich.dev"""
    url = f"{STABLEENRICH_BASE}/api/firecrawl/search"
    payload = {"query": query, "limit": limit}
    result = x402_post(url, payload)
    if result:
        return result.get("results", [])
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
    "sirathu": {"lat": 25.63, "lng": 81.34},
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

    if not wallet_account:
        return jsonify({
            "error": "no_wallet",
            "message": "Server not configured. Set WALLET_PRIVATE_KEY env variable."
        }), 503

    # Check cache first
    cache_key = get_cache_key({"keywords": keywords, "areas": areas, "comments": comments})
    if cache_key in search_cache:
        cached = search_cache[cache_key]
        if time.time() - cached["time"] < CACHE_TTL:
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
            for place in places:
                normalized = normalize_place(place)
                normalized["area"] = area["name"]
                key = normalized["name"].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    all_results.append(normalized)

        # Web search (JustDial / IndiaMART)
        web_query = f"{keywords} {area['name']} Uttar Pradesh justdial indiamart"
        web_results = search_firecrawl(web_query, limit=5)
        for result in web_results:
            normalized = normalize_web_result(result)
            normalized["area"] = area["name"]
            key = normalized["name"].lower().strip()
            if key not in seen_names and any(
                kw in key for kw in keywords.lower().split()[:2]
            ):
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
    print("\n" + "=" * 60)
    print("  DukaanKhoj - Shop Finder Server")
    print("=" * 60)
    if not wallet_account:
        print("\n  ⚠️  To enable search, set your wallet key:")
        print("  export WALLET_PRIVATE_KEY='your_private_key_here'")
        print("\n  Get your key from your agentcash wallet or any EVM wallet.")
        print("  Your agentcash wallet: 0x7cdc3cD09B65B201C4272f9b58D19937f0e436B8")
    print(f"\n  Server: http://localhost:5001")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5001)
