"""Entry point for the Warframe Ducat/Platinum Trade Calculator."""

import tkinter as tk

from app import DucatCalculatorApp


def main():
    root = tk.Tk()
    DucatCalculatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
