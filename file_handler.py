from typing import Optional
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import os
import sys
import logging
import threading
import time
import datetime
import platform # Für Standardpfade
# import queue # Potenziell benötigt für komplexere Thread-Kommunikation

# --- Module importieren ---
try: import config
except ImportError: print("FEHLER: config.py nicht gefunden."); sys.exit(1)
try: import logger_setup
except ImportError: print("FEHLER: logger_setup.py nicht gefunden."); sys.exit(1)
try: import utils
except ImportError: print("FEHLER: utils.py nicht gefunden."); sys.exit(1)
try: import midi_parser
except ImportError: print("FEHLER: midi_parser.py nicht gefunden."); sys.exit(1)
try: import llm_converter
except ImportError: print("FEHLER: llm_converter.py nicht gefunden."); sys.exit(1)
try: import file_handler
except ImportError: print("FEHLER: file_handler.py nicht gefunden."); sys.exit(1)
try: import settings_manager # NEU
except ImportError: print("FEHLER: settings_manager.py nicht gefunden."); sys.exit(1)
# --- Ende Imports ---


class MidiConverterApp:
    """
    Hauptklasse für die MIDI-Konverter GUI-Anwendung.
    Verwaltet die Benutzeroberfläche und orchestriert die Konvertierungsprozesse.
    Enthält Logik zum Finden/Konfigurieren des MuseScore-Pfades.
    """
    def __init__(self, master):
        """Initialisiert die GUI, das Logging und den MuseScore-Pfad."""
        self.master = master
        master.title("MIDI zu LLM Konverter")

        # Logging zuerst einrichten (wird jetzt extern gemacht)
        # logger_setup.setup_logging() # Wird jetzt außerhalb der Klasse aufgerufen

        self.musescore_path: Optional[str] = None # Instanzvariable für den Pfad
        self._setup_musescore_path() # Finde/Konfiguriere MuseScore Pfad

        # --- GUI Elemente (wie zuvor) ---
        main_frame = ttk.Frame(master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        # ... (Rest der GUI-Elemente wie in der letzten Version von main.py) ...
         # --- Eingabe-Frame ---
        input_frame = ttk.LabelFrame(main_frame, text="Eingabe (MIDI / MuseScore)") # Text angepasst
        input_frame.pack(padx=5, pady=5, fill=tk.X)

        self.input_path_var = tk.StringVar()
        ttk.Label(input_frame, text="Datei:").pack(side=tk.LEFT, padx=(0, 5), pady=5)
        self.input_path_entry = ttk.Entry(input_frame, textvariable=self.input_path_var, width=60)
        self.input_path_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        self.browse_button = ttk.Button(input_frame, text="Durchsuchen...", command=self.browse_file)
        self.browse_button.pack(side=tk.LEFT, padx=(5, 0), pady=5)

        # --- Ausgabe/Ergebnis-Frame ---
        output_frame = ttk.LabelFrame(main_frame, text="Ausgabe (LLM Notation)")
        output_frame.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, width=80, height=20, state=tk.DISABLED)
        self.output_text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        # --- Steuerungs-Frame ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(padx=5, pady=5, fill=tk.X)

        self.convert_midi_to_text_button = ttk.Button(control_frame, text="Konvertieren -> Text", command=lambda: self.start_conversion_thread("->")) # Text angepasst
        self.convert_midi_to_text_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.convert_text_to_midi_button = ttk.Button(control_frame, text="Text -> MIDI", command=lambda: self.start_conversion_thread("<-"), state=tk.DISABLED)
        self.convert_text_to_midi_button.pack(side=tk.LEFT, padx=5, pady=5)

        # --- Logging-Frame ---
        logging_frame = ttk.LabelFrame(main_frame, text="Log")
        logging_frame.pack(padx=5, pady=5, fill=tk.X)

        self.log_output_text = scrolledtext.ScrolledText(logging_frame, wrap=tk.WORD, width=80, height=10, state=tk.DISABLED)
        self.log_output_text.pack(padx=5, pady=5, fill=tk.X)

        # --- Initialisierung ---
        self.log_output("GUI initialisiert.", "INFO")
        self.display_output_text("Bitte wählen Sie eine MIDI- oder MuseScore-Datei und starten Sie die Konvertierung.")


    def _is_valid_musescore_path(self, path: Optional[str]) -> bool:
        """Prüft, ob ein Pfad existiert und eine Datei ist."""
        if path and os.path.exists(path) and os.path.isfile(path):
            # Optional: Weitere Prüfungen (z.B. Dateiname endet auf .exe unter Windows)
            return True
        return False

    def _setup_musescore_path(self):
        """Lädt, prüft, sucht oder erfragt den Pfad zur MuseScore-Executable."""
        logging.info("Suche nach MuseScore-Pfad...")
        loaded_path = settings_manager.load_musescore_path()

        if self._is_valid_musescore_path(loaded_path):
            logging.info(f"Gültiger MuseScore-Pfad aus Einstellungen geladen: {loaded_path}")
            self.musescore_path = loaded_path
            return

        if loaded_path:
            logging.warning(f"Gespeicherter MuseScore-Pfad '{loaded_path}' ist ungültig. Suche erneut...")
        else:
            logging.info("Kein MuseScore-Pfad in Einstellungen gefunden. Suche Standardpfade...")

        # Standardpfade prüfen (aus config.py)
        # TODO: Wildcard-Suche für Linux AppImages implementieren (z.B. mit glob)
        # TODO: Suche im System-PATH implementieren (z.B. mit shutil.which)
        for default_path in getattr(config, 'DEFAULT_MUSESCORE_PATHS', []):
             # Einfache Existenzprüfung hier, ggf. erweitern
             if self._is_valid_musescore_path(default_path):
                 logging.info(f"MuseScore in Standardpfad gefunden: {default_path}")
                 if settings_manager.save_musescore_path(default_path):
                     logging.info("Standardpfad erfolgreich in Einstellungen gespeichert.")
                 else:
                     logging.warning("Konnte gefundenen Standardpfad nicht in Einstellungen speichern.")
                 self.musescore_path = default_path
                 return

        logging.warning("MuseScore wurde weder in den Einstellungen noch in Standardpfaden gefunden.")

        # Benutzer fragen
        user_agrees = messagebox.askyesno(
            title="MuseScore Pfad benötigt",
            message="MuseScore 4 konnte nicht automatisch gefunden werden.\n\n"
                    "Um MuseScore-Dateien (.mscz/.mscx) konvertieren zu können, "
                    "muss der Pfad zur MuseScore 4-Executable bekannt sein.\n\n"
                    "Möchten Sie jetzt manuell danach suchen?"
        )

        if not user_agrees:
            logging.warning("Benutzer hat manuelle Suche nach MuseScore abgelehnt. MuseScore-Konvertierung deaktiviert.")
            self.log_output("WARNUNG: MuseScore nicht gefunden. .mscz/.mscx Konvertierung nicht möglich.", "WARNING")
            self.musescore_path = None
            return

        # Dateidialog anzeigen
        filetypes = []
        if sys.platform == "win32":
            filetypes = [("MuseScore Executable", "MuseScore4.exe"), ("Alle Dateien", "*.*")]
        elif sys.platform == "darwin":
             # Auf macOS wählt man normalerweise die .app-Datei, aber wir brauchen die Executable darin
             # Besser den Benutzer informieren, wo er sie findet, oder einen Ordnerdialog?
             # Vorerst allgemeiner Dialog
             messagebox.showinfo("macOS Hinweis", "Bitte navigieren Sie zum MuseScore 4 Programm, klicken Sie mit der rechten Maustaste darauf, wählen Sie 'Paketinhalt zeigen' und navigieren Sie dann zu 'Contents/MacOS/mscore'. Wählen Sie die Datei 'mscore' aus.")
             filetypes = [("Alle Dateien", "*")] # Benutzer muss manuell navigieren
        else: # Linux
             filetypes = [("Alle Dateien", "*")] # AppImage oder Binary

        user_path = filedialog.askopenfilename(
            title="Bitte wählen Sie die MuseScore 4 Executable",
            filetypes=filetypes
        )

        if user_path and self._is_valid_musescore_path(user_path):
            logging.info(f"Benutzer hat gültigen MuseScore-Pfad ausgewählt: {user_path}")
            if settings_manager.save_musescore_path(user_path):
                logging.info("Benutzerdefinierter Pfad erfolgreich in Einstellungen gespeichert.")
            else:
                logging.warning("Konnte benutzerdefinierten Pfad nicht in Einstellungen speichern.")
            self.musescore_path = user_path
            self.log_output(f"MuseScore-Pfad gesetzt: {os.path.basename(user_path)}", "INFO")
        else:
            logging.error(f"Benutzer hat keinen gültigen Pfad ausgewählt oder abgebrochen. Auswahl: '{user_path}'")
            messagebox.showerror("Fehler", "Der ausgewählte Pfad ist ungültig oder es wurde keine Datei ausgewählt.\n\nMuseScore-Konvertierung wird für diese Sitzung deaktiviert.")
            self.log_output("FEHLER: Ungültiger MuseScore-Pfad ausgewählt. .mscz/.mscx Konvertierung nicht möglich.", "ERROR")
            self.musescore_path = None


    def browse_file(self):
        """Öffnet einen Dateidialog zur Auswahl der Eingabedatei (MIDI oder MuseScore)."""
        filetypes = [
            ("Musikdateien", "*.mid *.midi *.mscz *.mscx"),
            ("MIDI", "*.mid *.midi"),
            ("MuseScore", "*.mscz *.mscx"),
            ("Alle Dateien", "*.*")
        ]
        filepath = filedialog.askopenfilename(
            title="MIDI- oder MuseScore-Datei auswählen",
            filetypes=filetypes
        )
        if filepath:
            self.input_path_var.set(filepath)
            logging.info(f"Eingabe-Datei ausgewählt: {filepath}")
            self.log_output(f"Eingabe-Datei ausgewählt: {os.path.basename(filepath)}", "INFO")
            self.convert_midi_to_text_button.config(state=tk.NORMAL)


    def log_output(self, message, level="INFO"):
        """Schreibt eine Nachricht in das Log-Textfeld (Thread-sicher)."""
        # (Implementierung bleibt gleich)
        def _update_log():
            if hasattr(self, 'log_output_text') and self.log_output_text.winfo_exists():
                self.log_output_text.config(state=tk.NORMAL)
                self.log_output_text.insert(tk.END, f"[{level}] {message}\n")
                self.log_output_text.see(tk.END) # Zum Ende scrollen
                self.log_output_text.config(state=tk.DISABLED)
        if hasattr(self, 'master') and self.master.winfo_exists():
             self.master.after(0, _update_log)


    def display_output_text(self, text):
        """Zeigt Text im Haupt-Ausgabefeld an (Thread-sicher)."""
        # (Implementierung bleibt gleich)
        def _update_output():
             if hasattr(self, 'output_text') and self.output_text.winfo_exists():
                self.output_text.config(state=tk.NORMAL)
                self.output_text.delete("1.0", tk.END)
                self.output_text.insert(tk.END, text)
                self.output_text.config(state=tk.DISABLED)
        if hasattr(self, 'master') and self.master.winfo_exists():
            self.master.after(0, _update_output)


    def reactivate_buttons(self):
        """Aktiviert die Steuerungselemente nach Abschluss der Konvertierung (Thread-sicher)."""
        # (Implementierung bleibt gleich)
        def _update_buttons():
            if hasattr(self, 'convert_midi_to_text_button') and self.convert_midi_to_text_button.winfo_exists():
                 self.convert_midi_to_text_button.config(state=tk.NORMAL)
            # if hasattr(self, 'convert_text_to_midi_button') and self.convert_text_to_midi_button.winfo_exists():
            #    self.convert_text_to_midi_button.config(state=tk.NORMAL) # Aktivieren, wenn implementiert
            if hasattr(self, 'browse_button') and self.browse_button.winfo_exists():
                 self.browse_button.config(state=tk.NORMAL)
            if hasattr(self, 'input_path_entry') and self.input_path_entry.winfo_exists():
                 self.input_path_entry.config(state=tk.NORMAL)
        if hasattr(self, 'master') and self.master.winfo_exists():
            self.master.after(0, _update_buttons)


    def start_conversion_thread(self, direction):
        """Startet den Konvertierungsprozess in einem separaten Thread."""
        # (Implementierung bleibt weitgehend gleich, prüft nur Input)
        input_path = self.input_path_var.get()

        if direction == "->" and (not input_path or not os.path.exists(input_path)):
            messagebox.showerror("Fehler", "Bitte wählen Sie eine gültige Eingabedatei aus.")
            logging.error("Konvertierungsstart abgebrochen: Keine gültige Eingabedatei.")
            self.log_output("FEHLER: Keine gültige Eingabedatei ausgewählt!", "ERROR")
            return

        if direction == "<-":
             messagebox.showwarning("Nicht implementiert", "Die Konvertierung von Text zu MIDI ist noch nicht verfügbar.")
             logging.warning("Konvertierungsstart abgebrochen: Text -> MIDI nicht implementiert.")
             self.log_output("WARNUNG: Text -> MIDI Konvertierung nicht implementiert.", "WARNING")
             return

        # GUI-Elemente deaktivieren
        self.convert_midi_to_text_button.config(state=tk.DISABLED)
        self.convert_text_to_midi_button.config(state=tk.DISABLED)
        self.browse_button.config(state=tk.DISABLED)
        self.input_path_entry.config(state=tk.DISABLED)
        self.display_output_text("Konvertierung läuft...")

        logging.info(f"Starte Konvertierung ({direction}) für: {input_path}")
        self.log_output(f"Starte Konvertierung ({direction}) für: {os.path.basename(input_path)}...", "INFO")

        thread = threading.Thread(target=self.run_conversion, args=(input_path, direction), daemon=True)
        thread.start()


    def run_conversion(self, input_path, direction):
        """
        Führt die eigentliche Konvertierung durch (läuft in einem separaten Thread).
        Beinhaltet jetzt die Logik zur MuseScore-Konvertierung.
        """
        start_time = time.time()
        error_occurred = False
        result_message = "Ein unbekannter Fehler ist aufgetreten."
        guide_content = ""
        temp_midi_path = None # Pfad für temporär erstellte MIDI-Datei

        try:
            # Basispfad ermitteln
            if getattr(sys, 'frozen', False):
                script_dir = os.path.dirname(sys.executable)
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            output_folder = os.path.join(script_dir, config.OUTPUT_FOLDER_NAME)
            file_handler.ensure_folder_exists(output_folder)

            # Guide-Datei lesen
            guide_path = os.path.join(script_dir, config.GUIDE_PROMPT_FILENAME)
            logging.info(f"Versuche Guide-Datei zu lesen: {guide_path}")
            guide_content = file_handler.read_guide_file(guide_path)
            if guide_content is None:
                 guide_content = "FEHLER: Guide-Datei nicht gefunden oder konnte nicht gelesen werden."
                 self.log_output(f"WARNUNG: Guide-Datei '{config.GUIDE_PROMPT_FILENAME}' nicht gefunden/lesbar.", "WARNING")
            else:
                 self.log_output(f"Guide-Datei '{config.GUIDE_PROMPT_FILENAME}' geladen.", "INFO")

            if direction == "->":
                logging.info("MIDI -> LLM Text Konvertierungsprozess gestartet.")
                midi_input_path = input_path

                # --- NEU: MuseScore-Konvertierung, falls nötig ---
                if input_path.lower().endswith(('.mscz', '.mscx')):
                    if not self.musescore_path:
                         raise RuntimeError("MuseScore-Pfad ist nicht konfiguriert, Konvertierung von .mscz/.mscx nicht möglich.")

                    # Erzeuge temporären Pfad im Output-Ordner
                    temp_midi_basename = f"{os.path.splitext(os.path.basename(input_path))[0]}_temp.mid"
                    temp_midi_path = os.path.join(output_folder, temp_midi_basename)
                    logging.info(f"Versuche '{input_path}' nach '{temp_midi_path}' mit MuseScore zu konvertieren...")
                    self.log_output(f"Konvertiere {os.path.basename(input_path)} mit MuseScore...", "INFO")

                    # Rufe file_handler auf und übergebe den konfigurierten Pfad
                    success = file_handler.convert_musescore_to_midi(
                        mscore_exec_path=self.musescore_path, # Übergebe den Pfad
                        input_msc_path=input_path,
                        output_midi_path=temp_midi_path
                    )

                    if success:
                        midi_input_path = temp_midi_path # Verwende die konvertierte MIDI-Datei
                        logging.info(f"MuseScore-Datei erfolgreich nach {temp_midi_path} konvertiert.")
                        self.log_output(f"MuseScore-Konvertierung erfolgreich.", "INFO")
                    else:
                        # Fehler wurde bereits in file_handler geloggt
                        self.log_output(f"FEHLER bei MuseScore-Konvertierung für {os.path.basename(input_path)}.", "ERROR")
                        raise RuntimeError(f"MuseScore-Konvertierung für {input_path} fehlgeschlagen.")
                # --- Ende MuseScore-Konvertierung ---

                # MIDI-Datei parsen (entweder Original oder die temporäre)
                logging.info(f"Parse MIDI-Datei: {midi_input_path}")
                parsed_data = midi_parser.parse_midi_file(midi_input_path)

                if not parsed_data or 'midi_object' not in parsed_data:
                     logging.error(f"MIDI-Parsing gab ungültige Daten zurück: {parsed_data}")
                     raise ValueError("MIDI-Parsing fehlgeschlagen oder gab keine Daten zurück.")

                # Kernkonvertierung
                logging.info("Führe Kernkonvertierung zu LLM-Notation durch.")
                llm_text_result = llm_converter.midi_to_llm_text(parsed_data)

                # Ergebnis speichern
                output_basename = os.path.splitext(os.path.basename(input_path))[0] # Originalname als Basis
                output_path = os.path.join(output_folder, f"{output_basename}_llm.txt")
                logging.info(f"Speichere Ergebnis nach: {output_path}")
                file_content_to_write = llm_text_result
                if not file_handler.write_output_file(output_path, file_content_to_write):
                     self.log_output(f"FEHLER: Konnte Ergebnisdatei nicht schreiben: {output_path}", "ERROR")
                     result_message = f"Konvertierung OK, aber Fehler beim Speichern als:\n{os.path.basename(output_path)}"
                else:
                     # Verwende den tatsächlichen Pfad, falls nummeriert wurde
                     actual_output_path = output_path # Annahme, wird in write_output_file ggf. angepasst
                     # TODO: write_output_file könnte den tatsächlichen Pfad zurückgeben
                     result_message = f"Konvertierung erfolgreich. Gespeichert als:\n{os.path.basename(actual_output_path)}" # TODO: Anpassen

                # Ergebnis anzeigen
                display_content = llm_text_result
                self.display_output_text(display_content)

            # ... (Rest der Funktion: direction == '<-', else, except, finally) ...
            elif direction == "<-":
                logging.error("Text -> MIDI ist nicht implementiert.")
                error_occurred = True
                result_message = "FEHLER: Text -> MIDI Konvertierung ist nicht implementiert."
                self.display_output_text(result_message)

            else:
                logging.error(f"Ungültige Konvertierungsrichtung: {direction}")
                error_occurred = True
                result_message = f"FEHLER: Ungültige Konvertierungsrichtung: {direction}"
                self.display_output_text(result_message)

        except FileNotFoundError as e:
            error_occurred = True
            logging.error(f"FEHLER: Datei nicht gefunden - {e}", exc_info=True)
            result_message = f"FEHLER: Datei nicht gefunden:\n{e}"
            self.display_output_text(result_message)
        except NotImplementedError as e:
             error_occurred = True
             logging.error(f"FEHLER: Fehlendes Modul oder Funktion - {e}", exc_info=True)
             result_message = f"FEHLER: Eine benötigte Komponente fehlt:\n{e}"
             self.display_output_text(result_message)
        except ValueError as e:
             error_occurred = True
             logging.error(f"FEHLER: Ungültige Daten oder Wert - {e}", exc_info=True)
             result_message = f"FEHLER: Problem beim Verarbeiten der Daten:\n{e}"
             self.display_output_text(result_message)
        except RuntimeError as e: # Fängt den MuseScore-Fehler ab
             error_occurred = True
             logging.error(f"FEHLER: Laufzeitfehler (MuseScore?) - {e}", exc_info=False) # Traceback hier oft nicht nötig
             result_message = f"FEHLER: {e}"
             self.display_output_text(result_message)
        except Exception as e:
            error_occurred = True
            logging.exception("Ein unerwarteter Fehler ist während der Konvertierung aufgetreten:")
            result_message = f"Unerwarteter FEHLER:\n{type(e).__name__}: {e}\nDetails siehe Log."
            self.display_output_text(result_message)

        finally:
            # Temporäre MIDI-Datei löschen, falls erstellt
            if temp_midi_path and os.path.exists(temp_midi_path):
                try:
                    os.remove(temp_midi_path)
                    logging.info(f"Temporäre MIDI-Datei '{temp_midi_path}' gelöscht.")
                except OSError as e:
                    logging.error(f"Fehler beim Löschen der temporären MIDI-Datei '{temp_midi_path}': {e}")

            # Dauer berechnen und loggen
            end_time = time.time()
            duration = end_time - start_time
            status = "FEHLERN" if error_occurred else "erfolgreich"
            log_msg = f"Konvertierung {status} beendet in {duration:.2f} Sekunden."
            logging.info(log_msg)
            self.log_output(log_msg, "ERROR" if error_occurred else "INFO")
            self.log_output(result_message, "ERROR" if error_occurred else "INFO")

            # Buttons wieder aktivieren
            self.reactivate_buttons()


# --- Hauptteil zum Starten der Anwendung ---
if __name__ == "__main__":
    # Logging zuerst einrichten
    try:
        log_dir_fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(log_dir_fallback, exist_ok=True)
        logger_setup.setup_logging()
    except Exception as log_e:
        print(f"Konnte Logging nicht initialisieren: {log_e}")
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.error(f"Logging-Setup fehlgeschlagen: {log_e}", exc_info=True)

    # Hauptanwendung starten
    try:
        root = tk.Tk()
        app = MidiConverterApp(root)
        root.mainloop()
    except Exception as app_e:
        logging.exception("Schwerwiegender Fehler beim Starten oder Ausführen der Anwendung:")
        try:
            log_folder_name = "logs"
            try: log_folder_name = config.LOG_FOLDER
            except NameError: pass
            messagebox.showerror("Fataler Anwendungsfehler",
                                 f"Ein schwerwiegender Fehler ist aufgetreten:\n\n{app_e}\n\n"
                                 f"Die Anwendung wird möglicherweise beendet. Details finden Sie in den Log-Dateien im Ordner '{log_folder_name}'.")
        except Exception as mb_e:
            print(f"FATALER ANWENDUNGSFEHLER: {app_e}")
            print(f"(Fehler beim Anzeigen der Messagebox: {mb_e})")

