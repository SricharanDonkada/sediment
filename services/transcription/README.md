# Transcription Service

Consumes audio jobs produced by the [ingestion service](../ingestion), transcribes
them into a **speaker-labeled conversation script**, stores the script as a plain
`.txt` in MinIO, and enqueues a job for the extraction service.

This is a standalone **worker** (no web surface) — it blocks on a Redis queue,
processes one job at a time, and loops.

## Pipeline

```
audio-transcribe ──claim──▶ download audio ──▶ transcribe + diarize ──▶ merge ──▶ store .txt ──▶ extract
                  (MinIO `audio`)         (faster-whisper) (pyannote)  (script) (MinIO `transcripts`)
```

1. **Claim** a job from `audio-transcribe` (`BRPOPLPUSH` onto a processing list — see [Reliability](#reliability)).
2. **Download** the 16 kHz mono WAV from the `audio` bucket to a temp file.
3. **Transcribe** with `faster-whisper` → timestamped text segments.
4. **Diarize** with `pyannote` → speaker-labeled time spans.
5. **Merge**: assign each segment the speaker it overlaps most, relabel speakers
   `SPEAKER_A/B/…` by first appearance, join consecutive same-speaker segments.
6. **Store** the script as `<stem>.txt` in the `transcripts` bucket (creating it if needed).
7. **Enqueue** a `TranscriptionMessage{object_key, bucket}` onto `extract`, then **ack**.

### Stack: `faster-whisper` + `pyannote`, no WhisperX

WhisperX's value is word-level forced alignment, which isn't needed here — the goal
is a conversation script with speaker labels, not word-level timestamps. Dropping it
removes a dependency, avoids its alignment-dictionary limitation (which breaks on part
numbers, prices, and model numbers), and gives full control over the output format.
Each faster-whisper segment is labeled by overlapping it with pyannote's speaker
segments (a ~20–30 line custom merge in [`app/merge.py`](app/merge.py)).

### Example output

```
SPEAKER_A: I need a replacement for the Carrier 24ACC636A003.

SPEAKER_B: Would an aftermarket work or do you need exact match?

SPEAKER_A: Exact match preferred, open to compatible if it's cheaper.
```

## Modules

| File | Responsibility |
|---|---|
| [`app/config.py`](app/config.py) | `Settings` via pydantic-settings; defaults match `docker-compose.yml`. |
| [`app/storage.py`](app/storage.py) | MinIO: ensure `transcripts` bucket, download audio to a temp file, upload transcript. |
| [`app/queue.py`](app/queue.py) | Reliable Redis: `claim`, `ack`, `dead_letter`, `enqueue`. |
| [`app/transcribe.py`](app/transcribe.py) | faster-whisper singleton → `list[Segment]`. |
| [`app/diarize.py`](app/diarize.py) | pyannote singleton → `list[SpeakerTurn]`. |
| [`app/merge.py`](app/merge.py) | Pure core: speaker assignment + script rendering. |
| [`app/pipeline.py`](app/pipeline.py) | Orchestrates transcribe + diarize + merge for one file. |
| [`app/worker.py`](app/worker.py) | The loop: claim → process → store → enqueue → ack / dead-letter. |

## Reliability

`claim` uses `BRPOPLPUSH` to atomically move a job from `audio-transcribe` to
`audio-transcribe:processing` while it is in flight, so a crash mid-job does not lose it.
On success the job is `ack`ed (removed from the processing list); on **any** exception
the worker logs the failure and moves the job to `audio-transcribe:dead` for inspection.
Ordering is store → enqueue → ack, mirroring ingestion's "a stored-but-unqueued object
is inert" reasoning.

| Redis list | Role |
|---|---|
| `audio-transcribe` | Input (produced by ingestion) |
| `audio-transcribe:processing` | In-flight jobs |
| `extract` | Output to extraction |
| `audio-transcribe:dead` | Failed jobs, for inspection |

## Configuration

Environment variables (defaults match `docker-compose.yml`):

| Variable | Default | Notes |
|---|---|---|
| `MINIO_ENDPOINT` | `localhost:9000` | `minio:9000` in compose |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `sediment` / `sediment-dev` | |
| `MINIO_SECURE` | `false` | |
| `TRANSCRIPTS_BUCKET` | `transcripts` | Created on startup if missing |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `INGESTION_QUEUE` | `audio-transcribe` | |
| `TRANSCRIPTION_QUEUE` | `extract` | |
| `WHISPER_MODEL` | `large-v3-turbo` | Cost/accuracy tuning |
| `WHISPER_DEVICE` | `cpu` | Set `cuda` on a GPU host |
| `WHISPER_COMPUTE_TYPE` | `int8` | e.g. `float16` on GPU |
| `HF_TOKEN` | _(empty)_ | **Required** — see below |

> ⚠ **`HF_TOKEN` is required.** pyannote `community-1` is a gated model: create a
> Hugging Face token and accept the model terms at
> <https://huggingface.co/pyannote/speaker-diarization-community-1>. The worker fails
> fast with a clear error if the token is missing.

## Running

From the repo root, with `HF_TOKEN` set in your environment (or a `.env` file):

```bash
docker compose up -d transcription
docker compose logs -f transcription
```

The container caches downloaded models in the `hf-cache` named volume, so they are not
re-fetched on restart. For GPU, set `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16`
and expose a GPU to the container.

## Development & testing

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```bash
cd services/transcription
uv sync
uv run pytest -m "not slow"      # unit + integration tests
```

The queue and storage tests talk to **real** Redis and MinIO — start them first:

```bash
docker compose up -d redis minio
```

The faster-whisper / pyannote wrappers are unit-tested with the models mocked; the pure
`merge.py` core has thorough unit tests. Real model inference is left as an optional
`@pytest.mark.slow` integration test (too heavy for the default run).
