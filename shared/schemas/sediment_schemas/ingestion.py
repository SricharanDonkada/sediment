from pydantic import BaseModel


class IngestionMessage(BaseModel):
    """Job envelope pushed onto the Redis ingestion queue.

    Intentionally minimal: identifies the stored audio object only.
    Downstream services import this model to parse queue messages.
    """

    object_key: str
    bucket: str
