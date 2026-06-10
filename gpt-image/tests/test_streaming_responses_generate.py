import base64
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class StreamingResponsesGenerateTests(unittest.TestCase):
    def test_request_image_returns_partial_image_when_requested(self):
        from streaming_responses_generate import request_image

        class FakeResponse(io.BytesIO):
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        stream = (
            b'event: response.image_generation_call.partial_image\n'
            b'data: {"type":"response.image_generation_call.partial_image","partial_image_b64":"cGFydGlhbA=="}\n\n'
            b'event: keepalive\n'
            b'data: {"type":"keepalive","sequence_number":2}\n\n'
        )

        with patch("urllib.request.urlopen", return_value=FakeResponse(stream)):
            self.assertEqual(request_image({}, "local-key", "https://example.invalid", accept_partial=True), "cGFydGlhbA==")

    def test_launcher_defaults_to_streaming_responses_provider(self):
        import generate

        with patch.object(sys, "argv", ["generate.py", "-p", "test prompt", "--dry-run"]):
            self.assertEqual(generate.main(), 0)

    def test_launcher_accepts_legacy_provider_flag(self):
        import generate

        with patch.object(sys, "argv", ["generate.py", "--provider", "openai-cli"]):
            with patch.object(generate, "_import_local_or_installed_main", return_value=lambda: 0):
                self.assertEqual(generate.main(), 0)

    def test_resolves_private_skill_key_and_ignores_openai_key(self):
        from streaming_responses_generate import resolve_api_key

        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / ".env"
            key_file.write_text("GPT_IMAGE_API_KEY=local-skill-key\n", encoding="utf-8")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-global-key"}, clear=True):
                self.assertEqual(resolve_api_key([key_file]), "local-skill-key")

            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "openai-global-key",
                    "GPT_IMAGE_SKILL_API_KEY": "env-skill-key",
                },
                clear=True,
            ):
                self.assertEqual(resolve_api_key([key_file]), "env-skill-key")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-global-key"}, clear=True):
                self.assertIsNone(resolve_api_key([]))

    def test_resolves_endpoint_from_env_file(self):
        from streaming_responses_generate import resolve_endpoint

        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / ".env"
            config_file.write_text("GPT_IMAGE_ENDPOINT=https://provider.example/v1/responses\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(resolve_endpoint([config_file]), "https://provider.example/v1/responses")

    def test_converts_local_image_to_data_url(self):
        from streaming_responses_generate import image_reference_to_data_url

        png_header = base64.b64decode("iVBORw0KGgo=")
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "ref.png"
            image_path.write_bytes(png_header)

            data_url = image_reference_to_data_url(str(image_path))

        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        self.assertIn("iVBORw0KGgo=", data_url)

    def test_extracts_final_image_b64_from_response_completed_event(self):
        from streaming_responses_generate import extract_image_b64

        event = {
            "type": "response.completed",
            "response": {
                "output": [
                    {"type": "message", "content": []},
                    {"type": "image_generation_call", "result": "ZmFrZS1pbWFnZQ=="},
                ]
            },
        }

        self.assertEqual(extract_image_b64(event), "ZmFrZS1pbWFnZQ==")

    def test_normalizes_documented_size_aliases(self):
        from streaming_responses_generate import normalize_size

        self.assertEqual(normalize_size("landscape"), "3840x2160")
        self.assertEqual(normalize_size("portrait"), "2160x3840")
        self.assertEqual(normalize_size("square"), "1024x1024")
        self.assertEqual(normalize_size("2880x2880"), "2880x2880")


if __name__ == "__main__":
    unittest.main()
