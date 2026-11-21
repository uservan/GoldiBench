"""Shared paths and helpers of the judge / human-study experiments (paper Sec. 2 and Sec. 4.1, Supp. A and C).

Data (all released):
  GOLDIBENCH_DATA/                      the benchmark (HF VanWang/GoldiBench, scripts/download_data.sh): tasks of
                                        bench_b1_<app>/ (START / TARGET of the human-study pairs)
  GOLDIBENCH_DATA/supporting/<unit>/    the supporting experiments of the logs dataset (HF VanWang/GoldiBench-logs,
                                        scripts/download_supporting.sh): motivation_repo (judgments, manifests, audit
                                        tables), motivation_e3 / motivation_e3x / validation_v5 (candidate images)
  GOLDIBENCH_JUDGE_OUT                  where new runs write (default <data>/judge_runs); released files are never
                                        overwritten
  PSBENCH_DIR                           a clone of https://github.com/zyn1216/PSBench at commit 5a9a911 (the judge
                                        prompt is imported from its photoshop_evaluators.py; scripts/download_supporting.sh
                                        clones it to <data>/supporting/PSBench)
  PSBENCH_DATA                          PSBench's task folders (<id>.json, rubric, START, END) from the HF dataset
                                        zyn1216/PSBench (revision 929d071); download_supporting.sh fetches the 60 E3
                                        tasks to <data>/supporting/PSBench-data (--psbench-all: all 600, for C1)

Released files keep the original absolute paths with the storage prefix redacted ('<ROOT>/visual_effect_data/...',
'<ROOT>/visual-effect-skills/...'); `vpath` maps them to the downloaded copies. Released images are WebP (q90);
download_supporting.sh writes a PNG next to each, so the judges get PNG input as in the paper (decoded from WebP, so
pixel values differ slightly from the originals).
"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'bench'))
import gbpaths  # noqa: E402

DATA = gbpaths.DATA
SUP = Path(os.environ.get('GOLDIBENCH_SUPPORTING', DATA / 'supporting'))
MOT = SUP / 'motivation_repo' / 'visual-effect-skills' / 'motivation'   # judgments, manifests, audit tables
E3 = SUP / 'motivation_e3' / 'e3'            # E3 candidates (candidates/<task>/<cand>.png)
E3X = SUP / 'motivation_e3x' / 'e3x'         # E3-X darktable renders + PSBench-style task folders
V5 = SUP / 'validation_v5' / 'v5'            # human-study pairs, VLM judgments, ratings, candidate images
PSDATA = Path(os.environ.get('PSBENCH_DATA', SUP / 'PSBench-data'))
PSBENCH = Path(os.environ.get('PSBENCH_DIR', SUP / 'PSBench'))
OUT = Path(os.environ.get('GOLDIBENCH_JUDGE_OUT', DATA / 'judge_runs'))
APPS = ['darktable', 'gimp', 'rawtherapee', 'inkscape', 'blender']

# Judge endpoints of the paper (OpenAI-compatible; scripts/serve_vllm.sh for the open ones, goldibench/bench/bedrock_proxy.py
# on :8101 for the closed ones). A `judge:` section in configs/models.yaml (same fields as `program:`) overrides / adds.
JUDGES = {
    'qwen35': {'base_url': 'http://localhost:8001/v1', 'model': 'Qwen3.5-397B-A17B-FP8'},
    'glm53': {'base_url': 'http://localhost:8002/v1', 'model': 'GLM-5.3-Flash'},
    'dsv41': {'base_url': 'http://localhost:8003/v1', 'model': 'DeepSeek-V4.1-Flash'},
    'step37': {'base_url': 'http://localhost:8004/v1', 'model': 'Step-3.7-Flash-FP8'},
    'nemo35': {'base_url': 'http://localhost:8005/v1', 'model': 'NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16'},
    'opus55': {'base_url': 'http://localhost:8101/v1', 'model': 'opus55'},       # bedrock_proxy.py
    'gpt61sol': {'base_url': 'http://localhost:8101/v1', 'model': 'gpt61sol'},   # bedrock_proxy.py
}
JUDGES.update(gbpaths.models('judge'))


def judge_endpoint(name):
    e = JUDGES[name]
    return e['base_url'].rstrip('/'), e['model'], gbpaths.api_headers(e)


_PREFIXES = ('<ROOT>/visual_effect_data/', '<ROOT>/visual-effect-skills/')


def vpath(p):
    """A path from a released manifest / pairs file -> the downloaded file (first that exists; PNG preferred)."""
    p = str(p)
    rel = None
    for pre in _PREFIXES:
        if p.startswith(pre):
            rel = p[len(pre):]
            break
    if rel is None:
        return Path(p)
    if p.startswith(_PREFIXES[1]):
        roots = [SUP / 'motivation_repo' / 'visual-effect-skills']
    else:
        roots = [DATA, SUP / 'motivation_e3', SUP / 'motivation_e3x', SUP / 'validation_v5']
        # E3-X identity candidates point at the darktable pilot's START, released as the task folders' start image
        parts = rel.split('/')
        if parts[:2] == ['bench_pilot2', 'tasks'] and len(parts) == 4 and parts[3] == 'start.png':
            rel = f'e3x/tasks/{parts[2]}_explicit/start.png'
    for r in roots:
        for q in (r / rel, (r / rel).with_suffix('.png'), (r / rel).with_suffix('.webp')):
            if q.exists():
                return q
    return roots[0] / rel


def boot(per_task, n=4000, seed=0):
    """Mean and task-level bootstrap 95 % CI, in %."""
    import random, statistics as st
    r = random.Random(seed); xs = list(per_task)
    ms = sorted(st.mean(r.choices(xs, k=len(xs))) for _ in range(n))
    return 100 * st.mean(xs), 100 * ms[int(.025 * n)], 100 * ms[int(.975 * n) - 1]


def check(name, got, want, failures):
    """Compare a reproduced number with the paper's (both rounded as printed)."""
    ok = got == want
    if not ok:
        failures.append(f'{name}: got {got}, paper {want}')
    return ok


def _png(w):
    from PIL import Image
    p = w.with_suffix('.png'); tmp = p.with_suffix('.tmp.png')
    Image.open(w).convert('RGB').save(tmp, compress_level=1); tmp.rename(p)


def webp_to_png(root, workers=8):
    """Write <x>.png next to every <x>.webp under root (skips existing; 8 processes)."""
    from concurrent.futures import ProcessPoolExecutor
    todo = [w for w in Path(root).rglob('*.webp') if not w.with_suffix('.png').exists()]
    with ProcessPoolExecutor(workers) as ex: list(ex.map(_png, todo, chunksize=8))
    return len(todo)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['webp2png', 'paths']); a = ap.parse_args()
    if a.cmd == 'webp2png':
        print('converted', webp_to_png(SUP))
    else:
        for k in ('DATA', 'SUP', 'MOT', 'E3', 'E3X', 'V5', 'PSDATA', 'PSBENCH', 'OUT'):
            v = globals()[k]; print(f'{k:8s} {v}  {"ok" if v.exists() else "MISSING"}')
