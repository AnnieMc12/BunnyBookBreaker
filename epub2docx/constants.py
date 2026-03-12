"""Known CSS class mappings, front-matter keywords, and classification patterns."""

import re

# CSS class -> semantic role mapping
# These are seeded from Shatterpoint and common publisher patterns.
# Unknown classes fall back to "body_text" and get logged.
CSS_CLASS_ROLES = {
    # Body text
    "tx": "body_text",
    "text": "body_text",
    "body": "body_text",
    "p": "body_text",
    "para": "body_text",
    # Opening paragraph (no indent, sometimes drop cap)
    "cotx": "opening_text",
    "first": "opening_text",
    "initial": "opening_text",
    # Scene breaks
    "ls": "scene_break",
    "space-break": "scene_break",
    "sb": "scene_break",
    "asterism": "scene_break",
    "ornamental-break": "scene_break",
    "section-break": "scene_break",
    # Chapter number (usually an image)
    "cn": "chapter_number",
    "chapter-number": "chapter_number",
    "chap-num": "chapter_number",
    # Headings
    "h": "heading",
    "fmh": "heading",
    "fmh1": "heading",
    "ct": "heading",
    "chapter-title": "heading",
    "chap-head": "heading",
    # Author / subheading
    "fmah": "author_heading",
    # Block quotes / extracts
    "ext": "block_quote",
    "extract": "block_quote",
    "blockquote": "block_quote",
    "bq": "block_quote",
    "quote": "block_quote",
    # Dedication
    "ded": "dedication",
    "dedication": "dedication",
    # Epigraph
    "epi": "epigraph",
    "epigraph": "epigraph",
    # Calibre / rendering noise (ignore styling, treat content as body)
    "calibre1": "ignore_wrapper",
    "calibre2": "ignore_wrapper",
    "calibre3": "ignore_wrapper",
    "calibre4": "ignore_wrapper",
    "calibre5": "ignore_wrapper",
    "calibre6": "ignore_wrapper",
    "calibre7": "ignore_wrapper",
    "cover": "ignore_wrapper",
    "cover1": "ignore_wrapper",
}

# Front-matter keywords for spine item classification (case-insensitive)
FRONT_MATTER_KEYWORDS = {
    "dedication", "ded",
    "epigraph", "ep",
    "prologue",
    "introduction", "intro",
    "foreword",
    "preface",
    "acknowledgments", "acknowledgements",
    "about the author",
    "copyright",
    "title page",
    "table of contents", "toc", "contents",
    "also by",
}

# Back-matter keywords
BACK_MATTER_KEYWORDS = {
    "appendix",
    "glossary",
    "index",
    "bibliography",
    "notes",
    "afterword",
    "epilogue",
    "about the author",
    "also by",
    "copyright",
}

# Spine ID patterns for classification
SPINE_ID_PATTERNS = [
    (re.compile(r"^(tp|title[-_]?page)$", re.I), "title_page"),
    (re.compile(r"^(toc|contents)$", re.I), "toc"),
    (re.compile(r"^(ded|dedication)$", re.I), "dedication"),
    (re.compile(r"^(ep|epigraph)$", re.I), "epigraph"),
    (re.compile(r"^fm\d*$", re.I), "front_matter"),
    (re.compile(r"^bm\d*$", re.I), "back_matter"),
    (re.compile(r"^(ack|acknowledgment)$", re.I), "acknowledgments"),
    (re.compile(r"^(cop|copyright)$", re.I), "copyright"),
    (re.compile(r"^p\d+$", re.I), "part_divider"),
    (re.compile(r"^(c|ch|chapter)[-_]?(\d+)$", re.I), "chapter"),
]

# Characters illegal in filenames on Windows
ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')

# Max filename length (conservative for both platforms)
MAX_FILENAME_LENGTH = 200

# Generic chapter label pattern (indicates the real title might be elsewhere)
GENERIC_CHAPTER_PATTERN = re.compile(r"^(chapter|ch\.?)\s*\d+\s*$", re.I)

# Image alt-text values that are useless
USELESS_ALT_TEXT = {"image", "img", "cover", ""}
