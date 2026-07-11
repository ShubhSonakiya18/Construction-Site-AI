"""
tests/test_api_audio.py — Tests for POST /api/v1/audio/upload, GET /api/v1/audio/{id}/status.

run_pipeline (the Speech -> Extraction -> DB -> Generation orchestration in
app/services/pipeline_service.py) is monkeypatched to a no-op in these
tests. Testing the upload/status HTTP contract does not require actually
invoking Faster Whisper or the Groq API — those are already covered by
this session's manual end-to-end verification and by the existing
Sprint 3-5 unit test suites. What's under test here is: does the upload
endpoint validate correctly, save the file, create the AudioFile row, and
queue a background task; does the status endpoint report it correctly.
"""
from __future__ import annotations

import io
import uuid

import pytest

pytest_plugins = ["tests.conftest_api"]


@pytest.fixture(autouse=True)
def _stub_run_pipeline(monkeypatch):
    """Prevent the real pipeline (Whisper + Groq) from running during
    these HTTP-contract tests."""
    import app.api.v1.audio as audio_module

    monkeypatch.setattr(audio_module, "run_pipeline", lambda audio_file_id: None)


@pytest.fixture(autouse=True)
def _isolate_upload_dir(tmp_path, monkeypatch):
    """Redirect uploads to a pytest tmp_path instead of the real
    data/uploads/ directory, so tests never touch project files."""
    import app.api.v1.audio as audio_module

    monkeypatch.setattr(audio_module, "_UPLOAD_DIR", tmp_path / "uploads")


def _fake_wav_bytes() -> bytes:
    # Minimal valid-looking WAV header — upload_audio() only checks the
    # extension and size, not audio validity (that's speech/'s job, run
    # inside the stubbed-out background task).
    return b"RIFF____WAVEfmt "


class TestUploadAudio:
    def test_requires_authentication(self, api_client):
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("test.wav", io.BytesIO(_fake_wav_bytes()), "audio/wav")},
        )
        assert response.status_code == 401

    def test_accepts_valid_upload(self, api_client, auth_headers):
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("recording.wav", io.BytesIO(_fake_wav_bytes()), "audio/wav")},
            headers=auth_headers,
        )
        assert response.status_code == 202
        body = response.json()
        assert body["success"] is True
        assert body["data"]["processing_status"] == "pending"
        assert body["data"]["original_filename"] == "recording.wav"

    def test_rejects_unsupported_extension(self, api_client, auth_headers):
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("document.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_rejects_missing_file(self, api_client, auth_headers):
        response = api_client.post("/api/v1/audio/upload", headers=auth_headers)
        assert response.status_code == 422  # FastAPI's own required-field validation


class TestAudioStatus:
    def test_requires_authentication(self, api_client):
        response = api_client.get(f"/api/v1/audio/{uuid.uuid4()}/status")
        assert response.status_code == 401

    def test_nonexistent_audio_returns_404(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/audio/{uuid.uuid4()}/status", headers=auth_headers
        )
        assert response.status_code == 404

    def test_status_reflects_uploaded_file(self, api_client, auth_headers):
        upload_response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("recording.wav", io.BytesIO(_fake_wav_bytes()), "audio/wav")},
            headers=auth_headers,
        )
        audio_id = upload_response.json()["data"]["id"]

        status_response = api_client.get(
            f"/api/v1/audio/{audio_id}/status", headers=auth_headers
        )
        assert status_response.status_code == 200
        data = status_response.json()["data"]
        assert data["id"] == audio_id
        assert data["processing_status"] == "pending"  # run_pipeline was stubbed to a no-op
