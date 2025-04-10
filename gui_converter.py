# -*- coding: utf-8 -*-
# gui_converter.py - Fehlerbereinigte Version

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import os
import traceback
import mido
import logging
import threading
import subprocess
import tempfile
import shutil

# --- Konfiguration ---
LOG_FOLDER = "logs"
INSTRUCTIONS_SUBFOLDER = "llm_instructions"
GUIDE_PROMPT_FILENAME = "llm_guide_and_prompt_template.txt"
MUSESCORE_EXE_PATH = r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe"
DEFAULT_TICKS_PER_BEAT = 480
DEFAULT_TEMPO = 500000
DEFAULT_TIME_SIGNATURE = (4, 4)
DEFAULT_KEY_SIGNATURE = 'C'

# --- Logging-Konfiguration ---
def setup_logging():
    """Initialisiert das Logging-System."""
    try:
        os.makedirs(LOG_FOLDER, exist_ok=True)
        log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler = logging.FileHandler(os.path.join(LOG_FOLDER, "gui_converter.log"), mode='w', encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        if logger.hasHandlers():
            logger.handlers.clear()
        logger.addHandler(file_handler)
        logging.info("=" * 30)
        logging.info("Logging initialisiert.")
        logging.info("=" * 30)
    except Exception as e:
        print(f"FEHLER beim Initialisieren des Loggings: {e}")
        traceback.print_exc()

# --- Fallback-Anleitungstext ---
FALLBACK_GUIDE_TEXT = """
FEHLER: Konnte llm_guide_and_prompt_template.txt nicht laden!
Bitte stelle sicher, dass die Datei im Unterordner 'llm_instructions' existiert.
"""

# --- Hilfsfunktionen ---
def velocity_to_dynamic(velocity):
    """Konvertiert Velocity in Dynamik-Symbole."""
    VELOCITY_MAP = [
        (16, 'ppp'), (32, 'pp'), (48, 'p'), (64, 'mp'),
        (80, 'mf'), (96, 'f'), (112, 'ff'), (127, 'fff')
    ]
    for threshold, symbol in VELOCITY_MAP:
        if velocity <= threshold:
            return symbol
    return 'fff'

def midi_note_to_llm_pitch(midi_note):
    """Konvertiert eine MIDI-Note in LLM-Pitch."""
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    if not 0 <= midi_note <= 127:
        logging.warning("Ungültige MIDI-Notennummer: %s", midi_note)
        return "InvalidNote"
    octave = (midi_note // 12) - 1
    note_index = midi_note % 12
    return f"{NOTE_NAMES[note_index]}{octave}"

def get_track_names(mid_file):
    """Extrahiert die Namen der Tracks aus einer MIDI-Datei."""
    track_names = {}
    for i, track in enumerate(mid_file.tracks):
        for msg in track[:15]:
            if msg.is_meta and msg.type == 'track_name':
                track_names[i] = msg.name if isinstance(msg.name, str) else "[Name nicht dekodierbar]"
                break
        else:
            track_names[i] = "[Kein Name gefunden]"
    return track_names

# --- GUI-Klasse ---
class MidiConverterApp:
    def __init__(self, master):
        """Initialisiert die GUI."""
        self.master = master
        master.title("MIDI zu LLM Konverter")
        self.input_file_path = tk.StringVar()
        self.conversion_direction = tk.StringVar(value="->")

        # Layout
        main_frame = ttk.Frame(master, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Linker Bereich
        left_frame = ttk.LabelFrame(main_frame, text="Input / Output Datei", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(5, 2), pady=5, anchor='n')

        self.input_label = ttk.Label(left_frame, text="Input (MIDI/MSCZ):")
        self.input_label.pack(anchor=tk.W)

        self.filepath_entry = ttk.Entry(left_frame, textvariable=self.input_file_path, width=30, state='readonly')
        self.filepath_entry.pack(fill=tk.X, pady=(2, 5))

        self.select_button = ttk.Button(left_frame, text="Input wählen...", command=self.select_input_file)
        self.select_button.pack(fill=tk.X, pady=5)

        # Mittlerer Bereich
        middle_frame = ttk.Frame(main_frame, padding="10")
        middle_frame.pack(side=tk.LEFT, fill=tk.Y, padx=3, pady=5, anchor='n')

        self.direction_button = ttk.Button(middle_frame, textvariable=self.conversion_direction, command=self.toggle_direction, width=3)
        self.direction_button.pack(pady=20)

        self.convert_button = ttk.Button(middle_frame, text="Konvertieren", command=self.start_conversion_threaded, state='disabled')
        self.convert_button.pack(pady=20)

        # Rechter Bereich
        right_frame = ttk.LabelFrame(main_frame, text="LLM Notation / Anleitung", padding="10")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 5), pady=5)

        self.text_area = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, height=10, width=50)
        self.text_area.pack(fill=tk.BOTH, expand=True)
        self.text_area.insert(tk.END, "Anleitung/Prompt wird nach Konvertierung geladen...")
        self.text_area.configure(state='disabled')

        # Log-Bereich
        log_frame = ttk.LabelFrame(master, text="Log", padding="5")
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0, 5))

        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', height=8)
        self.log_area.pack(fill=tk.X, expand=True)

    def log_output(self, message, level="INFO"):
        """Schreibt Nachrichten ins GUI- und File-Log."""
        if level == "DEBUG":
            logging.debug(message)
        elif level == "WARNING":
            logging.warning(message)
        elif level == "ERROR":
            logging.error(message)
        else:
            logging.info(message)

        if hasattr(self, 'log_area') and self.log_area.winfo_exists():
            self.master.after(0, lambda: self.update_gui_log(message, level))

    def update_gui_log(self, message, level):
        """Aktualisiert das Log im GUI."""
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, f"[{level}] {message}\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)

    def select_input_file(self):
        """Öffnet einen Dateidialog für die Eingabedatei."""
        filetypes = [("Musikdateien", "*.mid *.midi *.mscz *.mscx"), ("Alle Dateien", "*.*")]
        filepath = filedialog.askopenfilename(title="MIDI/MuseScore Datei wählen", filetypes=filetypes)
        if filepath:
            self.input_file_path.set(filepath)
            self.log_output(f"Input-Datei ausgewählt: {filepath}", "INFO")
            self.convert_button.configure(state='normal')
        else:
            self.log_output("Keine Input-Datei ausgewählt.", "INFO")
            self.convert_button.configure(state='disabled')

    def select_output_file(self):
        """Öffnet einen Dateidialog für die Ausgabedatei."""
        filetypes = [("MIDI-Dateien", "*.mid *.midi"), ("Alle Dateien", "*.*")]
        filepath = filedialog.asksaveasfilename(title="MIDI Datei speichern unter", filetypes=filetypes, defaultextension=".mid")
        if filepath:
            self.input_file_path.set(filepath)
            self.log_output(f"Output-Datei ausgewählt: {filepath}", "INFO")
            self.convert_button.configure(state='normal')
        else:
            self.log_output("Keine Output-Datei ausgewählt.", "INFO")
            self.convert_button.configure(state='disabled')

    def toggle_direction(self):
        """Wechselt die Konvertierungsrichtung."""
        current_direction = self.conversion_direction.get()
        if current_direction == "->":
            self.conversion_direction.set("<-")
            self.input_label.configure(text="Output (MIDI):")
            self.select_button.configure(text="Output wählen...", command=self.select_output_file)
            self.text_area.configure(state='normal')
            self.text_area.delete('1.0', tk.END)
            self.text_area.insert('1.0', "# Hier LLM Notation einfügen...\nKey: C\n\nT0 Piano:\n| 1 C4/4 E4/4 G4/2 | 2 C5/1")
            self.log_output("Richtung geändert: Text -> MIDI", "INFO")
        else:
            self.conversion_direction.set("->")
            self.input_label.configure(text="Input (MIDI/MSCZ):")
            self.select_button.configure(text="Input wählen...", command=self.select_input_file)
            self.text_area.configure(state='normal')
            self.text_area.delete('1.0', tk.END)
            self.text_area.insert('1.0', "Anleitung/Prompt wird nach Konvertierung geladen...")
            self.text_area.configure(state='disabled')
            self.log_output("Richtung geändert: MIDI -> Text", "INFO")
        self.convert_button.configure(state='disabled')
        self.input_file_path.set("")

    def start_conversion_threaded(self):
        """Startet die Konvertierung in einem separaten Thread."""
        input_path = self.input_file_path.get()
        if not input_path:
            self.log_output("FEHLER: Keine Eingabedatei ausgewählt!", "ERROR")
            return

        self.log_output(f"Starte Konvertierung ({self.conversion_direction.get()}) für: {input_path}", "INFO")
        self.convert_button.configure(state='disabled')
        self.select_button.configure(state='disabled')
        self.direction_button.configure(state='disabled')

        thread = threading.Thread(target=self.run_conversion, args=(input_path,), daemon=True)
        thread.start()

    def run_conversion(self, input_file_path):
        """Führt die Konvertierung durch."""
        try:
            # Bestimme den vollständigen Pfad zur Anleitungs-/Prompt-Datei im Hauptverzeichnis
            guide_prompt_path = os.path.join(os.path.dirname(__file__), GUIDE_PROMPT_FILENAME)

            # Initialisiere eine Variable für den Textinhalt mit einem Fallback-Wert
            guide_text_content = FALLBACK_GUIDE_TEXT

            # Versuche, die Datei zu lesen
            if os.path.exists(guide_prompt_path):
                with open(guide_prompt_path, 'r', encoding='utf-8') as f_guide_read:
                    guide_text_content = f_guide_read.read()
                    self.log_output(f"Anleitung/Prompt-Datei gelesen: {guide_prompt_path}", "INFO")
            else:
                guide_text_content = f"FEHLER: Datei '{guide_prompt_path}' nicht gefunden..."
                self.log_output(guide_text_content, "ERROR")
                logging.error(guide_text_content)

            # Beginne die Konvertierung der MIDI-Datei
            mid = mido.MidiFile(input_file_path)
            output_text = []

            # Füge die Tonart und andere Metadaten hinzu
            output_text.append(f"Key: {DEFAULT_KEY_SIGNATURE}")

            # Iteriere über die Tracks und konvertiere die Events
            track_names = get_track_names(mid)
            for i, track in enumerate(mid.tracks):
                output_text.append(f"T{i} {track_names.get(i, 'Unbenannter Track')}:\n")
                measure_counter = 1
                measure_events = []
                ticks_per_beat = mid.ticks_per_beat
                current_time = 0

                for msg in track:
                    current_time += msg.time
                    if msg.type == 'note_on' and msg.velocity > 0:
                        pitch = midi_note_to_llm_pitch(msg.note)
                        duration = "1"  # Platzhalter für Dauer
                        measure_events.append(f"{pitch}/{duration}")
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        # Behandle Note-Off-Ereignisse
                        pass

                    # Füge Taktstriche hinzu, basierend auf der Zeit
                    if current_time >= ticks_per_beat * 4 * measure_counter:
                        output_text.append(f"| {measure_counter} {' '.join(measure_events)}")
                        measure_events = []
                        measure_counter += 1

                # Füge verbleibende Events hinzu
                if measure_events:
                    output_text.append(f"| {measure_counter} {' '.join(measure_events)}")

            # Schreibe die konvertierte Ausgabe in das Textfeld
            self.display_output_text("\n".join(output_text))

        except Exception as e:
            guide_text_content = FALLBACK_GUIDE_TEXT
            self.log_output(f"FEHLER beim Lesen der Anleitung/Prompt-Datei: {e}", "ERROR")
            logging.error("FEHLER beim Lesen der Anleitung/Prompt-Datei!", exc_info=True)

        # Der Rest der Funktion sollte guide_text_content verwenden
        self.display_output_text(guide_text_content)

    def reactivate_buttons(self):
        """Reaktiviert die Buttons nach Abschluss der Konvertierung."""
        self.convert_button.configure(state='normal')
        self.select_button.configure(state='normal')
        self.direction_button.configure(state='normal')
        self.log_output("Bereit für die nächste Aktion.", "INFO")

    def display_output_text(self, text_content):
        """Zeigt den Textinhalt im Textbereich an."""
        self.text_area.configure(state='normal')
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert('1.0', text_content)
        self.text_area.configure(state='disabled')

# --- Hauptteil ---
if __name__ == "__main__":
    setup_logging()
    root = tk.Tk()
    app = MidiConverterApp(root)
    app.log_output("GUI gestartet. Bitte Input-Datei auswählen.", "INFO")
    root.mainloop()
    logging.info("GUI geschlossen, Skript beendet.")