"""Cascading chapter title resolution.

Tries multiple strategies to determine the real title of a chapter:
1. NCX/TOC label (if it's more than just "Chapter N")
2. Text heading in the HTML (<h1>, <h2>, or classed heading)
3. Image alt-text (if not generic)
4. OCR on the title image via pytesseract
5. Fallback to "Chapter N"
"""

import io
import re
import logging
from typing import Optional, Tuple

from lxml import etree

from epub2docx.constants import GENERIC_CHAPTER_PATTERN, USELESS_ALT_TEXT

logger = logging.getLogger(__name__)

# Try importing OCR dependencies - they're optional
try:
    from PIL import Image, ImageFilter
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# Try to verify tesseract binary is actually installed
if OCR_AVAILABLE:
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        OCR_AVAILABLE = False


def is_ocr_available() -> bool:
    return OCR_AVAILABLE


def _tag(elem):
    t = elem.tag
    return t.split("}")[-1] if "}" in t else t


def resolve_title(
    spine_index: int,
    ncx_label: Optional[str],
    body_element,
    epub_images: dict,
    ocr_enabled: bool = True,
) -> Tuple[str, str]:
    """Resolve a chapter title using cascading strategies.

    Args:
        spine_index: The chapter's position in the spine (1-based for naming).
        ncx_label: The label from the NCX/TOC, if any.
        body_element: The lxml <body> element for this chapter.
        epub_images: Dict mapping image href -> bytes.
        ocr_enabled: Whether to attempt OCR.

    Returns:
        Tuple of (title_text, method_used).
        method_used is one of: "ncx", "html_heading", "alt_text", "ocr", "fallback".
    """
    # Strategy 1: NCX label if it contains more than just "Chapter N"
    if ncx_label and not GENERIC_CHAPTER_PATTERN.match(ncx_label.strip()):
        return ncx_label.strip(), "ncx"

    # Strategy 2: Text heading in the HTML
    heading_text = _find_text_heading(body_element)
    if heading_text and len(heading_text.strip()) > 2:
        return heading_text.strip(), "html_heading"

    # Strategy 3: Image alt-text
    alt_text = _find_image_alt(body_element)
    if alt_text and alt_text.strip().lower() not in USELESS_ALT_TEXT:
        return alt_text.strip(), "alt_text"

    # Strategy 4: OCR
    if ocr_enabled and OCR_AVAILABLE:
        img_src = _find_title_image_src(body_element)
        if img_src:
            img_bytes = _lookup_image(img_src, epub_images)
            if img_bytes:
                ocr_text = _ocr_image(img_bytes)
                if ocr_text and len(ocr_text.strip()) > 1:
                    cleaned = _clean_ocr_text(ocr_text, spine_index)
                    if cleaned:
                        return cleaned, "ocr"

    # Strategy 5: Fallback
    chapter_num = _extract_chapter_number(ncx_label, spine_index)
    return f"Chapter {chapter_num}", "fallback"


def _find_text_heading(body) -> Optional[str]:
    """Look for <h1>-<h6> or heading-classed elements with actual text."""
    for elem in body.iter():
        tag = _tag(elem)
        if tag in ("h1", "h2", "h3"):
            text = _get_all_text(elem).strip()
            if text and not GENERIC_CHAPTER_PATTERN.match(text):
                return text
    return None


def _find_image_alt(body) -> Optional[str]:
    """Find the first image's alt text in the chapter opening."""
    for elem in body.iter():
        if _tag(elem) == "img":
            alt = elem.attrib.get("alt", "")
            if alt:
                return alt
    return None


def _find_title_image_src(body) -> Optional[str]:
    """Find the src of the first image that's likely a chapter title."""
    for elem in body.iter():
        if _tag(elem) == "img":
            return elem.attrib.get("src", "")
    return None


def _lookup_image(img_src: str, epub_images: dict) -> Optional[bytes]:
    """Look up image bytes by src, trying various path forms."""
    import os

    # Try exact match
    if img_src in epub_images:
        return epub_images[img_src]

    # Try just the filename - handles path mismatches between HTML src and EPUB manifest
    basename = os.path.basename(img_src)
    for key, data in epub_images.items():
        if os.path.basename(key) == basename:
            return data

    # Try with common prefixes
    for prefix in ("OEBPS/", "OEBPS/OEBPS/", "OPS/", ""):
        candidate = prefix + img_src
        if candidate in epub_images:
            return epub_images[candidate]

    # Try matching by suffix (the src might be relative while manifest is absolute)
    for key, data in epub_images.items():
        if key.endswith(img_src) or key.endswith("/" + img_src):
            return data

    return None


def _ocr_image(img_bytes: bytes) -> Optional[str]:
    """Run OCR on image bytes with preprocessing for small title images.

    Uses a simple, reliable approach: scale up aggressively, threshold,
    and use PSM 7 (single text line). This works well for the typical
    publisher chapter-title image format.
    """
    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("L")
        w, h = img.size
        # Scale to ~800px wide for good OCR on small images
        scale = max(3, 800 // max(w, 1))
        img = img.resize((w * scale, h * scale), Image.LANCZOS)
        img = img.point(lambda x: 0 if x < 128 else 255, "1")
        text = pytesseract.image_to_string(img, config="--psm 7")
        return text.strip()
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return None


def _clean_ocr_text(text: str, chapter_num: int) -> Optional[str]:
    """Clean up OCR output for a chapter title.

    Removes the chapter number if it appears at the start, strips noise
    from cropped-image OCR, and title-cases the result.
    """
    # Remove common OCR artifacts
    text = text.strip().strip("—-_|")

    # OCR often reads "7" as "/" and splits two-digit numbers with spaces
    ch_str = str(chapter_num)
    if len(ch_str) == 2:
        # Two-digit: try "D D" pattern (e.g., "1 0" for 10)
        spaced = ch_str[0] + r"\s+" + ch_str[1]
        text = re.sub(r"^" + spaced + r"\s*[—\-_|/;:.]?\s*", "", text)
    # Also try the number as-is
    text = re.sub(r"^" + re.escape(ch_str) + r"\s*[—\-_|/;:.]?\s*", "", text)
    # Strip any remaining leading digits/slashes/punctuation noise
    text = re.sub(r"^[\d/|;:.\s]+(?=[A-Za-z])", "", text)

    # Strip leading short noise tokens (1-4 chars of non-word junk from
    # cropped images where the bottom of the chapter number bleeds in).
    # Repeatedly strip tokens that are too short to be real words and
    # contain non-alphabetic characters or are just 1-2 uppercase letters.
    words = text.split()
    while words:
        token = words[0]
        # Keep it if it's a real word (3+ alpha chars, or a common short word)
        alpha_chars = sum(1 for c in token if c.isalpha())
        is_short_noise = (
            alpha_chars <= 2
            and len(token) <= 4
            and token.upper() not in ("A", "AN", "IN", "OF", "ON", "OR", "TO", "THE")
        )
        if is_short_noise:
            words.pop(0)
        else:
            break
    text = " ".join(words)

    # Remove stray non-alphanumeric characters (keep apostrophes and hyphens)
    text = re.sub(r"[^\w\s'''\-]", "", text).strip()

    if not text or len(text) < 2:
        return None

    # Title case
    return text.title()


def _extract_chapter_number(ncx_label: Optional[str], spine_index: int) -> int:
    """Extract a chapter number from the NCX label or use the spine index."""
    if ncx_label:
        m = re.search(r"\d+", ncx_label)
        if m:
            return int(m.group())
    return spine_index


def _get_all_text(elem) -> str:
    """Get all text content from an element."""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem.iter():
        if child is not elem and child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)
