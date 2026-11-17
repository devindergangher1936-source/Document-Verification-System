"""Image forensics: EXIF inspection and Error Level Analysis (ELA).

ELA re-saves a JPEG at a known quality and diffs it with the original.
Regions edited after the last save recompress differently and show up
brighter. Approach follows the classic technique described by Neal Krawetz
and implemented in many GitHub projects (e.g. "error-level-analysis" repos).
"""
import io

from PIL import ExifTags, Image, ImageChops, ImageEnhance

from .pdf_checks import EDITOR_TOOLS

ELA_QUALITY = 90


def _percentile(hist, pct):
    total = sum(hist)
    target = total * pct
    running = 0
    for value, count in enumerate(hist):
        running += count
        if running >= target:
            return value
    return 255


def error_level_analysis(img: Image.Image, out_path=None):
    """Return (stats, findings). Writes an amplified ELA image to out_path."""
    rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=ELA_QUALITY)
    buf.seek(0)
    resaved = Image.open(buf)
    diff = ImageChops.difference(rgb, resaved)

    gray = diff.convert("L")
    hist = gray.histogram()
    total = sum(hist) or 1
    mean = sum(i * c for i, c in enumerate(hist)) / total
    p99 = _percentile(hist, 0.99)
    p999 = _percentile(hist, 0.999)
    max_diff = max(i for i, c in enumerate(hist) if c) if any(hist) else 0
    # Localized hotspots relative to the overall compression noise floor.
    contrast = p999 / (mean + 1)

    if out_path:
        # Scale to the 99.9th percentile so faint differences are visible.
        scale = 255.0 / max(p999, 1)
        ImageEnhance.Brightness(diff).enhance(min(scale, 60)).save(out_path, "PNG")

    stats = {"mean": round(mean, 2), "p99": p99, "p999": p999,
             "max": max_diff, "hotspot_ratio": round(contrast, 2)}
    findings = []
    if contrast > 12 and p999 > 25:
        findings.append(("medium", "image", "ELA shows localized compression anomalies",
                         "Some regions recompress very differently from the rest of the image, which often "
                         "indicates pasted or edited areas. Inspect the ELA image for bright patches."))
    elif contrast > 7 and p999 > 15:
        findings.append(("low", "image", "ELA shows mild compression inconsistencies",
                         "Can be caused by edits, but also by text/sharp edges. Review the ELA image."))
    return stats, findings


def analyze_image(path, ela_out=None):
    findings = []
    meta = {}
    with Image.open(path) as img:
        meta.update(format=img.format, mode=img.mode, width=img.width, height=img.height)
        exif = {}
        try:
            raw = img.getexif()
            for tag_id, value in raw.items():
                name = ExifTags.TAGS.get(tag_id, str(tag_id))
                if isinstance(value, bytes):
                    continue
                exif[name] = str(value)[:200]
            for tag_id, value in raw.get_ifd(ExifTags.IFD.Exif).items():
                name = ExifTags.TAGS.get(tag_id, str(tag_id))
                if not isinstance(value, bytes):
                    exif[name] = str(value)[:200]
        except Exception:
            pass
        meta["exif"] = exif

        software = exif.get("Software", "")
        hit = next((t for t in EDITOR_TOOLS if t in software.lower()), None)
        if hit:
            findings.append(("high", "metadata", f"Image was saved by editing software: {software}",
                             "Scans and camera photos normally record the device, not an image editor."))
        if exif.get("DateTime") and exif.get("DateTimeOriginal") and \
                exif["DateTime"] != exif["DateTimeOriginal"]:
            findings.append(("low", "metadata", "Image modified after it was captured",
                             f"Captured {exif['DateTimeOriginal']}, last modified {exif['DateTime']}."))
        if not exif:
            findings.append(("info", "metadata", "No EXIF metadata",
                             "Metadata is often stripped by messaging apps and editors - not suspicious on its own."))

        if img.format == "JPEG":
            stats, ela_findings = error_level_analysis(img, ela_out)
            meta["ela"] = stats
            findings += ela_findings
        else:
            findings.append(("info", "image", f"ELA skipped for {img.format} (only meaningful for JPEG)", ""))
    return meta, findings
