"""Run every check on an uploaded file and combine the results."""
import hashlib
import io
import re

from PIL import Image
from pypdf import PdfReader

from .fields import extract_fields
from .image_checks import analyze_image
from .ocr import ocr_available, ocr_image
from .pdf_checks import analyze_pdf

SEVERITY_POINTS = {"info": 0, "low": 10, "medium": 25, "high": 40}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_fingerprint(text):
    norm = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest() if len(norm) > 40 else None


def score(findings):
    total = min(100, sum(SEVERITY_POINTS[f["severity"]] for f in findings))
    if total >= 50:
        status = "flagged"
    elif total >= 20:
        status = "review"
    else:
        status = "passed"
    return total, status


def _ocr_pdf(path):
    """OCR embedded page images of a scanned PDF."""
    out = []
    reader = PdfReader(path)
    for page in reader.pages[:5]:
        for im in page.images:
            try:
                out.append(ocr_image(Image.open(io.BytesIO(im.data))))
            except Exception:
                pass
    return "\n".join(out)


def analyze(path, kind, ela_out):
    """kind is 'pdf' or 'image'. Returns dict with findings, fields, meta, text."""
    raw_findings = []
    if kind == "pdf":
        meta, raw_findings, text = analyze_pdf(path, ela_out)
        if len(text.strip()) < 20:
            if ocr_available():
                text = _ocr_pdf(path)
                meta["text_source"] = "ocr"
            else:
                raw_findings.append(("info", "text", "No text layer (scanned PDF) and OCR is not installed",
                                     "Install Tesseract to extract and validate fields from scans."))
        else:
            meta["text_source"] = "pdf"
    else:
        meta, raw_findings = analyze_image(path, ela_out)
        text = ""
        if ocr_available():
            with Image.open(path) as img:
                text = ocr_image(img)
            meta["text_source"] = "ocr"
        else:
            raw_findings.append(("info", "text", "OCR is not installed",
                                 "Install Tesseract to extract and validate fields from images."))

    fields, field_findings = extract_fields(text) if text else ({}, [])
    raw_findings += field_findings

    findings = [{"severity": s, "category": c, "title": t, "detail": d}
                for s, c, t, d in raw_findings]
    return {"findings": findings, "fields": fields, "meta": meta, "text": text}
