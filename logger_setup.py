# logger_setup.py
"""
Modul zur Konfiguration des Logging-Systems für die Anwendung.
(Version ohne separaten Error-Log und mit Datumsformat TT-MM-JJ_HH-MM)
"""

import logging
import os
import datetime
import sys

# Importiere die Konfiguration, um den Log-Ordner zu erhalten
try:
    import config
except ImportError:
    print("FEHLER: config.py nicht gefunden. Verwende Standard-Log-Ordner 'logs'.")
    class config:
        LOG_FOLDER = "logs"

def setup_logging():
    """
    Konfiguriert das zentrale Logging-System der Anwendung.

    - Erstellt den Log-Ordner, falls nicht vorhanden.
    - Richtet einen FileHandler für alle Logs (INFO und höher) ein.
    - Richtet einen StreamHandler für die Ausgabe auf der Konsole (INFO und höher) ein.
    - Verwendet das Format TT-MM-JJ_HH-MM für Zeitstempel in Dateinamen.
    - Es wird KEIN separater Error-Log mehr erstellt.
    """
    try:
        # Basispfad für Logs ermitteln (funktioniert für Skript und Bundle)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        log_directory = os.path.join(base_dir, config.LOG_FOLDER)
        os.makedirs(log_directory, exist_ok=True)

        # *** Geänderter Zeitstempel-Formatstring für TT-MM-JJ_HH-MM ***
        timestamp = datetime.datetime.now().strftime("%d-%m-%y_%H-%M")
        # Beispiel: 13-04-25_15-28

        # Define main log filename using the path from config and new timestamp format
        log_filename = os.path.join(log_directory, f"app_{timestamp}.log")
        # error_log_filename wird nicht mehr benötigt

        # Get the root logger
        logger = logging.getLogger()

        # Clear existing handlers (important if this function might be called multiple times)
        if logger.hasHandlers():
            logger.handlers.clear()

        # Set the lowest level the logger will handle
        logger.setLevel(logging.INFO) # Process INFO, WARNING, ERROR, CRITICAL

        # Create a formatter
        log_format = '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        formatter = logging.Formatter(log_format)

        # --- Main Log File Handler (INFO and above) ---
        try:
            info_file_handler = logging.FileHandler(log_filename, encoding='utf-8')
            info_file_handler.setLevel(logging.INFO)
            info_file_handler.setFormatter(formatter)
            logger.addHandler(info_file_handler)
        except Exception as e:
            print(f"FEHLER: Konnte Info-Log-Datei Handler nicht erstellen: {e}")


        # --- Error Log File Handler (ENTFERNT) ---
        # Der separate Error-Handler wird nicht mehr erstellt.
        # ERROR und CRITICAL Meldungen gehen jetzt auch in die Haupt-Logdatei.


        # --- Console Handler (INFO and above) ---
        try:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO) # Process INFO, WARNING, ERROR, CRITICAL
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
        except Exception as e:
            print(f"FEHLER: Konnte Konsolen-Log Handler nicht erstellen: {e}")

        # *** Angepasste initiale Log-Nachricht ***
        if logger.hasHandlers():
             logging.info(f"Logging initialisiert. Log-Datei: {log_filename}")
        else:
             print("WARNUNG: Logging konnte nicht vollständig initialisiert werden. Keine Handler aktiv.")

    except Exception as e:
        # Fallback basic config if setup fails catastrophically
        logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.error(f"Schwerwiegender Fehler im Logging-Setup: {e}", exc_info=True)
        print(f"FATALER FEHLER im Logging Setup: {e}. Fallback zu BasicConfig.")

