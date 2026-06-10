#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=1.55",
#     "python-dotenv>=1.0",
# ]
# ///
"""Skill launcher for the gpt-image skill.

Resolution order:
1. Default: run this skill's bundled streaming Responses API client.
2. With --provider openai-cli: delegate to the legacy shared gpt-image CLI.

This keeps `skills/gpt-image` usable when copied as a standalone skill folder
while preserving one canonical implementation for the installable Python CLI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_REPO_URL = "git+https://github.com/wuyoscar/gpt_image_2_skill"


def _take_provider_arg() -> str:
    """Remove this launcher's provider flag before forwarding other args."""
    provider = "streaming-responses"
    for index, arg in enumerate(list(sys.argv[1:]), start=1):
        if arg == "--provider" and index + 1 < len(sys.argv):
            provider = sys.argv[index + 1]
            del sys.argv[index : index + 2]
            return provider
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]
            del sys.argv[index]
            return provider
    return provider


def _run_streaming_responses_client() -> int:
    script_path = Path(__file__).resolve()
    sys.path.insert(0, str(script_path.parent))
    from streaming_responses_generate import main as streaming_main  # type: ignore

    return int(streaming_main(sys.argv[1:]) or 0)


def _import_local_or_installed_main():
    """Return gpt_image_cli.cli.main from repo-local src or installed package."""
    script_path = Path(__file__).resolve()

    # Full plugin/repo layout: <repo>/skills/gpt-image/scripts/generate.py
    # Standalone skill installs do not have this sibling src/ tree, so guard it.
    if len(script_path.parents) > 3:
        repo_src = script_path.parents[3] / "src"
        if (repo_src / "gpt_image_cli" / "cli.py").is_file():
            sys.path.insert(0, str(repo_src))

    try:
        from gpt_image_cli.cli import main  # type: ignore
    except ModuleNotFoundError:
        return None
    return main


def _delegate(command: list[str]) -> int:
    """Run another CLI process with the original argv and return its exit code."""
    completed = subprocess.run(command + sys.argv[1:], check=False)
    return completed.returncode


def main() -> int:
    provider = _take_provider_arg()
    if provider == "streaming-responses":
        return _run_streaming_responses_client()
    if provider != "openai-cli":
        print("error: --provider must be either 'streaming-responses' or 'openai-cli'", file=sys.stderr)
        return 2

    cli_main = _import_local_or_installed_main()
    if cli_main is not None:
        return int(cli_main() or 0)

    executable = shutil.which("gpt-image")
    if executable:
        return _delegate([executable])

    uvx = shutil.which("uvx") or shutil.which("uv")
    if uvx:
        if Path(uvx).name == "uv":
            return _delegate([uvx, "tool", "run", "--from", _REPO_URL, "gpt-image"])
        return _delegate([uvx, "--from", _REPO_URL, "gpt-image"])

    print(
        "error: could not find the gpt-image CLI backend. Install uv and run this skill "
        "again, or install the CLI first with:\n"
        f"  uv tool install {_REPO_URL}\n"
        "Then retry the same command.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
