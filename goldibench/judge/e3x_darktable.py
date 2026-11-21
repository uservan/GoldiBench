"""E3-X (paper Sec. 2, Fig. 2d, Supp. A.5): the judge stress test on real darktable renders.

Tasks: the 56 tasks of the darktable program-bench pilot (make_pilot.py, set bench_pilot2). Every candidate is a real
darktable render of the task's hidden program with each numeric field scaled k times as far from neutral
(make_pilot.scaled): end k = 1 (the target), half k = 0.5, over k = 3, opposite k = -1, plus identity (START). A
program that the app's parameter ranges clip is flagged (clipped) and left out of the summaries.

Each task is written as a PSBench task folder twice, so psbench_judge.py runs PSBench's judge on it unchanged:
  explicit  instruction = our L1 text (modules and exact values)
  vague     instruction = a client-style request written by Qwen3.5 from START and TARGET (look only, no tool names or
            numbers), like PSBench's vague tasks
Rubric as PSBench writes it: one criterion per sentence, "Compared with START, RESULT must visibly satisfy this
requirement: <sentence> Judge only ... explicitly stated." and, when the sentence has a number, PSBench's sentence on
numeric settings (Photoshop -> darktable). Our metric's pass is stored next to each candidate.

The paper's 112 task folders (with the vague requests) and renders are released (supporting/motivation_e3x/e3x), so the
judge can be rerun without this script:  python -m goldibench.judge.psbench_judge --exp e3x
To rebuild them (needs the pilot set: BENCH_APP=darktable BENCH_SET=bench_pilot2 python goldibench/bench/make_pilot.py,
darktable installed, Qwen3.5-397B served as judge 'qwen35'):
  BENCH_APP=darktable BENCH_SET=bench_pilot2 python -m goldibench.judge.e3x_darktable make [--out <GOLDIBENCH_JUDGE_OUT>/e3x]
  python -m goldibench.judge.e3x_darktable rubric --instruction "..."      (print the rubric of one instruction)
"""
import argparse, base64, csv, io, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from PIL import Image
from goldibench.judge import common as C

KS = {'end': 1, 'half': 0.5, 'over': 3, 'opposite': -1}
T = ('Compared with START, RESULT must visibly satisfy this requirement: {} Judge only the rendered final image, including the '
     'named subject, region, direction, color, text, geometry, and preservation constraints that are explicitly stated.')
NUM = ' Treat the stated numeric setting as an approximate visible target; do not claim to verify hidden darktable parameters exactly.'
PROMPT = ('The first image is a photo before editing, the second is the same photo after a client\'s requested edit. Write the '
          'request the client sent to the photo editor, in one or two sentences. Describe only the desired look (brightness, '
          'contrast, colour, mood, sharpness and so on), as a client would; do not name software, tools, sliders or numbers. '
          'Reply with the request only.')


def rubric(tid, instr):
    sents = [s for s in re.split(r'(?<=[.!?])\s+', instr.strip()) if s]
    return {'task_id': tid, 'instruction': instr, 'criteria': [{'id': f'criterion_{i + 1}', 'description': T.format(s) + (NUM if re.search(r'\d', s) else '')}
                                                             for i, s in enumerate(sents)]}


def b64(p):
    im = Image.open(p).convert('RGB'); b = io.BytesIO(); im.save(b, 'PNG'); return base64.b64encode(b.getvalue()).decode()


def vague(d, cache):
    f = cache / f'{d.name}_vague.txt'
    if f.exists(): return f.read_text()
    base, model, headers = C.judge_endpoint('qwen35')
    body = {'model': model, 'temperature': 0.6, 'top_p': 0.95, 'max_tokens': 8000,
            'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64(d / 'start.png')}},
                                                      {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64(d / 'target.png')}},
                                                      {'type': 'text', 'text': PROMPT}]}]}
    for attempt in range(4):   # Qwen3.5 sometimes spends the budget reasoning and returns no content: resample
        body['seed'] = attempt; r = httpx.post(f'{base}/chat/completions', json=body, headers=headers, timeout=900); r.raise_for_status()
        txt = (r.json()['choices'][0]['message']['content'] or '').strip().strip('"')
        if txt: f.parent.mkdir(parents=True, exist_ok=True); f.write_text(txt); return txt
    raise RuntimeError(f'no request text for {d.name}')


def build(task, mp, ops, out):
    tid = task['task_id']; src = mp.OUT / 'tasks' / tid; rows = []
    lt = mp.lab(src / 'target.png'); total = mp.de(mp.lab(src / 'start.png'), lt)
    cands = {'identity': (src / 'start.png', False)}
    for name, k in KS.items():
        p = out / 'renders' / tid / f'{name}.png'; prog, clipped = mp.scaled(task['program'], k)
        if not p.exists(): p.parent.mkdir(parents=True, exist_ok=True); ops.render(task['source_path'], prog, p)
        cands[name] = (p, clipped)
    instr = {'explicit': task['l1_instruction'], 'vague': vague(src, out / 'vague')}
    for variant, text in instr.items():
        d = out / 'tasks' / f'{tid}_{variant}'; d.mkdir(parents=True, exist_ok=True)
        Image.open(src / 'start.png').save(d / 'start.png'); Image.open(src / 'target.png').save(d / 'end.png')
        (d / f'{d.name}.json').write_text(json.dumps({'id': d.name, 'instruction': text, 'difficulty_level': variant, 'type': task['kind'],
            'resources': {'input_file': 'start.png'}, 'reference_output': {'expected_file': 'end.png'}, 'rubric_file': f'{d.name}_rubric.json'}, indent=1))
        (d / f'{d.name}_rubric.json').write_text(json.dumps(rubric(d.name, text), indent=1))
        for name, (p, clipped) in cands.items():
            dd = mp.de(mp.lab(p), lt)
            rows.append({'task_id': d.name, 'group': variant, 'e1_class': 'explicit' if variant == 'explicit' else 'vague', 'difficulty': task['kind'],
                         'candidate': name, 'path': str(p), 'clipped': clipped, 'de00': round(dd, 3), 'closeness': round(1 - dd / total, 3),
                         'metric_pass': mp.passed(dd, total)})
    return rows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['make', 'rubric']); ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--out', default=str(C.OUT / 'e3x')); ap.add_argument('--instruction'); ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    if a.mode == 'rubric':
        print(json.dumps(rubric('task', a.instruction), indent=1)); return
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'bench'))
    import make_pilot as mp, ops
    assert ops.APP == 'darktable' and mp.OUT.name == 'bench_pilot2', (ops.APP, mp.OUT)
    out = Path(a.out); tasks = [json.loads(l) for l in open(mp.OUT / 'tasks.jsonl')][:a.limit]
    with ThreadPoolExecutor(a.workers) as pool: rows = [r for rs in pool.map(lambda t: build(t, mp, ops, out), tasks) for r in rs]
    with (out / 'candidates_manifest.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(json.dumps({'tasks': len(tasks), 'rows': len(rows), 'metric_pass_by_candidate':
        {c: sum(r['metric_pass'] for r in rows if r['candidate'] == c) // 2 for c in ['identity', *KS]}}))


if __name__ == '__main__':
    main()
