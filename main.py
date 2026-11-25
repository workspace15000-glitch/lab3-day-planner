"""Планировщик дня на Tkinter."""

import json
import re
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from tkinter import messagebox, ttk
from uuid import uuid4

DATA_FILE = Path(__file__).resolve().with_name("planner_data.json")
DEFAULT_SIZE = (820, 560)
MIN_WIDTH, MIN_HEIGHT = 640, 420


def format_day(day):
    return f"{day.day:02d}.{day.month:02d}.{day.year:04d}"


def parse_day(text):
    text = text.strip()
    if not re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", text):
        raise ValueError("Введите дату в формате ДД.ММ.ГГГГ.")
    return datetime.strptime(text, "%d.%m.%Y").date()


def validate_task(time, title, note):
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", time):
        raise ValueError("Введите время от 00:00 до 23:59 в формате ЧЧ:ММ.")
    if not title.strip() or len(title) > 100:
        raise ValueError("Введите название задачи длиной от 1 до 100 символов.")
    if len(note) > 500:
        raise ValueError("Заметка должна содержать не более 500 символов.")


def load_data(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], DEFAULT_SIZE
    tasks, size = data["tasks"], data["window_size"]
    width, height = size
    if type(width) is not int or type(height) is not int or width < MIN_WIDTH or height < MIN_HEIGHT:
        raise ValueError("Некорректный размер окна в сохранённом файле.")
    if not isinstance(tasks, list):
        raise ValueError("Некорректный список задач.")
    ids = set()
    for task in tasks:
        task_id = task["id"]
        for field in ("id", "date", "time", "title", "note"):
            if not isinstance(task[field], str):
                raise ValueError("Некорректные поля задачи.")
            task[field].encode("utf-8")
        if not task_id.strip() or "\0" in task_id or task_id in ids:
            raise ValueError("Некорректный идентификатор задачи.")
        if date.fromisoformat(task["date"]).isoformat() != task["date"] or type(task["done"]) is not bool:
            raise ValueError("Некорректная дата или статус задачи.")
        validate_task(task["time"], task["title"], task["note"])
        ids.add(task_id)
    return tasks, (width, height)


def save_data(path, tasks, size):
    # Заменяем рабочий файл только после успешной записи.
    file = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = Path(file.name)
    try:
        with file:
            json.dump({"tasks": tasks, "window_size": size}, file, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class PlannerApp:
    def __init__(self, root, path=DATA_FILE):
        self.root, self.path = root, path
        self.day = date.today()
        self.day_text, self.summary = tk.StringVar(root), tk.StringVar(root)
        self.read_only = False
        try:
            self.tasks, self.saved_size = load_data(path)
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            self.tasks, self.saved_size = [], DEFAULT_SIZE
            self.read_only = True
            root.after_idle(lambda: self.error("Ошибка чтения плана. Файл оставлен без изменений."))
        self.max_width = max(MIN_WIDTH, root.winfo_screenwidth() - 40)
        self.max_height = max(MIN_HEIGHT, root.winfo_screenheight() - 100)
        self.size = (min(self.saved_size[0], self.max_width), min(self.saved_size[1], self.max_height))
        root.title("Планировщик дня")
        root.minsize(MIN_WIDTH, MIN_HEIGHT)
        root.geometry(f"{self.size[0]}x{self.size[1]}")
        root.bind("<Configure>", self.remember_size)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.actions = (
            ("Добавить задачу", self.task_dialog), ("Изменить", self.edit_task),
            ("Отметить / вернуть", self.toggle_task), ("Удалить", self.delete_task),
        )
        self.build_menu()
        self.build_window()
        self.refresh()

    def build_menu(self):
        menu = tk.Menu(self.root)
        sections = (
            ("Файл", (("Выход", self.close),)),
            ("Задачи", self.actions),
            ("Вид", (("Размер окна…", self.size_dialog), ("Сегодня", lambda: self.change_day(0)))),
            ("Справка", (("Как пользоваться", self.show_help),)),
        )
        for title, commands in sections:
            section = tk.Menu(menu, tearoff=False)
            state = "disabled" if self.read_only and title == "Задачи" else "normal"
            for label, command in commands:
                section.add_command(label=label, command=command, state=state)
            menu.add_cascade(label=title, menu=section)
        self.root.config(menu=menu)

    def build_window(self):
        panel = ttk.Frame(self.root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Планировщик дня", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        dates = ttk.Frame(panel)
        dates.pack(fill="x", pady=12)
        ttk.Button(dates, text="◀", width=3, command=lambda: self.change_day(-1)).pack(side="left")
        date_box = ttk.Entry(dates, textvariable=self.day_text, width=13, justify="center")
        date_box.pack(side="left", padx=5)
        date_box.bind("<Return>", lambda event: self.change_day())
        for label, days in (("Перейти", None), ("▶", 1), ("Сегодня", 0)):
            ttk.Button(dates, text=label, command=lambda value=days: self.change_day(value)).pack(side="left", padx=(0, 5))
        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(0, 8))
        state = "disabled" if self.read_only else "normal"
        for label, command in self.actions:
            ttk.Button(actions, text=label, command=command, state=state).pack(side="left", padx=(0, 6))
        self.tree = ttk.Treeview(panel, columns=("time", "title", "status"), show="headings", selectmode="browse")
        for column, label, width in (("time", "Время", 82), ("title", "Задача", 350), ("status", "Статус", 126)):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, stretch=column == "title")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda event: self.edit_task() if self.tree.identify_row(event.y) else None)
        ttk.Label(panel, textvariable=self.summary).pack(anchor="w", pady=(10, 0))

    def refresh(self):
        self.day_text.set(format_day(self.day))
        self.tree.delete(*self.tree.get_children())
        tasks = [task for task in self.tasks if task["date"] == self.day.isoformat()]
        for task in sorted(tasks, key=lambda item: (item["time"], item["title"].casefold())):
            status = "Выполнена" if task["done"] else "К выполнению"
            self.tree.insert("", "end", iid=task["id"], values=(task["time"], task["title"], status))
        completed = sum(task["done"] for task in tasks)
        summary = f"Выполнено {completed} из {len(tasks)}" if tasks else "На этот день задач нет"
        self.summary.set("Данные недоступны. Изменения задач отключены." if self.read_only else summary)

    def change_day(self, days=None):
        try:
            if days is None:
                self.day = parse_day(self.day_text.get())
            elif days == 0:
                self.day = date.today()
            else:
                self.day += timedelta(days=days)
            self.refresh()
        except (ValueError, OverflowError):
            self.error("Проверьте дату. Используйте формат ДД.ММ.ГГГГ.")

    def selected_task(self):
        selected = self.tree.selection()
        if selected and not self.read_only:
            return next((task for task in self.tasks if task["id"] == selected[0]), None)
        return None

    def error(self, text, parent=None):
        messagebox.showerror("Планировщик дня", text, parent=parent or self.root)

    def commit(self, tasks, size, parent=None):
        try:
            save_data(self.path, tasks, size)
        except OSError as error:
            self.error(f"Изменения не сохранены.\n{error}", parent)
            return False
        self.tasks, self.saved_size = tasks, size
        return True

    def task_dialog(self, task=None):
        day = date.fromisoformat(task["date"]) if task else self.day
        fields = (("Дата (ДД.ММ.ГГГГ)", format_day(day)), ("Время (ЧЧ:ММ)", task["time"] if task else "09:00"),
                  ("Название", task["title"] if task else ""))
        dialog, entries = self.form("Изменение задачи" if task else "Новая задача", fields, 30)
        ttk.Label(dialog, text="Заметка").grid(row=3, column=0, sticky="nw")
        note = tk.Text(dialog, width=32, height=4, wrap="word")
        note.grid(row=3, column=1, columnspan=2, padx=(8, 0), pady=4, sticky="ew")
        if task:
            note.insert("1.0", task["note"])

        def apply():
            try:
                day = parse_day(entries[0].get())
                time, title = entries[1].get().strip(), entries[2].get().strip()
                text = note.get("1.0", "end-1c").strip()
                validate_task(time, title, text)
            except ValueError as error:
                self.error(str(error), dialog)
                return
            updated = dict(id=task["id"] if task else uuid4().hex, date=day.isoformat(),
                           time=time, title=title, note=text, done=task["done"] if task else False)
            if self.replace_task(updated, dialog):
                dialog.destroy()

        self.dialog_buttons(dialog, 4, "Сохранить", apply)
        entries[2].focus_set()

    def form(self, title, fields, width):
        dialog = tk.Toplevel(self.root, padx=18, pady=14)
        dialog.title(title)
        entries = []
        for row, (label, value) in enumerate(fields):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = ttk.Entry(dialog, width=width)
            entry.insert(0, value)
            entry.grid(row=row, column=1, columnspan=2, padx=(8, 0), pady=4, sticky="ew")
            entries.append(entry)
        return dialog, entries

    def dialog_buttons(self, dialog, row, label, command):
        ttk.Button(dialog, text=label, command=command).grid(row=row, column=1, padx=5, pady=(8, 0), sticky="e")
        ttk.Button(dialog, text="Отмена", command=dialog.destroy).grid(row=row, column=2, pady=(8, 0))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.wait_visibility()
        dialog.grab_set()

    def replace_task(self, task, parent=None):
        tasks = [item for item in self.tasks if item["id"] != task["id"]] + [task]
        if not self.commit(tasks, self.size, parent):
            return False
        self.day = date.fromisoformat(task["date"])
        self.refresh()
        self.tree.selection_set(task["id"])
        return True

    def edit_task(self):
        task = self.selected_task()
        if task:
            self.task_dialog(task)

    def toggle_task(self):
        task = self.selected_task()
        if task:
            self.replace_task({**task, "done": not task["done"]})

    def delete_task(self):
        task = self.selected_task()
        if task and messagebox.askyesno("Удаление задачи", f"Удалить «{task['title']}»?", parent=self.root):
            if self.commit([item for item in self.tasks if item["id"] != task["id"]], self.size):
                self.refresh()

    def size_dialog(self):
        fields = ((f"Ширина ({MIN_WIDTH}–{self.max_width} пикс.)", self.size[0]),
                  (f"Высота ({MIN_HEIGHT}–{self.max_height} пикс.)", self.size[1]))
        dialog, entries = self.form("Размер окна", fields, 14)

        def apply():
            try:
                width, height = (int(entry.get()) for entry in entries)
                if not (MIN_WIDTH <= width <= self.max_width and MIN_HEIGHT <= height <= self.max_height):
                    raise ValueError
            except ValueError:
                self.error("Введите целые числа в указанных диапазонах.", dialog)
                return
            if self.read_only or self.commit(self.tasks, (width, height), dialog):
                self.size = (width, height)
                self.root.state("normal")
                self.root.geometry(f"{width}x{height}")
                dialog.destroy()

        self.dialog_buttons(dialog, 2, "Применить", apply)
        entries[0].focus_set()

    def remember_size(self, event):
        if event.widget is self.root and self.root.state() == "normal":
            if event.width >= MIN_WIDTH and event.height >= MIN_HEIGHT:
                self.size = (event.width, event.height)

    def show_help(self):
        text = "Выберите дату и добавьте задачу. Размер окна задаётся в меню «Вид»."
        messagebox.showinfo("Как пользоваться", text, parent=self.root)

    def close(self):
        if not self.read_only and self.size != self.saved_size and not self.commit(self.tasks, self.size):
            if not messagebox.askyesno("Выход", "Закрыть без сохранения размера окна?", parent=self.root):
                return
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    PlannerApp(root)
    root.mainloop()
