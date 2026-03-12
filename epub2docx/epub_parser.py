"""Opens an EPUB file and classifies its spine items.

Provides structured access to the book's content, metadata,
NCX navigation labels, images, and classified spine items.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import ebooklib
from ebooklib import epub
from lxml import etree

from epub2docx.constants import (
    FRONT_MATTER_KEYWORDS,
    BACK_MATTER_KEYWORDS,
    SPINE_ID_PATTERNS,
)


@dataclass
class SpineItem:
    """A classified item from the EPUB spine."""
    item_id: str
    href: str
    ncx_label: Optional[str]
    classification: str  # "chapter", "dedication", "part_divider", etc.
    chapter_number: Optional[int]  # For chapters, the sequential number
    content_bytes: bytes = field(repr=False)


@dataclass
class ParsedEpub:
    """The result of parsing an EPUB file."""
    title: str
    author: str
    spine_items: List[SpineItem]
    images: Dict[str, bytes]  # href -> image bytes


def parse_epub(epub_path: str) -> ParsedEpub:
    """Parse an EPUB file and classify its spine items.

    Args:
        epub_path: Path to the .epub file.

    Returns:
        A ParsedEpub with classified spine items and image data.
    """
    book = epub.read_epub(epub_path)

    # Extract metadata
    title = _get_metadata(book, "title") or "Unknown Title"
    author = _get_metadata(book, "creator") or ""

    # Build NCX label lookup: href -> label
    ncx_labels = _build_ncx_labels(book)

    # Build image lookup: href -> bytes
    images = {}
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        images[item.get_name()] = item.get_content()

    # Classify spine items
    spine_items = []
    chapter_counter = 0

    for item_id, linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None:
            continue

        href = item.get_name()
        ncx_label = ncx_labels.get(href)
        content = item.get_content()

        # Classify this spine item
        classification = _classify_item(item_id, ncx_label, content)

        chapter_number = None
        if classification == "chapter":
            chapter_counter += 1
            chapter_number = chapter_counter

        spine_items.append(SpineItem(
            item_id=item_id,
            href=href,
            ncx_label=ncx_label,
            classification=classification,
            chapter_number=chapter_number,
            content_bytes=content,
        ))

    return ParsedEpub(
        title=title,
        author=author,
        spine_items=spine_items,
        images=images,
    )


def _get_metadata(book, key: str) -> Optional[str]:
    """Extract a Dublin Core metadata value."""
    vals = book.get_metadata("DC", key)
    if vals:
        return vals[0][0]
    return None


def _build_ncx_labels(book) -> Dict[str, str]:
    """Build a mapping of href -> NCX/TOC label."""
    labels = {}

    def _walk_toc(toc_items):
        for item in toc_items:
            if isinstance(item, tuple):
                section, children = item
                # Section itself
                href = section.href.split("#")[0] if section.href else ""
                if href and section.title:
                    labels[href] = section.title
                _walk_toc(children)
            else:
                href = item.href.split("#")[0] if item.href else ""
                if href and item.title:
                    labels[href] = item.title

    _walk_toc(book.toc)
    return labels


def _classify_item(item_id: str, ncx_label: Optional[str], content: bytes) -> str:
    """Classify a spine item based on its ID, NCX label, and content."""

    # Check spine ID against known patterns
    for pattern, classification in SPINE_ID_PATTERNS:
        if pattern.match(item_id):
            return classification

    # Check NCX label against front-matter keywords
    if ncx_label:
        label_lower = ncx_label.strip().lower()
        for keyword in FRONT_MATTER_KEYWORDS:
            if keyword in label_lower:
                return keyword.replace(" ", "_")

        for keyword in BACK_MATTER_KEYWORDS:
            if keyword in label_lower:
                return "back_matter"

        # Check for part dividers
        if re.match(r"^part\s+", label_lower, re.I):
            return "part_divider"

        # Check for chapter labels
        if re.match(r"^(chapter|ch\.?)\s*\d+", label_lower, re.I):
            return "chapter"

    # Check content: if it's mostly images with little text, it's likely a divider
    text_content = _extract_text_from_html(content)
    if len(text_content.strip()) < 20:
        return "image_only"

    # Default: treat as a chapter (better to include than skip)
    return "chapter"


def _extract_text_from_html(content: bytes) -> str:
    """Quick text extraction from HTML bytes."""
    try:
        tree = etree.fromstring(content)
        return etree.tostring(tree, method="text", encoding="unicode")
    except Exception:
        try:
            # Try with HTML parser for malformed content
            parser = etree.HTMLParser()
            tree = etree.fromstring(content, parser)
            return etree.tostring(tree, method="text", encoding="unicode")
        except Exception:
            return ""
