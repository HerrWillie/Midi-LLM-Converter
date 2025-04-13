# config.py
"""
Zentrale Konfigurationsdatei für den MIDI-zu-LLM-Konverter.
Enthält Konstanten für Dateipfade, Standardwerte und Konvertierungsparameter.
"""

import os
import sys
import platform

# --- Verzeichnis- und Dateinamen ---
OUTPUT_FOLDER_NAME = "output"
LOG_FOLDER = "logs"
GUIDE_PROMPT_FILENAME = "llm_guide_and_prompt_template.txt"

# --- Einstellungsdatei ---
SETTINGS_FILENAME = "settings.cfg" # Datei zum Speichern dynamischer Einstellungen (z.B. MuseScore Pfad)

# --- Verhalten bei existierenden Output-Dateien ---
OVERWRITE_OUTPUT_FILES = False # Standard: Nicht überschreiben

# --- Standardwerte für MIDI-Metadaten ---
DEFAULT_TICKS_PER_BEAT = 480
DEFAULT_TEMPO = 120
DEFAULT_TIME_SIGNATURE = (4, 4)
DEFAULT_KEY_SIGNATURE = "C"

# --- Konvertierungsparameter ---
VELOCITY_THRESHOLDS = {
    'ppp': 16, 'pp': 32, 'p': 63, 'mp': 79,
    'mf': 95, 'f': 111, 'ff': 126, 'fff': 127
}
DURATION_QUANTIZATION_TOLERANCE = 0.05 # Relative Toleranz
QUANTIZATION_ABS_TOLERANCE_BEATS = 0.02 # Absolute Toleranz in Beats
MAX_QUANTIZATION_ERROR_BEATS = 0.25 # Schwellwert für Warnung bei nächster Nachbar Quantisierung
MIN_REST_DURATION_TICKS = 5

# --- Externe Programme (Pfade) ---

# Entfernt: MUSESCORE_EXECUTABLE_PATH = None
# Stattdessen definieren wir Standard-Suchpfade

# Typische Standard-Installationspfade für MuseScore 4 (Anpassen bei Bedarf)
DEFAULT_MUSESCORE_PATHS = []
if sys.platform == "win32":
    # Windows: Prüfe Standard Program Files Verzeichnisse
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    DEFAULT_MUSESCORE_PATHS.extend([
        os.path.join(program_files, "MuseScore 4", "bin", "MuseScore4.exe"),
        os.path.join(program_files_x86, "MuseScore 4", "bin", "MuseScore4.exe"),
        # Füge hier ggf. weitere typische Pfade hinzu (z.B. portable Versionen)
    ])
elif sys.platform == "darwin":
    # macOS: Prüfe Standard Applications Ordner
    DEFAULT_MUSESCORE_PATHS.append("/Applications/MuseScore 4.app/Contents/MacOS/mscore")
    # Füge hier ggf. Pfade im Benutzerverzeichnis hinzu
    # home = os.path.expanduser("~")
    # DEFAULT_MUSESCORE_PATHS.append(os.path.join(home, "Applications", "MuseScore 4.app", ...))
elif "linux" in sys.platform:
    # Linux: Schwieriger, da viele Varianten (Paketmanager, AppImage, Flatpak...)
    # Prüfe auf häufige AppImage-Namen oder Orte (Annahme: im Pfad oder bekanntem Ort)
    # Dies ist nur ein Beispiel, muss ggf. stark angepasst werden!
    home = os.path.expanduser("~")
    DEFAULT_MUSESCORE_PATHS.extend([
        # Suche nach AppImages im Home oder Downloads (Beispiele!)
        os.path.join(home, "MuseScore-4.*-x86_64.AppImage"), # Wildcard geht hier nicht direkt
        os.path.join(home, "Downloads", "MuseScore-4.*-x86_64.AppImage"),
        # Prüfe, ob 'mscore' oder 'musescore' im Systempfad ist (via 'which' oder 'shutil.which')
        # Dies wird besser in der main.py Logik gehandhabt
    ])
    # Flatpak wäre z.B. 'flatpak run org.musescore.MuseScore' - benötigt andere Aufruflogik

# Hinweis: Die tatsächliche Suche (z.B. mit Wildcards oder shutil.which)
# sollte in der main.py Logik erfolgen, hier sind nur die Basis-Pfade.

