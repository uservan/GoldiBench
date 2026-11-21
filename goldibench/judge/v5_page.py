"""Human study (paper Sec. 4.1, Supp. C.1): the annotation page for the pairs of v5_pairs.py.

Raters see START, TARGET and CANDIDATE, never the candidate kind or the metric: items carry an opaque id; the key
(id -> app, task, candidate, dE, closeness, pass, dc) is written to <out>/annotation_key.csv, not into the page.
Batches are whole tasks, dealt round-robin within each app, so every batch mixes all apps and candidate kinds
(~150 items, ~30 min). Images ship as one script file per batch (batch_<b>.js), loaded when the rater starts.
Questions (Chinese UI, as used in the paper): 1. does CANDIDATE reach TARGET's effect (yes / no / unsure); 2. compared
with TARGET: unchanged / too little / about the same / too much / different direction or style.
Answers: in the paper the page ran as a claude.ai artifact and stored them in its database (judgments/<user id>);
opened anywhere else, the page keeps them in the browser (localStorage) and offers a JSON export
("导出答案") with the same fields, one file per rater. Convert to v5/human_ratings.jsonl with
  python -m goldibench.judge.v5_page --import-answers <export.json> ... --ratings-out human_ratings.jsonl

  python -m goldibench.judge.v5_page --out <dir> [--pairs-dir <supporting>/validation_v5/v5]   # index.html + batch_*.js + annotation_key.csv
  python -m http.server -d <dir>                                                         # then open http://localhost:8000
"""
import argparse, base64, csv, hashlib, io, json
from pathlib import Path
from PIL import Image
from goldibench.judge import common as C

SALT = 'v5-human-v1'


def jpeg(path, side, q):
    im = Image.open(path).convert('RGB'); im.thumbnail((side, side), Image.Resampling.LANCZOS)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=q, optimize=True); return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()


def build(a):
    rows = [r for app in C.APPS if (Path(a.pairs_dir) / f'pairs_{app}.jsonl').exists() for r in map(json.loads, open(Path(a.pairs_dir) / f'pairs_{app}.jsonl'))]
    if a.limit: rows = rows[:a.limit]
    tasks = sorted({(r['app'], r['task_id']) for r in rows}); nb = max(1, round(len(rows) / a.per_batch)); letters = 'ABCDEFGHIJKL'[:nb]
    batch = {}
    for app in C.APPS:
        for i, k in enumerate(sorted(t for t in tasks if t[0] == app)): batch[k] = letters[(i + C.APPS.index(app)) % nb]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); items = []; key = []; per = {b: {'tasks': {}, 'img': {}} for b in letters}
    for r in sorted(rows, key=lambda r: (r['app'], r['task_id'], r['cand'])):
        k = (r['app'], r['task_id']); b = batch[k]; tk = f'{r["app"]}/{r["task_id"]}'; d = C.DATA / f'bench_b1_{r["app"]}' / 'tasks' / r['task_id']
        if tk not in per[b]['tasks']: per[b]['tasks'][tk] = {'start': jpeg(d / 'start.png', a.side, a.quality), 'target': jpeg(d / 'target.png', a.side, a.quality)}
        iid = hashlib.sha1(f'{SALT}|{tk}|{r["cand"]}'.encode()).hexdigest()[:10]
        per[b]['img'][iid] = jpeg(C.vpath(r['path']), a.side, a.quality); items.append({'id': iid, 't': tk, 'b': b})
        key.append({'item_id': iid, 'batch': b, 'app': r['app'], 'task_id': r['task_id'], 'steps': r['steps'], 'cand': r['cand'],
                    'as': r.get('as', r['cand']), 'model': r.get('model', ''), 'de': r['de'], 'de0': r['de0'], 'closeness': r['closeness'],
                    'pass': r['pass'], 'dc': '' if r['dc'] is None else r['dc']})
    with (out / 'annotation_key.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, list(key[0])); w.writeheader(); w.writerows(key)
    sizes = {}
    for b, v in per.items():
        js = f'window.V5_BATCH[{json.dumps(b)}]=' + json.dumps(v) + ';'; (out / f'batch_{b}.js').write_text(js); sizes[b] = round(len(js) / 1e6, 1)
    opts = '\n        '.join(f'<option value="{b}">{b} 批（{sum(i["b"] == b for i in items)} 题）</option>' for b in letters)
    html = (Path(__file__).with_name('v5_template.html').read_text(encoding='utf-8')
            .replace('/*__ITEMS__*/null', json.dumps(items)).replace('/*__BATCH_OPTIONS__*/', opts))
    (out / 'index.html').write_text(html, encoding='utf-8')
    print(json.dumps({'items': len(items), 'tasks': len(tasks), 'batches': {b: sum(i['b'] == b for i in items) for b in letters},
                      'batch_MB': sizes, 'metric_pass': round(sum(r['pass'] for r in rows) / len(rows), 3), 'out': str(out)}))


def import_answers(files, out):
    """Exports of the page (or documents of the artifact database) -> one row per rater x item."""
    with open(out, 'w') as h:
        n = 0
        for k, f in enumerate(files):
            d = json.load(open(f))
            for iid, a in sorted(d['answers'].items()):
                h.write(json.dumps({'item_id': iid, 'rater': f'r{k + 1}', 'expertise': d.get('expertise'), 'batch_chosen': d.get('batch'),
                                    'done': a.get('done'), 'degree': a.get('degree'), 'ms': a.get('ms')}) + '\n'); n += 1
    print(json.dumps({'raters': len(files), 'rows': n, 'out': out}))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out'); ap.add_argument('--side', type=int, default=640)
    ap.add_argument('--quality', type=int, default=82); ap.add_argument('--per-batch', type=int, default=150)
    ap.add_argument('--pairs-dir', default=str(C.V5)); ap.add_argument('--limit', type=int, help='first N pairs only (quick check)')
    ap.add_argument('--import-answers', nargs='*'); ap.add_argument('--ratings-out', default='human_ratings.jsonl')
    a = ap.parse_args()
    if a.import_answers: import_answers(a.import_answers, a.ratings_out); return
    if not a.out: ap.error('--out is required')
    build(a)


if __name__ == '__main__':
    main()
