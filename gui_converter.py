# gui_converter.py
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch, MagicMock, mock_open, call
from tkinter import scrolledtext
from tkinter import filedialog
import mido
import os
import sys
import logging
import time
import datetime
from collections import defaultdict
import math # Needed for duration calculation

# --- Constants ---
FALLBACK_GUIDE_TEXT = "Hier steht der Guide für das LLM. Er wird vor die konvertierten Daten gesetzt."
DEFAULT_TICKS_PER_BEAT = 480
DEFAULT_TEMPO = 120 # BPM
DEFAULT_TIME_SIGNATURE = (4, 4)
DEFAULT_KEY_SIGNATURE = "C"
# DEFAULT_NOTE_DURATION = 1 # No longer used directly for output duration
GUIDE_PROMPT_FILENAME = "llm_guide.txt"
OUTPUT_FOLDER_NAME = "output"
LOG_FOLDER = "logs"

# --- Helper Functions ---
def setup_logging():
    # ... (setup_logging function remains the same) ...
    """Configures logging to write INFO+ to a main file and console,
       and ERROR+ to a separate error file."""
    os.makedirs(LOG_FOLDER, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    # Define filenames
    log_filename = os.path.join(LOG_FOLDER, f"app_{timestamp}.log")
    error_log_filename = os.path.join(LOG_FOLDER, f"error_{timestamp}.log")

    # Get the root logger
    logger = logging.getLogger()
    # Clear existing handlers (important if this function might be called multiple times, e.g., in tests)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Set the lowest level the logger will handle (messages below this are ignored)
    # Set to INFO so INFO, WARNING, ERROR, CRITICAL messages are passed to handlers
    logger.setLevel(logging.INFO)

    # Create a formatter
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)

    # --- Main Log File Handler (INFO and above) ---
    info_file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    info_file_handler.setLevel(logging.INFO) # Process INFO, WARNING, ERROR, CRITICAL
    info_file_handler.setFormatter(formatter)
    logger.addHandler(info_file_handler)

    # --- Error Log File Handler (ERROR and above) ---
    error_file_handler = logging.FileHandler(error_log_filename, encoding='utf-8')
    error_file_handler.setLevel(logging.ERROR) # Process only ERROR, CRITICAL
    error_file_handler.setFormatter(formatter)
    logger.addHandler(error_file_handler)

    # --- Console Handler (INFO and above - like before) ---
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO) # Process INFO, WARNING, ERROR, CRITICAL
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logging.info("Logging initialisiert. Haupt-Log: %s, Fehler-Log: %s", log_filename, error_log_filename)


def velocity_to_dynamic(velocity):
    """Converts MIDI velocity to a dynamic marking symbol (ppp, pp, ..., fff)."""
    # ... (velocity_to_dynamic function remains the same) ...
    if velocity <= 16: return 'ppp'
    elif velocity <= 32: return 'pp'
    elif velocity <= 63: return 'p'
    elif velocity <= 79: return 'mp'
    elif velocity <= 95: return 'mf'
    elif velocity <= 111: return 'f'
    elif velocity <= 126: return 'ff'
    else: return 'fff'

def ensure_folder_exists(folder_path):
    # ... (ensure_folder_exists function remains the same) ...
    try:
        os.makedirs(folder_path, exist_ok=True)
    except OSError as e:
        logging.error(f"Fehler beim Erstellen des Ordners {folder_path}: {e}")

def get_track_names(midi_file):
    # ... (get_track_names function remains the same) ...
    track_names = {}
    for i, track in enumerate(midi_file.tracks):
        for msg in track:
            if msg.type == 'track_name':
                track_names[i] = msg.name
                break
    return track_names

def midi_note_to_llm_pitch(note_number):
    # ... (midi_note_to_llm_pitch function remains the same) ...
    if not 0 <= note_number <= 127:
        logging.warning(f"Ungültige MIDI-Notennummer: {note_number}. Gebe rohen Wert zurück.")
        return str(note_number)
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (note_number // 12) - 1
    note_index = note_number % 12
    return f"{note_names[note_index]}{octave}"

# --- NEW HELPER FUNCTIONS FOR LLM FORMAT ---

def ticks_to_duration_code(ticks, ticks_per_beat, time_signature_denominator=4):
    """
    Converts a duration in MIDI ticks to the LLM symbolic notation (e.g., /4, /8., /?).
    Handles standard and dotted durations.
    """
    if ticks <= 0 or ticks_per_beat <= 0:
        return "/?" # Invalid duration

    # Calculate duration in beats relative to a quarter note
    # A beat in Mido usually means a quarter note unless specified otherwise by time signature.
    # However, ticks_per_beat is absolute. Let's calculate beats directly.
    beats = ticks / ticks_per_beat

    # Define standard durations in beats (relative to quarter note = 1 beat)
    # and their codes. Prioritize non-dotted, then dotted.
    # Using a small tolerance to handle floating point inaccuracies.
    tolerance = 0.05 # Tolerance in beats

    # Durations based on quarter notes (denominator 4)
    base_beat_unit = 4.0 / time_signature_denominator # e.g., in 6/8, base is 4/8 = 0.5 quarter notes per beat

    # Map beat counts to duration codes
    # Order matters: check longer durations first, check dotted before non-dotted of similar length
    duration_map = [
        (4.0, '/1'),   # Whole note (4 quarter beats)
        (3.0, '/2.'),  # Dotted half
        (2.0, '/2'),   # Half note
        (1.5, '/4.'),  # Dotted quarter
        (1.0, '/4'),   # Quarter note
        (0.75, '/8.'), # Dotted eighth
        (0.5, '/8'),   # Eighth note
        (0.375, '/16.'),# Dotted sixteenth
        (0.25, '/16'),  # Sixteenth note
        (0.125, '/32'), # Thirty-second note
        (0.0625, '/64'),# Sixty-fourth note
        # Add others if needed, e.g., double whole /0.5 (8 beats)
    ]

    for beat_val, code in duration_map:
        if abs(beats - beat_val) < tolerance * beat_val: # Use relative tolerance
             return code

    # If no standard duration matches well
    logging.warning(f"Could not accurately quantize duration of {ticks} ticks ({beats:.3f} beats). Returning '/?'.")
    return "/?"

def calculate_ticks_per_measure(time_signature, ticks_per_beat):
    """Calculates ticks per measure based on time signature and TPB."""
    if time_signature[1] == 0: # Avoid division by zero
        logging.warning(f"Invalid time signature denominator 0. Using default 4/4.")
        return ticks_per_beat * 4
    # Formula: ticks_per_beat * beats_per_measure
    # beats_per_measure = numerator * (beat_unit_value / denominator_value)
    # Assuming beat unit is quarter note for ticks_per_beat
    # So, ticks per measure = ticks_per_beat * numerator * (4 / denominator)
    return int(ticks_per_beat * time_signature[0] * (4 / time_signature[1]))

# --- END OF NEW HELPER FUNCTIONS ---


# --- GUI Class ---

class MidiConverterApp:
    def __init__(self, master):
        # ... (GUI __init__ remains the same) ...
        self.master = master
        master.title("MIDI Konverter")

        # --- GUI Elements ---
        self.input_path_var = tk.StringVar()
        self.output_text = scrolledtext.ScrolledText(master, wrap=tk.WORD, width=80, height=20)
        self.output_text.pack(padx=10, pady=10)

        # --- Input Frame ---
        input_frame = ttk.LabelFrame(master, text="Eingabe")
        input_frame.pack(padx=10, pady=5, fill=tk.X)

        ttk.Label(input_frame, text="MIDI Datei:").pack(side=tk.LEFT, padx=5, pady=5)
        self.input_path_entry = ttk.Entry(input_frame, textvariable=self.input_path_var, width=60)
        self.input_path_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)

        self.browse_button = ttk.Button(input_frame, text="...", command=self.browse_file)
        self.browse_button.pack(side=tk.LEFT, padx=5, pady=5)

        # --- LLM Text Frame ---
        llm_text_frame = ttk.LabelFrame(master, text="LLM Text (Optional)")
        llm_text_frame.pack(padx=10, pady=5, fill=tk.X)

        self.llm_text_input = scrolledtext.ScrolledText(llm_text_frame, wrap=tk.WORD, width=80, height=10)
        self.llm_text_input.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        # --- Conversion Frame ---
        conversion_frame = ttk.LabelFrame(master, text="Konvertierung")
        conversion_frame.pack(padx=10, pady=5, fill=tk.X)

        self.convert_midi_to_text_button = ttk.Button(conversion_frame, text="MIDI -> Text", command=lambda: self.run_conversion(self.input_path_var.get(), "->", self.llm_text_input.get("1.0", tk.END)))
        self.convert_midi_to_text_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.convert_text_to_midi_button = ttk.Button(conversion_frame, text="Text -> MIDI", command=lambda: self.run_conversion("", "<-", self.llm_text_input.get("1.0", tk.END)))
        self.convert_text_to_midi_button.pack(side=tk.LEFT, padx=5, pady=5)

        # --- Logging Frame ---
        logging_frame = ttk.LabelFrame(master, text="Log")
        logging_frame.pack(padx=10, pady=5, fill=tk.X)

        self.log_output_text = scrolledtext.ScrolledText(logging_frame, wrap=tk.WORD, width=80, height=10)
        self.log_output_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        # --- Initial Setup ---
        self.log_output("GUI initialisiert.", "INFO")

    def browse_file(self):
        # ... (browse_file remains the same) ...
        filepath = filedialog.askopenfilename(
            title="MIDI auswählen",
            filetypes=[("MIDI", "*.mid *.midi"), ("Alle", "*.*")]
        )
        if filepath:
            self.input_path_var.set(filepath)
            logging.info(f"Eingabe-Datei ausgewählt: {filepath}")
            self.log_output(f"Eingabe-Datei ausgewählt: {filepath}", "INFO")

    def log_output(self, message, level="INFO"):
        # ... (log_output remains the same) ...
        def _update_log():
            self.log_output_text.insert(tk.END, f"[{level}] {message}\n")
            self.log_output_text.see(tk.END)
        self.master.after(0, _update_log) # Ensure GUI update is thread-safe

<<<<<<< HEAD
    def display_output_text(self, text):
        # ... (display_output_text remains the same) ...
        def _update_output():
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert(tk.END, text)
        self.master.after(0, _update_output)
=======
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
# >>>>>>> 073e7e394be9531c1f93b959e26c439554bbd316

    def reactivate_buttons(self):
        # ... (reactivate_buttons remains the same) ...
        def _update_buttons():
            self.convert_midi_to_text_button.config(state=tk.NORMAL)
            self.convert_text_to_midi_button.config(state=tk.NORMAL)
            self.browse_button.config(state=tk.NORMAL)
        self.master.after(0, _update_buttons)

<<<<<<< HEAD
    def run_conversion(self, input_path, direction, llm_input_text):
        # ... (run_conversion structure remains similar, calls new midi_to_text) ...
        self.convert_midi_to_text_button.config(state=tk.DISABLED)
        self.convert_text_to_midi_button.config(state=tk.DISABLED)
        self.browse_button.config(state=tk.DISABLED)

        start_time = time.time()
        script_dir = os.path.dirname(__file__) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        output_folder = os.path.join(script_dir, OUTPUT_FOLDER_NAME)
        ensure_folder_exists(output_folder)

        error_occurred = False

        if direction == "->":
            logging.info(f"Verarbeite Input: {input_path}")
            logging.info("Starte MIDI -> LLM Text Konvertierung...")
            self.log_output(f"Verarbeite Input: {input_path}", "INFO")
            self.log_output("Starte MIDI -> LLM Text Konvertierung...", "INFO")
            try:
                if not input_path or not os.path.exists(input_path):
                     raise FileNotFoundError(f"Eingabedatei nicht gefunden oder nicht angegeben: {input_path}")

                midi_file = mido.MidiFile(input_path, clip=True)
                track_names = get_track_names(midi_file)

                # --- CALL THE REVISED midi_to_text ---
                midi_data_string = self.midi_to_text(midi_file, track_names)
                # ---

                guide_path = os.path.join(script_dir, GUIDE_PROMPT_FILENAME)
                if os.path.exists(guide_path):
                    # Read only Part 1 (description) as guide, Part 2 is for LLM prompt
                    # Or just use a simpler guide text if llm_guide... is complex
                    try:
                        with open(guide_path, 'r', encoding='utf-8') as f:
                             # Simple approach: Use a predefined simpler guide or the fallback
                             # guide_content = f.read() # Read the whole file if needed
                             guide_content = FALLBACK_GUIDE_TEXT # Use fallback for simplicity
                             logging.info(f"Verwende Guide-Text (Fallback oder vereinfacht).")

                    except Exception as read_err:
                         guide_content = FALLBACK_GUIDE_TEXT
                         logging.warning(f"Konnte Guide-Datei nicht lesen ({read_err}): {guide_path}. Benutze Fallback.")
                         self.log_output(f"Konnte Guide-Datei nicht lesen: {guide_path}. Benutze Fallback.", "WARNING")

                else:
                    guide_content = FALLBACK_GUIDE_TEXT
                    logging.warning(f"Guide-Datei nicht gefunden: {guide_path}. Benutze Fallback.")
                    self.log_output(f"Guide-Datei nicht gefunden: {guide_path}. Benutze Fallback.", "WARNING")

                output_basename = os.path.splitext(os.path.basename(input_path))[0]
                output_path = os.path.join(output_folder, f"{output_basename}_llm.txt") # Changed extension
                with open(output_path, 'w', encoding='utf-8') as f:
                    # Decide whether to include the guide in the output file
                    # f.write(guide_content + "\n\n##########\n\n") # Optional guide prefix
                    f.write(midi_data_string) # Write only the converted data

                logging.info(f"Konvertierte Datei gespeichert: {output_path}")
                self.log_output(f"Konvertierte Datei gespeichert: {output_path}", "INFO")
                # Display the converted data without the guide prefix in the GUI
                self.display_output_text(midi_data_string)

            except FileNotFoundError as e:
                error_occurred = True
                logging.error(f"FEHLER: {e}")
                self.log_output(f"FEHLER: {e}", "ERROR")
                self.display_output_text(f"FEHLER:\n{e}")
            except mido.ParserError as e:
                error_occurred = True
                logging.error(f"MIDI Parsing FEHLER: {e}. Ist die Datei gültig?")
                self.log_output(f"MIDI Parsing FEHLER: {e}. Ist die Datei gültig?", "ERROR")
                self.display_output_text(f"MIDI Parsing FEHLER:\n{e}")
            except Exception as e:
                error_occurred = True
                logging.exception("Ein unerwarteter Fehler ist bei der MIDI->Text Konvertierung aufgetreten:")
                self.log_output(f"FEHLER: {e}", "ERROR")
                self.display_output_text(f"FEHLER:\n{e}")

        # ... (rest of run_conversion: Text->MIDI, error handling, timing, reactivate_buttons) ...
        elif direction == "<-":
            error_occurred = True
            output_midi_path = os.path.join(output_folder, "output.mid")
            logging.info(f"LLM Text -> MIDI Konvertierung nach: {output_midi_path}")
            logging.error("Text -> MIDI Konvertierung ist noch nicht implementiert.")
            self.log_output(f"LLM Text -> MIDI Konvertierung nach: {output_midi_path}", "INFO")
            self.log_output("Text -> MIDI Konvertierung ist noch nicht implementiert.", "ERROR")
            self.display_output_text("FEHLER: Text -> MIDI Konvertierung ist nicht implementiert.")
        else:
            error_occurred = True
            logging.error(f"Ungültige Konvertierungsrichtung: {direction}")
            self.log_output(f"Ungültige Konvertierungsrichtung: {direction}", "ERROR")
            self.display_output_text(f"FEHLER: Ungültige Konvertierungsrichtung: {direction}")

        end_time = time.time()
        duration = end_time - start_time

        if error_occurred:
            logging.info(f"Konvertierung mit FEHLERN beendet in {duration:.2f} Sekunden.")
            self.log_output(f"Konvertierung mit FEHLERN beendet in {duration:.2f} Sekunden.", "INFO")
        else:
            logging.info(f"Konvertierung abgeschlossen in {duration:.2f} Sekunden.")
            self.log_output(f"Konvertierung abgeschlossen in {duration:.2f} Sekunden.", "INFO")

        self.reactivate_buttons()


    # --- REVISED midi_to_text METHOD ---
    def midi_to_text(self, midi_file, track_names):
        """
        Converts a MIDI file to a text representation following the LLM guide format.
        """
        output_lines = []

        # --- Global Metadata Extraction ---
        key_signature = DEFAULT_KEY_SIGNATURE
        initial_tempo = DEFAULT_TEMPO
        initial_time_signature = DEFAULT_TIME_SIGNATURE
        ticks_per_beat = midi_file.ticks_per_beat if midi_file.ticks_per_beat > 0 else DEFAULT_TICKS_PER_BEAT

        if midi_file.ticks_per_beat <= 0:
            logging.warning(f"MIDI file has invalid ticks_per_beat ({midi_file.ticks_per_beat}). Using default: {DEFAULT_TICKS_PER_BEAT}")
            self.log_output(f"MIDI file has invalid ticks_per_beat ({midi_file.ticks_per_beat}). Using default: {DEFAULT_TICKS_PER_BEAT}", "WARNING")

        # Find first key, tempo, time signature (usually in track 0)
        # Tempo might change later, but we need an initial value for calculations.
        found_key, found_tempo, found_time_sig = False, False, False
        for msg in midi_file.tracks[0]:
            if not found_tempo and msg.type == 'set_tempo':
                initial_tempo = mido.tempo2bpm(msg.tempo)
                found_tempo = True
            elif not found_key and msg.type == 'key_signature':
                key_signature = msg.key
                found_key = True
            elif not found_time_sig and msg.type == 'time_signature':
                initial_time_signature = (msg.numerator, msg.denominator)
                found_time_sig = True
            if found_key and found_tempo and found_time_sig:
                break

        output_lines.append(f"Key: {key_signature}")

        # --- Process Each Track ---
        for track_index, track in enumerate(midi_file.tracks):
            track_name = track_names.get(track_index, f"Track {track_index}")
            logging.info(f"Processing Track {track_index}: {track_name}")

            # Store events with absolute ticks: (tick, type, data)
            events = []
            current_tick = 0
            active_notes = {}  # {note_num: {'start_tick': tick, 'velocity': vel}}

            for msg in track:
                current_tick += msg.time
                msg_type = msg.type

                if msg_type == 'note_on' and msg.velocity > 0:
                    note_num = msg.note
                    if note_num in active_notes: # Handle note re-trigger before note_off (overlap)
                         logging.warning(f"Track {track_index}: Note {note_num} re-triggered at tick {current_tick} before note_off. Handling previous note.")
                         # Treat previous note as ending just before this one
                         prev_note = active_notes[note_num]
                         events.append({'tick': prev_note['start_tick'], 'type': 'note',
                                        'pitch': note_num, 'velocity': prev_note['velocity'],
                                        'duration': current_tick - prev_note['start_tick']})
                         del active_notes[note_num]

                    active_notes[note_num] = {'start_tick': current_tick, 'velocity': msg.velocity}

                elif msg_type == 'note_off' or (msg_type == 'note_on' and msg.velocity == 0):
                    note_num = msg.note
                    if note_num in active_notes:
                        start_tick = active_notes[note_num]['start_tick']
                        velocity = active_notes[note_num]['velocity']
                        duration = current_tick - start_tick
                        if duration > 0: # Ignore zero-duration notes
                             events.append({'tick': start_tick, 'type': 'note',
                                            'pitch': note_num, 'velocity': velocity,
                                            'duration': duration})
                        else:
                             logging.warning(f"Track {track_index}: Ignoring zero-duration note {note_num} at tick {start_tick}")
                        del active_notes[note_num]
                    # else: ignore note_off without matching note_on

                elif msg_type == 'time_signature':
                    events.append({'tick': current_tick, 'type': 'timesig',
                                   'numerator': msg.numerator, 'denominator': msg.denominator})
                # Add other relevant events if needed (e.g., tempo changes, specific CCs for dynamics)
                # For now, dynamics are derived from note velocity only.

            # Handle notes still active at the end of the track
            for note_num, note_data in active_notes.items():
                 logging.warning(f"Track {track_index}: Note {note_num} still active at end of track (tick {note_data['start_tick']}). Assigning arbitrary duration.")
                 # Assign a default duration (e.g., 1 beat) or calculate to end_of_track if available
                 duration = ticks_per_beat # Default to 1 beat duration
                 events.append({'tick': note_data['start_tick'], 'type': 'note',
                                'pitch': note_num, 'velocity': note_data['velocity'],
                                'duration': duration})


            # --- Second Pass: Sort events and create musical objects ---
            events.sort(key=lambda x: x['tick'])

            musical_objects = [] # Stores {'tick': t, 'obj': FormattedString | OtherMarker}
            last_event_end_tick = 0
            current_dynamic = None
            current_time_sig = initial_time_signature # Use initial time sig for the whole track as per guide limitation

            # Calculate ticks per measure based *only* on the initial time signature
            # This is a limitation specified in the llm_guide.txt
            ticks_per_measure = calculate_ticks_per_measure(initial_time_signature, ticks_per_beat)
            if ticks_per_measure <= 0:
                 logging.error(f"Track {track_index}: Invalid ticks_per_measure ({ticks_per_measure}). Skipping track formatting.")
                 continue # Skip this track if measure calculation fails


            for event in events:
                event_tick = event['tick']

                # --- Add Rests ---
                rest_duration = event_tick - last_event_end_tick
                if rest_duration > 5: # Add rests for significant gaps (tolerance for timing jitter)
                    rest_code = ticks_to_duration_code(rest_duration, ticks_per_beat, current_time_sig[1])
                    # Check for whole measure rests (needs measure context, handle later)
                    musical_objects.append({'tick': last_event_end_tick, 'type': 'rest', 'code': f"R{rest_code}"})

                # --- Process Event ---
                if event['type'] == 'note':
                    # Check for dynamic change *before* the note
                    dynamic_symbol = velocity_to_dynamic(event['velocity'])
                    if dynamic_symbol != current_dynamic:
                        musical_objects.append({'tick': event_tick, 'type': 'dynamic', 'code': f"dyn({dynamic_symbol})"})
                        current_dynamic = dynamic_symbol

                    # Add the note object (duration code calculated later)
                    musical_objects.append({
                        'tick': event_tick,
                        'type': 'note',
                        'pitch_num': event['pitch'], # Keep number for sorting chords
                        'pitch_str': midi_note_to_llm_pitch(event['pitch']),
                        'duration_ticks': event['duration']
                    })
                    last_event_end_tick = event_tick + event['duration']

                elif event['type'] == 'timesig':
                     # As per guide, just insert the marker, don't change measure calculation
                     ts_code = f"[{event['numerator']}/{event['denominator']}]"
                     musical_objects.append({'tick': event_tick, 'type': 'timesig', 'code': ts_code})
                     # Do NOT update current_time_sig or ticks_per_measure here based on guide
                     # last_event_end_tick = max(last_event_end_tick, event_tick) # Time sigs are instantaneous

                # Add handlers for other event types if needed

            # --- Third Pass: Format into string with chords and bar lines ---
            musical_objects.sort(key=lambda x: x['tick']) # Ensure order

            track_string = f"T{track_index} {track_name}:\n"
            track_line = [] # Build the line element by element
            current_measure = 0
            last_tick_in_measure = 0
            last_obj_tick = 0

            # Group simultaneous notes into chords
            i = 0
            while i < len(musical_objects):
                obj = musical_objects[i]
                tick = obj['tick']

                # --- Add Bar Lines ---
                measure_at_tick = tick // ticks_per_measure
                if measure_at_tick > current_measure:
                    # Add bar line for previous measure(s)
                    for m in range(current_measure + 1, measure_at_tick + 1):
                         bar_num_marker = f" {m}" if (m == 1 or m % 5 == 0) else ""
                         track_line.append(f"|{bar_num_marker}")
                    current_measure = measure_at_tick
                    last_tick_in_measure = tick # Reset for new measure

                # --- Handle object type ---
                obj_type = obj['type']

                if obj_type == 'note':
                    # Check for chord: Look ahead for notes at the same tick
                    chord_notes = [obj]
                    j = i + 1
                    while j < len(musical_objects) and musical_objects[j]['tick'] == tick and musical_objects[j]['type'] == 'note':
                        chord_notes.append(musical_objects[j])
                        j += 1

                    # Sort notes within chord by pitch number
                    chord_notes.sort(key=lambda n: n['pitch_num'])
                    pitches = [n['pitch_str'] for n in chord_notes]

                    # Duration: Use the maximum duration of notes in the chord
                    # (Simplification: assumes chord notes end together, which might not be true)
                    # A more robust way would track individual note offs, but gets complex.
                    max_duration_ticks = max(n['duration_ticks'] for n in chord_notes)
                    duration_code = ticks_to_duration_code(max_duration_ticks, ticks_per_beat, current_time_sig[1])

                    if len(pitches) > 1:
                        track_line.append(f"{'+'.join(pitches)}{duration_code}")
                    else:
                        track_line.append(f"{pitches[0]}{duration_code}")

                    i = j # Move index past the consumed chord notes
                    last_obj_tick = tick + max_duration_ticks # Update last tick based on chord duration

                elif obj_type == 'rest' or obj_type == 'dynamic' or obj_type == 'timesig':
                    track_line.append(obj['code'])
                    i += 1
                    last_obj_tick = max(last_obj_tick, tick) # Rests/markers don't advance end tick much
                else:
                    i += 1 # Skip unknown object types

            # Add final bar line
            track_line.append("|")

            # Join the elements with spaces
            track_string += " ".join(track_line)
            output_lines.append(track_string)


        # --- Combine Tracks ---
        return "\n\n".join(output_lines)

# --- Main ---
# =======
    def display_output_text(self, text_content):
        """Zeigt den Textinhalt im Textbereich an."""
        self.text_area.configure(state='normal')
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert('1.0', text_content)
        self.text_area.configure(state='disabled')

# --- Hauptteil ---
# >>>>>>> 073e7e394be9531c1f93b959e26c439554bbd316
if __name__ == "__main__":
    setup_logging()
    try:
        root = tk.Tk()
        app = MidiConverterApp(root)
        root.mainloop()
    except Exception as e:
        logging.exception("Schwerwiegender Fehler beim Starten oder Ausführen der Anwendung:")
        try:
            import tkinter.messagebox
            tkinter.messagebox.showerror("Fatal Error", f"A critical error occurred:\n{e}\n\nCheck the logs for details.")
        except Exception as inner_e:
            print(f"FATAL ERROR: {e}")
            print(f"Messagebox Error: {inner_e}")

# --- Tests ---
# Keep the existing test classes, but they will likely need significant updates
# to mock the new behavior and assert the new output format.
# Mocking mido.MidiFile will need to provide tracks with realistic note_on/note_off pairs.
# Assertions will check for the specific LLM format string.

# Example of how TestRunConversion might need changes:
class TestRunConversion(unittest.TestCase):

     # Mock setup needs to be robust
     @patch('tkinter.Tk')
     @patch('tkinter.ttk.LabelFrame')
     @patch('tkinter.ttk.Label')
     @patch('tkinter.ttk.Entry')
     @patch('tkinter.ttk.Button')
     @patch('tkinter.scrolledtext.ScrolledText')
     @patch('tkinter.StringVar')
     @patch('tkinter.filedialog.askopenfilename')
     @patch('mido.MidiFile') # Mock the MidiFile class
     @patch('builtins.open', new_callable=mock_open) # Mock file open
     @patch('os.path.exists')
     @patch('os.makedirs') # Mock folder creation
     @patch('time.time')
     @patch('logging.getLogger') # Mock the logger to check calls
     def setUp(self, mock_get_logger, mock_time, mock_makedirs, mock_exists, mock_open_func,
               mock_mido, mock_askopenfilename, mock_stringvar, mock_scrolledtext,
               mock_button, mock_entry, mock_label, mock_labelframe, mock_tk):

         # --- Mock Logger ---
         self.mock_logger = MagicMock()
         # Prevent clear handlers error if setup_logging is called multiple times
         self.mock_logger.hasHandlers.return_value = False
         mock_get_logger.return_value = self.mock_logger

         # --- Mock Time ---
         mock_time.side_effect = [1000.0, 1001.5] # Example start/end times

         # --- Mock Filesystem ---
         mock_exists.side_effect = lambda path: 'llm_guide.txt' not in path # Assume guide doesn't exist for simplicity
         self.mock_open_func = mock_open_func

         # --- Mock MIDI Data ---
         self.mock_mid = MagicMock(spec=mido.MidiFile)
         self.mock_mid.ticks_per_beat = 480
         # Define realistic track data with note_on/note_off
         track0 = mido.MidiTrack([
             mido.MetaMessage('track_name', name='Control', time=0),
             mido.MetaMessage('key_signature', key='C', time=0),
             mido.MetaMessage('time_signature', numerator=4, denominator=4, time=0),
             mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120), time=0),
             mido.MetaMessage('end_of_track', time=1)
         ])
         track1 = mido.MidiTrack([
             mido.MetaMessage('track_name', name='Piano', time=0),
             # Measure 1: C4 quarter, E4 quarter, G4 half
             mido.Message('note_on', note=60, velocity=80, time=0),    # C4 on @ 0
             mido.Message('note_off', note=60, velocity=0, time=480),   # C4 off @ 480 (1 beat)
             mido.Message('note_on', note=64, velocity=80, time=0),    # E4 on @ 480
             mido.Message('note_off', note=64, velocity=0, time=480),   # E4 off @ 960 (1 beat)
             mido.Message('note_on', note=67, velocity=70, time=0),    # G4 on @ 960
             mido.Message('note_off', note=67, velocity=0, time=960),   # G4 off @ 1920 (2 beats)
             # Measure 2: Rest quarter, F4 quarter (pp), Rest half
             # Note: Rest is implicit gap here
             mido.Message('note_on', note=65, velocity=30, time=480), # F4 on @ 1920+480 = 2400
             mido.Message('note_off', note=65, velocity=0, time=480),  # F4 off @ 2400+480 = 2880
             mido.MetaMessage('end_of_track', time=960) # End after half rest (2880+960 = 3840)
         ])
         self.mock_mid.tracks = [track0, track1]
         mock_mido.return_value = self.mock_mid

         # --- Mock GUI ---
         self.mock_master = MagicMock()
         # Mock the 'after' method to call callbacks immediately for testing
         self.mock_master.after = lambda delay, func: func()
         self.app = MidiConverterApp(self.mock_master)

         # Mock specific GUI methods if needed (e.g., to check calls)
         self.app.log_output = MagicMock()
         self.app.display_output_text = MagicMock()
         self.app.reactivate_buttons = MagicMock() # Mock to check if called

         # Mock input values
         self.app.input_path_var.get.return_value = "test.mid"
         self.app.llm_text_input.get.return_value = "Some LLM text" # Not used in this direction


     def test_midi_to_text_conversion_llm_format(self):
         """Test MIDI to Text conversion produces the correct LLM format."""
         self.app.run_conversion("test.mid", "->", "") # Run the conversion

         # --- Assertions ---
         # 1. Check if logger was called correctly (example)
         self.mock_logger.info.assert_any_call("Processing Track 1: Piano")

         # 2. Check the final output displayed/written
         # Expected output based on mocked MIDI data and LLM format rules
         expected_output = (
             "Key: C\n\n"
             "T1 Piano:\n"
             " | 1 C4/4 E4/4 G4/2 | 2 R/4 dyn(pp) F4/4 R/2 |" # Note: Rests are tricky, this is an idealization
         )
         # Check the text displayed in the GUI
         self.app.display_output_text.assert_called_once()
         call_args, _ = self.app.display_output_text.call_args
         actual_output = call_args[0]

         # Normalize whitespace for comparison (flexible)
         normalize = lambda s: " ".join(s.split())
         self.assertEqual(normalize(actual_output), normalize(expected_output),
                          f"Expected:\n{expected_output}\nGot:\n{actual_output}")

         # 3. Check if file was written correctly (optional)
         # self.mock_open_func.assert_called_with(os.path.join('output', 'test_llm.txt'), 'w', encoding='utf-8')
         # handle = self.mock_open_func()
         # written_content = "".join(call[0][0] for call in handle.write.call_args_list)
         # self.assertEqual(normalize(written_content), normalize(expected_output)) # Assuming no guide prefix

         # 4. Check if buttons were reactivated
         self.app.reactivate_buttons.assert_called_once()

         # 5. Check final log message
         self.app.log_output.assert_any_call("Konvertierung abgeschlossen in 1.50 Sekunden.", "INFO")


# --- Test Helper Functions ---
class TestMidiConverterHelpersLLM(unittest.TestCase):

     def test_ticks_to_duration_code(self):
         tpb = 480
         self.assertEqual(ticks_to_duration_code(1920, tpb), '/1') # Whole
         self.assertEqual(ticks_to_duration_code(960, tpb), '/2')  # Half
         self.assertEqual(ticks_to_duration_code(480, tpb), '/4')  # Quarter
         self.assertEqual(ticks_to_duration_code(240, tpb), '/8')  # Eighth
         self.assertEqual(ticks_to_duration_code(120, tpb), '/16') # Sixteenth
         self.assertEqual(ticks_to_duration_code(60, tpb), '/32')  # 32nd
         self.assertEqual(ticks_to_duration_code(30, tpb), '/64')  # 64th
         # Dotted
         self.assertEqual(ticks_to_duration_code(720, tpb), '/4.') # Dotted Quarter
         self.assertEqual(ticks_to_duration_code(360, tpb), '/8.') # Dotted Eighth
         self.assertEqual(ticks_to_duration_code(1440, tpb), '/2.')# Dotted Half
         # Approx / Inexact
         self.assertEqual(ticks_to_duration_code(475, tpb), '/4')  # Close enough to quarter
         self.assertEqual(ticks_to_duration_code(710, tpb), '/4.') # Close enough to dotted quarter
         self.assertEqual(ticks_to_duration_code(50, tpb), '/?')   # Too far from /32 or /64
         self.assertEqual(ticks_to_duration_code(0, tpb), '/?')
         self.assertEqual(ticks_to_duration_code(1000, tpb), '/?') # Between /2 and /2.

     def test_calculate_ticks_per_measure(self):
         self.assertEqual(calculate_ticks_per_measure((4, 4), 480), 1920)
         self.assertEqual(calculate_ticks_per_measure((3, 4), 480), 1440)
         self.assertEqual(calculate_ticks_per_measure((6, 8), 480), 1440) # 6 * (4/8) * 480 = 6 * 0.5 * 480
         self.assertEqual(calculate_ticks_per_measure((2, 2), 480), 1920) # 2 * (4/2) * 480 = 2 * 2 * 480
         self.assertEqual(calculate_ticks_per_measure((4, 0), 480), 1920) # Handles invalid denominator


# --- Run Tests ---
# (Keep the test execution logic if you use it)
# Example:
# if __name__ == '__main__':
#     # Check if running tests is intended
#     if len(sys.argv) > 1 and sys.argv[1] == 'test':
#         logging.disable(logging.CRITICAL) # Disable logging during tests
#         sys.argv.pop(1)
#         # Add the new test suite
#         suite = unittest.TestSuite()
#         suite.addTest(unittest.makeSuite(TestRunConversion))
#         suite.addTest(unittest.makeSuite(TestMidiConverterHelpersLLM))
#         # Add previous helper tests if they exist:
#         # suite.addTest(unittest.makeSuite(TestMidiConverterHelpers))
#         runner = unittest.TextTestRunner(verbosity=2)
#         runner.run(suite)
#     else:
#         # Run the application (already handled above the test section)
#         pass
