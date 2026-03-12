"""
       /)  /)
      ( ^.^ )    Bunny Book Breaker
      (")_(")    EPUB to DOCX Converter

A cute and adorable batch EPUB converter with a bunny theme!
"""

import os
import sys
import random
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QFileDialog,
    QProgressBar,
    QLineEdit,
)

from epub2docx.converter import convert_batch, find_epubs
from epub2docx.title_resolver import is_ocr_available


# ── Bunny Theme Colors ───────────────────────────────────────────────

COLORS = {
    "bg": "#FFF5F5",
    "frame_bg": "#FFE4E6",
    "button": "#F9A8D4",
    "button_hover": "#F472B6",
    "button_pressed": "#EC4899",
    "accent": "#FDA4AF",
    "text": "#831843",
    "text_light": "#BE185D",
    "white": "#FFFFFF",
    "success": "#86EFAC",
    "success_text": "#065F46",
    "error": "#FCA5A5",
    "error_text": "#991B1B",
}

# ── Bunny Image Paths ────────────────────────────────────────────────

PICS_DIR = Path(__file__).parent.parent / "pics"

BUNNY_IMAGES = {
    "idle": PICS_DIR / "basebun.png",
    "working": PICS_DIR / "workbub.png",
    "happy": PICS_DIR / "winbun.png",
    "chomp": PICS_DIR / "chompbun.png",
    "error": PICS_DIR / "madbun.png",
    "shock": PICS_DIR / "shockbun.png",
    "sleepy": PICS_DIR / "sleepbun.png",
    "yawn": PICS_DIR / "yawnbun.png",
}

BUNNY_IMG_HEIGHT = 150

IDLE_MESSAGES = [
    "Hop hop! Ready to break some books!",
    "Welcome to my cozy book-breaking burrow!",
    "*wiggles nose* Got EPUBs? I'll munch 'em into chapters!",
    "Your friendly neighborhood book-breaking bunny!",
    "Ready to nibble through your library!",
]

WORKING_MESSAGES = [
    "*nibble nibble* Chewing through pages...",
    "*munch munch* Breaking chapters apart...",
    "Hopping through the pages!",
    "*busy bunny noises* Almost there...",
    "Nom nom nom... tasty chapters!",
]

SUCCESS_MESSAGES = [
    "Yay! All done! *happy bunny dance*",
    "Your books are ready! *wiggles tail*",
    "Conversion complete! Time for a carrot break!",
    "*happy nose wiggles* All books broken!",
    "Hop-pily converted!",
]

ERROR_MESSAGES = [
    "*sad bunny noises*",
    "Oh no! Something went wrong...",
    "*flops ears* That didn't work...",
]


# ── Converter Signals ────────────────────────────────────────────────

class ConverterSignals(QObject):
    log_message = pyqtSignal(str, str)  # text, level
    book_started = pyqtSignal(str, int, int)  # name, index, total
    book_done = pyqtSignal(str, bool)  # name, success
    batch_done = pyqtSignal(int, int, int, bool)  # total, succeeded, failed, cancelled


# ── Main Window ──────────────────────────────────────────────────────

class BunnyBookBreakerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bunny Book Breaker")
        self.resize(600, 750)
        self.setMinimumSize(500, 650)

        self._signals = ConverterSignals()
        self._signals.log_message.connect(self._on_log)
        self._signals.book_started.connect(self._on_book_started)
        self._signals.book_done.connect(self._on_book_done)
        self._signals.batch_done.connect(self._on_batch_done)

        self._cancel_event = threading.Event()
        self._worker_thread = None
        self._running = False
        self._total_books = 0

        self._build_ui()
        self._apply_theme()
        self._set_idle()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 15, 20, 15)

        # ── Bunny Header ──
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        self._bunny_label = QLabel()
        self._bunny_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bunny_label.setFixedHeight(BUNNY_IMG_HEIGHT + 10)
        header_layout.addWidget(self._bunny_label)

        title = QLabel("Bunny Book Breaker")
        title.setFont(QFont("Georgia", 22, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)

        subtitle = QLabel("EPUB to DOCX Chapter Converter")
        subtitle.setFont(QFont("Georgia", 11))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setProperty("class", "subtitle")
        header_layout.addWidget(subtitle)

        self._message_label = QLabel("")
        self._message_label.setFont(QFont("Georgia", 10))
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setProperty("class", "cute-message")
        self._message_label.setWordWrap(True)
        header_layout.addWidget(self._message_label)

        layout.addWidget(header)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(2)
        layout.addWidget(sep)

        # ── Folder Selection ──
        folder_frame = QWidget()
        folder_frame.setProperty("class", "section-frame")
        folder_layout = QVBoxLayout(folder_frame)
        folder_layout.setContentsMargins(12, 10, 12, 10)
        folder_layout.setSpacing(6)

        folder_title = QLabel("Book Folder")
        folder_title.setFont(QFont("Georgia", 11, QFont.Weight.Bold))
        folder_layout.addWidget(folder_title)

        folder_row = QHBoxLayout()
        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText("Choose a folder full of EPUBs...")
        self._folder_input.setFont(QFont("Georgia", 10))
        self._folder_input.setReadOnly(True)
        folder_row.addWidget(self._folder_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.setProperty("class", "accent-btn")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse)
        folder_row.addWidget(browse_btn)

        folder_layout.addLayout(folder_row)
        layout.addWidget(folder_frame)

        # ── Options ──
        opts_frame = QWidget()
        opts_frame.setProperty("class", "section-frame")
        opts_layout = QVBoxLayout(opts_frame)
        opts_layout.setContentsMargins(12, 10, 12, 10)
        opts_layout.setSpacing(6)

        opts_title = QLabel("Options")
        opts_title.setFont(QFont("Georgia", 11, QFont.Weight.Bold))
        opts_layout.addWidget(opts_title)

        self._ocr_cb = QCheckBox("Attempt OCR for image-based chapter titles")
        self._ocr_cb.setFont(QFont("Georgia", 10))
        self._ocr_cb.setChecked(True)
        opts_layout.addWidget(self._ocr_cb)

        if not is_ocr_available():
            self._ocr_cb.setChecked(False)
            self._ocr_cb.setEnabled(False)
            ocr_note = QLabel("  (Install tesseract-ocr for OCR support)")
            ocr_note.setFont(QFont("Georgia", 9))
            ocr_note.setProperty("class", "subtitle")
            opts_layout.addWidget(ocr_note)

        self._delete_cb = QCheckBox("Delete original EPUBs after conversion")
        self._delete_cb.setFont(QFont("Georgia", 10))
        opts_layout.addWidget(self._delete_cb)

        layout.addWidget(opts_frame)

        # ── Start Button ──
        self._start_btn = QPushButton("Start Converting!")
        self._start_btn.setFont(QFont("Georgia", 16, QFont.Weight.Bold))
        self._start_btn.setMinimumHeight(65)
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.setProperty("class", "start-btn")
        self._start_btn.clicked.connect(self._start)
        layout.addWidget(self._start_btn)

        # ── Progress ──
        progress_frame = QWidget()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(4)

        self._progress_label = QLabel("")
        self._progress_label.setFont(QFont("Georgia", 10))
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setProperty("class", "status")
        progress_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(22)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)

        layout.addWidget(progress_frame)

        # ── Log Output ──
        log_header = QHBoxLayout()
        log_title = QLabel("Conversion Log")
        log_title.setFont(QFont("Georgia", 11, QFont.Weight.Bold))
        log_header.addWidget(log_title)

        log_header.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("class", "small-btn")
        clear_btn.clicked.connect(lambda: self._log_view.clear())
        log_header.addWidget(clear_btn)

        layout.addLayout(log_header)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 9))
        self._log_view.setPlaceholderText(
            "*sniff sniff* No conversions yet...\n"
            "Pick a folder and let me at those books!"
        )
        layout.addWidget(self._log_view, 1)

        # ── Footer ──
        footer = QLabel("Made with love and carrots")
        footer.setFont(QFont("Georgia", 8))
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setProperty("class", "footer")
        layout.addWidget(footer)

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {COLORS['bg']};
                color: {COLORS['text']};
            }}
            QLabel {{
                color: {COLORS['text']};
                background: transparent;
            }}
            QLabel[class="subtitle"] {{
                color: {COLORS['text_light']};
                font-style: italic;
            }}
            QLabel[class="cute-message"] {{
                color: {COLORS['accent']};
            }}
            QLabel[class="footer"] {{
                color: {COLORS['accent']};
                font-style: italic;
            }}
            QLabel[class="status"] {{
                color: {COLORS['text_light']};
                padding: 4px;
            }}

            QWidget[class="section-frame"] {{
                background-color: {COLORS['frame_bg']};
                border-radius: 8px;
            }}

            QFrame {{
                background-color: {COLORS['accent']};
                border: none;
            }}

            QLineEdit {{
                background-color: {COLORS['white']};
                color: {COLORS['text']};
                border: 2px solid {COLORS['accent']};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 10pt;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['button_hover']};
            }}

            QPushButton {{
                background-color: {COLORS['button']};
                color: {COLORS['text']};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-family: Georgia;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {COLORS['button_hover']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['button_pressed']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['frame_bg']};
                color: {COLORS['accent']};
            }}

            QPushButton[class="accent-btn"] {{
                background-color: {COLORS['button']};
                font-weight: bold;
            }}

            QPushButton[class="small-btn"] {{
                background-color: {COLORS['white']};
                border: 1px solid {COLORS['accent']};
                padding: 4px 10px;
                font-size: 9pt;
            }}
            QPushButton[class="small-btn"]:hover {{
                background-color: {COLORS['frame_bg']};
            }}

            QPushButton[class="start-btn"] {{
                background-color: {COLORS['button']};
                border: 3px solid {COLORS['button_hover']};
                border-radius: 12px;
                font-size: 16pt;
            }}
            QPushButton[class="start-btn"]:hover {{
                background-color: {COLORS['button_hover']};
                color: white;
            }}
            QPushButton[class="start-btn"]:pressed {{
                background-color: {COLORS['button_pressed']};
            }}

            QTextEdit {{
                background-color: {COLORS['white']};
                color: {COLORS['text']};
                border: 2px solid {COLORS['accent']};
                border-radius: 8px;
                padding: 8px;
                font-size: 9pt;
            }}

            QCheckBox {{
                color: {COLORS['text']};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {COLORS['accent']};
                border-radius: 4px;
                background-color: {COLORS['white']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLORS['button']};
                border-color: {COLORS['button_hover']};
            }}
            QCheckBox::indicator:disabled {{
                background-color: {COLORS['frame_bg']};
            }}

            QProgressBar {{
                border: 2px solid {COLORS['accent']};
                border-radius: 8px;
                background-color: {COLORS['white']};
                text-align: center;
                font-family: Georgia;
                font-size: 9pt;
                color: {COLORS['text']};
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['button']};
                border-radius: 6px;
            }}
        """)

    # ── Bunny Image ────────────────────────────────────────────────────

    def _set_bunny_image(self, state: str):
        path = BUNNY_IMAGES.get(state, BUNNY_IMAGES["idle"])
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(
                BUNNY_IMG_HEIGHT, Qt.TransformationMode.SmoothTransformation
            )
            self._bunny_label.setPixmap(scaled)
        else:
            self._bunny_label.setText(f"[{state}]")

    def _set_idle(self):
        self._set_bunny_image("idle")
        self._message_label.setText(random.choice(IDLE_MESSAGES))
        self._progress_label.setText("")

    # ── Folder Browse ─────────────────────────────────────────────────

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder containing EPUB files"
        )
        if folder:
            self._folder_input.setText(folder)
            epubs = find_epubs(folder)
            count = len(epubs)
            if count:
                self._message_label.setText(
                    f"*sniff sniff* Found {count} book{'s' if count != 1 else ''}!"
                )
                self._set_bunny_image("shock" if count > 10 else "idle")
            else:
                self._message_label.setText("No EPUBs found in that burrow...")
                self._set_bunny_image("yawn")

    # ── Start / Cancel ────────────────────────────────────────────────

    def _start(self):
        if self._running:
            self._cancel_event.set()
            self._start_btn.setText("Cancelling...")
            self._start_btn.setEnabled(False)
            self._message_label.setText("*flattens ears* Stopping after this book...")
            return

        folder = self._folder_input.text().strip()
        if not folder or not os.path.isdir(folder):
            self._set_bunny_image("error")
            self._message_label.setText(random.choice(ERROR_MESSAGES))
            self._progress_label.setText("Please select a valid folder first!")
            self._progress_label.setStyleSheet(f"color: {COLORS['error_text']};")
            QTimer.singleShot(3000, self._set_idle)
            return

        epubs = find_epubs(folder)
        if not epubs:
            self._set_bunny_image("yawn")
            self._message_label.setText("No EPUBs in there... *yawns*")
            return

        if self._delete_cb.isChecked():
            ok = QMessageBox.question(
                self, "Confirm",
                f"This will convert {len(epubs)} EPUB(s) and DELETE the originals.\n"
                "Are you sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ok != QMessageBox.StandardButton.Yes:
                return

        self._running = True
        self._cancel_event.clear()
        self._total_books = len(epubs)
        self._start_btn.setText("Cancel")
        self._progress_bar.setMaximum(self._total_books)
        self._progress_bar.setValue(0)
        self._set_bunny_image("chomp")
        self._message_label.setText(random.choice(WORKING_MESSAGES))

        self._worker_thread = threading.Thread(
            target=self._run_conversion,
            args=(folder,),
            daemon=True,
        )
        self._worker_thread.start()

    def _run_conversion(self, folder: str):
        signals = self._signals

        def on_progress(msg):
            signals.log_message.emit(msg, "info")

        def on_book_start(path, index, total):
            signals.book_started.emit(Path(path).stem, index, total)

        def on_book_done(path, success):
            signals.book_done.emit(Path(path).stem, success)

        result = convert_batch(
            root_folder=folder,
            ocr_enabled=self._ocr_cb.isChecked(),
            delete_original=self._delete_cb.isChecked(),
            on_progress=on_progress,
            on_book_start=on_book_start,
            on_book_done=on_book_done,
            cancel_check=lambda: self._cancel_event.is_set(),
        )

        signals.batch_done.emit(
            result["total"],
            result["succeeded"],
            result["failed"],
            result.get("cancelled", False),
        )

    # ── Signal Handlers ───────────────────────────────────────────────

    def _on_log(self, text: str, level: str):
        color_map = {
            "info": COLORS["text"],
            "warn": COLORS["text_light"],
            "error": COLORS["error_text"],
        }
        color = color_map.get(level, COLORS["text"])
        self._log_view.append(f'<span style="color:{color}">{text}</span>')
        scrollbar = self._log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_book_started(self, name: str, index: int, total: int):
        self._progress_label.setText(f"{name}  ({index + 1} of {total})")
        self._progress_label.setStyleSheet(f"color: {COLORS['text_light']};")
        states = ["chomp", "working", "chomp", "working"]
        self._set_bunny_image(states[index % len(states)])
        self._message_label.setText(random.choice(WORKING_MESSAGES))

    def _on_book_done(self, name: str, success: bool):
        val = self._progress_bar.value()
        self._progress_bar.setValue(val + 1)

    def _on_batch_done(self, total: int, succeeded: int, failed: int, cancelled: bool):
        self._running = False
        self._start_btn.setText("Start Converting!")
        self._start_btn.setEnabled(True)

        if cancelled:
            self._set_bunny_image("yawn")
            self._message_label.setText("*yawns* Stopped early. Maybe next time!")
        elif failed == 0:
            self._set_bunny_image("happy")
            self._message_label.setText(random.choice(SUCCESS_MESSAGES))
        else:
            self._set_bunny_image("shock")
            self._message_label.setText(
                f"Done, but {failed} book{'s' if failed != 1 else ''} had issues!"
            )

        status = f"Complete: {succeeded}/{total} succeeded"
        if failed:
            status += f", {failed} failed"
        if cancelled:
            status += " (cancelled)"
        self._progress_label.setText(status)
        self._progress_label.setStyleSheet(f"color: {COLORS['success_text']};")

        QTimer.singleShot(8000, self._set_idle)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Bunny Book Breaker")
    app.setStyle("Fusion")

    window = BunnyBookBreakerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
