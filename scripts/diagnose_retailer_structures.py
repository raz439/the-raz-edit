#!/usr/bin/env python3

import html
import json
import os
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener


PRODUCTS = [
    ("ZARA", "https://www.zara.com/il/he/ג-קט-בומבר-עם-לשוניות-p05070666.html?v1=598725468"),
    ("ASOS", "https://www.asos.com/asos-design/asos-design-washed-cotton-bomber-jacket-in-cream/prd/209493214"),
    ("Bershka", "https://www.bershka.com/il/ג'קט-דמוי-עור-c0p229723163.html?colorId=800"),
    ("Terminal X", "https://www.terminalx.com/r602330007?color=22"),
]

USER_AGENT = "Mozilla/5.0 (compatible; TheRazEditStructureDiagnostic/1.0)"


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
                "id": values.get("id", ""),
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


def fetch(url):
    encoded = quote(url, safe=":/?#[]@!$&'()*+,;=%")
    request = Request(
        encoded,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        method="GET",
    )
    try:
        with build_opener().open(request, timeout=12) as response:
            return {
                "status": response.status,
                "final_url": response.geturl(),
                "content_type": response.headers.get("Content-Type", ""),
                "body": response.read(750_000).decode("utf-8", "replace"),
                "error": None,
            }
    except HTTPError as exc:
        return {
            "status": exc.code,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type", "") if exc.headers else "",
            "body": "",
            "error": f"HTTPError: {exc.reason}",
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "status": None,
            "final_url": url,
            "content_type": "",
            "body": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


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


def get_first(mapping, names):
    for name in names:
        if name in mapping and mapping[name] not in (None, ""):
            return mapping[name]
    return None


def compact(value):
    if value is None:
        return "none"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:77] + "..." if len(text) > 80 else text


def parse_json_ld(scripts):
    valid_scripts = 0
    invalid_scripts = 0
    product_nodes = []
    offers = []

    for index, script in enumerate(scripts):
        if script["type"] != "application/ld+json":
            continue
        try:
            root = json.loads(html.unescape(script["text"]))
            valid_scripts += 1
        except json.JSONDecodeError:
            invalid_scripts += 1
            continue

        for path, node in walk(root):
            if not isinstance(node, dict):
                continue
            kind = type_name(node.get("@type")).lower()
            if "product" in kind:
                product_nodes.append((path, node))
            if "offer" in kind:
                offers.append(make_offer(path, node))

            # Handle Product nodes whose offers are nested inline.
            if "product" in kind:
                nested = node.get("offers")
                nested = nested if isinstance(nested, list) else [nested] if isinstance(nested, dict) else []
                for nested_index, offer in enumerate(nested):
                    if isinstance(offer, dict):
                        offers.append(make_offer(
                            f"{path}.offers[{nested_index}]",
                            offer,
                            product=node,
                        ))

    unique = []
    seen = set()
    for offer in offers:
        key = tuple(sorted((str(k), str(v)) for k, v in offer.items()))
        if key not in seen:
            seen.add(key)
            unique.append(offer)

    return {
        "valid_scripts": valid_scripts,
        "invalid_scripts": invalid_scripts,
        "product_nodes": len(product_nodes),
        "offers": unique,
    }


def make_offer(path, offer, product=None):
    product = product or {}
    return {
        "path": path,
        "price": get_first(offer, ("price", "lowPrice", "highPrice")),
        "currency": get_first(offer, ("priceCurrency", "currency")),
        "availability": get_first(offer, ("availability", "stockStatus")),
        "sku": get_first(offer, ("sku", "mpn", "productID")),
        "product_id": get_first(product, ("productID", "sku", "mpn")),
        "size": get_first(offer, ("size", "sizeCode", "sizeId")),
        "color": get_first(offer, ("color", "colorName", "colorId")),
        "name": get_first(product, ("name",)),
    }


def parse_embedded_json(scripts):
    records = []
    field_names = (
        "price", "salePrice", "currentPrice", "lowPrice", "highPrice",
        "currency", "currencyCode", "productId", "productID", "sku",
        "variantId", "variantID", "size", "sizeId", "sizeCode",
        "color", "colorId", "colorName", "availability", "stockStatus",
        "inStock", "outOfStock",
    )

    for index, script in enumerate(scripts):
        text = script["text"].strip()
        if not text:
            continue
        candidates = [text]
        assignment = re.match(r"^(?:window\.[A-Za-z0-9_.]+|[A-Za-z0-9_.]+)\s*=\s*(.+)$", text, re.S)
        if assignment:
            candidates.append(assignment.group(1).rstrip(";"))

        root = None
        for candidate in candidates:
            try:
                root = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if root is None:
            continue

        field_paths = set()
        offer_candidates = []
        for path, node in walk(root):
            if not isinstance(node, dict):
                continue
            normalized = {str(key): value for key, value in node.items()}
            keys = set(normalized)
            key_hits = [name for name in field_names if name in keys]
            field_paths.update(f"{path}.{name}" for name in key_hits)
            price_like = any(
                re.search(r"(price|sale|cost|amount)", str(key), re.I)
                for key in keys
            )
            if price_like:
                offer_candidates.append(make_offer(path, normalized))

        kind = "embedded JSON"
        if "__NEXT_DATA__" in script["id"] or "__next_f" in script["id"]:
            kind = "Next.js"
        elif "__NUXT" in text.upper() or "__NUXT_DATA__" in text.upper():
            kind = "Nuxt"

        if field_paths or offer_candidates:
            records.append({
                "script": index,
                "kind": kind,
                "field_paths": sorted(field_paths)[:20],
                "offers": offer_candidates[:8],
            })
    return records


def metadata(parser):
    return {
        "names": sorted(set(v for v in (
            parser.meta.get("og:title"),
            parser.meta.get("twitter:title"),
        ) if v)),
        "prices": sorted(set(v for v in (
            parser.meta.get("product:price:amount"),
            parser.meta.get("og:price:amount"),
            parser.meta.get("price"),
        ) if v)),
        "currencies": sorted(set(v for v in (
            parser.meta.get("product:price:currency"),
            parser.meta.get("og:price:currency"),
            parser.meta.get("currency"),
        ) if v)),
        "availability": sorted(set(v for v in (
            parser.meta.get("product:availability"),
            parser.meta.get("og:availability"),
        ) if v)),
        "product_id": parser.meta.get("product:retailer_item_id") or parser.meta.get("product:id"),
    }


def join(values):
    return ", ".join(str(value) for value in values) if values else "none"


def main():
    summaries = []
    print("# Retailer public-structure diagnostic")

    for retailer, url in PRODUCTS:
        result = fetch(url)
        redirected = result["final_url"] != quote(url, safe=":/?#[]@!$&'()*+,;=%")

        if not result["body"]:
            print(
                f"[{retailer}] HTTP={result['status'] or 'N/A'} "
                f"redirect={redirected} structures=none "
                f"error={result['error'] or 'empty body'}"
            )
            continue

        parser = PageParser()
        parser.feed(result["body"])
        json_ld = parse_json_ld(parser.scripts)
        embedded = parse_embedded_json(parser.scripts)
        meta = metadata(parser)

        framework = []
        if re.search(r"__NEXT_DATA__|__next_f|/_next/", result["body"], re.I):
            framework.append("Next.js")
        if re.search(r"__NUXT__|__NUXT_DATA__|/_nuxt/", result["body"], re.I):
            framework.append("Nuxt")

        promising = []
        if json_ld["valid_scripts"]:
            promising.append("JSON-LD")
        if any(record["kind"] == "Next.js" for record in embedded):
            promising.append("Next.js")
        if any(record["kind"] == "Nuxt" for record in embedded):
            promising.append("Nuxt")
        if meta["prices"]:
            promising.append("Open Graph/meta")
        if not promising:
            promising.append("none detected")

        print(
            f"[{retailer}] HTTP={result['status']} redirect={redirected} "
            f"scripts={len(parser.scripts)} json_ld_valid={json_ld['valid_scripts']} "
            f"json_ld_invalid={json_ld['invalid_scripts']} "
            f"product_nodes={json_ld['product_nodes']} "
            f"framework={join(framework)} promising={join(promising)}"
        )

        if json_ld["offers"]:
            for offer in json_ld["offers"][:8]:
                print(
                    "  Offer "
                    f"path={offer['path']} price={compact(offer['price'])} "
                    f"currency={compact(offer['currency'])} "
                    f"availability={compact(offer['availability'])} "
                    f"sku={compact(offer['sku'])} "
                    f"size={compact(offer['size'])} "
                    f"color={compact(offer['color'])}"
                )
        else:
            print("  JSON-LD offers: none")

        for record in embedded[:6]:
            print(
                f"  Embedded {record['kind']} script[{record['script']}]: "
                f"fields={join(record['field_paths'])}"
            )
            for offer in record["offers"][:4]:
                print(
                    "    Candidate "
                    f"path={offer['path']} price={compact(offer['price'])} "
                    f"currency={compact(offer['currency'])} "
                    f"availability={compact(offer['availability'])} "
                    f"sku={compact(offer['sku'])} "
                    f"size={compact(offer['size'])} "
                    f"color={compact(offer['color'])}"
                )

        if meta["names"] or meta["prices"] or meta["availability"]:
            print(
                "  Metadata "
                f"identity={join(meta['names'])} "
                f"price={join(meta['prices'])} "
                f"currency={join(meta['currencies'])} "
                f"availability={join(meta['availability'])} "
                f"product_id={meta['product_id'] or 'none'}"
            )

        summaries.append({
            "retailer": retailer,
            "status": result["status"],
            "redirected": redirected,
            "scripts": len(parser.scripts),
            "json_ld": json_ld,
            "embedded": embedded,
            "meta": meta,
            "framework": framework,
        })

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("# Retailer public-structure diagnostic\n\n")
            summary.write("| Retailer | HTTP | Redirect | Scripts | Valid JSON-LD | Product nodes | JSON-LD offers | Framework |\n")
            summary.write("|---|---:|---|---:|---:|---:|---:|---|\n")
            for item in summaries:
                json_ld = item["json_ld"]
                summary.write(
                    f"| {item['retailer']} | {item['status']} | {item['redirected']} "
                    f"| {item['scripts']} | {json_ld['valid_scripts']} "
                    f"| {json_ld['product_nodes']} | {len(json_ld['offers'])} "
                    f"| {join(item['framework'])} |\n"
                )


if __name__ == "__main__":
    main()
