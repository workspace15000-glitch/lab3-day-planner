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
        self.build_menu()
        self.build_window()
        self.refresh()

    def build_menu(self):
        menu = tk.Menu(self.root)
        sections = (
            ("Файл", (("Выход", self.close),)),
            ("Вид", (("Сегодня", lambda: self.change_day(0)),)),
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
        self.tree = ttk.Treeview(panel, columns=("time", "title", "status"), show="headings", selectmode="browse")
        for column, label, width in (("time", "Время", 82), ("title", "Задача", 350), ("status", "Статус", 126)):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, stretch=column == "title")
        self.tree.pack(fill="both", expand=True)
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
