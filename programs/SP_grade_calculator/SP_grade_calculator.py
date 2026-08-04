from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from SP_footer_picture import add_footer
from SP_window_utils import center_window

# --- Constants ---
# A common default grading scale (used as a placeholder/example, and as a
# fallback if the user leaves the grade scale field empty).
DEFAULT_GRADE_SCALE = (
    "1.0=95-100\n"
    "1.3=90-94.9\n"
    "1.7=85-89.9\n"
    "2.0=80-84.9\n"
    "2.3=75-79.9\n"
    "2.7=70-74.9\n"
    "3.0=65-69.9\n"
    "3.3=60-64.9\n"
    "3.7=55-59.9\n"
    "4.0=50-54.9\n"
    "5.0=0-49.9"
)

PARTICIPANTS_PLACEHOLDER = "e.g.\n87.5\n62\n45"

DEFAULT_FAIL_THRESHOLD = "5.0"
UNMATCHED_LABEL = "X"

# --- Pure logic: parsing, evaluation and statistics ---
class InputError(Exception):
    """Raised when the grade scale or participant input can't be parsed."""


def parse_number(raw: str) -> float:
    """Parse a number, accepting both '.' and ',' as decimal separators."""
    return float(raw.strip().replace(",", "."))


def format_grade(value: float) -> str:
    """Render a numeric grade with one consistent decimal place, e.g. 1.0 -> '1.0'."""
    return f"{value:.1f}"


def parse_grade_scale(text: str) -> list[tuple[float, float, float]]:
    """
    Parse lines of the form 'grade=min-max' into a list of
    (grade, min, max) tuples, sorted from best to worst grade.

    Raises InputError with a line-specific message on malformed input,
    instead of the previous behaviour of silently failing on any error.
    """
    scale: list[tuple[float, float, float]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            # maxsplit=1 avoids crashing on a stray extra '=' or '-'
            grade_part, range_part = line.split("=", 1)
            min_part, max_part = range_part.split("-", 1)
            grade = parse_number(grade_part)
            low = parse_number(min_part)
            high = parse_number(max_part)
        except ValueError as exc:
            raise InputError(
                f"Grade scale line {line_no} ('{line.strip()}') is invalid. "
                "Expected the format 'grade=min-max', e.g. '1.0=95-100'."
            ) from exc
        if low > high:
            raise InputError(
                f"Grade scale line {line_no}: the minimum ({low}) is greater "
                f"than the maximum ({high})."
            )
        scale.append((grade, low, high))

    if not scale:
        raise InputError("The grade scale is empty.")

    scale.sort(key=lambda item: item[0])
    return scale


def parse_participants(text: str) -> list[float]:
    """Parse one score per line into a list of floats."""
    scores: list[float] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            scores.append(parse_number(line))
        except ValueError as exc:
            raise InputError(
                f"Participant score line {line_no} ('{line.strip()}') is not a valid number."
            ) from exc

    if not scores:
        raise InputError("No participant scores were entered.")
    return scores


def evaluate_scores(
    scores: list[float], scale: list[tuple[float, float, float]]
) -> list[tuple[float, str]]:
    """
    Map each score to the grade label of the range it falls into.
    UNMATCHED_LABEL is used only if no range in the scale covers the score at
    all (a gap in the scale) — whether a matched grade counts as Pass or Fail
    is decided later, by comparing it against the fail threshold.
    Returns a list of (score, label) sorted by score, best first.
    """
    results: list[tuple[float, str]] = []
    for score in scores:
        label = UNMATCHED_LABEL
        for grade, low, high in scale:
            if low <= score <= high:
                label = format_grade(grade)
                break
        results.append((score, label))

    results.sort(key=lambda item: item[0], reverse=True)
    return results

def grade_status(label: str, fail_threshold: float) -> str:
    """
    Classify a matched grade label as 'Passed', 'Failed', or 'Unmatched'.
    A grade counts as Failed once its numeric value is >= fail_threshold —
    e.g. a scale entry like '5.0=0-49.9' with threshold 5.0 marks every
    participant in that tier as Failed.
    """
    if label == UNMATCHED_LABEL:
        return "Unmatched"
    return "Failed" if float(label) >= fail_threshold else "Passed"

@dataclass
class Statistics:
    """Aggregate numbers derived from a list of evaluated results."""

    total: int
    passed: int
    failed: int
    unmatched: int
    average_all: float
    average_passed: float
    distribution_grades: Counter


def compute_statistics(results: list[tuple[float, str]], fail_threshold: float) -> Statistics:
    total = len(results)
    passed_values: list[float] = []
    all_values: list[float] = []
    distribution_grades: Counter = Counter()
    unmatched = 0

    for _, label in results:
        distribution_grades[label] += 1
        status = grade_status(label, fail_threshold)
        if status == "Unmatched":
            unmatched += 1
            continue
        value = float(label)
        all_values.append(value)
        if status == "Passed":
            passed_values.append(value)

    passed = len(passed_values)
    failed = total - passed - unmatched
    average_all = sum(all_values) / len(all_values) if all_values else 0.0
    average_passed = sum(passed_values) / passed if passed else 0.0

    return Statistics(
        total=total,
        passed=passed,
        failed=failed,
        unmatched=unmatched,
        average_all=average_all,
        average_passed=average_passed,
        distribution_grades=distribution_grades,
    )

# --- Session data (used for save / load) ---
@dataclass
class Session:
    """Everything needed to reproduce one tab's input."""

    name: str
    grade_scale_text: str
    participants_text: str
    fail_threshold_text: str = DEFAULT_FAIL_THRESHOLD
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    file_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "grade_scale_text": self.grade_scale_text,
            "participants_text": self.participants_text,
            "fail_threshold_text": self.fail_threshold_text,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict, file_path: str | None = None) -> "Session":
        fail_threshold_text = data.get(
            "fail_threshold_text", data.get("fail_value_text", DEFAULT_FAIL_THRESHOLD)
        )
        return Session(
            name=data.get("name", "Untitled"),
            grade_scale_text=data.get("grade_scale_text", ""),
            participants_text=data.get("participants_text", ""),
            fail_threshold_text=fail_threshold_text,
            created_at=data.get("created_at", datetime.now().isoformat(timespec="seconds")),
            file_path=file_path,
        )


# --- UI building block: a Text widget with a real, disappearing placeholder ---
class PlaceholderText(tk.Text):
    """
    A tk.Text widget that shows gray placeholder/preview text while empty
    and unfocused. The placeholder disappears the moment the user clicks in
    and starts typing, and reappears if the field is left empty again.

    get_value() / set_value() should be used instead of get()/insert() so
    that placeholder text is never mistaken for real user input.
    """

    def __init__(
        self,
        master: tk.Widget,
        placeholder: str,
        placeholder_color: str = "#999999",
        **kwargs,
    ):
        self._normal_color = kwargs.pop("fg", "black")
        super().__init__(master, fg=placeholder_color, **kwargs)
        self._placeholder = placeholder
        self._placeholder_color = placeholder_color
        self._showing_placeholder = False

        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self.delete("1.0", "end")
        self.insert("1.0", self._placeholder)
        self.config(fg=self._placeholder_color)
        self._showing_placeholder = True

    def _on_focus_in(self, _event: object) -> None:
        if self._showing_placeholder:
            self.delete("1.0", "end")
            self.config(fg=self._normal_color)
            self._showing_placeholder = False

    def _on_focus_out(self, _event: object) -> None:
        if not self.get("1.0", "end-1c").strip():
            self._show_placeholder()

    def get_value(self) -> str:
        """Return '' while the placeholder is showing, otherwise the real text."""
        if self._showing_placeholder:
            return ""
        return self.get("1.0", "end-1c")

    def set_value(self, text: str) -> None:
        """Set real content, or show the placeholder again if text is empty."""
        self.delete("1.0", "end")
        if text:
            self.insert("1.0", text)
            self.config(fg=self._normal_color)
            self._showing_placeholder = False
        else:
            self._show_placeholder()


# --- UI building block: a simple bar chart drawn on a Canvas ---
def draw_bar_chart(
    canvas: tk.Canvas,
    data: Counter,
    *,
    width: int,
    height: int,
    fail_threshold: float | None = None,
) -> None:
    canvas.delete("all")
    width = max(width, 100)
    height = max(height, 80)
    canvas.config(width=width, height=height)

    if not data:
        canvas.create_text(width / 2, height / 2, text="No data yet", fill="#999999")
        return

    def sort_key(item: tuple[str, int]) -> tuple[int, float]:
        label = item[0]
        return (1, 0.0) if label == UNMATCHED_LABEL else (0, float(label))

    def bar_color(label: str) -> str:
        if label == UNMATCHED_LABEL:
            return "#69baf0"
        if fail_threshold is not None and float(label) >= fail_threshold:
            return "#C55E5E"
        return "#3A8B63"

    items = sorted(data.items(), key=sort_key)
    max_count = max(count for _, count in items) or 1

    margin_bottom = 32
    margin_top = 18
    usable_height = max(height - margin_bottom - margin_top, 10)

    n = len(items)
    available_width = width - 20
    bar_width = max(18, available_width // n - 10)
    gap = max(4, (available_width - bar_width * n) / n)

    x = 10
    for label, count in items:
        bar_height = (count / max_count) * usable_height
        y1 = height - margin_bottom
        y0 = y1 - bar_height
        canvas.create_rectangle(x, y0, x + bar_width, y1, fill=bar_color(label), outline="")
        canvas.create_text(x + bar_width / 2, y1 + 12, text=label, font=("Arial", 9))
        canvas.create_text(
            x + bar_width / 2, y0 - 10, text=str(count), font=("Arial", 9, "bold")
        )
        x += bar_width + gap


def compute_point_buckets(
    scores: list[float], num_buckets: int = 8
) -> tuple[list[tuple[str, int]], float]:
    """
    Bucket raw point scores into `num_buckets` equal-width ranges for a
    histogram. Returns the ordered [(label, count), ...] list plus the
    arithmetic mean of the scores.
    """
    if not scores:
        return [], 0.0

    mean = sum(scores) / len(scores)
    lowest = min(scores)
    highest = max(scores)

    if lowest == highest:
        return [(f"{lowest:g}", len(scores))], mean

    width = (highest - lowest) / num_buckets
    counts = [0] * num_buckets
    for score in scores:
        index = int((score - lowest) / width)
        if index >= num_buckets:  # the highest score lands exactly on the top edge
            index = num_buckets - 1
        counts[index] += 1

    buckets = []
    for i in range(num_buckets):
        low = lowest + i * width
        high = low + width
        buckets.append((f"{low:.0f}-{high:.0f}", counts[i]))
    return buckets, mean


def draw_points_histogram(
    canvas: tk.Canvas, scores: list[float], *, width: int, height: int, num_buckets: int = 8
) -> None:
    """
    Draw a histogram of raw participant scores (not grades), with a dashed
    marker line at the mean so the average is visible directly on the shape
    of the distribution.
    """
    canvas.delete("all")
    width = max(width, 100)
    height = max(height, 80)
    canvas.config(width=width, height=height)

    if not scores:
        canvas.create_text(width / 2, height / 2, text="No data yet", fill="#999999")
        return

    buckets, mean = compute_point_buckets(scores, num_buckets)
    max_count = max(count for _, count in buckets) or 1

    margin_bottom = 32
    margin_top = 40  # extra room for the mean label above the bars
    usable_height = max(height - margin_bottom - margin_top, 10)

    n = len(buckets)
    available_width = width - 20
    bar_width = max(14, available_width // n - 6)
    gap = max(2, (available_width - bar_width * n) / n)

    x = 10
    for label, count in buckets:
        bar_height = (count / max_count) * usable_height
        y1 = height - margin_bottom
        y0 = y1 - bar_height
        canvas.create_rectangle(x, y0, x + bar_width, y1, fill="#2f6690", outline="")
        if count:
            canvas.create_text(
                x + bar_width / 2, y0 - 10, text=str(count), font=("Arial", 8, "bold")
            )
        canvas.create_text(x + bar_width / 2, y1 + 12, text=label, font=("Arial", 7))
        x += bar_width + gap

    lowest = min(scores)
    highest = max(scores)
    if highest == lowest:
        mean_x = 10 + available_width / 2
    else:
        mean_x = 10 + ((mean - lowest) / (highest - lowest)) * available_width
    canvas.create_line(
        mean_x, margin_top - 15, mean_x, height - margin_bottom,
        fill="#A56D6D", dash=(4, 2), width=2,
    )
    canvas.create_text(
        mean_x, margin_top - 25, text=f"Mean: {mean:.1f}", fill="#C55E5E", font=("Arial", 8, "bold")
    )


def draw_sort_legend(canvas: tk.Canvas, width: int, height: int) -> None:
    """
    Draw a small vertical arrow with a rotated label to the left of the
    results table, indicating that rows are sorted from the highest score
    (top) to the lowest score (bottom).
    """
    canvas.delete("all")
    width = max(width, 32)
    height = max(height, 60)
    canvas.config(width=width, height=height)

    line_x = 14
    top, bottom = 14, height - 14
    canvas.create_line(
        line_x, top, line_x, bottom, width=2, fill="#666666", arrow="last", arrowshape=(8, 10, 4)
    )
    canvas.create_text(
        width - 12,
        height / 2,
        text="Highest to lowest score",
        angle=90,
        fill="#666666",
        font=("Arial", 8, "bold"),
    )


# --- One evaluation workspace (one tab) ---
class SessionTab(ttk.Frame):
    """A single workspace: inputs on top, structured results below."""

    def __init__(self, master: tk.Widget, app: "GradeCalculatorApp", session: Session):
        super().__init__(master, padding=10)
        self.app = app
        self.session = session
        self.file_path: str | None = session.file_path
        self._last_distribution_grades: Counter | None = None
        self._last_scores: list[float] | None = None
        self._last_fail_threshold: float | None = None

        self._build_widgets()
        self.grade_input.set_value(session.grade_scale_text)
        self.participants_input.set_value(session.participants_text)

    # --- widget construction ---

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(5, weight=1)  # results table gets any extra vertical space

        self.meta_label = ttk.Label(self, text=self._meta_text(), foreground="#666666")
        self.meta_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        input_frame = ttk.LabelFrame(self, text="Input")
        input_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        input_frame.columnconfigure(0, weight=3)
        input_frame.columnconfigure(1, weight=2)

        ttk.Label(input_frame, text="Grade Scale (Grade=Min-Max)").grid(
            row=0, column=0, sticky="w", padx=5, pady=(5, 0)
        )
        ttk.Label(input_frame, text="Participant Scores (one per line)").grid(
            row=0, column=1, sticky="w", padx=5, pady=(5, 0)
        )

        self.grade_input = PlaceholderText(
            input_frame, placeholder=DEFAULT_GRADE_SCALE, width=32, height=11, wrap="none"
        )
        self.grade_input.grid(row=1, column=0, sticky="nsew", padx=(5, 10), pady=5)

        self.participants_input = PlaceholderText(
            input_frame, placeholder=PARTICIPANTS_PLACEHOLDER, width=22, height=11, wrap="none"
        )
        self.participants_input.grid(row=1, column=1, sticky="nsew", padx=(0, 5), pady=5)

        options_frame = ttk.Frame(input_frame)
        options_frame.grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))
        ttk.Label(
            options_frame, text="Fail threshold — a grade \u2265 this value counts as Failed:"
        ).pack(side="left")
        self.fail_threshold_var = tk.StringVar(value=self.session.fail_threshold_text)
        ttk.Entry(options_frame, textvariable=self.fail_threshold_var, width=6).pack(
            side="left", padx=5
        )

        button_frame = ttk.Frame(self)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Button(button_frame, text="Calculate", command=self.calculate).pack(side="left")
        ttk.Button(
            button_frame, text="Save Session", command=lambda: self.app.save_session(self)
        ).pack(side="left", padx=5)

        summary_frame = ttk.LabelFrame(self, text="Summary")
        summary_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.summary_label = ttk.Label(
            summary_frame, text="Enter data and press Calculate.", justify="left"
        )
        self.summary_label.pack(anchor="w", padx=5, pady=5)

        charts_frame = ttk.Frame(self)
        charts_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        charts_frame.columnconfigure(0, weight=1)
        charts_frame.columnconfigure(1, weight=1)

        # Grades on the left: how many participants landed in each grade
        # tier (colored green/red by the fail threshold).
        grades_chart_frame = ttk.LabelFrame(charts_frame, text="Distribution — Grades")
        grades_chart_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.grades_chart = tk.Canvas(
            grades_chart_frame, bg="white", height=160, highlightthickness=0
        )
        self.grades_chart.pack(fill="both", expand=True, padx=5, pady=5)
        self.grades_chart.bind("<Configure>", self._on_grades_chart_resize)

        # Points on the right: the raw score distribution (all participants),
        # with a marker line at the mean.
        points_chart_frame = ttk.LabelFrame(charts_frame, text="Distribution — Points")
        points_chart_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self.points_chart = tk.Canvas(
            points_chart_frame, bg="white", height=160, highlightthickness=0
        )
        self.points_chart.pack(fill="both", expand=True, padx=5, pady=5)
        self.points_chart.bind("<Configure>", self._on_points_chart_resize)

        table_frame = ttk.LabelFrame(self, text="Results")
        table_frame.grid(row=5, column=0, columnspan=2, sticky="nsew")
        table_frame.columnconfigure(1, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # A narrow legend to the left of the table: an arrow pointing down
        # makes the sort order (highest score at top) visible at a glance.
        self.legend_canvas = tk.Canvas(table_frame, width=40, highlightthickness=0, bg="white")
        self.legend_canvas.grid(row=0, column=0, sticky="ns", padx=(5, 0), pady=5)
        self.legend_canvas.bind(
            "<Configure>", lambda e: draw_sort_legend(self.legend_canvas, e.width, e.height)
        )
        draw_sort_legend(self.legend_canvas, 40, 200)

        # A dedicated style so the table's values are bold and left-aligned,
        # with tighter rows than the ttk default.
        style = ttk.Style()
        style.configure("GradeResults.Treeview", font=("Arial", 10, "bold"), rowheight=22)
        style.configure("GradeResults.Treeview.Heading", font=("Arial", 9, "bold"))

        self.result_table = ttk.Treeview(
            table_frame,
            columns=("score", "grade", "status"),
            show="headings",
            height=10,
            style="GradeResults.Treeview",
        )
        self.result_table.heading(
            "score", text="Score", command=lambda: self._sort_table("score", False)
        )
        self.result_table.heading(
            "grade", text="Grade", command=lambda: self._sort_table("grade", False)
        )
        self.result_table.heading("status", text="Status")
        self.result_table.column("score", width=80, anchor="w")
        self.result_table.column("grade", width=80, anchor="w")
        self.result_table.column("status", width=90, anchor="w")
        self.result_table.tag_configure("passed", foreground="#3A8B63")
        self.result_table.tag_configure("failed", foreground="#C55E5E")
        self.result_table.tag_configure("unmatched", foreground="#69baf0")
        self.result_table.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=5)

        table_scroll = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.result_table.yview
        )
        self.result_table.configure(yscrollcommand=table_scroll.set)
        table_scroll.grid(row=0, column=2, sticky="ns", pady=5, padx=(0, 5))

    def _meta_text(self) -> str:
        location = self.file_path or "not saved yet"
        return f"Session: {self.session.name}    File: {location}"

    # --- chart resize handlers ---

    def _on_grades_chart_resize(self, event: tk.Event) -> None:
        if self._last_distribution_grades is not None:
            draw_bar_chart(
                self.grades_chart,
                self._last_distribution_grades,
                width=event.width,
                height=event.height,
                fail_threshold=self._last_fail_threshold,
            )

    def _on_points_chart_resize(self, event: tk.Event) -> None:
        if self._last_scores is not None:
            draw_points_histogram(
                self.points_chart, self._last_scores, width=event.width, height=event.height
            )


    # --- table sorting ---

    def _sort_table(self, column: str, reverse: bool) -> None:
        def sort_value(value: str):
            try:
                return float(value)
            except ValueError:
                return float("inf")  # sorts "Fail" after numeric grades

        rows = [
            (self.result_table.set(item, column), item)
            for item in self.result_table.get_children("")
        ]
        rows.sort(key=lambda row: sort_value(row[0]), reverse=reverse)
        for index, (_, item) in enumerate(rows):
            self.result_table.move(item, "", index)
        self.result_table.heading(column, command=lambda: self._sort_table(column, not reverse))

    # --- core logic ---

    def calculate(self) -> None:
        grade_text = self.grade_input.get_value().strip() or DEFAULT_GRADE_SCALE
        participants_text = self.participants_input.get_value().strip()

        try:
            scale = parse_grade_scale(grade_text)
            scores = parse_participants(participants_text)
            fail_threshold = parse_number(self.fail_threshold_var.get())
        except InputError as exc:
            messagebox.showerror("Invalid Input", str(exc))
            return
        except ValueError:
            messagebox.showerror("Invalid Input", "The fail threshold must be a number.")
            return

        results = evaluate_scores(scores, scale)
        stats = compute_statistics(results, fail_threshold)
        self._render_results(results, stats, fail_threshold)

    def _render_results(
        self, results: list[tuple[float, str]], stats: Statistics, fail_threshold: float
    ) -> None:
        self.result_table.delete(*self.result_table.get_children())
        for score, label in results:
            status = grade_status(label, fail_threshold)
            self.result_table.insert(
                "", "end", values=(score, label, status), tags=(status.lower(),)
            )

        summary_lines = [
            f"Participants: {stats.total}    Passed: {stats.passed}    Failed: {stats.failed}",
            f"Average grade — all participants: {stats.average_all:.2f}",
            f"Average grade — passed participants only: {stats.average_passed:.2f}",
        ]
        if stats.unmatched:
            summary_lines.append(
                f"\u26a0 {stats.unmatched} score(s) did not fall into any defined grade range "
                "and were excluded from both averages."
            )
        self.summary_label.config(text="\n".join(summary_lines))

        self._last_distribution_grades = stats.distribution_grades
        self._last_scores = [score for score, _ in results]
        self._last_fail_threshold = fail_threshold

        draw_bar_chart(
            self.grades_chart,
            stats.distribution_grades,
            width=self.grades_chart.winfo_width() or 400,
            height= 160,
            fail_threshold=fail_threshold,
        )
        draw_points_histogram(
            self.points_chart,
            self._last_scores,
            width=self.points_chart.winfo_width() or 400,
            height= 160,
        )

    def refresh_meta(self) -> None:
        self.meta_label.config(text=self._meta_text())


# --- Application shell: menu bar + tabbed notebook of sessions ---
class GradeCalculatorApp:
    """Owns the main window, the menu bar, and the notebook of session tabs."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Grade Calculator")
        self.root.geometry("820x900")
        self.root.minsize(820, 690)
        add_footer(root, image_path="footer.png")
        center_window(root)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        self._build_menu()
        self.new_tab()

    # --- menu ---

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Tab", command=self.new_tab, accelerator="Ctrl+N")
        file_menu.add_command(
            label="Open Session(s)...", command=self.open_sessions, accelerator="Ctrl+O"
        )
        file_menu.add_command(
            label="Save Session",
            command=lambda: self.save_session(self._current_tab()),
            accelerator="Ctrl+S",
        )
        file_menu.add_command(
            label="Save Session As...",
            command=lambda: self.save_session(self._current_tab(), force_dialog=True),
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Close Tab", command=self.close_current_tab, accelerator="Ctrl+W"
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        self.root.config(menu=menubar)

        self.root.bind("<Control-n>", lambda _e: self.new_tab())
        self.root.bind("<Control-o>", lambda _e: self.open_sessions())
        self.root.bind("<Control-s>", lambda _e: self.save_session(self._current_tab()))
        self.root.bind("<Control-w>", lambda _e: self.close_current_tab())

    # --- tab management ---

    def _current_tab(self) -> SessionTab | None:
        if not self.notebook.tabs():
            return None
        return self.notebook.nametowidget(self.notebook.select())

    def new_tab(self, session: Session | None = None) -> SessionTab:
        if session is None:
            count = len(self.notebook.tabs()) + 1
            session = Session(
                name=f"Untitled {count}",
                grade_scale_text="",
                participants_text="",
            )
        tab = SessionTab(self.notebook, self, session)
        self.notebook.add(tab, text=session.name)
        self.notebook.select(tab)
        return tab

    def close_current_tab(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return
        if len(self.notebook.tabs()) == 1:
            messagebox.showinfo("Grade Calculator", "At least one tab must stay open.")
            return
        self.notebook.forget(tab)

    # --- file I/O ---

    def open_sessions(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Open Session(s)",
            filetypes=[("Grade Calculator Session", "*.json"), ("All Files", "*.*")],
        )
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                messagebox.showerror("Open Session", f"Could not open '{path}':\n{exc}")
                continue

            session = Session.from_dict(data, file_path=path)
            session.name = Path(path).stem
            tab = self.new_tab(session)
            tab.calculate()  # show results right away so tabs are ready to compare

    def save_session(self, tab: SessionTab | None, force_dialog: bool = False) -> None:
        if tab is None:
            return

        path = tab.file_path
        if force_dialog or not path:
            path = filedialog.asksaveasfilename(
                title="Save Session",
                defaultextension=".json",
                filetypes=[("Grade Calculator Session", "*.json")],
                initialfile=f"{tab.session.name}.json",
            )
            if not path:
                return

        session_to_save = Session(
            name=Path(path).stem,
            grade_scale_text=tab.grade_input.get_value(),
            participants_text=tab.participants_input.get_value(),
            fail_threshold_text=tab.fail_threshold_var.get(),
        )

        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(session_to_save.to_dict(), handle, indent=2)
        except OSError as exc:
            messagebox.showerror("Save Session", f"Could not save session:\n{exc}")
            return

        tab.file_path = path
        tab.session.name = session_to_save.name
        tab.refresh_meta()
        self.notebook.tab(tab, text=session_to_save.name)
        messagebox.showinfo("Save Session", f"Session saved to:\n{path}")


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    GradeCalculatorApp(root)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
