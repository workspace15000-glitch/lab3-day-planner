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

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Планировщик дня")
    root.geometry("820x560")
    ttk.Label(root, text="Планировщик дня").pack(pady=20)
    root.mainloop()
