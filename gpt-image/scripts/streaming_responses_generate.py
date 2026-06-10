#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

DEFAULT_ENDPOINT = ""
ENDPOINT_ENV_NAMES = (
    "GPT_IMAGE_ENDPOINT",
    "GPT_IMAGE_RESPONSES_ENDPOINT",
    "IMAGE_RESPONSES_ENDPOINT",
)
KEY_ENV_NAMES = (
    "GPT_IMAGE_SKILL_API_KEY",
    "GPT_IMAGE_API_KEY",
    "IMAGE_API_KEY",
    "RESPONSES_API_KEY",
)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 CodexGptImageSkill/1.0"
)
SIZE_ALIASES = {
    "1k": "1024x1024",
    "2k": "1536x1024",
    "4k": "3840x2160",
    "square": "1024x1024",
    "landscape": "3840x2160",
    "wide": "3840x2160",
    "portrait": "2160x3840",
    "tall": "2160x3840",
}


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def default_key_files() -> list[Path]:
    root = skill_dir()
    return [root / ".env"]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("'\"")
        if name:
            values[name] = value
    return values


def resolve_api_key(key_files: Iterable[Path] | None = None) -> str | None:
    for name in KEY_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value

    for key_file in default_key_files() if key_files is None else key_files:
        values = parse_env_file(Path(key_file))
        for name in KEY_ENV_NAMES:
            value = values.get(name)
            if value:
                return value
    return None


def resolve_endpoint(config_files: Iterable[Path] | None = None) -> str:
    for name in ENDPOINT_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value

    for config_file in default_key_files() if config_files is None else config_files:
        values = parse_env_file(Path(config_file))
        for name in ENDPOINT_ENV_NAMES:
            value = values.get(name)
            if value:
                return value
    return DEFAULT_ENDPOINT


def normalize_size(value: str) -> str:
    return SIZE_ALIASES.get(value.lower(), value)


def image_reference_to_data_url(reference: str) -> str:
    if reference.startswith(("data:image/", "http://", "https://")):
        return reference

    image_path = Path(reference)
    if not image_path.is_file():
        raise FileNotFoundError(f"reference image not found: {reference}")

    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    content: list[dict[str, str]] = []
    for image in args.image or []:
        content.append({"type": "input_image", "image_url": image_reference_to_data_url(image)})
    content.append({"type": "input_text", "text": args.prompt})

    return {
        "model": args.model,
        "input": [{"role": "user", "content": content}],
        "tools": [
            {
                "type": "image_generation",
                "size": normalize_size(args.size),
                "quality": args.quality,
                "output_format": args.format,
            }
        ],
        "stream": True,
    }


def iter_b64_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key in ("result", "b64_json", "partial_image_b64"):
            item = value.get(key)
            if isinstance(item, str) and item:
                yield item
        for item in value.values():
            yield from iter_b64_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_b64_values(item)


def extract_image_b64(event: dict[str, Any]) -> str | None:
    for value in iter_b64_values(event):
        if value.startswith("data:image/"):
            return value.split(",", 1)[1] if "," in value else value
        return value
    return None


def iter_sse_events(response: Any) -> Iterable[dict[str, Any]]:
    data_lines: list[str] = []
    while True:
        raw_line = response.readline()
        if raw_line == b"":
            break

        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data_lines:
                raw_data = "\n".join(data_lines).strip()
                data_lines.clear()
                if raw_data == "[DONE]":
                    break
                if raw_data:
                    yield json.loads(raw_data)
            continue

        if line.startswith("data:"):
            data_lines.append(line[5:].strip())


def request_image(
    payload: dict[str, Any],
    api_key: str,
    endpoint: str,
    *,
    accept_partial: bool = False,
    accept_partial_after: float = 240.0,
) -> str:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": os.environ.get("GPT_IMAGE_HTTP_USER_AGENT", DEFAULT_USER_AGENT),
        },
    )

    latest_b64: str | None = None
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            for event in iter_sse_events(response):
                image_b64 = extract_image_b64(event)
                if image_b64:
                    latest_b64 = image_b64
                    if accept_partial and time.monotonic() - started >= accept_partial_after:
                        return latest_b64
                if event.get("type") == "response.completed" and latest_b64:
                    return latest_b64
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc

    if not latest_b64:
        raise RuntimeError("stream completed without an image payload")
    return latest_b64


def output_path(base: str | None, index: int, count: int, image_format: str) -> Path:
    suffix = "." + ("jpg" if image_format == "jpeg" else image_format)
    if base:
        path = Path(base)
        if not path.suffix:
            path = path.with_suffix(suffix)
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = Path.cwd() / f"gpt-image-{stamp}{suffix}"

    if count <= 1:
        return path
    return path.with_name(f"{path.stem}-{index + 1}{path.suffix}")


def write_image(image_b64: str, path: Path) -> Path:
    if image_b64.startswith("data:image/") and "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(image_b64))
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate images through a configurable streaming Responses API.")
    parser.add_argument("-p", "--prompt", required=True, help="Prompt or edit instruction.")
    parser.add_argument("-f", "--file", help="Output image path. Auto-named when omitted.")
    parser.add_argument("-i", "--image", action="append", help="Reference image path, data URL, or public URL.")
    parser.add_argument("-m", "--mask", help="Not supported by the default streaming Responses client.")
    parser.add_argument("--model", default=os.environ.get("GPT_IMAGE_MODEL", "gpt-image-2"))
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--quality", default="high", choices=["auto", "low", "medium", "high"])
    parser.add_argument("-n", "--n", type=int, default=1)
    parser.add_argument("--format", default="png", choices=["png", "jpeg", "webp"])
    parser.add_argument("--compression", type=int, help="Accepted for CLI compatibility; not sent to this API.")
    parser.add_argument("--background", help="Accepted for CLI compatibility; not sent to this API.")
    parser.add_argument("--moderation", help="Accepted for CLI compatibility; not sent to this API.")
    parser.add_argument("--user", help="Accepted for CLI compatibility; not sent to this API.")
    parser.add_argument("--endpoint", default=None, help="Streaming Responses endpoint; overrides GPT_IMAGE_ENDPOINT.")
    parser.add_argument("--provider", default="streaming-responses", choices=["streaming-responses", "openai-cli"])
    parser.add_argument("--dry-run", action="store_true", help="Print the request body without calling the API.")
    parser.add_argument(
        "--accept-partial-after",
        type=float,
        default=240.0,
        help="Save the latest partial image after this many seconds if no final event arrives; use 0 for first preview.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mask:
        print("error: --mask/inpainting is not supported by the default streaming Responses client", file=sys.stderr)
        return 2
    if args.n < 1:
        print("error: --n must be at least 1", file=sys.stderr)
        return 2

    try:
        payload = build_payload(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({"endpoint": args.endpoint or resolve_endpoint(), "payload": payload}, ensure_ascii=False, indent=2))
        return 0

    api_key = resolve_api_key()
    if not api_key:
        names = ", ".join(KEY_ENV_NAMES)
        print(
            f"error: missing skill image API key. Set one of {names}, or create "
            f"{skill_dir() / '.env'} with GPT_IMAGE_API_KEY=...",
            file=sys.stderr,
        )
        return 2
    endpoint = args.endpoint or resolve_endpoint()
    if not endpoint:
        names = ", ".join(ENDPOINT_ENV_NAMES)
        print(
            f"error: missing streaming Responses endpoint. Set one of {names}, create "
            f"{skill_dir() / '.env'} with GPT_IMAGE_ENDPOINT=..., or pass --endpoint.",
            file=sys.stderr,
        )
        return 2

    written: list[Path] = []
    try:
        for index in range(args.n):
            image_b64 = request_image(
                payload,
                api_key,
                endpoint,
                accept_partial=True,
                accept_partial_after=args.accept_partial_after,
            )
            path = write_image(image_b64, output_path(args.file, index, args.n, args.format))
            written.append(path)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
