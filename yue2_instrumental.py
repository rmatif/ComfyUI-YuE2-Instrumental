"""YuE2 native score conversion, adapted from the upstream instrumental workflow."""

# https://github.com/multimodal-art-projection/YuE/tree/main/skills/yue2-music/instrumental
# MIT License
#
# Copyright (c) 2026 yue2-music contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import re
from dataclasses import dataclass, field
from fractions import Fraction
from math import lcm

VOICES = ("Vocal", "Ins")
DURATIONS = {1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48}
QUALITIES = ("", "m", "dim", "aug", "7", "maj7", "m7", "dim7", "m7b5",
             "sus4", "sus2", "6", "m6", "7sus4", "m(maj7)")
PITCH_NAME = r"[A-G](?:bb|##|b|#)?"
CHORD = re.compile(PITCH_NAME + "(?:" + "|".join(re.escape(q) for q in QUALITIES)
                   + ")(?:/" + PITCH_NAME + ")?")
TOKEN = re.compile(
    r'"(?P<chord>[^"\n]*)"|\[K:(?P<key>[^\]\n]+)\]|'
    r"(?P<acc>\^\^|__|\^|_|=)?(?P<note>[A-Ga-gz])"
    r"(?P<oct>[,']*)(?P<duration>[0-9]*)(?P<tie>-?)"
)
NATURAL = dict(zip("CDEFGAB", (0, 2, 4, 5, 7, 9, 11)))
KEYS = {
    **dict(zip(("Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"), range(-7, 8))),
    **dict(zip(("Abm", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m"), range(-7, 8))),
}


class AbcError(ValueError):
    """Unsupported notation or a failed structural invariant."""


def fail(condition: bool, message: str) -> None:
    if condition:
        raise AbcError(message)


def key_accidentals(key: str) -> dict[str, int]:
    fail(key not in KEYS, f"Unsupported key {key!r}; use a standard major or minor K: field")
    count = KEYS[key]
    result = {letter: 0 for letter in NATURAL}
    for letter in ("FCGDAEB" if count > 0 else "BEADGCF")[:abs(count)]:
        result[letter] = 1 if count > 0 else -1
    return result


def meter_value(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]*)/([1-9][0-9]*)", text)
    fail(match is None, f"Unsupported meter {text!r}; write an explicit fraction")
    n, d = map(int, match.groups())
    fail(d > 1024 or d & (d - 1) != 0, f"Unsupported meter denominator {d}")
    return n, d


@dataclass
class Voice:
    meter: tuple[int, int]
    key: str
    time: Fraction = Fraction(0)
    notes: list = field(default_factory=list)
    bars: list = field(default_factory=list)
    chords: list = field(default_factory=list)
    keys: list = field(default_factory=list)
    pending: tuple | None = None


@dataclass
class Score:
    text: str
    unit: Fraction
    bpm: int
    voices: dict[str, Voice]
    music_lines: dict[int, str]


def parse_bar(body: str, voice: Voice, unit: Fraction, context: str) -> None:
    n, d = voice.meter
    length = Fraction(4 * n, d)
    start = voice.time
    offset = Fraction(0)
    local = {}  # Native exporters propagate accidentals by letter, across octaves.
    if body == "Z":
        fail(voice.pending is not None, f"{context}: tie enters a full-measure rest")
        offset = length
    else:
        cursor = 0
        while cursor < len(body):
            if body[cursor].isspace():
                cursor += 1
                continue
            match = TOKEN.match(body, cursor)
            fail(match is None, f"{context}: unsupported token at {body[cursor:cursor + 24]!r}")
            cursor = match.end()
            chord, key = match.group("chord", "key")
            fail(offset >= length, f"{context}: event after the measure end")
            if chord is not None:
                fail(CHORD.fullmatch(chord) is None, f"{context}: unsupported chord {chord!r}")
                voice.chords.append((start + offset, chord))
                continue
            if key is not None:
                key_accidentals(key)
                voice.key = key
                voice.keys.append((start + offset, key))
                local = {}
                continue
            note, acc, octave, tie = match.group("note", "acc", "oct", "tie")
            units = int(match.group("duration") or "1")
            fail(units not in DURATIONS, f"{context}: unsupported duration {units}; split it into tied supported lengths")
            duration = units * unit * 4
            fail(offset + duration > length, f"{context}: note/rest exceeds meter duration")
            fail("," in octave and "'" in octave, f"{context}: mixed octave marks")
            if note == "z":
                fail(bool(acc or octave or tie), f"{context}: a rest cannot have accidentals, octave marks or ties")
                fail(voice.pending is not None, f"{context}: tie enters a rest")
            else:
                letter = note.upper()
                written = 60 + NATURAL[letter] + (12 if note.islower() else 0)
                written += 12 * (octave.count("'") - octave.count(","))
                alteration = local.get(letter, key_accidentals(voice.key)[letter])
                if acc:
                    alteration = {"=": 0, "_": -1, "__": -2, "^": 1, "^^": 2}[acc]
                    local[letter] = alteration
                pitch = written + alteration
                if voice.pending is not None:
                    old_pitch, old_written = voice.pending
                    # An unmarked continuation retains its tied accidental across
                    # a barline. It does not alter later untied notes in that bar.
                    if not acc and written == old_written:
                        pitch = old_pitch
                    fail(pitch != old_pitch, f"{context}: tie changes pitch from {old_pitch} to {pitch}")
                    voice.notes[-1][2] += duration
                else:
                    fail(not 0 <= pitch <= 127, f"{context}: pitch {pitch} is outside MIDI range")
                    voice.notes.append([start + offset, pitch, duration])
                voice.pending = (pitch, written) if tie else None
            offset += duration
    fail(offset != length, f"{context}: duration {offset} quarter notes != meter duration {length}")
    voice.bars.append((start, length, voice.meter))
    voice.time += length


def parse(text: str) -> Score:
    """Fail closed for unsupported tokens; resolve sounding notes, not token counts."""
    lines = text.splitlines()
    fail(len(lines) < 12, "Incomplete native two-voice ABC")
    fail(lines[0:2] != ["X:1", "T:"], "Expected native X:1 and blank T: header")
    fail(not lines[2].startswith("M:"), "Missing header M:")
    meter = meter_value(lines[2][2:])
    unit_match = re.fullmatch(r"L:1/([1-9][0-9]*)", lines[3])
    fail(unit_match is None, "Expected L:1/<power of two>, usually L:1/32")
    denominator = int(unit_match.group(1))
    fail(denominator > 1024 or denominator & (denominator - 1) != 0, "Unsupported L: denominator")
    unit = Fraction(1, denominator)
    tempo_match = re.fullmatch(r"Q:1/4=([1-9][0-9]*)", lines[4])
    fail(tempo_match is None, "Expected integer quarter-note tempo Q:1/4=<BPM>")
    expected_voices = ['V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
                       'V: Ins clef=treble name="Ins Melody" snm="Inst."']
    fail(lines[5:7] != expected_voices, "Preserve native Vocal and Ins voice definitions")
    fail(not lines[7].startswith("K:"), "Missing header K:")
    key = lines[7][2:]
    key_accidentals(key)
    voices = {name: Voice(meter, key, keys=[(Fraction(0), key)]) for name in VOICES}
    music_lines = {}
    cursor = 8
    group = 0
    while cursor < len(lines):
        while cursor < len(lines) and lines[cursor].startswith("% "):
            cursor += 1
        fail(cursor == len(lines), "Dangling section comment without music")
        group += 1
        counts = []
        for name in VOICES:
            context = f"group {group}, {name}"
            fail(cursor >= len(lines) or lines[cursor] != f"V: {name}", f"{context}: expected V: {name}")
            cursor += 1
            voice = voices[name]
            fields = set()
            while cursor < len(lines) and lines[cursor].startswith(("M:", "K:")):
                field_name, value = lines[cursor].split(":", 1)
                fail(field_name in fields, f"{context}: duplicate {field_name}: field")
                fields.add(field_name)
                if field_name == "M":
                    voice.meter = meter_value(value)
                else:
                    key_accidentals(value)
                    voice.key = value
                    voice.keys.append((voice.time, value))
                cursor += 1
            fail(cursor >= len(lines), f"{context}: missing music line")
            line = lines[cursor]
            fail(not line.endswith("|"), f"{context}: music line must end with a plain barline")
            music_lines[cursor] = name
            cursor += 1
            bars = []
            for bar in line[:-1].split("|"):
                bar = bar.strip()
                fail(not bar, f"{context}: empty measure or unsupported double/repeat barline")
                rest = re.fullmatch(r"Z([2-4])?", bar)
                if rest:
                    bars.extend(["Z"] * int(rest.group(1) or "1"))
                else:
                    bars.append(bar)
            fail(not 1 <= len(bars) <= 4, f"{context}: expected 1–4 measures after expanding Z rests")
            counts.append(len(bars))
            for bar in bars:
                parse_bar(bar, voice, unit, f"{context}, bar {len(voice.bars) + 1}")
        fail(counts[0] != counts[1], f"group {group}: voices have different measure counts")
    for name, voice in voices.items():
        fail(voice.pending is not None, f"{name}: unresolved tie at end of score")
    fail(voices["Ins"].chords != [], "Native chord symbols belong in Vocal, not Ins")
    fail(voices["Vocal"].bars != voices["Ins"].bars, "Voice meter/time grids differ")
    fail(voices["Vocal"].keys != voices["Ins"].keys, "Voice key-change timelines differ")
    return Score(text, unit, int(tempo_match.group(1)), voices, music_lines)



SECTIONS = {'intro', 'verse', 'pre-chorus', 'chorus', 'bridge', 'interlude', 'outro', 'instrumental'}


def fraction(value, context):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f'{context}: use integer or fraction string, not a float')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f'{context}: invalid fraction {value!r}') from exc


def lengths(value):
    if value.denominator != 1 or value <= 0:
        raise ValueError(f'Unrepresentable duration in ABC units: {value}')
    left = int(value)
    result = []
    for part in sorted(DURATIONS, reverse=True):
        while left >= part:
            result.append(part)
            left -= part
    return result


def spelling(pitch, key, active):
    signature = key_accidentals(key)
    prefer_sharp = sum(signature.values()) >= 0
    candidates = []
    for letter, pc in NATURAL.items():
        for alteration in (-1, 0, 1):
            base = pitch - alteration - 60 - pc
            if base % 12:
                continue
            octave = base // 12
            score = (alteration != signature[letter], abs(alteration),
                     (alteration < 0) if prefer_sharp else (alteration > 0))
            candidates.append((score, letter, alteration, octave))
    _, letter, alteration, octave = min(candidates)
    accidental = ''
    if alteration != active.get(letter, signature[letter]):
        accidental = {-1: '_', 0: '=', 1: '^'}[alteration]
        active[letter] = alteration
    name = letter + ',' * (-octave) if octave < 0 else (
        letter if octave == 0 else letter.lower() + "'" * (octave - 1))
    return accidental + name


def compress(bars):
    result, index = [], 0
    while index < len(bars):
        if bars[index] != 'Z':
            result.append(bars[index] + '|')
            index += 1
            continue
        end = index + 1
        while end < len(bars) and bars[end] == 'Z':
            end += 1
        count = end - index
        result.append('Z' + (str(count) if count > 1 else '') + '|')
        index = end
    return ''.join(result)


def compile_events(data):
    if not isinstance(data, dict) or set(data) - {'bpm', 'key', 'bars', 'notes', 'chords'}:
        raise ValueError('Score requires bpm, key, bars, notes and optional chords; unknown fields are rejected')
    bpm = data.get('bpm')
    if type(bpm) is not int or bpm <= 0:
        raise ValueError('bpm must be a positive integer quarter-note tempo')
    key = data.get('key', 'C')
    key_accidentals(key)
    if not isinstance(data.get('bars'), list) or not data['bars']:
        raise ValueError('bars must be a nonempty list')
    bars, time, meter, section = [], Fraction(0), '4/4', None
    unit_denominator = 32
    for i, item in enumerate(data['bars']):
        if not isinstance(item, dict) or set(item) - {'meter', 'key', 'section'}:
            raise ValueError(f'bar {i + 1}: only meter, key and section are supported')
        meter, key = item.get('meter', meter), item.get('key', key)
        n, d = meter_value(meter)
        key_accidentals(key)
        unit_denominator = lcm(unit_denominator, 4 * d)
        incoming = item.get('section', section)
        if incoming is not None and incoming not in SECTIONS:
            raise ValueError(f'bar {i + 1}: section must be one of {sorted(SECTIONS)}')
        section = incoming
        end = time + Fraction(4 * n, d)
        bars.append(dict(start=time, end=end, meter=meter, key=key, section=section))
        time = end
    notes = []
    for i, item in enumerate(data.get('notes', [])):
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError(f'note {i + 1}: expected [onset, duration, MIDI pitch]')
        start, duration = fraction(item[0], f'note {i + 1} onset'), fraction(item[1], f'note {i + 1} duration')
        pitch = item[2]
        if type(pitch) is not int or not 0 <= pitch <= 127:
            raise ValueError(f'note {i + 1}: pitch must be one MIDI integer; reduce polyphony first')
        if start < 0 or duration <= 0 or start + duration > time:
            raise ValueError(f'note {i + 1}: onset/duration is outside the score')
        notes.append((start, pitch, duration))
        unit_denominator = lcm(unit_denominator, (start / 4).denominator, (duration / 4).denominator)
    notes.sort()
    if not notes:
        raise ValueError('Instrumental score has no sounding notes')
    for a, b in zip(notes, notes[1:]):
        if a[0] + a[2] > b[0]:
            raise ValueError(f'Overlapping melody notes at quarter {b[0]}; choose one lead line before compilation')
    chords = []
    for i, item in enumerate(data.get('chords', [])):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f'chord {i + 1}: expected [onset, symbol]')
        when = fraction(item[0], f'chord {i + 1} onset')
        symbol = item[1]
        if when < 0 or when >= time or not isinstance(symbol, str) or not CHORD.fullmatch(symbol):
            raise ValueError(f'chord {i + 1}: unsupported symbol or onset')
        chords.append((when, symbol))
        unit_denominator = lcm(unit_denominator, (when / 4).denominator)
    chords.sort()
    if any(a[0] == b[0] for a, b in zip(chords, chords[1:])):
        raise ValueError('Conflicting/duplicate chord events at the same onset; choose one harmony timeline')
    if unit_denominator > 1024 or unit_denominator & (unit_denominator - 1):
        raise ValueError('Rhythm is outside the power-of-two training grid; explicitly quantize tuplets and record the changes')
    unit_quarters = Fraction(4, unit_denominator)
    ins, vocal = [], []
    for bar in bars:
        start, end = bar['start'], bar['end']
        events = [x for x in notes if x[0] < end and x[0] + x[2] > start]
        pieces, cursor, active = [], start, {}
        for onset, pitch, duration in events:
            a, b = max(start, onset), min(end, onset + duration)
            if a > cursor:
                pieces.extend('z' + (str(n) if n != 1 else '') for n in lengths((a - cursor) / unit_quarters))
            parts = lengths((b - a) / unit_quarters)
            for i, count in enumerate(parts):
                tie = '-' if i < len(parts) - 1 or b < onset + duration else ''
                pieces.append(spelling(pitch, bar['key'], active) + (str(count) if count != 1 else '') + tie)
            cursor = b
        if cursor < end:
            pieces.extend('z' + (str(n) if n != 1 else '') for n in lengths((end - cursor) / unit_quarters))
        ins.append(''.join(pieces) if events else 'Z')
        current = next((symbol for when, symbol in reversed(chords) if when <= start), None)
        changes = [(start, current)] + [(when, symbol) for when, symbol in chords if start < when < end]
        chunks = []
        for i, (when, symbol) in enumerate(changes):
            stop = changes[i + 1][0] if i + 1 < len(changes) else end
            chunks.append(('"' + symbol + '"') if symbol else '')
            chunks.extend('z' + (str(n) if n != 1 else '') for n in lengths((stop - when) / unit_quarters))
        vocal.append(''.join(chunks) if any(symbol for _, symbol in changes) else 'Z')
    header = ['X:1', 'T:', 'M:' + bars[0]['meter'], f'L:1/{unit_denominator}', f'Q:1/4={bpm}',
        'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
        'V: Ins clef=treble name="Ins Melody" snm="Inst."', 'K:' + bars[0]['key']]
    lines, index = header, 0
    while index < len(bars):
        bar = bars[index]
        previous = bars[index - 1] if index else bar
        end = index + 1
        while end < len(bars) and end - index < 4 and all(bars[end][k] == bar[k] for k in ('meter', 'key', 'section')):
            end += 1
        if bar['section'] is not None and (index == 0 or bar['section'] != previous['section']):
            lines.append('% ' + bar['section'])
        for voice, rendered in (('Vocal', vocal), ('Ins', ins)):
            lines.append('V: ' + voice)
            if bar['meter'] != previous['meter']:
                lines.append('M:' + bar['meter'])
            if bar['key'] != previous['key']:
                lines.append('K:' + bar['key'])
            lines.append(compress(rendered[index:end]))
        index = end
    text = '\n'.join(lines) + '\n'
    parsed = parse(text)
    if [tuple(x) for x in parsed.voices['Ins'].notes] != notes or parsed.voices['Vocal'].notes:
        raise ValueError('Internal note roundtrip failed')
    # Compare active harmony; repeating the active symbol at bar starts is native.
    def dedup(events):
        result = []
        for item in events:
            if not result or result[-1][1] != item[1]:
                result.append(tuple(item))
        return result
    if dedup(parsed.voices['Vocal'].chords) != dedup(chords):
        raise ValueError('Internal harmony roundtrip failed')
    return text



def section_starts(text, score):
    """Map native section comments to their absolute bar-start times."""
    cursor, pending = 0, None
    result = {}
    for index, line in enumerate(text.splitlines()):
        if line.startswith('% '):
            pending = line[2:]
            if pending not in SECTIONS:
                raise ValueError(f'Unknown section label: {pending}')
        if score.music_lines.get(index) != 'Vocal':
            continue
        if pending is not None:
            result[score.voices['Vocal'].bars[cursor][0]] = pending
            pending = None
        for bar in line[:-1].split('|'):
            rest = re.fullmatch(r'Z([2-4])?', bar.strip())
            cursor += int(rest.group(1) or 1) if rest else 1
    return result


def subtract_intervals(start, duration, occupied):
    pieces = [(start, start + duration)]
    for left, right in occupied:
        remaining = []
        for a, b in pieces:
            if right <= a or left >= b:
                remaining.append((a, b))
            else:
                if a < left:
                    remaining.append((a, left))
                if right < b:
                    remaining.append((right, b))
        pieces = remaining
    return pieces


def convert_score(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Need a nonempty native score')
    source = parse(text)
    vocal, ins = source.voices['Vocal'], source.voices['Ins']
    if not vocal.notes and not ins.notes:
        raise ValueError('The score contains no sounding notes')
    occupied = [(t, t+d) for t, _, d in vocal.notes]
    merged = [list(n) for n in vocal.notes]
    for start, pitch, duration in ins.notes:
        pieces = subtract_intervals(start, duration, occupied)
        merged.extend([a, pitch, b-a] for a,b in pieces)
    merged.sort()
    sections = section_starts(text, source)
    starts = {start for start, _, _ in vocal.bars}
    if any(when not in starts for when, _ in vocal.keys):
        raise ValueError('An inline key change occurs inside a bar; normalize its spelling without changing pitches first')
    bars = []
    for start, _, (n,d) in vocal.bars:
        key = next(key for t,key in reversed(vocal.keys) if t <= start)
        bar = dict(meter=f'{n}/{d}',key=key)
        if start in sections:
            bar['section'] = sections[start]
        bars.append(bar)
    chords = []
    for when,symbol in vocal.chords:
        if chords and chords[-1][0] == str(when):
            if chords[-1][1] != symbol:
                raise ValueError('Conflicting chord labels at the same time')
            continue
        chords.append([str(when),symbol])
    events = dict(bpm=source.bpm,key=vocal.keys[0][1],bars=bars,
        notes=[[str(t),str(d),p] for t,p,d in merged],chords=chords)
    converted = compile_events(events)
    target = parse(converted)
    if target.voices['Ins'].notes != merged or target.voices['Vocal'].notes:
        raise ValueError('Voice transfer changed the intended note events')
    if target.voices['Ins'].bars != ins.bars or target.bpm != source.bpm:
        raise ValueError('Voice transfer changed meter, timing or tempo')
    for note in vocal.notes:
        if note not in target.voices['Ins'].notes:
            raise ValueError('A vocal note was not preserved exactly')
    def harmony(chord_list):
        result=[]
        for event in chord_list:
            if not result or result[-1][1] != event[1]: result.append(event)
        return result
    if harmony(target.voices['Vocal'].chords) != harmony(vocal.chords):
        raise ValueError('Voice transfer changed harmony')
    lyrics = "\n\n".join("[" + label.title() + "]" for label in sections.values())
    return converted, lyrics

