# test_dialog.py (Version 2 - Korrigiert)
import tkinter as tk
from tkinter import filedialog
import sys
import traceback # <<< Fehlender Import hinzugefügt

print(f"Python Version: {sys.version}")
print(f"Tkinter Version: {tk.TkVersion}")

print("Erstelle Tkinter-Root...")
root = tk.Tk()
root.withdraw()
print("Rufe askopenfilename mit Keywords auf...")

filepath = None # Initialisieren für den Fall eines Fehlers
try:
    # Rufe den Dialog mit Keyword-Argumenten auf
    filepath = filedialog.askopenfilename(
        title="TEST - MIDI auswählen",
        filetypes=[("MIDI", "*.mid *.midi"), ("Alle", "*.*")]
    )
    print(f"Dialog beendet. Ergebnis: '{filepath}'")

except Exception as e:
    print(f"FEHLER aufgetreten: {e}")
    traceback.print_exc() # Jetzt sollte traceback definiert sein

finally:
    # Stelle sicher, dass das (unsichtbare) Root-Fenster geschlossen wird,
    # falls es noch existiert und der Dialog einen Fehler verursacht hat.
    # Das verhindert, dass das Skript manchmal hängen bleibt.
    try:
        if root and root.winfo_exists():
            root.destroy()
    except tk.TclError:
        pass # Fenster wurde vielleicht schon zerstört
    print("Test-Skript beendet.")