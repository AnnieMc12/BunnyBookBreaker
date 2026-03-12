"""HTML pre-processing sanitizers applied before the walker runs.

Each sanitizer modifies an lxml element tree in place to clean up
vendor-specific junk that would otherwise confuse the walker.
"""

from lxml import etree


def strip_gbs_anchors(root):
    """Remove Google Books page-marker anchors without losing text.

    GBS anchors look like: <a id="GBS.PA27.w.1.0.0"/>
    They are empty anchor elements scattered throughout paragraph text.
    Their tail text belongs to the paragraph flow. When removing the anchor,
    we must merge its tail into the previous sibling's tail (or parent's text
    if there's no previous sibling), otherwise the text gets lost or duplicated.
    """
    # Find all anchors with GBS-style IDs across all namespaces
    anchors = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "a" and "id" in elem.attrib:
            aid = elem.attrib["id"]
            if aid.startswith("GBS."):
                anchors.append(elem)

    for anchor in anchors:
        parent = anchor.getparent()
        if parent is None:
            continue
        tail = anchor.tail or ""
        prev = anchor.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
        parent.remove(anchor)


def strip_empty_anchors(root):
    """Remove all empty anchor elements (no text, no children) that are just ID markers.

    Many EPUBs scatter empty <a id="..."/> throughout paragraphs as
    navigation targets. These serve no purpose in DOCX output.
    """
    anchors = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "a" and len(elem) == 0 and not elem.text:
            # Only strip if it has an id but no href (it's a target, not a link)
            if "id" in elem.attrib and "href" not in elem.attrib:
                anchors.append(elem)

    for anchor in anchors:
        parent = anchor.getparent()
        if parent is None:
            continue
        tail = anchor.tail or ""
        prev = anchor.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
        parent.remove(anchor)


def sanitize_html(root):
    """Run all sanitizers on an lxml element tree."""
    strip_gbs_anchors(root)
    strip_empty_anchors(root)
