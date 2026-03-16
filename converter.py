"""Orchestrates EPUB to DOCX conversion for single books and batch folders."""

import os
import re
import logging
from pathlib import Path
from typing import Callable, Optional

from lxml import etree

from epub2docx.epub_parser import parse_epub, SpineItem
from epub2docx.sanitizers import sanitize_html
from epub2docx.html_walker import walk_body
from epub2docx.docx_writer import write_docx, append_to_docx
from epub2docx.title_resolver import resolve_title
from epub2docx.notes_writer import NotesWriter
from epub2docx.chapter_splitter import should_split, detect_chapters, split_body, extract_orphaned_content
from epub2docx.constants import ILLEGAL_FILENAME_CHARS, MAX_FILENAME_LENGTH

logger = logging.getLogger(__name__)

# Classifications that produce output files
OUTPUT_CLASSIFICATIONS = {
    "chapter", "dedication", "epigraph", "prologue", "introduction",
    "foreword", "preface", "front_matter", "back_matter",
    "acknowledgments", "epilogue",
}

# Classifications to skip (no output file)
SKIP_CLASSIFICATIONS = {
    "title_page", "toc", "image_only", "part_divider", "copyright",
    "table_of_contents", "contents", "half_title",
}

# Human-readable labels for front-matter classifications
CLASSIFICATION_LABELS = {
    "dedication": "Dedication",
    "epigraph": "Epigraph",
    "prologue": "Prologue",
    "introduction": "Introduction",
    "foreword": "Foreword",
    "preface": "Preface",
    "front_matter": "Front Matter",
    "back_matter": "Back Matter",
    "acknowledgments": "Acknowledgments",
    "epilogue": "Epilogue",
}


def sanitize_filename(name: str) -> str:
    """Make a filename safe for both Linux and Windows."""
    name = ILLEGAL_FILENAME_CHARS.sub("", name)
    name = name.strip(". ")
    if len(name) > MAX_FILENAME_LENGTH:
        name = name[:MAX_FILENAME_LENGTH]
    return name


def convert_single_epub(
    epub_path: str,
    ocr_enabled: bool = True,
    delete_original: bool = False,
    on_progress: Optional[Callable] = None,
    cancel_check: Optional[Callable] = None,
) -> bool:
    """Convert a single EPUB file into a folder of DOCX files.

    Args:
        epub_path: Path to the .epub file.
        ocr_enabled: Whether to attempt OCR for image-based titles.
        delete_original: Whether to delete the original EPUB after conversion.
        on_progress: Callback(message: str) for progress updates.
        cancel_check: Callable that returns True if conversion should be cancelled.

    Returns:
        True if conversion succeeded, False if it failed or was cancelled.
    """
    epub_path = str(Path(epub_path).resolve())

    def log(msg):
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    def cancelled():
        return cancel_check and cancel_check()

    # Determine output folder
    epub_name = Path(epub_path).stem
    output_dir = str(Path(epub_path).parent / epub_name)

    log(f"Converting: {Path(epub_path).name}")

    try:
        parsed = parse_epub(epub_path)
    except Exception as e:
        log(f"ERROR: Failed to parse EPUB: {e}")
        return False

    os.makedirs(output_dir, exist_ok=True)

    notes = NotesWriter(
        book_title=Path(epub_path).name,
        author=parsed.author,
    )

    file_counter = 0
    chapter_counter = 0
    last_chapter_path = None  # Track last written chapter for orphan appending

    for item in parsed.spine_items:
        if cancelled():
            log("Cancelled.")
            return False

        classification = item.classification

        # Skip non-content items
        if classification in SKIP_CLASSIFICATIONS:
            notes.add_skipped(
                f"{item.item_id} ({classification}): "
                f"NCX='{item.ncx_label or 'N/A'}'"
            )
            continue

        # Parse HTML content
        try:
            tree = etree.fromstring(item.content_bytes)
        except Exception:
            try:
                parser = etree.HTMLParser()
                tree = etree.fromstring(item.content_bytes, parser)
            except Exception as e:
                notes.add_issue(f"Failed to parse HTML for {item.item_id}: {e}")
                continue

        # Find body
        ns = {"x": "http://www.w3.org/1999/xhtml"}
        body = tree.find(".//x:body", ns)
        if body is None:
            body = tree.find(".//body")
        if body is None:
            # Try using the root element
            body = tree

        # Sanitize
        sanitize_html(body)

        # Check if this spine item contains multiple chapters that
        # need splitting (common in poorly-structured EPUBs where
        # the entire book is packed into one or two HTML files).
        if classification == "chapter" and should_split(body):
            is_first_content = (chapter_counter == 0)
            break_indices = detect_chapters(body, is_first_content=is_first_content)
        else:
            break_indices = None

        if break_indices is not None:
            # This spine item contains multiple chapters — split and
            # process each one individually.

            # First, check for orphaned content before the first break.
            # This happens when the EPUB splits mid-chapter across HTML
            # files — the tail of the previous chapter ends up here.
            orphan = extract_orphaned_content(body, break_indices)
            if orphan is not None and last_chapter_path is not None:
                orphan_ops, _ = walk_body(orphan.elements)
                if orphan_ops:
                    try:
                        append_to_docx(orphan_ops, last_chapter_path)
                        log(f"  Appended {orphan.paragraph_count} orphaned "
                            f"paragraphs to previous chapter")
                        notes.add_issue(
                            f"{item.item_id}: {orphan.paragraph_count} paragraphs "
                            f"before first chapter marker appended to previous chapter "
                            f"(EPUB split mid-chapter across HTML files)."
                        )
                    except Exception as e:
                        notes.add_issue(
                            f"Failed to append orphaned content to "
                            f"{last_chapter_path}: {e}"
                        )

            sub_chapters = split_body(body, break_indices)
            log(f"  Split {item.item_id} into {len(sub_chapters)} chapters"
                f" (detected via internal markers)")
            notes.add_issue(
                f"{item.item_id}: Detected {len(sub_chapters)} internal "
                f"chapters via textual heuristics. Split into separate files."
            )

            for sub_ch in sub_chapters:
                if cancelled():
                    log("Cancelled.")
                    return False

                ops, unknown_classes = walk_body(sub_ch.elements)

                if unknown_classes:
                    notes.add_issue(
                        f"{item.item_id} (sub-chapter): Unknown CSS classes: "
                        f"{unknown_classes}. Treated as body text."
                    )

                if not ops:
                    continue

                chapter_counter += 1
                chapter_num = chapter_counter

                # Use the sub-chapter's detected title, or fall back
                if sub_ch.title:
                    title_text = sub_ch.title
                else:
                    title_text = f"Chapter {chapter_num}"

                display_title = f"Chapter {chapter_num}: {title_text}"
                file_label = f"Chapter {chapter_num} - {title_text}"
                filename = f"{file_counter:02d} - {sanitize_filename(file_label)}.docx"

                output_path = os.path.join(output_dir, filename)
                try:
                    write_docx(ops, display_title, output_path)
                    notes.add_file(filename)
                    log(f"  Created: {filename}")
                    file_counter += 1
                    last_chapter_path = output_path
                except Exception as e:
                    notes.add_issue(f"Failed to write {filename}: {e}")
                    log(f"  ERROR writing {filename}: {e}")
        else:
            # Normal path: one spine item = one output file.
            ops, unknown_classes = walk_body(body)

            if unknown_classes:
                notes.add_issue(
                    f"{item.item_id}: Unknown CSS classes: {unknown_classes}. "
                    f"Treated as body text."
                )

            # Skip if no content was extracted
            if not ops:
                notes.add_skipped(
                    f"{item.item_id}: No text content extracted "
                    f"(classification={classification})"
                )
                continue

            # Determine title and filename
            if classification == "chapter":
                chapter_counter += 1
                chapter_num = item.chapter_number or chapter_counter

                # Resolve the real chapter title
                title_text, method = resolve_title(
                    spine_index=chapter_num,
                    ncx_label=item.ncx_label,
                    body_element=body,
                    epub_images=parsed.images,
                    ocr_enabled=ocr_enabled,
                )

                if method == "ocr":
                    notes.add_issue(
                        f"Chapter {chapter_num}: Title '{title_text}' resolved via OCR."
                    )
                elif method == "fallback":
                    notes.add_issue(
                        f"Chapter {chapter_num}: Could not determine subtitle. "
                        f"Using generic title. Image-based title may exist."
                    )

                # Build the display title and filename
                if title_text.lower().startswith("chapter"):
                    display_title = title_text
                    file_label = title_text
                else:
                    display_title = f"Chapter {chapter_num}: {title_text}"
                    file_label = f"Chapter {chapter_num} - {title_text}"

                filename = f"{file_counter:02d} - {sanitize_filename(file_label)}.docx"
            else:
                # Front/back matter - prefer NCX label, then classification label
                if item.ncx_label and item.ncx_label.strip():
                    label = item.ncx_label.strip().title()
                else:
                    label = CLASSIFICATION_LABELS.get(classification, classification.replace("_", " ").title())
                display_title = label
                filename = f"{file_counter:02d} - {sanitize_filename(label)}.docx"

            # Write the DOCX
            output_path = os.path.join(output_dir, filename)
            try:
                write_docx(ops, display_title, output_path)
                notes.add_file(filename)
                log(f"  Created: {filename}")
                file_counter += 1
                if classification == "chapter":
                    last_chapter_path = output_path
            except Exception as e:
                notes.add_issue(f"Failed to write {filename}: {e}")
                log(f"  ERROR writing {filename}: {e}")

    # Write conversion notes
    notes_path = os.path.join(output_dir, "CONVERSION NOTES.txt")
    notes.write(notes_path)
    log(f"  Notes: CONVERSION NOTES.txt ({len(notes.issues)} issues)")

    # Delete original if requested
    if delete_original and file_counter > 0:
        try:
            os.remove(epub_path)
            log(f"  Deleted original: {Path(epub_path).name}")
        except Exception as e:
            log(f"  WARNING: Could not delete original: {e}")

    log(f"  Done: {file_counter} files created.")
    return True


def find_epubs(root_folder: str) -> list:
    """Recursively find all .epub files in a folder."""
    epubs = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        for f in sorted(filenames):
            if f.lower().endswith(".epub"):
                epubs.append(os.path.join(dirpath, f))
    return epubs


def convert_batch(
    root_folder: str,
    ocr_enabled: bool = True,
    delete_original: bool = False,
    on_progress: Optional[Callable] = None,
    on_book_start: Optional[Callable] = None,
    on_book_done: Optional[Callable] = None,
    cancel_check: Optional[Callable] = None,
) -> dict:
    """Convert all EPUB files found in a folder tree.

    Args:
        root_folder: Root directory to search for .epub files.
        ocr_enabled: Whether to attempt OCR for image-based titles.
        delete_original: Whether to delete originals after conversion.
        on_progress: Callback(message: str) for log messages.
        on_book_start: Callback(book_path: str, index: int, total: int).
        on_book_done: Callback(book_path: str, success: bool).
        cancel_check: Callable returning True if batch should stop.

    Returns:
        Dict with keys: "total", "succeeded", "failed", "cancelled".
    """
    epubs = find_epubs(root_folder)
    total = len(epubs)
    succeeded = 0
    failed = 0

    if on_progress:
        on_progress(f"Found {total} EPUB file(s) in {root_folder}")

    for i, epub_path in enumerate(epubs):
        if cancel_check and cancel_check():
            if on_progress:
                on_progress("Batch cancelled.")
            return {"total": total, "succeeded": succeeded, "failed": failed, "cancelled": True}

        if on_book_start:
            on_book_start(epub_path, i, total)

        try:
            ok = convert_single_epub(
                epub_path,
                ocr_enabled=ocr_enabled,
                delete_original=delete_original,
                on_progress=on_progress,
                cancel_check=cancel_check,
            )
            if ok:
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            if on_progress:
                on_progress(f"ERROR: {Path(epub_path).name}: {e}")
            failed += 1

        if on_book_done:
            on_book_done(epub_path, ok if "ok" in dir() else False)

    if on_progress:
        on_progress(f"Batch complete: {succeeded}/{total} succeeded, {failed} failed.")

    return {"total": total, "succeeded": succeeded, "failed": failed, "cancelled": False}
