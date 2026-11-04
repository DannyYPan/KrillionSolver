"""Search, edit, delete, and export the local answer history."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .answer_history import delete, export_csv, search, update
from .learned_answers import migrate_legacy_history


class AnswerHistoryWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("KrillionSolver Answer History")
        self.geometry("920x600")
        self.minsize(720, 480)
        self.selected_id: int | None = None
        self.visible_rows: list[dict[str, object]] = []
        self.query = tk.StringVar()
        self.mode_filter = tk.StringVar(value="All games")
        self.status_filter = tk.StringVar(value="All statuses")
        self.edit_mode = tk.StringVar(value="Krillion")
        self.edit_prompt = tk.StringVar()
        self.edit_answer = tk.StringVar()
        self.edit_status = tk.StringVar(value="accepted")
        self.message = tk.StringVar(value="Select a row to edit it")
        self._build()
        migrate_legacy_history()
        self.refresh()

    def _build(self) -> None:
        filters = ttk.Frame(self, padding=10)
        filters.pack(fill="x")
        ttk.Label(filters, text="Search").pack(side="left")
        query_entry = ttk.Entry(filters, textvariable=self.query, width=34)
        query_entry.pack(side="left", padx=(6, 12), fill="x", expand=True)
        mode = ttk.Combobox(
            filters, textvariable=self.mode_filter,
            values=["All games", "Krillion", "Puffer Party"], state="readonly", width=15,
        )
        mode.pack(side="left", padx=(0, 8))
        status = ttk.Combobox(
            filters, textvariable=self.status_filter,
            values=["All statuses", "accepted", "rejected"], state="readonly", width=13,
        )
        status.pack(side="left")
        ttk.Button(filters, text="Export CSV", command=self._export).pack(side="left", padx=(8, 0))
        self.query.trace_add("write", lambda *_: self.refresh())
        mode.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        status.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        table_frame = ttk.Frame(self, padding=(10, 0))
        table_frame.pack(fill="both", expand=True)
        columns = ("mode", "prompt", "answer", "status", "observations")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "mode": "Game", "prompt": "Prompt", "answer": "Answer",
            "status": "Status", "observations": "Seen",
        }
        widths = {"mode": 110, "prompt": 360, "answer": 190, "status": 85, "observations": 55}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], minwidth=45, stretch=column in {"prompt", "answer"})
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self._select)

        editor = ttk.LabelFrame(self, text="Edit selected history entry", padding=10)
        editor.pack(fill="x", padx=10, pady=10)
        editor.columnconfigure(1, weight=1)
        editor.columnconfigure(3, weight=1)
        ttk.Label(editor, text="Game").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            editor, textvariable=self.edit_mode, values=["Krillion", "Puffer Party"],
            state="readonly", width=15,
        ).grid(row=0, column=1, sticky="w", padx=(6, 14))
        ttk.Label(editor, text="Status").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            editor, textvariable=self.edit_status, values=["accepted", "rejected"],
            state="readonly", width=12,
        ).grid(row=0, column=3, sticky="w", padx=(6, 0))
        ttk.Label(editor, text="Prompt").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(editor, textvariable=self.edit_prompt).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(8, 0)
        )
        ttk.Label(editor, text="Answer").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(editor, textvariable=self.edit_answer).grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(8, 0)
        )
        actions = ttk.Frame(editor)
        actions.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Save changes", command=self._save).pack(side="left")
        ttk.Button(actions, text="Delete", command=self._delete).pack(side="left", padx=6)
        ttk.Label(actions, textvariable=self.message).pack(side="left", padx=(12, 0))
        ttk.Label(
            editor,
            text="History edits affect instant suggestions. Fine-tuning JSONL is managed by Edit Training Data.bat.",
            foreground="#555",
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))
        query_entry.focus_set()

    def refresh(self) -> None:
        mode = "" if self.mode_filter.get() == "All games" else self.mode_filter.get()
        status = "" if self.status_filter.get() == "All statuses" else self.status_filter.get()
        self.visible_rows = search(self.query.get(), mode=mode, status=status)
        self.table.delete(*self.table.get_children())
        for row in self.visible_rows:
            self.table.insert("", "end", iid=str(row["id"]), values=(
                row["mode"], row["prompt"], row["answer"], row["status"], row["observations"],
            ))
        self.message.set(f"{len(self.visible_rows)} entries")

    def _select(self, _event=None) -> None:
        selected = self.table.selection()
        if not selected:
            return
        self.selected_id = int(selected[0])
        row = next((item for item in self.visible_rows if item["id"] == self.selected_id), None)
        if row:
            self.edit_mode.set(str(row["mode"]))
            self.edit_prompt.set(str(row["prompt"]))
            self.edit_answer.set(str(row["answer"]))
            self.edit_status.set(str(row["status"]))

    def _save(self) -> None:
        if self.selected_id is None:
            self.message.set("Select an entry first")
            return
        if update(
            self.selected_id, mode=self.edit_mode.get(), prompt=self.edit_prompt.get(),
            answer=self.edit_answer.get(), status=self.edit_status.get(),
        ):
            self.refresh()
            self.message.set("Changes saved")
        else:
            self.message.set("Could not save; check for an empty or duplicate entry")

    def _delete(self) -> None:
        if self.selected_id is None:
            self.message.set("Select an entry first")
            return
        if not messagebox.askyesno("Delete history entry", "Remove this answer from instant history?", parent=self):
            return
        if delete(self.selected_id):
            self.selected_id = None
            self.refresh()
            self.message.set("Entry deleted")

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Export answer history", defaultextension=".csv",
            filetypes=[("CSV spreadsheet", "*.csv")], initialfile="KrillionSolver-answer-history.csv",
        )
        if not path:
            return
        count = export_csv(path, self.visible_rows)
        self.message.set(f"Exported {count} entries")


def open_history_window(parent: tk.Misc) -> None:
    AnswerHistoryWindow(parent)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    window = AnswerHistoryWindow(root)
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
