#!/usr/bin/env python3
"""Benchmark vision models for intel image extraction.

Usage:
    python scripts/benchmark_vision.py --provider ollama --model llava path/to/images/
    python scripts/benchmark_vision.py --provider anthropic --model claude-sonnet-4-6 path/to/images/
    python scripts/benchmark_vision.py --provider ollama --model llava,moondream,llama3.2-vision path/to/images/

Prints extracted text for each image under each model, with timing.
Useful for comparing models before setting intel_vision_model in config.json.
"""

import sys
import time
from pathlib import Path

# Allow running from repo root or scripts/ dir.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env for API keys.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# Hardcoded settings. Update these values directly in the script.
PROVIDER = "ollama"
MODEL = "gemma4:31b-cloud"
#gemma4:31b-cloud , kimi-k2.5:cloud , qwen3.5:397b-cloud
IMAGE_DIR = ROOT / "images"

from applycling.llm import LLMError, extract_image_text

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}


def main() -> None:
    img_dir = IMAGE_DIR.expanduser()
    if not img_dir.is_dir():
        print(f"Error: {img_dir} is not a directory.", file=sys.stderr)
        sys.exit(1)

    images = sorted(f for f in img_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"No image files found in {img_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Provider: {PROVIDER}")
    print(f"Model:    {MODEL}")
    print(f"Images:   {len(images)} files in {img_dir}")
    print(f"{'=' * 72}\n")

    for image in images:
        print(f"--- {image.name} ---")
        size_kb = image.stat().st_size / 1024
        print(f"    Size: {size_kb:.0f} KB\n")

        print(f"  [{MODEL}]")
        start = time.time()
        try:
            text = extract_image_text(image, MODEL, PROVIDER)
            elapsed = time.time() - start
            if text.strip():
                # Indent extracted text for readability.
                indented = "\n".join(f"    {line}" for line in text.strip().splitlines())
                print(indented)
            else:
                print("    (empty response)")
            print(f"    -- {elapsed:.1f}s --\n")
        except LLMError as e:
            elapsed = time.time() - start
            print(f"    ERROR: {e}")
            print(f"    -- {elapsed:.1f}s --\n")

    print("=" * 72)
    print("Done. If desired, update data/config.json with the chosen model/provider.")


if __name__ == "__main__":
    main()
