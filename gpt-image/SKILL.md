---
name: gpt-image
description: "Use this skill whenever a user asks to generate, create, draw, render, or edit images with GPT Image 2 / gpt-image-2, text-to-image, reference-image editing, posters, typography, Chinese text, UI mockups, diagrams, or gallery prompts. For real products, brands, people, places, current events, or any subject where factual visual details matter, first use Codex's active model/tools to search or inspect sources, summarize the relevant facts, write a source-grounded prompt, then call the bundled img.gohok.top streaming Responses API client with a skill-private API key (`GPT_IMAGE_SKILL_API_KEY`, `GOHOK_IMAGE_API_KEY`, or `.gohok.env`). Only use the legacy OpenAI CLI when explicitly requested with `--provider openai-cli`."
metadata:
  compatibility: "Requires Python 3.11+. Default API calls use img.gohok.top `/v1/responses` with a skill-private key and may incur provider charges. Legacy OpenAI CLI fallback requires `gpt-image`, `uv`, or `uvx` plus `OPENAI_API_KEY`."
  openclaw:
    requires:
      anyBins: ["python"]
    primaryEnv: "GOHOK_IMAGE_API_KEY"
    homepage: "https://img.gohok.top/docs.html"
---

# gpt-image

Agent runbook for GPT Image 2 generation and reference-image editing. For factual subjects, research and summarize first; then use the prompt library; then call the bundled streaming API client. Do not write new image-generation request code for normal image requests.

## Operating Loop

1. **Classify the request**: `generate` or `reference edit`; identify whether the subject is factual/current, asset type, exact text, aspect ratio, reference files, safety constraints, and quality.
2. **Research factual subjects first**: for real products, brands, people, places, current events, or visually specific subjects, use Codex's active model/tools to search the web or inspect provided sources before prompting. Summarize the visual facts to preserve: names, colors, shapes, materials, logos/text treatment, camera/product features, setting, era, and constraints. Cite or mention the sources used in the final reply when web search was used.
3. **Write a source-grounded prompt**: convert the research summary into a concise image prompt. Keep verified facts explicit; mark imaginative parts as concept/art direction. Avoid inventing specs, claims, logos, or text not supported by the research unless the user asks for a fictional concept.
4. **Search skill references**: open `references/gallery.md`; load/search the closest `references/gallery-<category>.md` file(s). Read actual `**Prompt**` text before choosing a pattern.
5. **Refine with craft**: load `references/craft.md` for dense text, diagrams, UI, data visualization, multi-panel layouts, weak prompts, or no close gallery match.
6. **Confer when useful**: before costly or ambiguous calls, present 1-2 matched directions plus planned size/quality; ask at most one concise question. Skip long discussion for precise "generate now" requests.
7. **Preflight**: verify the output path, reference-image paths, endpoint mode, size, quality, and whether the skill-private key exists. Never print secret values.
8. **Execute**: call `scripts/generate.py`, which defaults to the bundled `img.gohok.top` streaming Responses API client.
9. **Report**: output file path(s), key flags, factual sources used, and one concise refinement suggestion if useful.

Fast path: precise fictional/stylistic prompt + explicit "generate now" -> quick reference/craft check, then `scripts/generate.py`. Do not use this fast path for real-world factual subjects unless the user explicitly says not to search.

## Default API

The local API documentation at `D:\Download\流式生图 API 文档.html` describes the default provider:

- Endpoint: `POST https://img.gohok.top/v1/responses`
- Auth: `Authorization: Bearer <skill-private-key>`
- Headers: `Content-Type: application/json`, `Accept: text/event-stream`
- Model: `gpt-image-2`
- Tool: `{"type":"image_generation","size":"...","quality":"...","output_format":"png"}`
- Text input: `{"type":"input_text","text":"..."}`
- Reference images: add `{"type":"input_image","image_url":"data:image/png;base64,..."}` before the text input
- SSE image fields: preview images may appear in `partial_image_b64`; final images usually appear in `response.output[].result`

The bundled client reads the SSE stream and writes the latest final image payload to disk.

## Key Rules

- Default provider reads only skill-private key names: `GPT_IMAGE_SKILL_API_KEY`, `GOHOK_IMAGE_API_KEY`, `AISWING_IMAGE_API_KEY`, or `IMG_GOHOK_API_KEY`.
- Default provider also reads `C:\Users\huishengli\.codex\skills\gpt-image\.gohok.env` or `.env` inside this skill folder. Use `GOHOK_IMAGE_API_KEY=...`.
- Default provider intentionally does **not** read `OPENAI_API_KEY`; that variable is only for the legacy `--provider openai-cli` path.
- If the private key is missing, report that it is missing and ask for/setup the key file only if the user requested setup.
- Never print, echo, commit, or paste API key values.

## CLI Usage

Preferred default:

```bash
python "C:\Users\huishengli\.codex\skills\gpt-image\scripts\generate.py" -p "PROMPT" -f "out.png" --size landscape --quality high
```

Reference image editing:

```bash
python "C:\Users\huishengli\.codex\skills\gpt-image\scripts\generate.py" -p "Keep the same subject, turn it into a cinematic product poster" -i "reference.png" -f "out.png" --size landscape --quality high
```

Dry-run request body without API call:

```bash
python "C:\Users\huishengli\.codex\skills\gpt-image\scripts\generate.py" -p "PROMPT" --dry-run
```

Legacy OpenAI CLI fallback only when explicitly needed:

```bash
python "C:\Users\huishengli\.codex\skills\gpt-image\scripts\generate.py" --provider openai-cli -p "PROMPT" -f "out.png"
```

## Flags

| Flag | Values | Use |
|---|---|---|
| `-p, --prompt` | string | Required prompt/edit instruction |
| `-f, --file` | path | Output path; auto-named if omitted |
| `-i, --image` | repeatable path/URL/data URL | Adds reference images to the Responses request |
| `--model` | default `gpt-image-2` | Image model |
| `--size` | `1024x1024`, `1536x1024`, `1024x1536`, `3840x2160`, `2160x3840`, `2880x2880`, `auto`, or aliases | Canvas size |
| `--quality` | `auto`, `low`, `medium`, `high` | Cost/quality dial |
| `-n, --n` | integer | Number of sequential generations |
| `--format` | `png`, `jpeg`, `webp` | Output encoding |
| `--provider` | `gohok`, `openai-cli` | Default is `gohok`; legacy fallback is opt-in |
| `--dry-run` | boolean | Print endpoint and JSON body without calling the API |

Compatibility-only flags accepted by the default provider but not sent to the API: `--compression`, `--background`, `--moderation`, `--user`.

Unsupported on the default provider: `--mask` / inpainting. Use `--provider openai-cli` only if inpainting is required and OpenAI key setup is available.

## Size Policy

- default/social square: `1024x1024` or alias `square`
- poster/mobile/beauty: `2160x3840` or alias `portrait`
- landscape/gameplay/photo/hero: `3840x2160` or alias `landscape`
- balanced horizontal: `1536x1024`
- balanced vertical: `1024x1536`
- large square: `2880x2880`

## Quality Policy

- `low`: cheap drafts and broad exploration.
- `medium`: normal exploration and style probing.
- `high`: final assets, Chinese text, posters, diagrams, UI, paper figures, dense labels, or 4K.

## Reference Loading

- `references/gallery.md`: routing index for the Reference Gallery Atlas. Load first.
- `references/gallery-*.md`: concrete prompts, previews, paths, metadata, attribution. Load 1 category for normal requests; 2-3 for hybrids.
- `references/craft.md`: prompt-craft checklist. Load for prompt repair, exact text, UI/data/diagram grammar, edit invariants, and multi-panel consistency.
- `references/openai-cookbook.md`: use only for legacy OpenAI parameter/model behavior.

Load the smallest useful slice; never load all category files by default.

## Verification

- Before API call: confirm provider, endpoint mode, size, quality, output path, and reference files.
- After CLI call: report path(s) printed by the CLI and surface stderr on failure.
- For reference edits: verify every `-i` path exists unless it is already a data URL or public URL.
- For script changes: run `python -m unittest discover -s "C:\Users\huishengli\.codex\skills\gpt-image\tests" -v` and skill validation.
