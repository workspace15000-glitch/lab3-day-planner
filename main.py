import tkinter as tk
from tkinter import ttk


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Планировщик дня")
    root.geometry("820x560")
    ttk.Label(root, text="Планировщик дня").pack(pady=20)
    root.mainloop()
