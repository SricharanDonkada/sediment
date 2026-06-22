from app import db, embed
from app.config import settings


def resolve(mention: str) -> str | None:
    result = db.find_entity_exact(mention)
    if result:
        return result["canonical_name"]

    result = db.find_entity_by_alias(mention)
    if result:
        return result["canonical_name"]

    embedding = embed.embed_entity(mention)
    result = db.find_closest_entity(embedding, settings.entity_resolution_threshold)
    if result:
        return result["canonical_name"]

    return None
