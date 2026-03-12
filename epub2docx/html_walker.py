"""Walks an lxml HTML element tree and emits document operations.

The walker does NOT call python-docx directly. Instead it produces a list
of DocOp dataclass objects that the docx_writer consumes. This keeps
parsing and writing independently testable.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from epub2docx.constants import CSS_CLASS_ROLES


# --- Document operation types ---

@dataclass
class DocOp:
    """Base class for document operations."""
    pass


@dataclass
class AddHeading(DocOp):
    text: str = ""
    level: int = 1


@dataclass
class StartParagraph(DocOp):
    style: str = "body_text"  # matches CSS_CLASS_ROLES values


@dataclass
class AddRun(DocOp):
    text: str = ""
    bold: bool = False
    italic: bool = False


@dataclass
class AddSceneBreak(DocOp):
    pass


@dataclass
class AddLineBreak(DocOp):
    pass


# --- Walker ---

def _tag(elem):
    """Get the local tag name, stripping any namespace."""
    t = elem.tag
    return t.split("}")[-1] if "}" in t else t


def _get_role(elem):
    """Map an element's CSS class to a semantic role."""
    cls = elem.attrib.get("class", "").strip()
    if not cls:
        return None
    # An element can have multiple classes; check each
    for c in cls.split():
        role = CSS_CLASS_ROLES.get(c)
        if role and role != "ignore_wrapper":
            return role
    return None


def _is_scene_break(elem):
    """Check if an element represents a scene break."""
    cls = elem.attrib.get("class", "").strip()
    for c in cls.split():
        if CSS_CLASS_ROLES.get(c) == "scene_break":
            return True
    return False


def _is_chapter_number(elem):
    """Check if an element is a chapter number (usually image-based)."""
    cls = elem.attrib.get("class", "").strip()
    for c in cls.split():
        if CSS_CLASS_ROLES.get(c) == "chapter_number":
            return True
    return False


def _has_only_image(elem):
    """Check if a paragraph contains only an image (and maybe anchors)."""
    has_img = False
    for child in elem.iter():
        tag = _tag(child)
        if tag == "img":
            has_img = True
        elif tag in ("a", "span", "div", "p"):
            continue
        elif child.text and child.text.strip():
            return False
    return has_img


def _collect_unknown_classes(elem):
    """Return any CSS classes not in our known mapping."""
    cls = elem.attrib.get("class", "").strip()
    unknown = []
    for c in cls.split():
        if c and c not in CSS_CLASS_ROLES:
            unknown.append(c)
    return unknown


def walk_body(body) -> tuple[List[DocOp], List[str]]:
    """Walk an HTML <body> element and return (operations, unknown_classes).

    Args:
        body: An lxml Element for the <body> tag (already sanitized).

    Returns:
        A tuple of (list of DocOp objects, list of unknown CSS class names).
    """
    ops: List[DocOp] = []
    unknown_classes: List[str] = []

    for elem in body.iter():
        tag = _tag(elem)

        # We only care about block-level elements
        if tag not in ("p", "h1", "h2", "h3", "h4", "h5", "h6"):
            continue

        # Track unknown classes
        unknown_classes.extend(_collect_unknown_classes(elem))

        # Handle headings
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = _extract_full_text(elem).strip()
            if text:
                ops.append(AddHeading(text=text, level=level))
            continue

        # Handle <p> elements
        role = _get_role(elem)

        # Scene break
        if _is_scene_break(elem):
            ops.append(AddSceneBreak())
            continue

        # Chapter number image - skip (titles handled by title_resolver)
        if _is_chapter_number(elem) or (_has_only_image(elem) and role is None):
            continue

        # Extract formatted runs
        runs = _extract_runs(elem)

        # Skip empty paragraphs
        full_text = "".join(r.text for r in runs).strip()
        if not full_text:
            continue

        # Determine paragraph style
        style = role if role else "body_text"

        ops.append(StartParagraph(style=style))
        ops.extend(runs)

    # Deduplicate unknown classes
    unknown_classes = sorted(set(unknown_classes))
    return ops, unknown_classes


def _extract_full_text(elem) -> str:
    """Extract all text from an element (ignoring formatting)."""
    parts = []

    def _walk(node):
        if node.text:
            parts.append(node.text)
        for child in node:
            tag = _tag(child)
            if tag == "br":
                parts.append("\n")
            elif tag == "img":
                pass
            else:
                _walk(child)
            if child.tail:
                parts.append(child.tail)

    _walk(elem)
    return "".join(parts)


def _extract_runs(elem) -> List[AddRun]:
    """Extract text runs with formatting from a paragraph element."""
    runs: List[AddRun] = []

    def _walk(node, italic=False, bold=False):
        tag = _tag(node)

        # Update formatting context
        node_italic = italic
        node_bold = bold
        if tag in ("em", "i"):
            node_italic = True
        if tag in ("b", "strong"):
            node_bold = True

        # This node's direct text
        if node.text:
            runs.append(AddRun(text=node.text, italic=node_italic, bold=node_bold))

        # Process children
        for child in node:
            child_tag = _tag(child)
            if child_tag == "br":
                runs.append(AddRun(text="\n"))
            elif child_tag == "img":
                pass  # Skip images
            else:
                _walk(child, node_italic, node_bold)
            # Tail text after child
            if child.tail:
                runs.append(AddRun(text=child.tail, italic=node_italic, bold=node_bold))

    _walk(elem)
    return runs
