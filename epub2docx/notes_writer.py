"""Accumulates conversion notes per book and writes CONVERSION NOTES.txt."""

from datetime import date
from typing import List, Optional


class NotesWriter:
    """Collects notes during conversion and writes them to a text file."""

    def __init__(self, book_title: str, author: str = ""):
        self.book_title = book_title
        self.author = author
        self.issues: List[str] = []
        self.file_list: List[str] = []
        self.skipped: List[str] = []

    def add_issue(self, message: str):
        self.issues.append(message)

    def add_file(self, filename: str):
        self.file_list.append(filename)

    def add_skipped(self, description: str):
        self.skipped.append(description)

    def write(self, output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("EPUB to DOCX Conversion Notes\n")
            f.write(f"Source: {self.book_title}\n")
            if self.author:
                f.write(f"Author: {self.author}\n")
            f.write(f"Date of conversion: {date.today().isoformat()}\n")
            f.write("=" * 70 + "\n\n")

            if self.file_list:
                f.write("FILES CREATED\n")
                f.write("-" * 40 + "\n")
                for fname in self.file_list:
                    f.write(f"  {fname}\n")
                f.write("\n")

            if self.skipped:
                f.write("SKIPPED SECTIONS\n")
                f.write("-" * 40 + "\n")
                for desc in self.skipped:
                    f.write(f"  {desc}\n")
                f.write("\n")

            if self.issues:
                f.write("\nISSUES AND DECISIONS\n")
                f.write("-" * 40 + "\n\n")
                for i, issue in enumerate(self.issues, 1):
                    f.write(f"{i}. {issue}\n\n")
