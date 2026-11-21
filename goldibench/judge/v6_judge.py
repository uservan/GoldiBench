"""VLM judges on the human-study pairs (paper Sec. 4.1, Tab. judge; Supp. C.1), asked the raters' question.

The judge sees START, TARGET and CANDIDATE (order and wording of the annotation page, translated) and answers
{"reaches": bool, "degree": under|same|over|different|unchanged, "reason"}. Paper: Qwen3.5-397B and GLM-5.3 (vLLM),
GPT-6.1 and Claude Opus 5.5 (Amazon Bedrock through goldibench/bench/bedrock_proxy.py on :8101, which drops
temperature / seed for them); temperature 0.6, top_p 0.95, 3 repeats per pair, majority = the judge's verdict.
Pairs: <pairs-dir>/pairs_<app>.jsonl (v5_pairs.py; default the released ones), START / TARGET from the benchmark.
Output: <GOLDIBENCH_JUDGE_OUT>/v5/v6_judgments.jsonl (one row per pair x judge x repeat; resumable: rows with
reaches = None are retried) and a summary: judge pass rate per candidate kind next to the metric's, and agreement.
Full numbers with the human ratings: python -m goldibench.judge.human_agreement --judgments <out>

  python -m goldibench.judge.v6_judge [--judges qwen35 glm53 opus55 gpt61sol] [--repeats 3] [--limit N] [--summary-only FILE]
"""
from pathlib import Path
import argparse, asyncio, base64, json
from collections import defaultdict
import httpx
from goldibench.judge import common as C

DEGREES = ['under', 'same', 'over', 'different', 'unchanged']
SYSTEM = """You check retouching work. Each item has three images: the original (START), the effect the client asked for
(TARGET) and the result a retoucher delivered (CANDIDATE). TARGET and CANDIDATE were both edited from START.
Judge it like an acceptance check: does CANDIDATE achieve TARGET's effect?
- reaches: could CANDIDATE be handed to the client who asked for TARGET as finished work? Small differences that are
  only visible on careful comparison do not count as failing.
- degree: compared with TARGET, CANDIDATE is edited too little (under), about the same (same), too much (over), in a
  different direction or style (different); if it is nearly identical to START, answer unchanged.
Answer with JSON only: {"reaches": true|false, "degree": "under"|"same"|"over"|"different"|"unchanged", "reason": "<one sentence>"}"""
SCHEMA = {'type': 'object', 'required': ['reaches', 'degree', 'reason'], 'properties': {'reaches': {'type': 'boolean'},
          'degree': {'type': 'string', 'enum': DEGREES}, 'reason': {'type': 'string'}}}


def img(p):
    return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(Path(p).read_bytes()).decode()}}


def messages(r):
    d = C.DATA / f"bench_b1_{r['app']}" / 'tasks' / r['task_id']
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': [{'type': 'text', 'text': 'START (original):'}, img(d / 'start.png'),
            {'type': 'text', 'text': 'TARGET (the effect asked for):'}, img(d / 'target.png'), {'type': 'text', 'text': 'CANDIDATE (the delivered result):'},
            img(C.vpath(r['path'])), {'type': 'text', 'text': 'Does CANDIDATE achieve TARGET\'s effect? JSON only.'}]}]


async def ask(client, sem, key, r, rep, seed):
    base, model, headers = C.judge_endpoint(key); rec = {k: r.get(k) for k in ('app', 'task_id', 'cand', 'kind', 'arg', 'pass', 'closeness', 'de')} | {'judge': key, 'rep': rep}
    body = {'model': model, 'messages': messages(r), 'temperature': 0.6, 'top_p': 0.95, 'max_tokens': 12000,
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'verdict', 'schema': SCHEMA}}}
    err = None
    async with sem:
        for attempt in range(3):
            body['seed'] = seed + 100 * rep + attempt
            try:
                x = await client.post(f'{base}/chat/completions', json=body, headers=headers, timeout=900); x.raise_for_status()
                v = json.loads(x.json()['choices'][0]['message']['content'])
                return rec | {'reaches': bool(v['reaches']), 'degree': v.get('degree'), 'reason': str(v.get('reason', ''))[:300]}
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as e:
                err = repr(e)[:200]
    return rec | {'reaches': None, 'error': err}


def summary(out):
    rows = [j for j in map(json.loads, open(out)) if j['reaches'] is not None]; votes = defaultdict(list)
    for j in rows: votes[(j['app'], j['task_id'], j['cand'], j['judge'])].append(j)
    by = defaultdict(lambda: [0, 0, 0, 0])   # (judge, kind-bucket): n, judge pass, metric pass, agree
    for (app, t, c, k), v in votes.items():
        jp = sum(x['reaches'] for x in v) > len(v) / 2; mp = bool(v[0]['pass']); kind = v[0]['kind']; arg = v[0]['arg']
        b = f"{kind} {arg}" if kind == 'scale' else (kind if kind != 'agent' else f'agent {arg}')
        for key in (b, 'ALL'): s = by[(k, key)]; s[0] += 1; s[1] += jp; s[2] += mp; s[3] += jp == mp
    print(f"{'judge':9s} {'candidate':16s} {'n':>4s} {'judge pass%':>11s} {'metric pass%':>12s} {'agree%':>7s}")
    for (k, b), (n, jp, mp, ag) in sorted(by.items()): print(f"{k:9s} {b:16s} {n:4d} {100 * jp / n:11.0f} {100 * mp / n:12.0f} {100 * ag / n:7.0f}")


async def run(a):
    pairs = [json.loads(l) for app in C.APPS if (Path(a.pairs_dir) / f'pairs_{app}.jsonl').exists() for l in open(Path(a.pairs_dir) / f'pairs_{app}.jsonl')]
    if a.limit: pairs = pairs[:a.limit]
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); done = set()
    if out.exists(): done = {(j['app'], j['task_id'], j['cand'], j['judge'], j['rep']) for j in map(json.loads, open(out)) if j['reaches'] is not None}
    jobs = [(k, r, rep) for k in a.judges for rep in range(a.repeats) for r in pairs if (r['app'], r['task_id'], r['cand'], k, rep) not in done]
    print(json.dumps({'pairs': len(pairs), 'jobs': len(jobs), 'out': str(out)}), flush=True)
    sems = {k: asyncio.Semaphore(a.concurrency) for k in a.judges}
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=None)) as client:
        with out.open('a') as h:
            for fut in asyncio.as_completed([ask(client, sems[k], k, r, rep, a.seed) for k, r, rep in jobs]):
                h.write(json.dumps(await fut) + '\n'); h.flush()
    summary(out)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--judges', nargs='+', default=['qwen35', 'glm53']); ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--concurrency', type=int, default=8); ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--pairs-dir', default=str(C.V5)); ap.add_argument('--out', default=str(C.OUT / 'v5' / 'v6_judgments.jsonl'))
    ap.add_argument('--limit', type=int, help='first N pairs only (quick check)'); ap.add_argument('--summary-only', metavar='FILE')
    a = ap.parse_args()
    if a.summary_only: summary(a.summary_only); return
    asyncio.run(run(a))


if __name__ == '__main__':
    main()
