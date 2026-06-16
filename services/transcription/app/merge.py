from dataclasses import dataclass


@dataclass
class Segment:
    """A transcript segment from faster-whisper."""

    start: float
    end: float
    text: str


@dataclass
class SpeakerTurn:
    """A speaker-labeled time span from pyannote."""

    start: float
    end: float
    speaker: str


def _overlap(s1: float, e1: float, s2: float, e2: float) -> float:
    """Seconds of overlap between two intervals (0 if disjoint)."""
    return max(0.0, min(e1, e2) - max(s1, s2))


def _gap(seg: Segment, turn: SpeakerTurn) -> float:
    """Seconds between a segment and a turn that do not overlap."""
    if seg.end < turn.start:
        return turn.start - seg.end
    if turn.end < seg.start:
        return seg.start - turn.end
    return 0.0


def _assign_speaker(seg: Segment, turns: list[SpeakerTurn]) -> str | None:
    """Pick the pyannote speaker label for a segment by max total overlap;
    fall back to the nearest turn when nothing overlaps. None if no turns."""
    if not turns:
        return None
    totals: dict[str, float] = {}
    for t in turns:
        ov = _overlap(seg.start, seg.end, t.start, t.end)
        if ov > 0:
            totals[t.speaker] = totals.get(t.speaker, 0.0) + ov
    if totals:
        return max(totals, key=lambda k: totals[k])
    return min(turns, key=lambda t: _gap(seg, t)).speaker


def to_script(segments: list[Segment], turns: list[SpeakerTurn]) -> str:
    """Render segments + diarization into a speaker-labeled conversation script.

    Each segment is labeled with its overlapping speaker, raw labels are
    remapped to SPEAKER_A/B/... in first-appearance order, consecutive
    same-speaker segments are joined into one turn, and turns are separated
    by a blank line.
    """
    if not segments:
        return ""

    # Label each segment with a raw speaker (or a single placeholder).
    labeled: list[tuple[str, str]] = []  # (raw_speaker, text)
    for seg in segments:
        raw = _assign_speaker(seg, turns) or "_SINGLE"
        labeled.append((raw, seg.text.strip()))

    # Drop segments whose text is empty after stripping (e.g. silence).
    labeled = [(raw, text) for raw, text in labeled if text]
    if not labeled:
        return ""

    # Remap raw labels to SPEAKER_A, SPEAKER_B, ... by first appearance.
    mapping: dict[str, str] = {}
    for raw, _ in labeled:
        if raw not in mapping:
            if len(mapping) >= 26:
                raise ValueError("too many speakers (>26) to label")
            mapping[raw] = f"SPEAKER_{chr(ord('A') + len(mapping))}"

    # Join consecutive same-speaker segments into turns.
    turns_out: list[tuple[str, list[str]]] = []
    for raw, text in labeled:
        label = mapping[raw]
        if turns_out and turns_out[-1][0] == label:
            turns_out[-1][1].append(text)
        else:
            turns_out.append((label, [text]))

    lines = [f"{label}: {' '.join(parts)}" for label, parts in turns_out]
    return "\n\n".join(lines) + "\n"
