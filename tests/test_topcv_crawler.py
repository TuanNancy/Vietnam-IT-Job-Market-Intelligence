from __future__ import annotations

import unittest

from scrapers.topcv_crawler import extract_job_urls, is_block_page, job_id_from_url, normalize_job_url


class TopCVCrawlerUrlTests(unittest.TestCase):
    def test_normalizes_topcv_detail_urls(self) -> None:
        self.assertEqual(
            normalize_job_url("/viec-lam/back-end-developer/2084326.html"),
            "https://www.topcv.vn/viec-lam/back-end-developer/2084326.html",
        )
        self.assertEqual(
            normalize_job_url("https://topcv.vn/viec-lam/python-developer/123.html?utm=ignored"),
            "https://www.topcv.vn/viec-lam/python-developer/123.html",
        )

    def test_rejects_non_detail_or_external_urls(self) -> None:
        self.assertIsNone(normalize_job_url("https://example.com/viec-lam/python/123.html"))
        self.assertIsNone(normalize_job_url("/cong-ty/example"))
        self.assertIsNone(normalize_job_url("/viec-lam/python-developer"))

    def test_extracts_and_dedupes_urls_from_anchor_and_json_ld(self) -> None:
        html = """
        <html><head>
          <script type="application/ld+json">
          {
            "@type": "ItemList",
            "itemListElement": [
              {"url": "https://www.topcv.vn/viec-lam/back-end-developer/2084326.html"}
            ]
          }
          </script>
        </head><body>
          <a href="/viec-lam/back-end-developer/2084326.html">Backend</a>
          <a href="/viec-lam/frontend-developer/2084327.html">Frontend</a>
        </body></html>
        """

        self.assertEqual(
            extract_job_urls(html),
            [
                "https://www.topcv.vn/viec-lam/back-end-developer/2084326.html",
                "https://www.topcv.vn/viec-lam/frontend-developer/2084327.html",
            ],
        )

    def test_job_id_uses_numeric_detail_id(self) -> None:
        self.assertEqual(
            job_id_from_url("https://www.topcv.vn/viec-lam/back-end-developer/2084326.html"),
            "topcv_2084326",
        )

    def test_detects_block_page(self) -> None:
        self.assertTrue(is_block_page("<html><title>Attention Required! | Cloudflare</title></html>"))


if __name__ == "__main__":
    unittest.main()
