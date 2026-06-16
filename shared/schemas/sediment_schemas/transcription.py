from pydantic import BaseModel


class TranscriptionMessage(BaseModel):
    """Job envelope pushed onto the Redis transcription queue.

    Points at the stored transcript object. The extraction service imports
    this model to parse queue messages.
    """

    object_key: str
    bucket: str
