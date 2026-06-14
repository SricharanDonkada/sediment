from app.merge import Segment, SpeakerTurn, to_script


def test_overlap_picks_majority_speaker():
    # Segment 0-2s overlaps SPEAKER_00 for 1.5s and SPEAKER_01 for 0.5s.
    segments = [Segment(start=0.0, end=2.0, text="hello there")]
    turns = [
        SpeakerTurn(start=0.0, end=1.5, speaker="SPEAKER_00"),
        SpeakerTurn(start=1.5, end=2.0, speaker="SPEAKER_01"),
    ]
    assert to_script(segments, turns) == "SPEAKER_A: hello there\n"


def test_two_speakers_labeled_by_first_appearance():
    segments = [
        Segment(start=0.0, end=1.0, text="first"),
        Segment(start=1.0, end=2.0, text="second"),
    ]
    # pyannote's raw label for the first speaker is SPEAKER_01, but first
    # appearance must map to SPEAKER_A regardless of the raw label.
    turns = [
        SpeakerTurn(start=0.0, end=1.0, speaker="SPEAKER_01"),
        SpeakerTurn(start=1.0, end=2.0, speaker="SPEAKER_00"),
    ]
    assert to_script(segments, turns) == "SPEAKER_A: first\n\nSPEAKER_B: second\n"


def test_consecutive_same_speaker_segments_are_joined():
    segments = [
        Segment(start=0.0, end=1.0, text="part one"),
        Segment(start=1.0, end=2.0, text="part two"),
    ]
    turns = [SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00")]
    assert to_script(segments, turns) == "SPEAKER_A: part one part two\n"


def test_segment_with_no_overlap_falls_back_to_nearest_turn():
    # Segment 5-6s overlaps nothing; nearest turn is SPEAKER_00 (ends at 2s).
    segments = [Segment(start=5.0, end=6.0, text="late")]
    turns = [
        SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=20.0, end=21.0, speaker="SPEAKER_01"),
    ]
    assert to_script(segments, turns) == "SPEAKER_A: late\n"


def test_empty_diarization_is_single_speaker():
    segments = [
        Segment(start=0.0, end=1.0, text="alpha"),
        Segment(start=1.0, end=2.0, text="beta"),
    ]
    assert to_script(segments, []) == "SPEAKER_A: alpha beta\n"


def test_empty_segments_is_empty_string():
    assert to_script([], [SpeakerTurn(0.0, 1.0, "SPEAKER_00")]) == ""


def test_mixed_overlap_and_fallback_distinct_speakers():
    # seg1 overlaps SPEAKER_00; seg2 overlaps nothing and falls back to its
    # nearest turn SPEAKER_01 (gap 0.5s) over SPEAKER_00 (gap 9s).
    segments = [
        Segment(start=0.0, end=1.0, text="hi"),
        Segment(start=10.0, end=11.0, text="bye"),
    ]
    turns = [
        SpeakerTurn(start=0.0, end=1.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=9.0, end=9.5, speaker="SPEAKER_01"),
    ]
    assert to_script(segments, turns) == "SPEAKER_A: hi\n\nSPEAKER_B: bye\n"


def test_empty_text_segments_are_dropped():
    segments = [
        Segment(start=0.0, end=1.0, text="real"),
        Segment(start=1.0, end=2.0, text="   "),
    ]
    turns = [SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00")]
    assert to_script(segments, turns) == "SPEAKER_A: real\n"
