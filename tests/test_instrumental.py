from fractions import Fraction

from yue2_instrumental import convert_score, parse


def test_moves_melody_without_changing_timing_or_harmony():
    source = '''X:1
T:
M:4/4
L:1/8
Q:1/4=100
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
"C"C4"G"D4|
V: Ins
E8|
% outro
V: Vocal
Z|
V: Ins
G8|
'''
    converted, lyrics = convert_score(source)
    score = parse(converted)
    original = parse(source)

    assert score.voices['Vocal'].notes == []
    assert score.voices['Ins'].notes == [
        [Fraction(0), 60, Fraction(2)],
        [Fraction(2), 62, Fraction(2)],
        [Fraction(4), 67, Fraction(4)],
    ]
    chords = score.voices['Vocal'].chords
    changes = [event for i, event in enumerate(chords) if i == 0 or event[1] != chords[i - 1][1]]
    assert changes == original.voices['Vocal'].chords
    assert score.voices['Ins'].bars == original.voices['Ins'].bars
    assert score.bpm == original.bpm
    assert lyrics == '[Verse]\n\n[Outro]'
