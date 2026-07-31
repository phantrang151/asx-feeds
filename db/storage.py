from db.client import get_client

DOCUMENTS_BUCKET = "documents"


def ensure_documents_bucket() -> None:
    """Idempotent bucket creation, same spirit as PostgresStore/PostgresSaver's .setup()
    in agent/chat/persistence.py - safe to call on every process start. get_bucket()
    raises when the bucket doesn't exist yet, so that's the signal to create it."""
    storage = get_client().storage
    try:
        storage.get_bucket(DOCUMENTS_BUCKET)
    except Exception:
        storage.create_bucket(DOCUMENTS_BUCKET, options={"public": False})
