#!/usr/bin/env python3

import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit
from urllib.request import Request, build_opener


USER_AGENT = "Mozilla/5.0 (compatible; TheRazEditPriceMonitor/1.0)"
MAX_BODY_BYTES = 750_000
SUPPORTED_RETAILERS = {
    "terminalx.com": "TERMINAL X",
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.scripts = []
        self._script = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag.lower() == "meta":
            key = values.get("property") or values.get("name")
            if key and values.get("content"):
                self.meta[key.lower()] = html.unescape(values["content"]).strip()
        elif tag.lower() == "script":
            self._script = {
                "type": values.get("type", "").lower(),
                "text": [],
            }

    def handle_data(self, data):
        if self._script is not None:
            self._script["text"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._script is not None:
            self._script["text"] = "".join(self._script["text"]).strip()
            self.scripts.append(self._script)
            self._script = None


def walk(value, path="$"):
    if isinstance(value, dict):
        yield path, value
        for key, nested in value.items():
            yield from walk(nested, f"{path}.{key}")
    elif isinstance(value, list):
        yield path, value
        for index, nested in enumerate(value):
            yield from walk(nested, f"{path}[{index}]")


def type_name(value):
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value or "")


def first(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_host(host):
    host = host.lower().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def retailer_for_url(url):
    host = normalize_host(urlsplit(url).hostname or "")
    for domain, retailer in SUPPORTED_RETAILERS.items():
        if host == domain or host.endswith("." + domain):
            return retailer
    return None


def canonical_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), normalize_host(parts.netloc), parts.path.rstrip("/"), "", ""))


def fetch_page(url, opener=None):
    encoded_url = quote(url, safe=":/?#[]@!$&'()*+,;=%")
    request = Request(
        encoded_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        method="GET",
    )
    try:
        with (opener or build_opener()).open(request, timeout=12) as response:
            return {
                "status": response.status,
                "final_url": response.geturl(),
                "body": response.read(MAX_BODY_BYTES).decode("utf-8", "replace"),
                "error": None,
            }
    except HTTPError as exc:
        return {
            "status": exc.code,
            "final_url": exc.geturl(),
            "body": "",
            "error": f"http_{exc.code}",
        }
    except (URLError, TimeoutError, OSError):
        return {
            "status": None,
            "final_url": url,
            "body": "",
            "error": "request_failed",
        }


def parse_offers(body):
    parser = PageParser()
    parser.feed(body)
    offers = []
    product_names = []
    product_ids = []

    for script in parser.scripts:
        if script["type"] != "application/ld+json":
            continue
        try:
            root = json.loads(html.unescape(script["text"]))
        except json.JSONDecodeError:
            continue
        for path, node in walk(root):
            if not isinstance(node, dict):
                continue
            kind = type_name(node.get("@type")).lower()
            if "product" in kind:
                if node.get("name"):
                    product_names.append(str(node["name"]))
                product_id = first(node, ("productID", "sku", "mpn"))
                if product_id:
                    product_ids.append(str(product_id))
                nested = node.get("offers")
                nested = nested if isinstance(nested, list) else [nested] if isinstance(nested, dict) else []
                for index, offer in enumerate(nested):
                    if isinstance(offer, dict) and "offer" not in type_name(offer.get("@type")).lower():
                        offers.append(make_offer(f"{path}.offers[{index}]", offer, node))
            elif "offer" in kind:
                offers.append(make_offer(path, node, {}))

    return {
        "parser": parser,
        "offers": deduplicate(offers),
        "product_names": sorted(set(product_names)),
        "product_ids": sorted(set(product_ids)),
    }


def make_offer(path, offer, product):
    return {
        "path": path,
        "price": first(offer, ("price", "lowPrice", "highPrice")),
        "currency": first(offer, ("priceCurrency", "currency")),
        "availability": first(offer, ("availability", "stockStatus")),
        "url": first(offer, ("url",)),
        "sku": first(offer, ("sku", "mpn", "productID")) or first(product, ("sku", "mpn", "productID")),
        "name": first(product, ("name",)),
        "color": first(offer, ("color", "colorName", "colorId")),
        "size": first(offer, ("size", "sizeName", "sizeId")),
    }


def deduplicate(values):
    result = []
    seen = set()
    for value in values:
        key = tuple(sorted((key, str(item)) for key, item in value.items() if key != "path"))
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def parse_price(value):
    try:
        price = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


def selected_color_id(url):
    values = parse_qs(urlsplit(url).query).get("color", [])
    return values[0] if values else None


def exact_terminalx_observation(product, page):
    url = str(product.get("url") or "").strip()
    if retailer_for_url(url) != "TERMINAL X":
        return failed_observation(product, "unsupported_retailer")

    requested_path = urlsplit(url).path.rstrip("/")
    final_url = page["final_url"]
    if page["error"] or not page["status"] or not 200 <= page["status"] < 300:
        return failed_observation(product, page["error"] or f"http_{page['status']}")
    if retailer_for_url(final_url) != "TERMINAL X":
        return failed_observation(product, "unexpected_redirect_host")
    if urlsplit(final_url).path.rstrip("/") != requested_path:
        return failed_observation(product, "unexpected_product_path")

    parsed = parse_offers(page["body"])
    expected_product_id = requested_path.rsplit("/", 1)[-1].lower()
    parsed_product_ids = {value.lower() for value in parsed["product_ids"]}
    if parsed_product_ids and expected_product_id not in parsed_product_ids:
        return failed_observation(product, "product_id_mismatch")
    expected_color = selected_color_id(url)
    offers = []
    for offer in parsed["offers"]:
        price = parse_price(offer["price"])
        if price is None or str(offer.get("currency") or "").upper() != "ILS":
            continue
        offer_text = json.dumps(offer, ensure_ascii=False).lower()
        color_matches = not expected_color or expected_color.lower() in offer_text
        if color_matches:
            offers.append(offer)

    if not offers:
        return failed_observation(product, "no_verified_ils_offer")

    prices = {round(parse_price(offer["price"]), 2) for offer in offers}
    if len(prices) != 1:
        return failed_observation(product, "conflicting_prices")

    names = " ".join(parsed["product_names"]).lower()
    board_name = str(product.get("name") or "").lower()
    name_tokens = [token for token in re.findall(r"[\wא-ת]+", board_name) if len(token) > 2]
    if name_tokens and sum(token in names for token in name_tokens) < min(2, len(name_tokens)):
        return failed_observation(product, "product_identity_mismatch")

    return {
        "product_id": str(product.get("id") or ""),
        "product_url": url,
        "retailer_domain": normalize_host(urlsplit(url).hostname or ""),
        "canonical_url": canonical_url(final_url),
        "retailer_product_id": requested_path.rsplit("/", 1)[-1],
        "selected_color_id": expected_color,
        "price": round(next(iter(prices)), 2),
        "currency": "ILS",
        "source": "terminalx_jsonld",
        "verification_status": "verified",
        "availability": sorted(set(str(offer.get("availability")) for offer in offers if offer.get("availability"))),
        "error_code": None,
        "error_message": None,
    }


def failed_observation(product, code):
    return {
        "product_id": str(product.get("id") or ""),
        "product_url": str(product.get("url") or ""),
        "retailer_domain": normalize_host(urlsplit(str(product.get("url") or "")).hostname or ""),
        "canonical_url": None,
        "retailer_product_id": None,
        "selected_color_id": selected_color_id(str(product.get("url") or "")),
        "price": None,
        "currency": None,
        "source": "terminalx_jsonld",
        "verification_status": "failed",
        "availability": [],
        "error_code": code,
        "error_message": code,
    }


def read_catalogue(supabase_url, service_key):
    request = Request(
        supabase_url.rstrip("/") + "/rest/v1/board_content?id=eq.1&select=content",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
    )
    with build_opener().open(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload or not isinstance(payload[0].get("content"), dict):
        raise RuntimeError("board_content_missing")
    products = payload[0]["content"].get("products")
    if not isinstance(products, list):
        raise RuntimeError("board_products_missing")
    return products


def write_observation(supabase_url, service_key, observation):
    request = Request(
        supabase_url.rstrip("/") + "/rest/v1/price_observations",
        data=json.dumps(observation).encode("utf-8"),
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    with build_opener().open(request, timeout=12):
        return


def run_monitor():
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        raise RuntimeError("missing_supabase_configuration")

    products = read_catalogue(supabase_url, service_key)
    supported = [product for product in products if retailer_for_url(str(product.get("url") or ""))]
    results = []
    for product in supported:
        page = fetch_page(product["url"])
        result = exact_terminalx_observation(product, page)
        write_observation(supabase_url, service_key, result)
        results.append(result)
    return results


def main():
    try:
        results = run_monitor()
    except Exception as error:
        print(f"Monitor stopped before writing observations: {error}", file=sys.stderr)
        return 1

    verified = sum(result["verification_status"] == "verified" for result in results)
    print(f"Checked {len(results)} supported Terminal X product(s); verified {verified}.")
    for result in results:
        status = result["verification_status"]
        detail = f"{result['price']} {result['currency']}" if status == "verified" else result["error_code"]
        print(f"[{status}] {result['product_id']} {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
