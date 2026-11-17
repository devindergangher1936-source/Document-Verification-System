"""Optional OCR via Tesseract. Works only if the tesseract binary is installed."""
import os
import shutil

from PIL import Image

_CANDIDATES = [
    os.environ.get("TESSERACT_CMD", ""),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _tesseract_cmd():
    found = shutil.which("tesseract")
    if found:
        return found
    return next((c for c in _CANDIDATES if c and os.path.exists(c)), None)


def ocr_available():
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return _tesseract_cmd() is not None


def ocr_image(img: Image.Image) -> str:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd()
    return pytesseract.image_to_string(img.convert("RGB"))
