"""Where GoldiBench finds its data, its local install directory and its model list.

  GOLDIBENCH_DATA    the benchmark data (the HF dataset VanWang/GoldiBench, downloaded by scripts/download_data.sh);
                     runs are written to <data>/bench_b1_<app>[_gui]/runs/<run>/. Default: <repo>/data
  VE_LOCAL           local install dir of the apps, X tools, OSWorld agents and the vLLM env (scripts/setup_*.sh).
                     Default: ~/.cache/goldibench. Use a fast local disk.
  GOLDIBENCH_MODELS  model list (YAML, see configs/models.example.yaml). Default: <repo>/configs/models.yaml if present.
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('GOLDIBENCH_DATA', REPO / 'data')).resolve()
LOCAL = Path(os.environ.get('VE_LOCAL', Path.home() / '.cache' / 'goldibench'))


def models(channel):
    """{name: entry} for one channel ('program' or 'gui') from the YAML model list; {} when there is none.
    entry: base_url, model (served name), optional api_key_env (env var holding the key), kind (GUI agent adapter)."""
    p = Path(os.environ.get('GOLDIBENCH_MODELS', REPO / 'configs' / 'models.yaml'))
    if not p.exists():
        return {}
    import yaml
    cfg = yaml.safe_load(p.read_text()) or {}
    return {k: v for k, v in (cfg.get(channel) or {}).items()}


def api_headers(entry):
    k = entry.get('api_key_env') if isinstance(entry, dict) else None
    return {'Authorization': f'Bearer {os.environ[k]}'} if k and os.environ.get(k) else {}


import re as _re
_REL = _re.compile(r'"((?:sources|assets|manuals|minimanual|bench_[A-Za-z0-9_]+)/)')


def open_tasks(path):
    """Lines of a tasks.jsonl with the dataset-relative paths in it (sources/..., assets/..., bench_b1_<app>/...) made
    absolute under DATA, so tasks work wherever the dataset was downloaded."""
    root = str(DATA).replace('\\', '/')
    with open(path) as f:
        for line in f:
            yield _REL.sub(lambda m: '"' + root + '/' + m.group(1), line)
