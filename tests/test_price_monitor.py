import unittest

from scripts.price_monitor import exact_terminalx_observation, parse_offers


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
            ["https://schema.org/InStock", "https://schema.org/OutOfStock"],
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
            self.product(name="שמלה אדומה"),
            self.page(),
        )
        self.assertEqual(result["error_code"], "product_identity_mismatch")

    def test_parse_offers_preserves_offer_relationships(self):
        parsed = parse_offers(HTML)
        self.assertEqual(len(parsed["offers"]), 2)
        self.assertEqual(parsed["offers"][0]["size"], "M")
        self.assertEqual(parsed["offers"][1]["availability"], "https://schema.org/OutOfStock")


if __name__ == "__main__":
    unittest.main()
