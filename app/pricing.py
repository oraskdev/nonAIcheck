import math
import re

from .config import settings


def count_words(text):
    # Count CJK characters separately, plus Unicode letter/number runs elsewhere.
    cjk = re.findall(r"[\u3400-\u9fff\u3040-\u30ff]", text)
    other = re.sub(r"[\u3400-\u9fff\u3040-\u30ff]", " ", text)
    return len(cjk) + len(re.findall(r"\w+(?:['’-]\w+)*", other, re.UNICODE))


def quote(words, ocr_pages=0, slides=0, detector=False):
    units = max(1, math.ceil(words / 1000))
    rows = [{"label": "Three-engine review · first 1,000 words", "cents": settings.base_price}]
    if units > 1:
        rows.append({"label": f"Additional words · {units - 1} × 1,000", "cents": (units - 1) * settings.extra_price})
    if ocr_pages:
        rows.append({"label": f"Scanned pages · {ocr_pages}", "cents": ocr_pages * settings.ocr_price})
    if slides:
        rows.append({"label": f"Slide reconstruction · {slides}", "cents": slides * settings.slide_price})
    detector_cents = units * settings.detector_price if detector else 0
    if detector:
        rows.append({"label": "GPTZero before / after assessment", "cents": detector_cents})
    return {"total_cents": sum(r["cents"] for r in rows), "detector_cents": detector_cents, "items": rows}
