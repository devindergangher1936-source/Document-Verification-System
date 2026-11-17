"""Extract and validate structured identifiers from document text.

Checksum validation for Indian IDs uses python-stdnum
(https://github.com/arthurdejong/python-stdnum).
"""
import re

from stdnum.in_ import aadhaar, gstin, pan

PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")
AADHAAR_RE = re.compile(r"(?<!\d)(\d{4}[ -]?\d{4}[ -]?\d{4})(?!\d)")
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
DATE_RE = re.compile(
    r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})\b",
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR)\s?([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE)
INVOICE_RE = re.compile(
    r"\b(?:invoice|inv|bill)\s*(?:no|number|#)\.?\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,})",
    re.IGNORECASE,
)


def mask_aadhaar(number: str) -> str:
    return "XXXX XXXX " + number[-4:]


def _unique(items):
    return list(dict.fromkeys(items))


def extract_fields(text: str):
    """Return (fields, findings). Findings use the shared finding shape."""
    findings = []
    upper = text.upper()

    gstins = _unique(GSTIN_RE.findall(upper))
    # PANs embedded in a GSTIN are reported via the GSTIN, not separately.
    gst_text = " ".join(gstins)
    pans = _unique(p for p in PAN_RE.findall(upper) if p not in gst_text)
    aadhaars = _unique(re.sub(r"\D", "", a) for a in AADHAAR_RE.findall(text))

    fields = {"gstin": [], "pan": [], "aadhaar": [], "ifsc": [], "email": [],
              "dates": [], "amounts": [], "invoice_numbers": []}

    for g in gstins:
        ok = gstin.is_valid(g)
        fields["gstin"].append({"value": g, "valid": ok})
        if not ok:
            findings.append(("high", "fields", f"GSTIN {g} fails checksum validation",
                             "A genuine GSTIN always has a valid check digit. Typos or fabricated numbers fail."))

    for p in pans:
        ok = pan.is_valid(p)
        fields["pan"].append({"value": p, "valid": ok})
        if not ok:
            findings.append(("medium", "fields", f"PAN {p} has an invalid structure",
                             "The 4th character must be a valid holder type (P, C, H, F, A, T, B, L, J, G)."))

    for a in aadhaars:
        ok = aadhaar.is_valid(a)
        fields["aadhaar"].append({"value": mask_aadhaar(a), "valid": ok})
        if not ok:
            findings.append(("medium", "fields", f"Aadhaar ending {a[-4:]} fails Verhoeff checksum",
                             "Could also be another 12-digit number (phone, account no.) - check manually."))

    # GSTIN characters 3-12 are the holder's PAN: cross-check against PANs on the page.
    if gstins and pans:
        gst_pans = {g[2:12] for g in gstins}
        for p in pans:
            if p not in gst_pans:
                findings.append(("low", "fields", f"PAN {p} does not match any GSTIN on the document",
                                 "GSTIN embeds the holder's PAN. A mismatch can be legitimate (buyer vs seller) "
                                 "but is worth checking."))

    fields["ifsc"] = _unique(IFSC_RE.findall(upper))
    fields["email"] = _unique(EMAIL_RE.findall(text))[:10]
    fields["dates"] = _unique(DATE_RE.findall(text))[:15]
    fields["amounts"] = _unique(AMOUNT_RE.findall(text))[:15]
    fields["invoice_numbers"] = _unique(m.upper() for m in INVOICE_RE.findall(text))[:5]
    return fields, findings
