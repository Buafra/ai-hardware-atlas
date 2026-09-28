"""The Android app download: the newest signed APK from this repository's GitHub releases, served by the site itself.

Each signed build is published as a GitHub release tagged android-v<major>.<minor>.<patch> with one asset named
Cipher-Lacuna.apk (see README, "Android app"). The publish workflow runs this script before the build (a new release
starts that workflow at once). It finds the newest such release, downloads the APK into .cache/android (kept between
runs by actions/cache) and checks it:
- its size and SHA-256 match GitHub's record;
- it is a ZIP file;
- it carries the Cipher Lacuna signing certificate.

build.py then copies it to dist/download/Cipher-Lacuna.apk with dist/download/latest.json beside it, and shows the
download card (About section, footer). A new release replaces the file at the same address.

The certificate check reads the certificate from the APK's v2/v3 signature block. It stops a wrong file (a debug
build, another app) from reaching the site. It does not verify the signature itself: Android does that when the app
is installed, and refuses an update signed with another key.

It never fails the build. Without a checked APK (no release yet, or GitHub unreachable with nothing cached), the site
has no download card.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'android'
REPO = 'Buafra/ai-hardware-atlas'
ASSET = 'Cipher-Lacuna.apk'
PUBLIC_DIR = 'download'                       # dist/download/: the APK and latest.json
PUBLIC_APK = f'{PUBLIC_DIR}/{ASSET}'          # the address the site links to (cipherlacuna.ae/download/Cipher-Lacuna.apk)
SITE_URL = 'https://cipherlacuna.ae/'
TAG = re.compile(r'^android-v(\d{1,4})\.(\d{1,4})\.(\d{1,4})$')
# SHA-256 of the Cipher Lacuna release certificate (apksigner: "Signer #1 certificate SHA-256 digest"). Public, not a
# secret: every APK the site serves must carry it, or phones with the app could not install it as an update.
SIGNER_SHA256 = '1d3d4f1b0496d193b7294ce761d362961c15cb0fee422e9d25f9cb8aa7b6f912'
MIN_ANDROID = '8.0'                           # minSdk 26 in the app's build.gradle.kts
MAX_BYTES = 100 * 1024 * 1024
UA = 'Cipher-Lacuna-site-build (+https://cipherlacuna.ae/)'
INFO_KEYS = ('tag', 'version', 'published', 'size', 'sha256')

def _iso(value):
    """A GitHub timestamp ('2026-09-28T08:19:58Z') as given, or '' when it is not one."""
    s = str(value or '')
    try:
        datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return ''
    return s if s[:4].isdigit() and 'T' in s else ''

def version_of(tag):
    """'android-v1.0.12' -> (1, 0, 12); anything else -> None."""
    m = TAG.match(str(tag or ''))
    return tuple(int(x) for x in m.groups()) if m else None

def pick(releases):
    """The newest usable release in a GitHub API release list, or None: published (not a draft or pre-release), tagged
    android-vX.Y.Z and holding an uploaded Cipher-Lacuna.apk on github.com. "Newest" is the highest version number, not
    the latest date, so re-publishing an old tag never replaces a newer app."""
    best = None
    for r in releases if isinstance(releases, list) else []:
        if not isinstance(r, dict) or r.get('draft') or r.get('prerelease'):
            continue
        ver = version_of(r.get('tag_name'))
        if not ver:
            continue
        asset = next((a for a in r.get('assets') or [] if isinstance(a, dict) and a.get('name') == ASSET), None)
        url = str((asset or {}).get('browser_download_url') or '')
        if not asset or asset.get('state', 'uploaded') != 'uploaded' or not url.startswith('https://github.com/'):
            continue
        size = asset.get('size')
        if not isinstance(size, int) or not 0 < size <= MAX_BYTES:
            continue
        digest = str(asset.get('digest') or '')
        sha = digest[7:].lower() if re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest) else None
        if best is None or ver > best[0]:
            best = (ver, {'tag': r['tag_name'], 'version': '.'.join(map(str, ver)),
                          'published': _iso(r.get('published_at')), 'size': size, 'sha256': sha, 'url': url})
    return best[1] if best else None

# ---------- the APK file ----------

def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def _prefixed(buf, pos, what):
    """A uint32 length-prefixed field of the signature block -> (bytes, position after it)."""
    if pos + 4 > len(buf):
        raise ValueError(f'truncated {what}')
    n = struct.unpack_from('<I', buf, pos)[0]
    if pos + 4 + n > len(buf):
        raise ValueError(f'truncated {what}')
    return buf[pos + 4:pos + 4 + n], pos + 4 + n

def _sequence(buf, what):
    """The items of a length-prefixed sequence of length-prefixed items."""
    body, _ = _prefixed(buf, 0, what)
    items, pos = [], 0
    while pos < len(body):
        item, pos = _prefixed(body, pos, what)
        items.append(item)
    return items

V2_ID, V3_ID, V31_ID = 0x7109871A, 0xF05368C0, 0x1B93AD61

def signing_certs(path):
    """SHA-256 fingerprints of the certificates in the APK Signature Scheme v2/v3 block (the same digests apksigner
    prints). Raises ValueError when the file has no such block. Reads the structure only; see the module docstring."""
    data = Path(path).read_bytes()
    eocd = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    if eocd < 0 or eocd + 22 > len(data):
        raise ValueError('not a ZIP file')
    cd_offset = struct.unpack_from('<I', data, eocd + 16)[0]
    if cd_offset < 32 or cd_offset > eocd or data[cd_offset - 16:cd_offset] != b'APK Sig Block 42':
        raise ValueError('no APK signature block (v2/v3)')
    size = struct.unpack_from('<Q', data, cd_offset - 24)[0]
    start = cd_offset - size - 8
    if start < 0 or struct.unpack_from('<Q', data, start)[0] != size:
        raise ValueError('damaged APK signature block')
    pairs, pos, certs = data[start + 8:cd_offset - 24], 0, set()
    while pos + 12 <= len(pairs):
        n, pid = struct.unpack_from('<QI', pairs, pos)
        if n < 4 or pos + 8 + n > len(pairs):
            raise ValueError('damaged APK signature block')
        value = pairs[pos + 12:pos + 8 + n]
        pos += 8 + n
        if pid not in (V2_ID, V3_ID, V31_ID):
            continue
        # signers -> signer: signed data (digests, certificates, …), …
        for signer in _sequence(value, 'signers'):
            signed, _ = _prefixed(signer, 0, 'signed data')
            _, after_digests = _prefixed(signed, 0, 'digests')
            for cert in _sequence(signed[after_digests:], 'certificates'):
                certs.add(hashlib.sha256(cert).hexdigest())
    if not certs:
        raise ValueError('no v2/v3 signer certificate')
    return certs

def check_apk(path, size=None, sha256=None, signer=SIGNER_SHA256):
    """Raise ValueError unless the file is the expected APK. Returns its SHA-256."""
    path = Path(path)
    actual = path.stat().st_size
    if size is not None and actual != size:
        raise ValueError(f'size {actual} bytes, the release says {size}')
    if not 0 < actual <= MAX_BYTES:
        raise ValueError(f'size {actual} bytes')
    digest = _sha256(path)
    if sha256 and digest != sha256.lower():
        raise ValueError('SHA-256 differs from the release record')
    if not zipfile.is_zipfile(path):
        raise ValueError('not a ZIP file')
    with zipfile.ZipFile(path) as z:
        if 'AndroidManifest.xml' not in z.namelist():
            raise ValueError('no AndroidManifest.xml: not an APK')
    if signer.lower() not in signing_certs(path):
        raise ValueError('not signed with the Cipher Lacuna certificate')
    return digest

# ---------- cache (.cache/android) ----------

def load(cache=CACHE, signer=SIGNER_SHA256):
    """The checked APK in the cache as {tag, version, published, size, sha256, path}, or None. Re-checks the file
    (hash and certificate), so a damaged or swapped cache never reaches the site."""
    cache = Path(cache)
    try:
        info = json.loads((cache / 'latest.json').read_text(encoding='utf-8'))
        if not version_of(info.get('tag')) or info.get('version') != '.'.join(map(str, version_of(info['tag']))):
            return None
        apk = cache / ASSET
        check_apk(apk, info.get('size'), info.get('sha256') or '-', signer)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    return {**{k: info[k] for k in INFO_KEYS}, 'published': _iso(info.get('published')), 'path': apk}

def clear(cache=CACHE):
    for name in (ASSET, 'latest.json', ASSET + '.part'):
        try:
            (Path(cache) / name).unlink()
        except FileNotFoundError:
            pass

def _get(url, token=None, opener=urlopen, timeout=60):
    headers = {'User-Agent': UA, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return opener(Request(url, headers=headers), timeout=timeout)

def fetch(repo=REPO, cache=CACHE, token=None, opener=urlopen, signer=SIGNER_SHA256, log=print):
    """Bring .cache/android up to date with the newest release. Returns what happened: 'current' (already cached),
    'updated', 'kept' (GitHub unreachable or the new file failed its checks: the cached APK stays), 'none' (no release,
    or nothing usable). Never raises."""
    cache = Path(cache)
    cached = load(cache, signer)
    try:
        with _get(f'https://api.github.com/repos/{repo}/releases?per_page=50', token, opener) as r:
            releases = json.loads(r.read().decode('utf-8'))
    except Exception as e:  # network, HTTP or JSON: keep what we have
        log(f'Android app: could not read the releases ({type(e).__name__}); ' + ('keeping ' + cached['tag'] if cached else 'no download card'))
        return 'kept' if cached else 'none'
    rel = pick(releases)
    if not rel:
        # No release (or the owner deleted them): the card goes too.
        clear(cache)
        log('Android app: no android-vX.Y.Z release with ' + ASSET + '; no download card')
        return 'none'
    if cached and cached['tag'] == rel['tag'] and cached['size'] == rel['size'] and (not rel['sha256'] or rel['sha256'] == cached['sha256']):
        log(f'Android app: {rel["tag"]} already cached')
        return 'current'
    cache.mkdir(parents=True, exist_ok=True)
    part = cache / (ASSET + '.part')
    try:
        # No token on the download: the asset is public and the request is redirected to another host.
        with opener(Request(rel['url'], headers={'User-Agent': UA, 'Accept': 'application/octet-stream'}), timeout=120) as r, open(part, 'wb') as f:
            total = 0
            for chunk in iter(lambda: r.read(1 << 20), b''):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError('file too large')
                f.write(chunk)
        digest = check_apk(part, rel['size'], rel['sha256'], signer)
    except Exception as e:
        part.unlink(missing_ok=True)
        log(f'Android app: {rel["tag"]} rejected ({type(e).__name__}: {e}); ' + ('keeping ' + cached['tag'] if cached else 'no download card'))
        return 'kept' if cached else 'none'
    os.replace(part, cache / ASSET)
    info = {'tag': rel['tag'], 'version': rel['version'], 'published': rel['published'], 'size': rel['size'], 'sha256': digest}
    (cache / 'latest.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    log(f'Android app: {rel["tag"]} ready ({rel["size"]} bytes, SHA-256 {digest})')
    return 'updated'

# ---------- the site ----------

def publish(out_dir, info):
    """Copy the checked APK to <out_dir>/download/Cipher-Lacuna.apk and write download/latest.json beside it (for a later
    in-app update check). Without an APK, removes any old download folder, so the site never serves a stale file."""
    target = Path(out_dir) / PUBLIC_DIR
    if target.exists():
        shutil.rmtree(target)
    if not info:
        return None
    target.mkdir(parents=True)
    shutil.copyfile(info['path'], target / ASSET)
    latest = {**{k: info[k] for k in INFO_KEYS}, 'min_android': MIN_ANDROID, 'url': SITE_URL + PUBLIC_APK}
    (target / 'latest.json').write_text(json.dumps(latest, indent=2) + '\n', encoding='utf-8', newline='\n')
    return target / ASSET

def size_mb(n):
    """2878160 -> '2.7' (MB, 1 MB = 1,048,576 bytes, as phones show it)."""
    return f'{n / 1048576:.1f}'

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY') or REPO)
    parser.add_argument('--cache', type=Path, default=CACHE)
    args = parser.parse_args(argv)
    fetch(args.repo, args.cache, token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'))
    return 0

if __name__ == '__main__':
    sys.exit(main())
