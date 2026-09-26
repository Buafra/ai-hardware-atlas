"""List the models on OpenRouter and record how big the open-weight ones are.

OpenRouter (/api/v1/models, no key needed) gives names and, for open-weight models,
the Hugging Face repo. Parameter counts come from Hugging Face's safetensors metadata,
which counts every expert of a mixture-of-experts model - the figure that decides memory.
Only when a repo has no metadata do we read a size from the model name, and never for
MoE-style names ("8x22B", "A22B", "16E") where the name states active, not total, size.
Closed models are listed as cloud-only. Previously resolved counts are reused, and a
failed fetch keeps the existing file.
"""
import concurrent.futures
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/models.json'
OPENROUTER = 'https://openrouter.ai/api/v1/models'
HF_API = 'https://huggingface.co/api/models/'
UA = {'User-Agent': 'AI-Hardware-Atlas/1.0 (model size lookup)'}
VARIANT = re.compile(r':(free|batch|beta|extended|thinking|online|floor|nitro|exacto)$')
MOE_NAME = re.compile(r'\d+x\d+(\.\d+)?b|[-_ ]a\d+(\.\d+)?b\b|\d+e\b', re.I)
SIZE_NAME = re.compile(r'(?<![\d.])(\d+(?:\.\d+)?)\s?b\b', re.I)

def get_json(url, timeout=30):
    with urlopen(Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read(20_000_001))

def hf_total(repo):
    """Total parameters from Hugging Face safetensors metadata, or None."""
    try:
        info = get_json(HF_API + repo, timeout=25)
    except Exception:
        return None
    total = (info.get('safetensors') or {}).get('total')
    return total if isinstance(total, int) and total > 0 else None

def size_from_name(*names):
    """Billions of parameters stated in a dense model's name, else None."""
    for name in names:
        if not name or MOE_NAME.search(name):
            continue
        m = SIZE_NAME.findall(name.replace('_', ' ').replace('-', ' '))
        if len(set(m)) == 1:
            return float(m[0])
    return None

def build(openrouter, previous):
    known = {m['hf']: m for m in previous.get('models', []) if m.get('hf') and m.get('params_b')}
    seen, models = set(), []
    for m in openrouter:
        base = VARIANT.sub('', m['id'])
        if base in seen:
            continue
        seen.add(base)
        models.append({'id': base, 'name': VARIANT.sub('', m['name']).replace(' (free)', '').strip(),
                       'hf': m.get('hugging_face_id') or None, 'context': m.get('context_length'),
                       'created': m.get('created')})
    todo = sorted({m['hf'] for m in models if m['hf'] and m['hf'] not in known})
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fresh = dict(zip(todo, pool.map(hf_total, todo)))
    for m in models:
        if not m['hf']:
            m.update(open=False, params_b=None, params_source=None, moe=False)
            continue
        m['open'] = True
        if m['hf'] in known:
            m.update(params_b=known[m['hf']]['params_b'], params_source=known[m['hf']]['params_source'])
        elif fresh.get(m['hf']):
            m.update(params_b=round(fresh[m['hf']] / 1e9, 2), params_source='huggingface')
        else:
            b = size_from_name(m['hf'].split('/')[-1], m['name'])
            m.update(params_b=b, params_source='name' if b else None)
        # MoE: the name states active parameters (or experts) but memory must hold all of them.
        named = size_from_name(m['hf'].split('/')[-1], m['name'])
        m['moe'] = bool(MOE_NAME.search(m['hf'] + ' ' + m['name']) or (named and m['params_b'] and m['params_b'] > named * 1.3))
    models.sort(key=lambda m: (not m['open'], m['name'].casefold()))
    return models

def main():
    previous = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    try:
        openrouter = get_json(OPENROUTER)['data']
    except Exception as exc:
        print(f'OpenRouter unreachable ({type(exc).__name__}); keeping existing model list.', file=sys.stderr)
        return 0
    if len(openrouter) < 50:
        print('OpenRouter returned too few models; keeping existing list.', file=sys.stderr)
        return 0
    models = build(openrouter, previous)
    data = {'updated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(), 'source': OPENROUTER, 'models': models}
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    tmp.replace(OUT)
    sized = sum(1 for m in models if m['params_b'])
    print(f"Models: {len(models)} on OpenRouter, {sum(m['open'] for m in models)} open-weight, {sized} with a size "
          f"({sum(1 for m in models if m['params_source'] == 'name')} from name)")
    return 0

if __name__ == '__main__':
    sys.exit(main())
