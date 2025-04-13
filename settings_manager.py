# settings_manager.py
"""
Modul zum Lesen und Schreiben von Anwendungseinstellungen aus einer einfachen .cfg-Datei.
Fokus liegt aktuell auf dem Speichern des MuseScore-Pfades.
"""

import os
import logging
import sys
from typing import Optional # <--- Hinzugefügter Import

# Importiere config nur, um den Dateinamen zu bekommen
try:
    import config
except ImportError:
    print("FEHLER: config.py nicht gefunden in settings_manager.py.")
    class config:
        SETTINGS_FILENAME = "settings.cfg" # Fallback

# Definiere den Schlüssel für den MuseScore-Pfad in der Datei
MUSESCORE_PATH_KEY = "musescore_path"

def _get_settings_filepath() -> str:
    """Ermittelt den Pfad zur Einstellungsdatei."""
    # Basispfad ermitteln (funktioniert für Skript und Bundle)
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        # __file__ ist der Pfad zu settings_manager.py, wir wollen das Verzeichnis davon
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, config.SETTINGS_FILENAME)

def load_musescore_path() -> Optional[str]: # Jetzt ist Optional bekannt
    """
    Lädt den gespeicherten MuseScore-Pfad aus der Einstellungsdatei.

    Returns:
        Den Pfad als String, wenn gefunden und lesbar, sonst None.
    """
    settings_file = _get_settings_filepath()
    if not os.path.exists(settings_file):
        logging.info(f"Keine Einstellungsdatei gefunden unter: {settings_file}")
        return None

    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith(MUSESCORE_PATH_KEY + "="):
                    # Extrahiere den Wert nach dem ersten '='
                    path = line.split('=', 1)[1].strip()
                    # Entferne mögliche Anführungszeichen am Anfang/Ende
                    path = path.strip('\'"')
                    logging.info(f"MuseScore-Pfad aus '{config.SETTINGS_FILENAME}' geladen: {path}")
                    return path
        logging.info(f"Schlüssel '{MUSESCORE_PATH_KEY}' nicht in '{config.SETTINGS_FILENAME}' gefunden.")
        return None # Schlüssel nicht gefunden
    except IOError as e:
        logging.error(f"IO-Fehler beim Lesen von '{settings_file}': {e}")
        return None
    except Exception as e:
        logging.error(f"Unerwarteter Fehler beim Lesen von '{settings_file}': {e}")
        return None

def save_musescore_path(path: str) -> bool:
    """
    Speichert den MuseScore-Pfad in der Einstellungsdatei.
    Überschreibt die Datei, wenn sie existiert (einfacher Ansatz).

    Args:
        path: Der zu speichernde Pfad.

    Returns:
        True bei Erfolg, False bei Fehlern.
    """
    settings_file = _get_settings_filepath()
    try:
        # Stelle sicher, dass das Verzeichnis existiert
        parent_dir = os.path.dirname(settings_file)
        if not os.path.exists(parent_dir):
             os.makedirs(parent_dir, exist_ok=True)

        # Schreibe den Pfad; einfache Implementierung überschreibt die Datei
        # Eine robustere Implementierung würde vorhandene Einstellungen beibehalten
        with open(settings_file, 'w', encoding='utf-8') as f:
            f.write(f"{MUSESCORE_PATH_KEY} = {path}\n")
            # Hier könnten später weitere Einstellungen hinzugefügt werden
        logging.info(f"MuseScore-Pfad '{path}' erfolgreich in '{config.SETTINGS_FILENAME}' gespeichert.")
        return True
    except IOError as e:
        logging.error(f"IO-Fehler beim Schreiben von '{settings_file}': {e}")
        return False
    except Exception as e:
        logging.error(f"Unerwarteter Fehler beim Schreiben von '{settings_file}': {e}")
        return False
