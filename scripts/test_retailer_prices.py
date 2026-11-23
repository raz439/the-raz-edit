#!/usr/bin/env python3

import html as html_lib
import json
import os
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener


PRODUCTS = [
    {
        "retailer": "ZARA",
        "url": "https://www.zara.com/il/he/ג-קט-בומבר-עם-לשוניות-p05070666.html?v1=598725468",
    },
    {
        "retailer": "Terminal X (MANGO)",
        "url": "https://www.terminalx.com/r602330007?color=22",
    },
    {
        "retailer": "ASOS",
        "url": "https://www.asos.com/asos-design/asos-design-washed-cotton-bomber-jacket-in-cream/prd/209493214",
    },
    {
        "retailer": "Bershka",
        "url": "https://www.bershka.com/il/ג'קט-דמוי-עור-c0p229723163.html?colorId=800",
    },
    {
        "retailer": "H&M",
        "url": "https://www2.hm.com/hw_il/productpage.1367399001.html",
    },
]

USER_AGENT = "Mozilla/5.0 (compatible; TheRazEditPriceTest/1.0)"


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return
        values = dict(attrs)
        key = values.get("property") or values.get("name")
        content = values.get("content")
        if key and content:
            self.meta[key.lower()] = html_lib.unescape(content).strip()


def walk(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk(nested)


def type_name(value):
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value or "")


def extract_json_ld(document):
    script_pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    found_product = False
    found_offer = False
    prices = []
    currencies = []
    availability = []
    names = []
    skus = []

    for match in script_pattern.finditer(document):
        raw = html_lib.unescape(match.group(1)).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for node in walk(parsed):
            node_type = type_name(node.get("@type")).lower()
            if "product" in node_type:
                found_product = True
                if node.get("name"):
                    names.append(str(node["name"]))
                if node.get("sku"):
                    skus.append(str(node["sku"]))

                offers = node.get("offers")
                candidates = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
                if offers is not None:
                    for offer in candidates:
                        if isinstance(offer, dict):
                            found_offer = True
                            collect_offer(offer, prices, currencies, availability)
            elif "offer" in node_type:
                found_offer = True
                collect_offer(node, prices, currencies, availability)

    return {
        "found_product": found_product,
        "found_offer": found_offer,
        "names": sorted(set(names)),
        "skus": sorted(set(skus)),
        "prices": sorted(set(prices)),
        "currencies": sorted(set(currencies)),
        "availability": sorted(set(availability)),
    }


def collect_offer(offer, prices, currencies, availability):
    for key in ("price", "lowPrice", "highPrice"):
        value = offer.get(key)
        if value is not None:
            prices.append(str(value))
    if offer.get("priceCurrency"):
        currencies.append(str(offer["priceCurrency"]))
    if isinstance(offer.get("availability"), str):
        availability.append(offer["availability"])


def extract_metadata(document):
    parser = MetadataParser()
    parser.feed(document)
    meta = parser.meta
    price_keys = (
        "product:price:amount",
        "og:price:amount",
        "price",
    )
    currency_keys = (
        "product:price:currency",
        "og:price:currency",
        "currency",
    )
    return {
        "name": meta.get("og:title") or meta.get("twitter:title"),
        "image": meta.get("og:image") or meta.get("twitter:image"),
        "prices": sorted(set(meta[key] for key in price_keys if meta.get(key))),
        "currencies": sorted(set(meta[key] for key in currency_keys if meta.get(key))),
        "availability": sorted(set(
            meta[key]
            for key in ("product:availability", "og:availability")
            if meta.get(key)
        )),
    }


def fetch(url):
    encoded_url = quote(url, safe=":/?#[]@!$&'()*+,;=%")
    request = Request(
        encoded_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        },
        method="GET",
    )
    opener = build_opener()
    try:
        with opener.open(request, timeout=12) as response:
            status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            body = response.read(750_000).decode("utf-8", "replace")
            return {
                "status": status,
                "final_url": final_url,
                "redirected": final_url != encoded_url,
                "content_type": content_type,
                "body": body,
                "error": None,
            }
    except HTTPError as exc:
        return {
            "status": exc.code,
            "final_url": exc.geturl(),
            "redirected": exc.geturl() != encoded_url,
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "body": "",
            "error": f"HTTPError: {exc.reason}",
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "status": None,
            "final_url": url,
            "redirected": False,
            "content_type": "",
            "body": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def join(value):
    return ", ".join(value) if value else "not found"


def main():
    rows = []
    failures = 0
    all_output = []

    all_output.append("# Retailer price extraction test")
    all_output.append("")

    for product in PRODUCTS:
        result = fetch(product["url"])
        json_ld = {"found_product": False, "found_offer": False, "names": [], "skus": [], "prices": [], "currencies": [], "availability": []}
        metadata = {"name": None, "image": None, "prices": [], "currencies": [], "availability": []}

        if result["body"]:
            json_ld = extract_json_ld(result["body"])
            metadata = extract_metadata(result["body"])

        prices = sorted(set(json_ld["prices"] + metadata["prices"]))
        currencies = sorted(set(json_ld["currencies"] + metadata["currencies"]))
        availability = sorted(set(json_ld["availability"] + metadata["availability"]))

        if result["error"]:
            outcome = "FAIL"
            failures += 1
        elif result["status"] and 200 <= result["status"] < 400 and (prices or currencies):
            outcome = "PARTIAL" if not prices else "SUCCESS"
        else:
            outcome = "FAIL"
            failures += 1

        identity = join(json_ld["names"])
        if metadata["name"] and metadata["name"] not in json_ld["names"]:
            identity = metadata["name"] if identity == "not found" else f"{identity}; metadata: {metadata['name']}"

        redirect_text = "yes" if result["redirected"] else "no"
        row = (
            f"| {product['retailer']} "
            f"| `{product['url']}` "
            f"| {outcome}; HTTP {result['status'] or 'N/A'}; redirect: {redirect_text} "
            f"| {join(prices)} "
            f"| {join(currencies)} "
            f"| {join(availability)} "
            f"| {identity} "
            f"| {json_ld['found_product']} "
            f"| {result['error'] or 'none'} |"
        )
        rows.append(row)

        line = (
            f"[{outcome}] {product['retailer']} "
            f"HTTP={result['status'] or 'N/A'} redirect={redirect_text} "
            f"prices={join(prices)} currencies={join(currencies)} "
            f"availability={join(availability)} "
            f"JSON-LD product={json_ld['found_product']} offer={json_ld['found_offer']} "
            f"identity={identity}"
        )
        if result["error"]:
            line += f" error={result['error']}"
        print(line)

    all_output.append(
        "| Retailer | URL | Outcome / access | Price | Currency | Availability | Product identity | JSON-LD Product | Error |"
    )
    all_output.append("|---|---|---|---|---|---|---|---|---|")
    all_output.extend(rows)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("\n".join(all_output))
            summary.write("\n")

    if failures:
        print(f"Test completed with {failures} failed or unusable page(s).")
    else:
        print("Test completed; all pages returned usable HTTP or metadata responses.")


if __name__ == "__main__":
    main()
