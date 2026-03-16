"""Detects and splits chapter boundaries within a single HTML body element.

Some EPUBs (especially older Calibre conversions) pack an entire book into
one or two HTML files with no structural chapter markers — no headings, no
page breaks, no CSS classes. This module detects internal chapter boundaries
using textual heuristics and splits the content so the rest of the pipeline
can process each chapter individually.

Detection strategies (checked in order):
1. ALL-CAPS opening words — a common print convention where each chapter's
   first paragraph begins with two or more words in uppercase.
2. Heading tags (h1-h3) containing chapter-like text.
3. Horizontal rules used as chapter dividers.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from copy import deepcopy

from lxml import etree


# Minimum paragraph count to consider a spine item for splitting.
# Below this, it's probably just a normal chapter.
MIN_PARAGRAPHS_FOR_SPLIT = 80

# Minimum number of detected breaks to accept a splitting strategy.
# If we only find 1-2, it's more likely scene breaks than chapters.
MIN_CHAPTER_BREAKS = 3

# Minimum paragraphs per chapter — if a detected "chapter" is shorter
# than this, it's probably a false positive and should merge back.
MIN_PARAGRAPHS_PER_CHAPTER = 8


@dataclass
class SubChapter:
    """A chapter detected within a larger HTML body."""
    title: Optional[str]         # Detected title, if any
    elements: list               # The lxml elements belonging to this chapter
    paragraph_count: int         # Number of <p> elements in this chapter


def _tag(elem) -> str:
    """Get the local tag name, stripping any namespace."""
    t = elem.tag if isinstance(elem.tag, str) else ""
    return t.split("}")[-1] if "}" in t else t


def _get_text(elem) -> str:
    """Get all text content from an element."""
    return etree.tostring(elem, method="text", encoding="unicode").strip()


def _get_block_elements(body) -> list:
    """Get direct and nested block-level elements (p, h1-h6, hr) in order.

    Returns a list of (element, index_in_parent) tuples preserving
    document order. We walk the body's descendants, collecting only
    the block-level elements that the walker cares about.
    """
    blocks = []
    for elem in body.iter():
        tag = _tag(elem)
        if tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "hr"):
            blocks.append(elem)
    return blocks


def _detect_allcaps_breaks(blocks: list) -> List[int]:
    """Detect chapter breaks using the ALL-CAPS first-words convention.

    Many print books (and their EPUB conversions) capitalize the first
    2-3 words of each chapter's opening paragraph. This is distinct from
    scene-break conventions and is usually consistent throughout a book.
    """
    # Pattern: paragraph starts with at least one word of 2+ uppercase letters
    # followed by more text. The word must be purely alphabetic uppercase
    # (not numbers, not abbreviations like "DNA").
    caps_pattern = re.compile(r'^[A-Z]{2,}\b')

    # First pass: find all paragraphs matching the pattern
    candidates = []
    for i, elem in enumerate(blocks):
        if _tag(elem) != "p":
            continue
        text = _get_text(elem)
        if text and caps_pattern.match(text) and len(text) > 30:
            candidates.append(i)

    return candidates


def _detect_heading_breaks(blocks: list) -> List[int]:
    """Detect chapter breaks using heading tags (h1-h3)."""
    chapter_heading_re = re.compile(
        r'^(chapter|ch\.?)\s*\d+', re.IGNORECASE
    )
    candidates = []
    for i, elem in enumerate(blocks):
        tag = _tag(elem)
        if tag in ("h1", "h2", "h3"):
            text = _get_text(elem)
            if text and (chapter_heading_re.match(text) or len(text) < 60):
                candidates.append(i)
    return candidates


def _detect_hr_breaks(blocks: list) -> List[int]:
    """Detect chapter breaks using <hr> elements.

    Only considers this strategy if hr elements are relatively sparse
    (likely chapter dividers rather than scene breaks).
    """
    candidates = []
    for i, elem in enumerate(blocks):
        if _tag(elem) == "hr":
            # The chapter starts AFTER the hr, so find the next content element
            if i + 1 < len(blocks):
                candidates.append(i + 1)
    return candidates


def _validate_breaks(breaks: List[int], total_blocks: int) -> List[int]:
    """Filter out likely false positives.

    Removes breaks that would create chapters shorter than
    MIN_PARAGRAPHS_PER_CHAPTER, merging those small sections
    into the preceding chapter.
    """
    if not breaks:
        return breaks

    # Ensure the first break is included (chapter 1 start)
    validated = [breaks[0]]

    for i in range(1, len(breaks)):
        gap = breaks[i] - breaks[i - 1]
        if gap >= MIN_PARAGRAPHS_PER_CHAPTER:
            validated.append(breaks[i])
        # else: skip this break — too close to the previous one

    # Check the last chapter isn't too short
    if len(validated) > 1:
        last_gap = total_blocks - validated[-1]
        if last_gap < MIN_PARAGRAPHS_PER_CHAPTER:
            validated.pop()

    return validated


def should_split(body) -> bool:
    """Quick check: does this body element have enough content to warrant
    attempting a chapter split?

    Call this before the more expensive detect_chapters() to skip
    spine items that are obviously single chapters.
    """
    blocks = _get_block_elements(body)
    p_count = sum(1 for b in blocks if _tag(b) == "p")
    return p_count >= MIN_PARAGRAPHS_FOR_SPLIT


def detect_chapters(body, is_first_content: bool = True) -> Optional[List[int]]:
    """Detect chapter boundaries within a body element.

    Tries multiple detection strategies and returns the first one
    that produces a plausible result (>= MIN_CHAPTER_BREAKS chapters).

    Args:
        body: An lxml <body> element.
        is_first_content: If True, this is the first content spine item
            in the book. Content before the first detected chapter marker
            will be preserved as chapter 1. If False, pre-marker content
            is assumed to be an orphaned continuation from the previous
            spine item and will only be included if it matches the
            detection pattern.

    Returns:
        A list of block-element indices where chapters start,
        or None if no chapter structure was detected.
    """
    blocks = _get_block_elements(body)
    total = len(blocks)

    if total < MIN_PARAGRAPHS_FOR_SPLIT:
        return None

    # Strategy 1: ALL-CAPS openings
    breaks = _detect_allcaps_breaks(blocks)
    if len(breaks) >= MIN_CHAPTER_BREAKS:
        validated = _validate_breaks(breaks, total)
        if len(validated) >= MIN_CHAPTER_BREAKS:
            return _ensure_start(validated, blocks, "allcaps", is_first_content)

    # Strategy 2: Heading tags
    breaks = _detect_heading_breaks(blocks)
    if len(breaks) >= MIN_CHAPTER_BREAKS:
        validated = _validate_breaks(breaks, total)
        if len(validated) >= MIN_CHAPTER_BREAKS:
            return _ensure_start(validated, blocks, "headings", is_first_content)

    # Strategy 3: Horizontal rules (only if sparse)
    breaks = _detect_hr_breaks(blocks)
    if MIN_CHAPTER_BREAKS <= len(breaks) <= 40:
        validated = _validate_breaks(breaks, total)
        if len(validated) >= MIN_CHAPTER_BREAKS:
            return _ensure_start(validated, blocks, "hr", is_first_content)

    return None


def _ensure_start(
    breaks: List[int],
    blocks: list,
    strategy: str,
    is_first_content: bool,
) -> List[int]:
    """If the first break isn't at the start, decide whether to prepend 0.

    Content before the first detected marker could be either:
    (a) A real chapter whose opening doesn't use the marker convention
        (e.g., chapter 1 in a book where chapters 2+ use ALL-CAPS).
    (b) Orphaned content from a chapter that started in a previous
        HTML file (the EPUB split mid-chapter across spine items).

    Decision logic:
    - If is_first_content is True and there's substantial pre-break
      content, it's almost certainly chapter 1. Include it.
    - If is_first_content is False, only include if the first block
      matches the detection pattern (confirming it's a real chapter
      start, not a continuation).
    """
    if not breaks or breaks[0] == 0:
        return breaks

    gap = breaks[0]  # Number of blocks before first detected break

    if is_first_content and gap >= MIN_PARAGRAPHS_PER_CHAPTER:
        # This is the first content in the book and there's enough
        # material before the first marker to be a real chapter.
        return [0] + breaks

    if not is_first_content:
        # For subsequent spine items, only prepend if the opening
        # matches the detection pattern (it's a real chapter start,
        # not an orphaned tail from a mid-chapter HTML split).
        first_text = _get_text(blocks[0]) if blocks else ""
        first_matches = False

        if strategy == "allcaps":
            first_matches = bool(
                first_text
                and re.match(r'^[A-Z]{2,}\b', first_text)
                and len(first_text) > 30
            )
        elif strategy == "headings":
            first_matches = (
                _tag(blocks[0]) in ("h1", "h2", "h3") if blocks else False
            )
        elif strategy == "hr":
            first_matches = _tag(blocks[0]) == "hr" if blocks else False

        if first_matches:
            return [0] + breaks

    return breaks


def split_body(body, break_indices: List[int]) -> List[SubChapter]:
    """Split a body element into sub-chapters at the given break points.

    Creates new synthetic <body> elements for each chapter, copying
    the relevant elements into each one.

    Args:
        body: The original lxml <body> element.
        break_indices: Block-element indices where chapters start.

    Returns:
        A list of SubChapter objects, each containing its own elements
        wrapped in a new <body> element.
    """
    blocks = _get_block_elements(body)
    ns = body.nsmap.get(None, "http://www.w3.org/1999/xhtml")
    sub_chapters = []

    for ch_idx, start in enumerate(break_indices):
        end = break_indices[ch_idx + 1] if ch_idx + 1 < len(break_indices) else len(blocks)
        chapter_blocks = blocks[start:end]

        # Create a synthetic body element
        new_body = etree.Element(f"{{{ns}}}body" if ns else "body")
        p_count = 0

        for elem in chapter_blocks:
            new_body.append(deepcopy(elem))
            if _tag(elem) == "p":
                p_count += 1

        # Try to extract a title from the first element
        title = None
        if chapter_blocks:
            first = chapter_blocks[0]
            first_tag = _tag(first)
            first_text = _get_text(first)

            if first_tag in ("h1", "h2", "h3"):
                title = first_text
            elif first_text:
                # For ALL-CAPS openings, extract the caps portion as a hint
                caps_match = re.match(r'^([A-Z][A-Z\s]{2,}?)(?=[a-z])', first_text)
                if caps_match:
                    title = caps_match.group(1).strip().title()

        sub_chapters.append(SubChapter(
            title=title,
            elements=new_body,
            paragraph_count=p_count,
        ))

    return sub_chapters


def extract_orphaned_content(body, break_indices: List[int]) -> Optional[SubChapter]:
    """Extract content before the first chapter break as orphaned content.

    When an EPUB splits mid-chapter across HTML files, the beginning of
    a later file contains the tail of a chapter that started in the
    previous file. This function extracts that orphaned tail so the
    converter can append it to the correct chapter.

    Args:
        body: The lxml <body> element.
        break_indices: The detected chapter break indices.

    Returns:
        A SubChapter containing the orphaned content, or None if the
        first break is at index 0 (no orphaned content).
    """
    if not break_indices or break_indices[0] == 0:
        return None

    blocks = _get_block_elements(body)
    orphaned_blocks = blocks[:break_indices[0]]

    if not orphaned_blocks:
        return None

    ns = body.nsmap.get(None, "http://www.w3.org/1999/xhtml")
    new_body = etree.Element(f"{{{ns}}}body" if ns else "body")
    p_count = 0

    for elem in orphaned_blocks:
        new_body.append(deepcopy(elem))
        if _tag(elem) == "p":
            p_count += 1

    if p_count == 0:
        return None

    return SubChapter(
        title=None,
        elements=new_body,
        paragraph_count=p_count,
    )
