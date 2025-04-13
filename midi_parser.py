# midi_parser.py
"""
Modul zum Parsen von MIDI-Dateien mit mido.
Extrahiert Metadaten und Event-Daten in eine strukturierte Form.
"""

import logging
import os
from typing import Dict, List, Optional, Any, Tuple

try:
    import mido
except ImportError:
    logging.error("FATAL: Die 'mido' Bibliothek ist nicht installiert. Bitte installieren Sie sie (pip install mido).")
    # Erzeuge einen Dummy, damit der Rest des Codes zumindest importiert werden kann,
    # aber eine Exception wirft, wenn mido.MidiFile aufgerufen wird.
    class MidoDummy:
        def __getattr__(self, name):
            raise ImportError("mido ist nicht installiert oder konnte nicht importiert werden.")
    mido = MidoDummy()

try:
    import config
except ImportError:
    logging.error("FEHLER: config.py nicht gefunden in midi_parser.py. Verwende Fallback-Werte.")
    class config:
        DEFAULT_TICKS_PER_BEAT = 480
        DEFAULT_TEMPO = 120
        DEFAULT_TIME_SIGNATURE = (4, 4)
        DEFAULT_KEY_SIGNATURE = "C"

try:
    import utils
except ImportError:
    logging.error("FEHLER: utils.py nicht gefunden in midi_parser.py.")
    # Dummy-Funktion
    class utils:
        @staticmethod
        def get_track_names(midi_file): return {}


def parse_midi_file(filepath: str) -> Optional[Dict[str, Any]]:
    """
    Parst eine MIDI-Datei und extrahiert relevante musikalische Daten.

    Args:
        filepath: Der Pfad zur MIDI-Datei (.mid oder .midi).

    Returns:
        Ein Dictionary mit den extrahierten Daten bei Erfolg, sonst None.
        Das Dictionary enthält typischerweise:
        - 'midi_object': Das mido.MidiFile Objekt.
        - 'ticks_per_beat': Ticks pro Viertelnote.
        - 'metadata': Dict mit initialen Werten für 'key_signature', 'tempo', 'time_signature'.
        - 'track_names': Dict von Track-Index zu Track-Namen.
        - 'tracks_data': Eine Liste von Listen. Jede innere Liste enthält
                         Event-Dictionaries für einen Track. Event-Dicts können sein:
                         {'tick': abs_tick, 'type': 'note', 'pitch': num, 'velocity': vel, 'duration': dur_ticks}
                         {'tick': abs_tick, 'type': 'timesig', 'numerator': n, 'denominator': d}
                         {'tick': abs_tick, 'type': 'tempo', 'bpm': bpm_value}
                         ... (ggf. weitere Event-Typen)
    """
    if not os.path.exists(filepath):
        logging.error(f"MIDI-Datei nicht gefunden: {filepath}")
        return None

    try:
        midi_file = mido.MidiFile(filepath, clip=True) # clip=True verhindert negative Notenwerte
        logging.info(f"MIDI-Datei erfolgreich geladen: {filepath}")
    except FileNotFoundError:
        logging.error(f"MIDI-Datei nicht gefunden (trotz exist-Check?): {filepath}")
        return None
    except mido.ParserError as e:
        logging.error(f"Mido Parser Fehler beim Lesen von {filepath}: {e}")
        return None
    except IOError as e:
        logging.error(f"IO Fehler beim Lesen von {filepath}: {e}")
        return None
    except Exception as e:
        logging.exception(f"Unerwarteter Fehler beim Laden von {filepath}: {e}")
        return None

    # --- Globale Metadaten extrahieren ---
    tpb = midi_file.ticks_per_beat if midi_file.ticks_per_beat > 0 else config.DEFAULT_TICKS_PER_BEAT
    if midi_file.ticks_per_beat <= 0:
        logging.warning(f"Ungültiger ticks_per_beat Wert ({midi_file.ticks_per_beat}) in {filepath}. Verwende Standard: {tpb}")

    metadata = {
        'key_signature': config.DEFAULT_KEY_SIGNATURE,
        'tempo': config.DEFAULT_TEMPO,
        'time_signature': config.DEFAULT_TIME_SIGNATURE,
    }
    initial_key_found = False
    initial_tempo_found = False
    initial_time_sig_found = False

    # Suche primär in Track 0 nach den ersten Metadaten
    if midi_file.tracks:
        for msg in midi_file.tracks[0]:
            if not initial_key_found and msg.type == 'key_signature':
                metadata['key_signature'] = msg.key
                initial_key_found = True
            elif not initial_tempo_found and msg.type == 'set_tempo':
                metadata['tempo'] = round(mido.tempo2bpm(msg.tempo), 2) # Runde auf 2 Nachkommastellen
                initial_tempo_found = True
            elif not initial_time_sig_found and msg.type == 'time_signature':
                metadata['time_signature'] = (msg.numerator, msg.denominator)
                initial_time_sig_found = True
            # Breche ab, wenn alle initialen Metadaten gefunden wurden
            if initial_key_found and initial_tempo_found and initial_time_sig_found:
                break
    logging.info(f"Initiale Metadaten extrahiert: {metadata}")

    # --- Track-Namen extrahieren ---
    track_names = utils.get_track_names(midi_file)

    # --- Event-Daten pro Track extrahieren ---
    tracks_data: List[List[Dict[str, Any]]] = []

    for track_index, track in enumerate(midi_file.tracks):
        current_tick = 0
        active_notes: Dict[int, Dict[str, int]] = {} # {note_num: {'start_tick': tick, 'velocity': vel}}
        track_events: List[Dict[str, Any]] = []

        logging.debug(f"Verarbeite Track {track_index}: {track_names.get(track_index, '')}")

        for msg in track:
            # Delta-Zeit zum absoluten Zeitstempel addieren
            current_tick += msg.time

            msg_type = msg.type

            if msg_type == 'note_on' and msg.velocity > 0:
                note_num = msg.note
                # Prüfe auf überlappende Note (gleiche Tonhöhe noch aktiv)
                if note_num in active_notes:
                    prev_note = active_notes[note_num]
                    duration = current_tick - prev_note['start_tick']
                    logging.warning(f"Track {track_index}: Note {note_num} bei Tick {current_tick} re-triggered. "
                                    f"Vorherige Note (Start: {prev_note['start_tick']}) wird mit Dauer {duration} beendet.")
                    if duration > 0:
                        track_events.append({
                            'tick': prev_note['start_tick'], 'type': 'note',
                            'pitch': note_num, 'velocity': prev_note['velocity'],
                            'duration': duration
                        })
                    # Alte Note entfernen, bevor die neue hinzugefügt wird
                    del active_notes[note_num]

                # Neue Note als aktiv speichern
                active_notes[note_num] = {'start_tick': current_tick, 'velocity': msg.velocity}

            elif msg_type == 'note_off' or (msg_type == 'note_on' and msg.velocity == 0):
                note_num = msg.note
                if note_num in active_notes:
                    start_tick = active_notes[note_num]['start_tick']
                    velocity = active_notes[note_num]['velocity']
                    duration = current_tick - start_tick

                    if duration > 0: # Ignoriere Noten mit Nulldauer
                        track_events.append({
                            'tick': start_tick, 'type': 'note',
                            'pitch': note_num, 'velocity': velocity,
                            'duration': duration
                        })
                    else:
                         logging.debug(f"Track {track_index}: Ignoriere Note {note_num} mit Nulldauer bei Tick {start_tick}.")

                    del active_notes[note_num]
                # else: Ignoriere note_off ohne passendes note_on (kann vorkommen)

            elif msg_type == 'time_signature':
                track_events.append({
                    'tick': current_tick, 'type': 'timesig',
                    'numerator': msg.numerator, 'denominator': msg.denominator
                })
                logging.debug(f"Track {track_index}: Taktartwechsel {msg.numerator}/{msg.denominator} bei Tick {current_tick}")

            elif msg_type == 'set_tempo':
                 # Speichere Tempoänderungen ebenfalls, könnten nützlich sein
                 bpm = round(mido.tempo2bpm(msg.tempo), 2)
                 track_events.append({
                     'tick': current_tick, 'type': 'tempo', 'bpm': bpm
                 })
                 logging.debug(f"Track {track_index}: Tempoänderung auf {bpm} BPM bei Tick {current_tick}")

            # Hier könnten weitere Event-Typen hinzugefügt werden (z.B. Controller-Events für Sustain)

        # Behandle Noten, die am Ende des Tracks noch aktiv sind
        if active_notes:
             logging.warning(f"Track {track_index}: {len(active_notes)} Note(n) am Track-Ende noch aktiv.")
             for note_num, note_data in active_notes.items():
                 start_tick = note_data['start_tick']
                 velocity = note_data['velocity']
                 # Weise eine Standarddauer zu (z.B. 1 Beat) oder bis zum letzten Event?
                 # Hier verwenden wir 1 Beat als Fallback.
                 duration = tpb
                 logging.warning(f"  - Note {note_num} (Start: {start_tick}) erhält Fallback-Dauer {duration}.")
                 track_events.append({
                     'tick': start_tick, 'type': 'note',
                     'pitch': note_num, 'velocity': velocity,
                     'duration': duration
                 })

        # Sortiere die Events des Tracks nach ihrem Zeitstempel
        track_events.sort(key=lambda x: x['tick'])
        tracks_data.append(track_events)

    # --- Ergebnis zusammenstellen ---
    result = {
        'midi_object': midi_file, # Das Originalobjekt für evtl. weitere Analysen
        'ticks_per_beat': tpb,
        'metadata': metadata,
        'track_names': track_names,
        'tracks_data': tracks_data
    }

    logging.info(f"MIDI-Parsing abgeschlossen für {filepath}. {len(tracks_data)} Tracks verarbeitet.")
    return result

# Beispielaufruf (nur zum Testen des Moduls direkt)
if __name__ == '__main__':
    print("MIDI Parser Modul - Direkter Testlauf")
    # Erstelle eine Dummy-Konfiguration für den Test
    class config:
        DEFAULT_TICKS_PER_BEAT = 480
        DEFAULT_TEMPO = 100
        DEFAULT_TIME_SIGNATURE = (3, 4)
        DEFAULT_KEY_SIGNATURE = "Gm"
        LOG_FOLDER = "logs_test"
    # Erstelle Dummy utils
    class utils:
        @staticmethod
        def get_track_names(mf): return {0: "Test Track 0", 1: "Test Track 1"}

    # Richte einfaches Logging für den Test ein
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    # Erstelle eine einfache Test-MIDI-Datei im Speicher
    test_mid = mido.MidiFile()
    test_mid.ticks_per_beat = 480
    track0 = mido.MidiTrack()
    track0.append(mido.MetaMessage('track_name', name='Control', time=0))
    track0.append(mido.MetaMessage('key_signature', key='C', time=0))
    track0.append(mido.MetaMessage('time_signature', numerator=4, denominator=4, time=10))
    track0.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120), time=20))
    track0.append(mido.MetaMessage('end_of_track', time=100))
    test_mid.tracks.append(track0)

    track1 = mido.MidiTrack()
    track1.append(mido.MetaMessage('track_name', name='Piano', time=0))
    track1.append(mido.Message('note_on', note=60, velocity=80, time=0)) # C4 @ 0
    track1.append(mido.Message('note_off', note=60, velocity=0, time=480)) # C4 off @ 480 (dauer 480)
    track1.append(mido.Message('note_on', note=64, velocity=70, time=0)) # E4 @ 480
    track1.append(mido.Message('note_on', note=67, velocity=75, time=0)) # G4 @ 480 (Akkord)
    track1.append(mido.Message('note_off', note=64, velocity=0, time=960)) # E4 off @ 1440 (dauer 960)
    track1.append(mido.Message('note_off', note=67, velocity=0, time=0)) # G4 off @ 1440 (dauer 960)
    track1.append(mido.MetaMessage('end_of_track', time=100))
    test_mid.tracks.append(track1)

    # Speichere die Testdatei temporär
    test_filepath = "temp_test_parser.mid"
    try:
        test_mid.save(test_filepath)
        print(f"Temporäre Test-MIDI-Datei '{test_filepath}' erstellt.")

        # Führe den Parser aus
        parsed_result = parse_midi_file(test_filepath)

        if parsed_result:
            print("\n--- Parser Ergebnis ---")
            print(f"Ticks Per Beat: {parsed_result['ticks_per_beat']}")
            print(f"Metadaten: {parsed_result['metadata']}")
            print(f"Track Namen: {parsed_result['track_names']}")
            print(f"Anzahl Tracks mit Daten: {len(parsed_result['tracks_data'])}")
            for i, track_data in enumerate(parsed_result['tracks_data']):
                print(f"\nTrack {i} ({parsed_result['track_names'].get(i, '')}): {len(track_data)} Events")
                # Gib die ersten paar Events aus
                for event in track_data[:5]:
                    print(f"  {event}")
                if len(track_data) > 5:
                    print("  ...")
            print("----------------------")
        else:
            print("Parser hat None zurückgegeben.")

    except Exception as e:
        print(f"Fehler im Testlauf: {e}")
    finally:
        # Lösche die temporäre Datei
        if os.path.exists(test_filepath):
            os.remove(test_filepath)
            print(f"Temporäre Test-MIDI-Datei '{test_filepath}' gelöscht.")

