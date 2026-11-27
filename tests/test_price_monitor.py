import unittest
from pathlib import Path

from scripts.price_monitor import (
    exact_terminalx_observation,
    parse_offers,
    select_test_product,
    validate_external_url,
    validate_redirect,
)


HTML = """
<script type="application/ld+json">
{
  "@type": "Product",
  "name": "מעיל ארוך לנשים - MANGO",
  "sku": "r602330007",
  "offers": [
    {
      "@type": "Offer",
      "url": "https://www.terminalx.com/r602330007?color=22",
      "price": "194.97",
      "priceCurrency": "ILS",
      "availability": "https://schema.org/InStock",
      "color": "22",
      "size": "M"
    },
    {
      "@type": "Offer",
      "url": "https://www.terminalx.com/r602330007?color=22",
      "price": "194.97",
      "priceCurrency": "ILS",
      "availability": "https://schema.org/OutOfStock",
      "color": "22",
      "size": "S"
    }
  ]
}
</script>
"""


class PriceMonitorTests(unittest.TestCase):
    def product(self, **overrides):
        product = {
            "id": "p-1",
            "name": "מעיל ארוך – MANGO",
            "store": "טרמינל איקס",
            "url": "https://www.terminalx.com/r602330007?color=22",
        }
        product.update(overrides)
        return product

    def page(self, **overrides):
        result = {
            "status": 200,
            "final_url": "https://www.terminalx.com/r602330007?color=22",
            "body": HTML,
            "error": None,
        }
        result.update(overrides)
        return result

    def test_extracts_exact_product_price_currency_color_and_separate_availability(self):
        result = exact_terminalx_observation(self.product(), self.page())
        self.assertEqual(result["verification_status"], "verified")
        self.assertEqual(result["price"], 194.97)
        self.assertEqual(result["currency"], "ILS")
        self.assertEqual(result["selected_color_id"], "22")
        self.assertEqual(
            result["availability"],
            [
                {
                    "availability": "https://schema.org/InStock",
                    "size": "M",
                    "color": "22",
                    "sku": "r602330007",
                },
                {
                    "availability": "https://schema.org/OutOfStock",
                    "size": "S",
                    "color": "22",
                    "sku": "r602330007",
                },
            ],
        )

    def test_rejects_unsupported_retailer(self):
        result = exact_terminalx_observation(
            self.product(url="https://www.asos.com/example/prd/1"),
            self.page(),
        )
        self.assertEqual(result["verification_status"], "failed")
        self.assertEqual(result["error_code"], "unsupported_retailer")

    def test_rejects_missing_price(self):
        result = exact_terminalx_observation(
            self.product(),
            self.page(body=HTML.replace('"price": "194.97"', '"price": ""')),
        )
        self.assertEqual(result["error_code"], "no_verified_ils_offer")

    def test_rejects_failed_http_request(self):
        result = exact_terminalx_observation(
            self.product(),
            self.page(status=403, body="", error="http_403"),
        )
        self.assertEqual(result["error_code"], "http_403")

    def test_rejects_identity_mismatch(self):
        result = exact_terminalx_observation(
            self.product(),
            self.page(body=HTML.replace('"sku": "r602330007"', '"sku": "r999999999"')),
        )
        self.assertEqual(result["error_code"], "product_id_mismatch")

    def test_parse_offers_preserves_offer_relationships(self):
        parsed = parse_offers(HTML)
        self.assertEqual(len(parsed["offers"]), 2)
        self.assertEqual(parsed["offers"][0]["size"], "M")
        self.assertEqual(parsed["offers"][1]["availability"], "https://schema.org/OutOfStock")


    def test_rejects_missing_retailer_product_id(self):
        body = HTML.replace('"sku": "r602330007"', '"sku": ""')
        result = exact_terminalx_observation(
            self.product(),
            self.page(body=body),
        )
        self.assertEqual(result["error_code"], "retailer_product_id_missing")

    def test_rejects_missing_selected_color_association(self):
        body = HTML.replace('      "color": "22",\n', "")
        result = exact_terminalx_observation(
            self.product(),
            self.page(body=body),
        )
        self.assertEqual(result["error_code"], "no_verified_ils_offer")

    def test_rejects_arbitrary_color_substring(self):
        body = HTML.replace('"color": "22"', '"color": "122"')
        result = exact_terminalx_observation(
            self.product(),
            self.page(body=body),
        )
        self.assertEqual(result["error_code"], "no_verified_ils_offer")

    def test_rejects_ambiguous_conflicting_prices(self):
        body = HTML.replace('"price": "194.97"', '"price": "194.97"', 1)
        body = body.replace('"price": "194.97"', '"price": "204.97"', 1)
        result = exact_terminalx_observation(
            self.product(),
            self.page(body=body),
        )
        self.assertEqual(result["error_code"], "conflicting_prices")

    def test_rejects_missing_test_color(self):
        products = [self.product()]
        with self.assertRaisesRegex(RuntimeError, "test_product_color_missing"):
            select_test_product(products, "https://www.terminalx.com/r602330007")

    def test_test_mode_selects_exactly_one_catalogue_product(self):
        products = [
            self.product(),
            self.product(id="p-2", url="https://www.terminalx.com/r602330007?color=23"),
        ]
        selected = select_test_product(
            products,
            "https://www.terminalx.com/r602330007?color=22",
        )
        self.assertEqual([item["id"] for item in selected], ["p-1"])

    def test_http_validation(self):
        self.assertEqual(validate_external_url("http://www.terminalx.com/r602330007"), "non_https_url")
        self.assertEqual(validate_external_url("https://evil.example/r602330007"), "unsupported_retailer")
        self.assertIsNone(validate_external_url("https://www.terminalx.com/r602330007"))
        self.assertEqual(
            validate_redirect("https://www.terminalx.com/a", "http://evil.example/a"),
            "redirect_non_https",
        )
        self.assertEqual(
            validate_redirect("https://www.terminalx.com/a", "https://evil.example/a"),
            "unsupported_retailer",
        )

    def test_migration_keeps_public_access_verified_only_and_server_writes(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "supabase/migrations/20261123_price_observations.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("using (verification_status = 'verified')", migration)
        self.assertIn("revoke all on public.price_observations from anon, authenticated;", migration)
        self.assertIn("grant select on public.price_observations", migration)


if __name__ == "__main__":
    unittest.main()
