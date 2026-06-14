from app import diarize, merge, transcribe


def run(audio_path: str) -> str:
    """Transcribe + diarize one audio file and return the conversation script."""
    segments = transcribe.transcribe(audio_path)
    turns = diarize.diarize(audio_path)
    return merge.to_script(segments, turns)
