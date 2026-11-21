"""E3 / E3-X / C1 (paper Sec. 2, Supp. A): score candidate results with PSBench's released judge prompt.

The system prompt, user message, image encoding and pass rule come verbatim from PSBench's photoshop_evaluators.py
(PhotoshopEvaluator._build_messages / _normalize_report, PSBench @ 5a9a911, PSBENCH_DIR). Only the transport changes:
open VLMs on OpenAI-compatible endpoints (common.JUDGES) instead of gpt-5.4, each model's recommended sampling
(temperature 0.6, top_p 0.95; temperature 0 loops on whitespace under JSON constraints for Qwen3.5), room for
reasoning (12k tokens), json_schema output. Results are labelled "PSBench rubric, substitute judge".
One row per task x candidate x judge x repeat; resumable (rows with passed=None are retried).

  # E3, judge stress test on 60 PSBench tasks (manifest + candidates from the release, or from psbench_candidates.py)
  python -m goldibench.judge.psbench_judge --exp e3
  # E3-X, darktable renders posed as PSBench task folders (released under supporting/motivation_e3x/e3x/tasks)
  python -m goldibench.judge.psbench_judge --exp e3x --judges qwen35 glm53
  # C1, Qwen-Image-Edit outputs (c1_image_edit.py)
  python -m goldibench.judge.psbench_judge --exp c1 --judges qwen35 glm53 --manifest <out>/c1/candidates_manifest.csv
Options: --limit N (first N manifest rows, for a quick check), --out FILE (default <GOLDIBENCH_JUDGE_OUT>/<exp>/judgments.jsonl).
Summaries: python -m goldibench.judge.motivation_numbers
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse, asyncio, csv, json, sys
import httpx
from goldibench.judge import common as C

sys.path.insert(0, str(C.PSBENCH))
from photoshop_evaluators import PhotoshopEvaluator  # noqa: E402  PSBench @ 5a9a911

SCHEMA = {'type': 'object', 'required': ['summary', 'criteria'], 'properties': {'summary': {'type': 'string'},
          'criteria': {'type': 'array', 'items': {'type': 'object', 'required': ['id', 'passed', 'reason'],
                       'properties': {'id': {'type': 'string'}, 'passed': {'type': 'boolean'}, 'reason': {'type': 'string'}}}}}}

EXPS = {   # default manifest and task root per experiment
    'e3': (C.MOT / 'e3' / 'candidates_manifest.csv', C.PSDATA, ['qwen35', 'glm53', 'dsv41', 'step37', 'nemo35']),
    'e3x': (C.MOT / 'e3x' / 'candidates_manifest.csv', C.E3X / 'tasks', ['qwen35', 'glm53']),
    'c1': (C.MOT / 'c1' / 'candidates_manifest.csv', C.PSDATA, ['qwen35', 'glm53']),
}
TASKS = C.PSDATA
REPORTS = C.OUT / 'psbench_reports'   # PSBench's evaluator wants a result folder; nothing is written there by this script


def evaluator(task):
    return PhotoshopEvaluator(task_folder=str(TASKS / task), result_folder=str(REPORTS), api_key='unused')


_messages = {}


def build(row):
    """PSBench's _build_messages re-encodes both images as optimised PNG, which is slow; do it once per candidate."""
    key = (row['task_id'], row['candidate'])
    if key not in _messages:
        ev = evaluator(row['task_id']); rubric = ev.load_rubric()
        _messages[key] = (ev, rubric, ev._build_messages(rubric, ev.get_start_path(), C.vpath(row['path'])))
    return _messages[key]


async def judge(client, sem, key, row, rep, seed):
    base, model, headers = C.judge_endpoint(key); ev, rubric, msgs = _messages[(row['task_id'], row['candidate'])]
    body = {'model': model, 'messages': msgs, 'temperature': 0.6, 'top_p': 0.95, 'max_tokens': 12000,
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'report', 'schema': SCHEMA}}}
    rec = {k: row[k] for k in ('task_id', 'group', 'e1_class', 'difficulty', 'candidate')} | {'judge': key, 'rep': rep}
    err = None
    async with sem:
        for attempt in range(3):
            body['seed'] = seed + 100 * rep + attempt
            try:
                r = await client.post(f'{base}/chat/completions', json=body, headers=headers, timeout=900); r.raise_for_status()
                rep_ = ev._normalize_report(json.loads(r.json()['choices'][0]['message']['content']), rubric)
                return rec | {'passed': rep_['passed'], 'failed_requirements': rep_['failed_requirements'], 'summary': rep_['summary'][:500]}
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as e:
                err = repr(e)[:200]
    return rec | {'passed': None, 'error': err}


async def run(args):
    global TASKS
    man, troot, _ = EXPS[args.exp]
    TASKS = Path(args.tasks_root or troot)
    rows = list(csv.DictReader(open(args.manifest or man)))
    if args.limit: rows = rows[:args.limit]
    out = Path(args.out or C.OUT / args.exp / 'judgments.jsonl'); out.parent.mkdir(parents=True, exist_ok=True); done = set()
    if out.exists():
        done = {(j['task_id'], j['candidate'], j['judge'], j['rep']) for j in map(json.loads, open(out)) if j['passed'] is not None}
    jobs = [(k, r, rep) for k in args.judges for rep in range(args.repeats) for r in rows if (r['task_id'], r['candidate'], k, rep) not in done]
    with ThreadPoolExecutor(8) as pool: list(pool.map(build, {(r['task_id'], r['candidate']): r for _, r, _ in jobs}.values()))
    print(json.dumps({'encoded': len(_messages), 'jobs': len(jobs), 'out': str(out)}), flush=True)
    sems = {k: asyncio.Semaphore(args.concurrency) for k in args.judges}
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=None)) as client:
        with out.open('a') as h:
            for fut in asyncio.as_completed([judge(client, sems[k], k, r, rep, args.seed) for k, r, rep in jobs]):
                h.write(json.dumps(await fut) + '\n'); h.flush()
    print(json.dumps({'judged': len(jobs)}))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--exp', choices=list(EXPS), default='e3')
    ap.add_argument('--judges', nargs='+'); ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--seed', type=int, default=0); ap.add_argument('--concurrency', type=int, default=8)
    ap.add_argument('--manifest'); ap.add_argument('--tasks-root'); ap.add_argument('--out'); ap.add_argument('--limit', type=int)
    a = ap.parse_args(); a.judges = a.judges or EXPS[a.exp][2]
    asyncio.run(run(a))


if __name__ == '__main__':
    main()
