#!/usr/bin/env python3
"""
Bulk import recipe photos into the meal planner Google Sheet.

Each image is sent to the Gemini vision API to extract a recipe, then all
extracted recipes are POSTed to the Apps Script web app which writes them
to the Sheet.

Usage:
    python bulk_import.py photo1.png photo2.heic       # specific files
    python bulk_import.py ~/Desktop/recipe-photos/     # all images in a dir
    python bulk_import.py *.jpg --dry-run              # extract only, no write
    python bulk_import.py *.jpg --yes                  # skip confirmation

    python bulk_import.py --check                      # verify web app is live
"""
import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Supported image extensions (lowercase)
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.tiff', '.tif'}

# Use 2.5-flash-lite for bulk import — more generous free tier quota than 2.5-flash
GEMINI_ENDPOINT = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-2.5-flash-lite:generateContent'
)

RECIPE_PROMPT = (
    'Extract the recipe from this image. Return a JSON object with:\n'
    '- "name": the recipe name (string)\n'
    '- "ingredients": array of strings, each formatted as "quantity unit ingredient"\n'
    '  e.g. ["2 cups flour", "1 lb chicken thighs", "3 cloves garlic"]\n\n'
    'Return only the JSON object, no other text.'
)

RECIPE_PROMPT_STRICT = (
    'Return ONLY valid JSON with keys "name" (string) and "ingredients" (array of strings). '
    'No markdown, no explanation, no code fences.'
)


def _load_env():
    script_dir = Path(__file__).parent
    for d in [script_dir, script_dir.parent]:
        env_file = d / '.env'
        if env_file.exists():
            load_dotenv(env_file)
            return
    load_dotenv()


def _require(key):
    val = os.getenv(key, '').strip()
    if not val:
        print(f'Error: {key} is not set. Add it to your .env file.', file=sys.stderr)
        sys.exit(1)
    return val


def _get(key, default=''):
    return os.getenv(key, default).strip()


def collect_image_paths(inputs):
    """Expand a list of files/directories into a flat list of image Paths."""
    paths = []
    for inp in inputs:
        p = Path(inp).expanduser()
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
                    paths.append(child)
        elif p.is_file():
            if p.suffix.lower() not in IMAGE_EXTENSIONS:
                print(f'Warning: unsupported extension "{p.suffix}" — skipping {p.name}')
            else:
                paths.append(p)
        else:
            print(f'Warning: not found — skipping {inp}')
    return paths


def heic_to_jpeg(path):
    """Convert HEIC/HEIF to a temp JPEG via macOS sips.

    Returns (working_path, was_converted).
    On non-macOS or sips missing, returns (original_path, False) — Gemini
    accepts image/heic directly so the file is tried as-is.
    """
    if path.suffix.lower() not in {'.heic', '.heif'}:
        return path, False

    try:
        fd, tmp_path = tempfile.mkstemp(suffix='.jpg', prefix='bulk_import_')
        os.close(fd)
        subprocess.run(
            ['sips', '-s', 'format', 'jpeg', str(path), '--out', tmp_path],
            check=True,
            capture_output=True,
        )
        return Path(tmp_path), True
    except FileNotFoundError:
        print(f'  Warning: sips not found — sending {path.name} as HEIC directly')
        return path, False
    except subprocess.CalledProcessError as e:
        print(f'  Warning: sips conversion failed for {path.name} — sending as HEIC directly')
        return path, False


def image_to_base64(path):
    """Read an image file, return (base64_string, mime_type)."""
    mime_type, _ = mimetypes.guess_type(str(path))
    # Fallback MIME types for formats mimetypes may not know
    if not mime_type:
        ext = path.suffix.lower()
        mime_type = {
            '.heic': 'image/heic',
            '.heif': 'image/heif',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
        }.get(ext, 'image/png')

    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    return data, mime_type


def _extract_json(text):
    """Extract the first {...} block from text and parse it as JSON."""
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def parse_recipe_via_gemini(base64_data, mime_type, api_key, filename):
    """Call Gemini vision API to extract a recipe from an image.

    Returns a dict {name, ingredients} or None on any failure.
    Never raises.
    """
    def _call(prompt):
        resp = requests.post(
            GEMINI_ENDPOINT,
            params={'key': api_key},
            json={
                'contents': [{
                    'parts': [
                        {'inlineData': {'mimeType': mime_type, 'data': base64_data}},
                        {'text': prompt},
                    ],
                }],
            },
            timeout=60,
        )
        return resp

    try:
        # Retry on 429/503 using the retry delay from the response body
        resp = None
        for attempt in range(4):
            resp = _call(RECIPE_PROMPT)
            if resp.status_code not in (429, 503):
                break
            body = resp.json()
            retry_delay = 60  # default
            for detail in body.get('error', {}).get('details', []):
                if detail.get('@type', '').endswith('RetryInfo'):
                    delay_str = detail.get('retryDelay', '60s')
                    retry_delay = int(re.sub(r'[^0-9]', '', delay_str) or '60') + 2
                    break
            print(f'\n  Rate limited — waiting {retry_delay}s… ', end='', flush=True)
            time.sleep(retry_delay)

        body = resp.json()

        if resp.status_code != 200:
            print(f'  Error: Gemini returned HTTP {resp.status_code} for {filename}', file=sys.stderr)
            return None

        text = body['candidates'][0]['content']['parts'][0]['text']
        recipe = _extract_json(text)

        if recipe is None:
            # Retry with a stricter prompt
            resp2 = _call(RECIPE_PROMPT_STRICT)
            body2 = resp2.json()
            text2 = body2['candidates'][0]['content']['parts'][0]['text']
            recipe = _extract_json(text2)

        if recipe is None:
            print(f'  Error: could not parse JSON from Gemini response for {filename}', file=sys.stderr)
            return None

        if not recipe.get('name') or not isinstance(recipe.get('ingredients'), list):
            print(f'  Error: unexpected JSON shape from Gemini for {filename}: {recipe}', file=sys.stderr)
            return None

        return recipe

    except Exception as e:
        print(f'  Error processing {filename}: {e}', file=sys.stderr)
        return None


def post_recipes_to_sheet(recipes, sheet_name, webapp_url, secret=None):
    """POST the recipe list to the Apps Script web app.

    Returns the parsed JSON response dict.
    Raises on HTTP/network error or if the response body contains a non-200 status.
    """
    body = {'recipes': recipes, 'sheet_name': sheet_name}
    if secret:
        body['secret'] = secret

    resp = requests.post(webapp_url, json=body, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    if data.get('status', 200) not in (200, None):
        raise RuntimeError(f'Web app error: {data}')
    return data


def check_webapp(webapp_url):
    """GET the web app URL as a health check. Returns True if ok."""
    try:
        resp = requests.get(webapp_url, timeout=15)
        data = resp.json()
        return data.get('ok') is True
    except Exception as e:
        print(f'Health check failed: {e}', file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Bulk import recipe photos into the meal planner Google Sheet.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'images',
        nargs='*',
        help='Image files or directories to process',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Extract recipes via Gemini but do not write to the sheet',
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip the confirmation prompt before writing to the sheet',
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Verify the Apps Script web app is reachable, then exit',
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=7.0,
        metavar='SECONDS',
        help='Seconds to wait between Gemini API calls (default: 7, free tier limit is ~10 req/min)',
    )
    parser.add_argument(
        '--sheet',
        metavar='SHEET_NAME',
        help='Sheet tab name to write recipes into (required unless --dry-run or --check)',
    )
    args = parser.parse_args()

    _load_env()

    # Health check mode
    if args.check:
        webapp_url = _require('APPS_SCRIPT_WEBAPP_URL')
        print(f'Checking {webapp_url} …')
        if check_webapp(webapp_url):
            print('Web app is live.')
            return 0
        else:
            print('Web app did not respond as expected.', file=sys.stderr)
            return 1

    if not args.images:
        parser.print_help()
        return 1

    api_key = _require('GEMINI_API_KEY')
    webapp_url = None
    secret = None
    sheet_name = args.sheet
    if not args.dry_run:
        webapp_url = _require('APPS_SCRIPT_WEBAPP_URL')
        secret = _get('BULK_IMPORT_SECRET') or None
        if not sheet_name:
            print('Error: --sheet SHEET_NAME is required when writing to the sheet.', file=sys.stderr)
            print('       Use --dry-run to extract recipes without writing.', file=sys.stderr)
            return 1

    # Collect image paths
    image_paths = collect_image_paths(args.images)
    if not image_paths:
        print('No supported image files found.')
        return 1
    print(f'Found {len(image_paths)} image(s) to process.\n')

    # Process each image
    results = []  # list of (path, recipe_or_none)
    for i, path in enumerate(image_paths, 1):
        if i > 1 and args.delay > 0:
            time.sleep(args.delay)

        print(f'[{i}/{len(image_paths)}] {path.name} … ', end='', flush=True)

        working_path, was_converted = heic_to_jpeg(path)
        try:
            b64, mime = image_to_base64(working_path)
        finally:
            if was_converted:
                try:
                    os.unlink(working_path)
                except OSError:
                    pass

        recipe = parse_recipe_via_gemini(b64, mime, api_key, path.name)
        if recipe:
            ing_count = len(recipe.get('ingredients', []))
            print(f'"{recipe["name"]}" ({ing_count} ingredients)')
        else:
            print('FAILED')
        results.append((path, recipe))

    # Summary
    successes = [(p, r) for p, r in results if r is not None]
    failures = [(p, r) for p, r in results if r is None]

    print(f'\n--- Summary ---')
    print(f'  Extracted:  {len(successes)}/{len(results)}')
    if failures:
        print(f'  Failed:     {", ".join(p.name for p, _ in failures)}')

    if not successes:
        print('No recipes extracted. Nothing to write.')
        return 1

    # Deduplicate within-batch by name (case-insensitive)
    seen_names = {}
    deduped = []
    for path, recipe in successes:
        key = recipe['name'].lower()
        if key in seen_names:
            count = seen_names[key] + 1
            seen_names[key] = count
            new_name = f'{recipe["name"]} ({count})'
            print(f'Warning: duplicate name "{recipe["name"]}" renamed to "{new_name}"')
            recipe = dict(recipe, name=new_name)
        else:
            seen_names[key] = 1
        deduped.append(recipe)

    if args.dry_run:
        print('\n(dry-run — recipes not written to sheet)')
        print(json.dumps(deduped, indent=2))
        return 0

    # Confirm
    if not args.yes:
        answer = input(f'\nWrite {len(deduped)} recipe(s) to "{sheet_name}"? [y/N] ').strip().lower()
        if answer != 'y':
            print('Aborted.')
            return 0

    print(f'Writing to sheet "{sheet_name}"…')
    try:
        data = post_recipes_to_sheet(deduped, sheet_name, webapp_url, secret)
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

    written = data.get('written', 0)
    skipped = data.get('skipped', 0)
    col_count = data.get('current_col_count', '?')
    errors = data.get('errors', [])

    print(f'Done. Wrote {written} recipe(s). Skipped {skipped}. Sheet now has {col_count}/20 columns.')
    if errors:
        print('Skipped details:')
        for err in errors:
            print(f'  - {err}')

    return 0 if skipped == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
