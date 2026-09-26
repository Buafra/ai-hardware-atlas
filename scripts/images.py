"""Download each product's official image and store a small WebP copy in images/.

Only official NVIDIA / AMD HTTPS hosts are accepted (same rule as the source checker).
Existing files are kept unless --force is given. Run it after adding a product image URL.
"""
import argparse
import io
import json
import sys
from pathlib import Path
from urllib.request import Request, build_opener

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh import Redirects, official  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'images'
MAX_BYTES = 8_000_000
BOX = (640, 440)

def download(url):
    if not official(url):
        raise ValueError('Unofficial image host')
    req = Request(url, headers={'User-Agent': 'AI-Hardware-Atlas/1.0 (product images)', 'Accept': 'image/*'})
    with build_opener(Redirects).open(req, timeout=30) as r:
        if not official(r.url) or not r.headers.get('Content-Type', '').startswith('image/'):
            raise ValueError('Unsupported image response')
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Image too large')
    return raw

def shrink(raw):
    img = Image.open(io.BytesIO(raw))
    img = img.convert('RGBA' if 'A' in img.getbands() or img.mode == 'P' else 'RGB')
    img.thumbnail(BOX, Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, 'WEBP', quality=80, method=6)
    return out.getvalue()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='re-download existing images')
    args = parser.parse_args()
    path = ROOT / 'data/catalog.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    DIR.mkdir(exist_ok=True)
    done = failed = 0
    for p in data['products']:
        image = p.get('image')
        if not image:
            continue
        target = DIR / f"{p['id']}.webp"
        if target.exists() and not args.force:
            image['file'] = f'images/{target.name}'
            continue
        try:
            target.write_bytes(shrink(download(image['url'])))
            image['file'] = f'images/{target.name}'
            done += 1
        except Exception as exc:
            failed += 1
            print(f"{p['id']}: {type(exc).__name__}: {exc}", file=sys.stderr)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f'Images: {done} downloaded, {failed} failed, {sum(1 for p in data["products"] if p.get("image", {}).get("file"))} available')
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(main())
