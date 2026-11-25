"""Compatibility entry point: starts the Battleship Online client."""
import tkinter as tk
from client import BattleshipClient


if __name__ == "__main__":
    root = tk.Tk()
    BattleshipClient(root)
    root.mainloop()
