# utils.py
"""
Sammlung von Hilfsfunktionen für den MIDI-zu-LLM-Konverter.
(Version ohne ensure_folder_exists)
"""

# Imports bleiben gleich
import os
import logging
import math
from typing import Tuple, Dict, Optional

try:
    import mido
except ImportError:
    print("WARNUNG: mido ist nicht installiert. Einige Funktionen in utils.py könnten eingeschränkt sein.")
    class mido:
        class MidiFile: pass
        class MidiTrack: pass
        class Message: pass
        class MetaMessage: pass

try:
    import config
except ImportError:
    print("FEHLER: config.py nicht gefunden in utils.py. Verwende Fallback-Werte.")
    class config:
        VELOCITY_THRESHOLDS = {
            'ppp': 16, 'pp': 32, 'p': 63, 'mp': 79,
            'mf': 95, 'f': 111, 'ff': 126, 'fff': 127
        }

MIDI_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# --- Funktionen ---

def velocity_to_dynamic(velocity: int) -> str:
    """
    Wandelt eine MIDI-Velocity (0-127) in ein Dynamiksymbol um.
    Verwendet die Schwellwerte aus config.VELOCITY_THRESHOLDS.
    (Implementierung bleibt gleich)
    """
    if not 0 <= velocity <= 127:
        logging.warning(f"Ungültige Velocity empfangen: {velocity}. Gebe 'mf' zurück.")
        return 'mf'
    sorted_thresholds = sorted(config.VELOCITY_THRESHOLDS.items(), key=lambda item: item[1])
    for symbol, upper_bound in sorted_thresholds:
        if velocity <= upper_bound:
            return symbol
    logging.error(f"Konnte keine Dynamik für Velocity {velocity} finden. Fallback auf 'mf'.")
    return 'mf'

# ensure_folder_exists wurde nach file_handler.py verschoben

def get_track_names(midi_file: mido.MidiFile) -> Dict[int, str]:
    """
    Extrahiert die Namen der Tracks aus einer Mido MidiFile.
    (Implementierung bleibt gleich)
    """
    track_names: Dict[int, str] = {}
    if not midi_file or not hasattr(midi_file, 'tracks'):
        logging.error("Ungültiges MidiFile-Objekt an get_track_names übergeben.")
        return track_names
    for i, track in enumerate(midi_file.tracks):
        track_name_found = False
        for msg in track:
            if msg.type == 'track_name':
                track_names[i] = msg.name.strip().rstrip('\x00')
                track_name_found = True
                break
        if not track_name_found:
            track_names[i] = f"Unbenannter Track {i}"
    return track_names

def midi_note_to_llm_pitch(note_number: int) -> str:
    """
    Konvertiert eine MIDI-Notennummer (0-127) in die LLM-Notation (z.B. C4, F#5).
    (Implementierung bleibt gleich)
    """
    if not 0 <= note_number <= 127:
        logging.warning(f"Ungültige MIDI-Notennummer: {note_number}. Gebe rohen Wert zurück.")
        return str(note_number)
    octave = (note_number // 12) - 1
    note_index = note_number % 12
    note_name = MIDI_NOTE_NAMES[note_index]
    return f"{note_name}{octave}"

def calculate_ticks_per_measure(time_signature: Tuple[int, int], ticks_per_beat: int) -> int:
    """
    Berechnet die Anzahl der MIDI-Ticks pro Takt basierend auf Taktart und TPB.
    (Implementierung bleibt gleich)
    """
    if not isinstance(time_signature, tuple) or len(time_signature) != 2:
        logging.warning(f"Ungültiges time_signature-Format: {time_signature}. Verwende Standard 4/4.")
        time_signature = (4, 4)
    numerator, denominator = time_signature
    if denominator == 0:
        logging.warning(f"Ungültiger Taktart-Nenner 0. Verwende Fallback-Berechnung für 4/4.")
        return ticks_per_beat * 4
    if ticks_per_beat <= 0:
         logging.warning(f"Ungültiger ticks_per_beat Wert: {ticks_per_beat}. Verwende 1.")
         ticks_per_beat = 1
    try:
        ticks = int(ticks_per_beat * numerator * (4 / denominator))
        if ticks <= 0:
             logging.warning(f"Berechnete Ticks pro Takt sind <= 0 ({ticks}) für Taktart {time_signature} und TPB {ticks_per_beat}. Verwende Fallback.")
             return ticks_per_beat * 4
        return ticks
    except ZeroDivisionError:
         logging.error(f"Division durch Null bei Berechnung der Ticks pro Takt für Taktart {time_signature}.")
         return ticks_per_beat * 4
    except Exception as e:
        logging.error(f"Fehler bei Berechnung der Ticks pro Takt: {e}")
        return ticks_per_beat * 4

