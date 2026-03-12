"""tkinter GUI for the EPUB to DOCX Batch Converter."""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from epub2docx.converter import convert_batch, find_epubs
from epub2docx.progress import (
    ProgressReporter, LogMessage, BookStarted, BookDone, BatchDone,
)
from epub2docx.title_resolver import is_ocr_available


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("EPUB to DOCX Converter")
        self.root.geometry("700x550")
        self.root.minsize(600, 450)

        self._cancel_event = threading.Event()
        self._worker_thread = None
        self._progress = ProgressReporter()
        self._running = False

        self._build_ui()
        self._poll_progress()

    def _build_ui(self):
        # --- Folder selection ---
        folder_frame = ttk.LabelFrame(self.root, text="Source Folder", padding=8)
        folder_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        self.folder_var = tk.StringVar()
        folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_var)
        folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        browse_btn = ttk.Button(folder_frame, text="Browse...", command=self._browse)
        browse_btn.pack(side=tk.RIGHT)

        # --- Options ---
        opts_frame = ttk.LabelFrame(self.root, text="Options", padding=8)
        opts_frame.pack(fill=tk.X, padx=10, pady=5)

        self.ocr_var = tk.BooleanVar(value=True)
        ocr_cb = ttk.Checkbutton(
            opts_frame, text="Attempt OCR for image-based chapter titles",
            variable=self.ocr_var,
        )
        ocr_cb.pack(anchor=tk.W)
        if not is_ocr_available():
            ocr_cb.configure(state=tk.DISABLED)
            self.ocr_var.set(False)
            ocr_note = ttk.Label(
                opts_frame,
                text="(Tesseract not found - install tesseract-ocr for OCR support)",
                foreground="gray",
            )
            ocr_note.pack(anchor=tk.W, padx=(20, 0))

        self.delete_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts_frame, text="Delete original EPUB files after conversion",
            variable=self.delete_var,
        ).pack(anchor=tk.W)

        # --- Action buttons ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self.start_btn = ttk.Button(
            btn_frame, text="Start Conversion", command=self._start
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.cancel_btn = ttk.Button(
            btn_frame, text="Cancel", command=self._cancel, state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT)

        # --- Progress ---
        progress_frame = ttk.LabelFrame(self.root, text="Progress", padding=8)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        self.current_label = ttk.Label(progress_frame, text="Ready")
        self.current_label.pack(anchor=tk.W)

        self.book_progress = ttk.Progressbar(
            progress_frame, mode="determinate", length=300
        )
        self.book_progress.pack(fill=tk.X, pady=(2, 0))

        self.overall_label = ttk.Label(progress_frame, text="")
        self.overall_label.pack(anchor=tk.W, pady=(5, 0))

        self.overall_progress = ttk.Progressbar(
            progress_frame, mode="determinate", length=300
        )
        self.overall_progress.pack(fill=tk.X, pady=(2, 0))

        # --- Log output ---
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        self.log_text = tk.Text(
            log_frame, height=10, wrap=tk.WORD, font=("Courier", 9),
            state=tk.DISABLED,
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _browse(self):
        folder = filedialog.askdirectory(title="Select folder containing EPUB files")
        if folder:
            self.folder_var.set(folder)
            # Quick scan to show count
            epubs = find_epubs(folder)
            self._log(f"Found {len(epubs)} EPUB file(s) in {folder}")

    def _start(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Please select a valid folder.")
            return

        epubs = find_epubs(folder)
        if not epubs:
            messagebox.showinfo("No EPUBs", "No .epub files found in the selected folder.")
            return

        # Confirm deletion if enabled
        if self.delete_var.get():
            ok = messagebox.askyesno(
                "Confirm",
                f"This will convert {len(epubs)} EPUB(s) and DELETE the originals.\n"
                "Are you sure?",
            )
            if not ok:
                return

        self._running = True
        self._cancel_event.clear()
        self.start_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.book_progress["value"] = 0
        self.overall_progress["value"] = 0
        self.overall_progress["maximum"] = len(epubs)

        self._worker_thread = threading.Thread(
            target=self._run_conversion,
            args=(folder,),
            daemon=True,
        )
        self._worker_thread.start()

    def _cancel(self):
        self._cancel_event.set()
        self._log("Cancelling... (will stop after current book)")

    def _run_conversion(self, folder: str):
        """Runs in a background thread."""
        progress = self._progress

        def on_progress(msg):
            progress.log(msg)

        def on_book_start(path, index, total):
            progress.book_started(Path(path).stem, index, total)

        def on_book_done(path, success):
            progress.book_done(Path(path).stem, success)

        result = convert_batch(
            root_folder=folder,
            ocr_enabled=self.ocr_var.get(),
            delete_original=self.delete_var.get(),
            on_progress=on_progress,
            on_book_start=on_book_start,
            on_book_done=on_book_done,
            cancel_check=lambda: self._cancel_event.is_set(),
        )

        progress.batch_done(
            total=result["total"],
            succeeded=result["succeeded"],
            failed=result["failed"],
            cancelled=result.get("cancelled", False),
        )

    def _poll_progress(self):
        """Poll the progress queue from the main thread."""
        for msg in self._progress.get_messages():
            if isinstance(msg, LogMessage):
                prefix = {"info": "[INFO]", "warn": "[WARN]", "error": "[ERR]"}.get(
                    msg.level, "[INFO]"
                )
                self._log(f"{prefix} {msg.text}")

            elif isinstance(msg, BookStarted):
                self.current_label.configure(
                    text=f"{msg.book_name}  ({msg.book_index + 1} of {msg.total_books})"
                )
                self.book_progress["value"] = 0
                self.book_progress["maximum"] = 100
                self.overall_label.configure(
                    text=f"Overall: {msg.book_index} / {msg.total_books}"
                )

            elif isinstance(msg, BookDone):
                self.book_progress["value"] = 100
                val = self.overall_progress["value"]
                self.overall_progress["value"] = val + 1

            elif isinstance(msg, BatchDone):
                self._running = False
                self.start_btn.configure(state=tk.NORMAL)
                self.cancel_btn.configure(state=tk.DISABLED)
                self.current_label.configure(text="Done")
                status = f"Complete: {msg.succeeded}/{msg.total} succeeded"
                if msg.failed:
                    status += f", {msg.failed} failed"
                if msg.cancelled:
                    status += " (cancelled)"
                self.overall_label.configure(text=status)
                self._log(status)

        # Poll again in 100ms
        self.root.after(100, self._poll_progress)

    def _log(self, text: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
