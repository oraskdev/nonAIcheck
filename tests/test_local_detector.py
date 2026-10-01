import unittest
from unittest.mock import patch

from app import local_detector, providers


class LocalDetectorTests(unittest.TestCase):
    def test_windows_cover_every_token_including_the_end(self):
        for length in (1, 510, 511, 956, 10000, 40000):
            with self.subTest(length=length):
                source = list(range(length))
                pieces = list(local_detector.windows(source))
                self.assertEqual(sum(weight for _, weight in pieces), length)
                self.assertEqual(set(t for p, _ in pieces for t in p), set(source))
                self.assertEqual(pieces[-1][0][-1], length - 1)
                self.assertTrue(all(len(p) <= 510 and weight > 0 for p, weight in pieces))

    def test_local_failure_never_sends_text_to_external_detector(self):
        with patch("app.local_detector.assess", side_effect=RuntimeError("test")), patch("app.providers._request") as external:
            result = providers.detect("Private document text", provider="local")
        self.assertEqual(result["status"], "not_assessed")
        external.assert_not_called()

    def test_unknown_provider_never_sends_text(self):
        with patch("app.providers._request") as external:
            result = providers.detect("Private document text", provider="unknown")
        self.assertEqual(result["status"], "not_assessed")
        external.assert_not_called()
