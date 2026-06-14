# Ingestion Service

Accepts audio content — either a direct file upload or a YouTube URL — normalizes it
to **16 kHz mono WAV**, stores the result in MinIO, and enqueues a job for the
transcription service.

This is a **FastAPI web service** with a single `/ingest` endpoint (plus a minimal
browser UI at `/`).

## Pipeline

```
upload / YouTube URL ──▶ normalize (ffmpeg) ──▶ store .wav ──▶ ingestion_queue
                          16kHz mono WAV         (MinIO `audio`)   (Redis)
```

1. **Receive** a raw audio file (any format ffmpeg understands) or a YouTube URL.
2. **Download** YouTube audio with `yt-dlp` (URL path only).
3. **Normalize** with ffmpeg → 16 kHz mono WAV.
4. **Store** the WAV as `<uuid>.wav` in the `audio` bucket (created on startup if
   missing). Store happens before enqueue — a stored-but-unqueued object is inert,
   a queued-but-unstored key would crash the transcription worker.
5. **Enqueue** an `IngestionMessage{object_key, bucket}` onto `ingestion_queue`.
6. **Return** `{"object_key": "<uuid>.wav", "bucket": "audio"}` to the caller.

## Modules

| File | Responsibility |
|---|---|
| [`app/config.py`](app/config.py) | `Settings` via pydantic-settings; defaults match `docker-compose.yml`. |
| [`app/audio.py`](app/audio.py) | ffmpeg wrapper: any format → 16 kHz mono WAV bytes. |
| [`app/youtube.py`](app/youtube.py) | yt-dlp wrapper: download best audio for a YouTube URL to a temp file. |
| [`app/storage.py`](app/storage.py) | MinIO: ensure `audio` bucket, upload WAV bytes. |
| [`app/queue.py`](app/queue.py) | Redis: `LPUSH` an `IngestionMessage` onto `ingestion_queue`. |
| [`app/main.py`](app/main.py) | FastAPI app: `GET /` (browser UI), `POST /ingest`. |

## API

### `POST /ingest`

Accepts `multipart/form-data` with **exactly one** of:

| Field | Type | Description |
|---|---|---|
| `file` | binary | Audio file (mp3, m4a, ogg, wav, …) |
| `youtube_url` | string | YouTube video URL |

Providing both or neither returns HTTP 400.

**Success response (200):**
```json
{"object_key": "3fa85f64-5717-4562-b3fc-2c963f66afa6.wav", "bucket": "audio"}
```

**Error responses:**

| Status | Condition |
|---|---|
| 400 | Both or neither of `file` / `youtube_url` provided |
| 422 | YouTube download failed or audio could not be processed |
| 503 | MinIO or Redis unreachable |

### `GET /`

Minimal browser UI for manual testing.

## Configuration

Environment variables (defaults match `docker-compose.yml`):

| Variable | Default | Notes |
|---|---|---|
| `MINIO_ENDPOINT` | `localhost:9000` | `minio:9000` in compose |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `sediment` / `sediment-dev` | |
| `MINIO_SECURE` | `false` | |
| `INGESTION_BUCKET` | `audio` | Created on startup if missing |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `INGESTION_QUEUE` | `ingestion_queue` | Consumed by the transcription worker |

## Running

```bash
docker compose up -d ingestion
docker compose logs -f ingestion
```

The service is available at `http://localhost:8000`.

## Development & testing

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```bash
cd services/ingestion
uv sync
uv run pytest
```

The queue and storage tests talk to **real** Redis and MinIO — start them first:

```bash
docker compose up -d redis minio
```

The endpoint tests use `httpx.TestClient` and monkeypatch storage/queue calls, so
they run without infrastructure.
