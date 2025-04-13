# llm_converter.py
"""
Modul für die Konvertierung der geparsten MIDI-Daten in das LLM-Textformat.
(Version mit "Nächster-Nachbar"-Quantisierungslogik)
"""

import logging
import math
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

# Importiere benötigte Module und Konfiguration
try:
    import config
except ImportError:
    logging.error("FEHLER: config.py nicht gefunden in llm_converter.py. Verwende Fallback-Werte.")
    class config:
        DEFAULT_KEY_SIGNATURE = "C"
        DEFAULT_TICKS_PER_BEAT = 480
        DEFAULT_TIME_SIGNATURE = (4, 4)
        # DURATION_QUANTIZATION_TOLERANCE wird nicht mehr direkt verwendet
        MIN_REST_DURATION_TICKS = 5
        # Optional: Schwellwert, ab wann Quantisierungsfehler als zu groß gelten
        MAX_QUANTIZATION_ERROR_BEATS = 0.25


try:
    import utils
except ImportError:
    logging.error("FEHLER: utils.py nicht gefunden in llm_converter.py.")
    # Dummy-Funktionen
    class utils:
        @staticmethod
        def velocity_to_dynamic(vel): return 'mf'
        @staticmethod
        def midi_note_to_llm_pitch(num): return f"N{num}"
        @staticmethod
        def calculate_ticks_per_measure(ts, tpb): return tpb * 4


# --- Interne Hilfsfunktion zur Dauer-Quantisierung ---

def _ticks_to_duration_code(ticks: int, ticks_per_beat: int, time_signature_denominator: int = 4) -> str:
    """
    Wandelt eine Dauer in MIDI-Ticks in die LLM-Symbolnotation um (z.B. /4, /8., /?).
    Findet den *nächstgelegenen* Standard-Notenwert.

    Args:
        ticks: Die Dauer in MIDI-Ticks.
        ticks_per_beat: Ticks pro Viertelnote.
        time_signature_denominator: Der Nenner der Taktart (aktuell nicht direkt verwendet).

    Returns:
        Den Dauer-Code des nächstgelegenen Standardwerts als String (z.B. "/4", "/8.").
        Gibt "/?" zurück, wenn die Abweichung selbst zum nächsten Wert zu groß ist
        oder bei ungültigen Eingaben.
    """
    if ticks <= 0 or ticks_per_beat <= 0:
        logging.warning(f"Ungültige Ticks ({ticks}) oder TPB ({ticks_per_beat}) für Dauerberechnung.")
        return "/?"

    # Berechne Dauer in Beats relativ zu einer Viertelnote (Viertel = 1 Beat)
    beats = ticks / ticks_per_beat

    # Dauer-Map: (Beat-Wert, Code) - Reihenfolge ist hier weniger kritisch als bei isclose
    duration_map = [
        (8.0, '/0.5'), (4.0, '/1'), (3.0, '/2.'), (2.0, '/2'), (1.5, '/4.'),
        (1.0, '/4'), (0.75, '/8.'), (0.5, '/8'), (0.375, '/16.'), (0.25, '/16'),
        (0.1875, '/32.'), (0.125, '/32'), (0.0625, '/64'),
    ]

    min_difference = float('inf')
    best_match_code = None

    # Finde den Code mit der geringsten absoluten Differenz in Beats
    for beat_val, code in duration_map:
        difference = abs(beats - beat_val)
        if difference < min_difference:
            min_difference = difference
            best_match_code = code

    # Prüfe, ob überhaupt ein Match gefunden wurde (sollte immer der Fall sein, wenn map nicht leer)
    if best_match_code is None:
        logging.error(f"Kein bester Match gefunden für Dauer {ticks} Ticks ({beats:.3f} Beats).")
        return "/?"

    # Optional: Prüfe, ob der beste Match immer noch "zu weit" entfernt ist
    max_allowed_error = getattr(config, 'MAX_QUANTIZATION_ERROR_BEATS', 0.25)
    if min_difference > max_allowed_error:
        logging.warning(f"Dauer von {ticks} Ticks ({beats:.3f} Beats) ist selbst vom nächsten Wert ({best_match_code} bei {min_difference:.3f} Beats Differenz) weit entfernt. Verwende trotzdem '{best_match_code}', aber ggf. ungenau.")
        # return "/?" # Alternativ hier doch '?' zurückgeben

    # Logge den gefundenen Wert (optional für Debugging)
    # logging.debug(f"Dauer {ticks} Ticks ({beats:.3f} Beats) quantisiert zu nächstem Wert: {best_match_code} (Differenz: {min_difference:.3f} Beats)")
    return best_match_code


# --- Haupt-Konvertierungsfunktion ---

def midi_to_llm_text(parsed_data: Dict[str, Any]) -> str:
    """
    Konvertiert die geparsten MIDI-Daten in einen String im LLM-Format.
    (Implementierung der Hauptlogik bleibt gleich, nur _ticks_to_duration_code wurde geändert)

    Args:
        parsed_data: Das von midi_parser.parse_midi_file zurückgegebene Dictionary.

    Returns:
        Der formatierte String im LLM-Format.
    """
    if not parsed_data:
        logging.error("midi_to_llm_text erhielt keine Daten vom Parser.")
        return "FEHLER: Keine Daten vom MIDI-Parser erhalten."

    output_lines = []

    # --- Globale Metadaten ---
    try:
        key_signature = parsed_data.get('metadata', {}).get('key_signature', config.DEFAULT_KEY_SIGNATURE)
        initial_time_signature = parsed_data.get('metadata', {}).get('time_signature', config.DEFAULT_TIME_SIGNATURE)
        ticks_per_beat = parsed_data.get('ticks_per_beat', config.DEFAULT_TICKS_PER_BEAT)
        track_names = parsed_data.get('track_names', {})
        tracks_data = parsed_data.get('tracks_data', [])
    except KeyError as e:
        logging.error(f"Fehlender Schlüssel in parsed_data: {e}")
        return f"FEHLER: Unvollständige Daten vom MIDI-Parser erhalten (fehlender Schlüssel: {e})."

    output_lines.append(f"Key: {key_signature}")

    # --- Verarbeite jeden Track ---
    for track_index, track_events in enumerate(tracks_data):
        track_name = track_names.get(track_index, f"Unbenannter Track {track_index}")
        logging.info(f"Konvertiere Track {track_index}: {track_name}")

        if not track_events:
            logging.info(f"Track {track_index} enthält keine Events, wird übersprungen.")
            continue

        # --- Pass 1: Erzeuge musikalische Objekte (Noten, Pausen, Marker) ---
        musical_objects: List[Dict[str, Any]] = []
        last_event_end_tick = 0
        current_dynamic = None

        try:
             ticks_per_measure = utils.calculate_ticks_per_measure(initial_time_signature, ticks_per_beat)
             if ticks_per_measure <= 0:
                 raise ValueError(f"Berechnete Ticks pro Takt <= 0 ({ticks_per_measure})")
        except Exception as e:
            logging.error(f"Fehler bei Berechnung der Ticks/Takt für Track {track_index} (Taktart: {initial_time_signature}, TPB: {ticks_per_beat}): {e}. Überspringe Track.")
            output_lines.append(f"T{track_index} {track_name}:\nFEHLER: Konnte Taktlänge nicht berechnen.")
            continue

        logging.debug(f"Track {track_index}: Verwende Ticks/Takt = {ticks_per_measure} (basiert auf {initial_time_signature})")

        for event in track_events:
            event_tick = event['tick']

            # --- Füge Pausen ein ---
            rest_duration = event_tick - last_event_end_tick
            if rest_duration >= config.MIN_REST_DURATION_TICKS:
                # Verwende die (jetzt geänderte) Quantisierungsfunktion
                rest_code = _ticks_to_duration_code(rest_duration, ticks_per_beat)
                musical_objects.append({'tick': last_event_end_tick, 'type': 'rest', 'code': f"R{rest_code}", 'duration_ticks': rest_duration})
                # logging.debug(f"Track {track_index}: Pause von Tick {last_event_end_tick} bis {event_tick} (Dauer {rest_duration}, Code {rest_code})")

            # --- Verarbeite das aktuelle Event ---
            event_type = event['type']

            if event_type == 'note':
                # --- Dynamikwechsel prüfen ---
                dynamic_symbol = utils.velocity_to_dynamic(event['velocity'])
                if dynamic_symbol != current_dynamic:
                    musical_objects.append({'tick': event_tick, 'type': 'dynamic', 'code': f"dyn({dynamic_symbol})"})
                    current_dynamic = dynamic_symbol
                    # logging.debug(f"Track {track_index}: Dynamikwechsel zu {dynamic_symbol} bei Tick {event_tick}")

                # --- Note hinzufügen ---
                musical_objects.append({
                    'tick': event_tick,
                    'type': 'note',
                    'pitch_num': event['pitch'],
                    'pitch_str': utils.midi_note_to_llm_pitch(event['pitch']),
                    'duration_ticks': event['duration']
                })
                last_event_end_tick = event_tick + event['duration']

            elif event_type == 'timesig':
                # --- Taktartwechsel-Marker hinzufügen ---
                ts_code = f"[{event['numerator']}/{event['denominator']}]"
                musical_objects.append({'tick': event_tick, 'type': 'timesig', 'code': ts_code})
                # logging.debug(f"Track {track_index}: Taktart-Marker {ts_code} bei Tick {event_tick}")

        # --- Pass 2: Formatiere die musikalischen Objekte in den String ---
        musical_objects.sort(key=lambda x: x['tick'])

        track_string_parts: List[str] = []
        current_measure = 0
        last_tick_in_measure = 0
        last_formatted_tick = -1

        # Füge initialen Taktstrich hinzu, nur wenn Objekte vorhanden sind
        if musical_objects:
            track_string_parts.append("| 1")
            current_measure = 1
        else: # Track ohne Events, aber Header soll trotzdem da sein
             output_lines.append(f"T{track_index} {track_name}:\n| 1 |") # Leerer Track
             continue


        i = 0
        while i < len(musical_objects):
            obj = musical_objects[i]
            tick = obj['tick']
            obj_type = obj['type']

            # --- Füge Taktstriche ein ---
            measure_at_tick = (tick // ticks_per_measure) + 1

            if measure_at_tick > current_measure:
                for m in range(current_measure + 1, measure_at_tick + 1):
                    bar_num_marker = f" {m}" if (m % 5 == 0) else ""
                    # Füge nur Taktstrich hinzu, wenn nicht schon einer da ist (verhindert ||)
                    if not track_string_parts or not track_string_parts[-1].startswith('|'):
                         track_string_parts.append(f"|{bar_num_marker}")
                    elif bar_num_marker: # Füge Nummer hinzu, wenn Taktstrich schon da ist
                         track_string_parts[-1] = f"|{bar_num_marker}"

                current_measure = measure_at_tick
                last_tick_in_measure = tick % ticks_per_measure

            # --- Verarbeite das Objekt ---
            advance_index = 1 # Standardmäßig Index um 1 erhöhen
            if obj_type == 'note':
                # --- Akkord-Erkennung ---
                chord_notes = [obj]
                j = i + 1
                while j < len(musical_objects) and \
                      musical_objects[j]['tick'] == tick and \
                      musical_objects[j]['type'] == 'note':
                    chord_notes.append(musical_objects[j])
                    j += 1

                chord_notes.sort(key=lambda n: n['pitch_num'])
                pitches = [n['pitch_str'] for n in chord_notes]

                # Bestimme Dauer (vereinfacht: max. Dauer im Akkord)
                max_duration_ticks = max(n['duration_ticks'] for n in chord_notes)
                # Verwende die (jetzt geänderte) Quantisierungsfunktion
                duration_code = _ticks_to_duration_code(max_duration_ticks, ticks_per_beat)

                # Formatiere Note oder Akkord
                if len(pitches) > 1:
                    track_string_parts.append(f"{'+'.join(pitches)}{duration_code}")
                else:
                    track_string_parts.append(f"{pitches[0]}{duration_code}")

                last_formatted_tick = tick
                advance_index = j - i # Setze Index hinter den verarbeiteten Akkord

            elif obj_type == 'rest':
                 # Ganztaktpausen-Logik (vereinfacht): Wenn Code R/1 ist und am Taktanfang
                 is_whole_measure_rest = False
                 if obj['code'] == "R/1" and tick % ticks_per_measure == 0:
                      is_whole_measure_rest = True
                      logging.debug(f"Track {track_index}: Ganztaktpause bei Tick {tick} angenommen.")
                      # Füge nichts hinzu, Taktstrich wird automatisch erzeugt
                 else:
                      track_string_parts.append(obj['code']) # Normale Pause

                 last_formatted_tick = tick

            elif obj_type == 'dynamic' or obj_type == 'timesig':
                 # Füge nur hinzu, wenn es nicht direkt vor einem Taktstrich am selben Tick steht
                 # (Vermeidet z.B. "| [4/4] |" -> "| [4/4]") - braucht evtl. Lookahead
                 # Einfacher Ansatz: Immer hinzufügen
                 track_string_parts.append(obj['code'])
                 # last_formatted_tick = tick # Nicht setzen, Note könnte folgen

            else:
                logging.warning(f"Unbekannter Objekttyp '{obj_type}' bei Tick {tick} in Track {track_index} ignoriert.")

            i += advance_index


        # --- Füge finalen Taktstrich hinzu ---
        last_event_final_tick = last_event_end_tick
        final_measure = (last_event_final_tick // ticks_per_measure) + 1
        if final_measure >= current_measure:
             for m in range(current_measure + 1, final_measure + 1):
                    bar_num_marker = f" {m}" if (m % 5 == 0) else ""
                    if not track_string_parts or not track_string_parts[-1].startswith('|'):
                        track_string_parts.append(f"|{bar_num_marker}")
                    elif bar_num_marker:
                        track_string_parts[-1] = f"|{bar_num_marker}"
             if not track_string_parts or not track_string_parts[-1].startswith('|'):
                 track_string_parts.append("|")


        # --- Track-String zusammensetzen ---
        track_header = f"T{track_index} {track_name}:"
        filtered_parts = [part for part in track_string_parts if part]
        cleaned_body = " ".join(filtered_parts).replace(" | |", " |").replace("||","|")
        # Entferne Leerzeichen vor Taktstrichen und am Ende
        cleaned_body = cleaned_body.replace(" |", "|").strip()
        # Stelle sicher, dass Taktstriche von Leerzeichen umgeben sind (außer am Anfang/Ende)
        cleaned_body = cleaned_body.replace("|", " | ").strip()
        # Korrigiere mehrfache Leerzeichen
        cleaned_body = ' '.join(cleaned_body.split())

        # Minimaler Inhalt für leere Tracks
        if cleaned_body == "|":
             cleaned_body = "| 1 |"

        output_lines.append(f"{track_header}\n{cleaned_body}")


    # --- Gesamten Text zusammensetzen ---
    return "\n\n".join(output_lines)
