"""E3 control (paper Sec. 2, Supp. A.4): does the PSBench judge separate right from wrong results once it SEES the
author's reference (END)?

Conditions (same 60 tasks, judges, sampling and pass rule as psbench_judge.py):
  noref  PSBench prompt verbatim; here run only on the near-correct candidates
  ref    PSBench prompt + REFERENCE image (END) shown between START and RESULT, with three edits to the system prompt:
         "You do not receive a reference answer." -> a REFERENCE sentence; the positive-reference policy's "that
         reference image is not shown during evaluation" clause dropped; a final REFERENCE POLICY block saying that
         strength is judged against REFERENCE (it overrides the strength tolerance above).
Candidates: the six of psbench_candidates.py plus near_0.9 / near_1.1 (START + k delta), so that a judge that only
accepts a pixel-identical END shows up as too strict.
Output: <GOLDIBENCH_JUDGE_OUT>/e3/judgments_ref.jsonl (one row per condition x task x candidate x judge x repeat). Resumable.

  python -m goldibench.judge.psbench_ref [--manifest <released or new manifest>] [--judges qwen35 glm53] [--limit-tasks N]
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse, asyncio, csv, json
import httpx
from goldibench.judge import common as C
from goldibench.judge import psbench_judge as J
from goldibench.judge.psbench_candidates import load, save

NEAR = {'near_0.9': 0.9, 'near_1.1': 1.1}
NOREF_SENTENCE = """You receive
the original START image and the candidate RESULT image. You do not receive a
reference answer."""
REF_SENTENCE = """You receive
the original START image, a REFERENCE image (a known-good result made by the task
author for this instruction) and the candidate RESULT image."""
HIDDEN_CLAUSE = ", but that\n  reference image is not shown during evaluation"
REF_POLICY = """

REFERENCE POLICY (overrides any strength tolerance above):
- REFERENCE shows the intended outcome. A criterion passes only when RESULT's change from
  START matches REFERENCE's change in kind, region, direction AND approximate strength.
- A change that is clearly weaker or clearly stronger than REFERENCE's fails, even if the
  direction is right. Differences from REFERENCE that a careful viewer would barely notice
  are acceptable."""


def near_rows(man, cand_dir):
    """Near-correct candidates next to the existing ones (built if missing); manifest rows for them."""
    out = []; seen = set()
    for r in man:
        if r['task_id'] in seen: continue
        seen.add(r['task_id'])
        for name, k in NEAR.items():
            p = C.vpath(str(Path(r['path']).with_name(f'{name}.png')))
            if not p.exists():
                p = cand_dir / r['task_id'] / f'{name}.png'
                if not p.exists(): start, end = load(r['task_id']); save(start + k * (end - start), p)
            out.append({**{c: r[c] for c in ('task_id', 'group', 'e1_class', 'difficulty')}, 'candidate': name, 'path': str(p)})
    return out


_msgs = {}


def build(cond, row, end_of):
    key = (cond, row['task_id'], row['candidate'])
    if key in _msgs: return
    ev, rubric, msgs = J.build(row)  # PSBench's own messages (system + START + RESULT)
    if cond == 'ref':
        sysp = msgs[0]['content']; assert NOREF_SENTENCE in sysp
        sysp = sysp.replace(NOREF_SENTENCE, REF_SENTENCE).replace(HIDDEN_CLAUSE, '') + REF_POLICY
        user = json.loads(msgs[1]['content'][0]['text']); user['image_order'] = ['START', 'REFERENCE', 'RESULT']
        ref = {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{ev._encode_image(end_of[row["task_id"]])}', 'detail': 'high'}}
        c = msgs[1]['content']
        msgs = [{'role': 'system', 'content': sysp}, {'role': 'user', 'content': [{'type': 'text', 'text': json.dumps(user, ensure_ascii=True, indent=2)},
                c[1], c[2], {'type': 'text', 'text': 'REFERENCE image:'}, ref, c[3], c[4]]}]
    _msgs[key] = (ev, rubric, msgs)


async def ask(client, sem, cond, key, row, rep, seed):
    base, model, headers = C.judge_endpoint(key); ev, rubric, msgs = _msgs[(cond, row['task_id'], row['candidate'])]
    body = {'model': model, 'messages': msgs, 'temperature': 0.6, 'top_p': 0.95, 'max_tokens': 12000,
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'report', 'schema': J.SCHEMA}}}
    rec = {k: row[k] for k in ('task_id', 'group', 'e1_class', 'difficulty', 'candidate')} | {'condition': cond, 'judge': key, 'rep': rep}
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
    man = list(csv.DictReader(open(args.manifest)))
    if args.limit_tasks:
        keep = sorted({r['task_id'] for r in man})[:args.limit_tasks]; man = [r for r in man if r['task_id'] in keep]
    if args.candidates: man = [r for r in man if r['candidate'] in args.candidates]
    J.TASKS = C.PSDATA
    near = near_rows(man, C.OUT / 'e3' / 'candidates')
    if args.candidates: near = [r for r in near if r['candidate'] in args.candidates]
    end_of = {r['task_id']: C.vpath(r['path']) for r in csv.DictReader(open(args.manifest)) if r['candidate'] == 'end'}
    jobs = [('ref', r) for r in man + near] + [('noref', r) for r in near]
    out = Path(args.out or C.OUT / 'e3' / 'judgments_ref.jsonl'); out.parent.mkdir(parents=True, exist_ok=True); done = set()
    if out.exists(): done = {(j['condition'], j['task_id'], j['candidate'], j['judge'], j['rep']) for j in map(json.loads, open(out)) if j['passed'] is not None}
    todo = [(c, k, r, rep) for k in args.judges for rep in range(args.repeats) for c, r in jobs if (c, r['task_id'], r['candidate'], k, rep) not in done]
    with ThreadPoolExecutor(8) as pool: list(pool.map(lambda x: build(*x, end_of), {(c, r['task_id'], r['candidate']): (c, r) for c, _, r, _ in todo}.values()))
    print(json.dumps({'encoded': len(_msgs), 'jobs': len(todo), 'out': str(out)}), flush=True)
    sems = {k: asyncio.Semaphore(args.concurrency) for k in args.judges}
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=None)) as client:
        with out.open('a') as h:
            for fut in asyncio.as_completed([ask(client, sems[k], c, k, r, rep, args.seed) for c, k, r, rep in todo]):
                h.write(json.dumps(await fut) + '\n'); h.flush()
    print(json.dumps({'judged': len(todo)}))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--judges', nargs='+', default=['qwen35', 'glm53']); ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--seed', type=int, default=0); ap.add_argument('--concurrency', type=int, default=8)
    ap.add_argument('--manifest', default=str(C.MOT / 'e3' / 'candidates_manifest.csv')); ap.add_argument('--out')
    ap.add_argument('--limit-tasks', type=int); ap.add_argument('--candidates', nargs='*', help='only these candidate names')
    asyncio.run(run(ap.parse_args()))


if __name__ == '__main__':
    main()
