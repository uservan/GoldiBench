"""C1 (paper Sec. 2, Supp. A.6): an image-editing model that never opens Photoshop, scored with PSBench's judge.

Qwen-Image-Edit-2511 (diffusers QwenImageEditPlusPipeline, model-card settings: 40 steps, true_cfg_scale 4.0, negative
prompt " ", seed 0) edits each of the 600 PSBench START images from the task instruction alone. The output is resized to
START's size (the model works at ~1 MP), as an agent's export would be.

Needs all 600 PSBench task folders (scripts/download_supporting.sh --psbench-all) and `pip install diffusers torch`.
  edit:      CUDA_VISIBLE_DEVICES=i python -m goldibench.judge.c1_image_edit edit --shard i --nshards 8 [--model Qwen/Qwen-Image-Edit-2511]
  manifest:  python -m goldibench.judge.c1_image_edit manifest   -> <out>/candidates_manifest.csv (edit, identity, end)
then:      python -m goldibench.judge.psbench_judge --exp c1 --manifest <out>/candidates_manifest.csv
The paper's judgments are released (supporting/motivation_repo/.../motivation/c1/judgments.jsonl); the edited images are not.
"""
import argparse, csv, json, time
from pathlib import Path
from PIL import Image
from goldibench.judge import common as C


def tasks(ps):
    return sorted(d.name for d in ps.iterdir() if d.is_dir() and (d / f'{d.name}.json').exists())


def task(ps, t):
    j = json.loads((ps / t / f'{t}.json').read_text())
    return j, ps / t / j['resources']['input_file'], ps / t / j['reference_output']['expected_file']


def edit(a, ps, out):
    import torch
    from diffusers import QwenImageEditPlusPipeline
    (out / 'edits').mkdir(parents=True, exist_ok=True)
    todo = [t for i, t in enumerate(tasks(ps)) if i % a.nshards == a.shard and not (out / 'edits' / f'{t}.png').exists()][:a.limit]
    pipe = QwenImageEditPlusPipeline.from_pretrained(a.model, torch_dtype=torch.bfloat16).to('cuda')
    pipe.set_progress_bar_config(disable=True)
    log = (out / f'edit_shard{a.shard}.jsonl').open('a')
    for t in todo:
        j, start, _ = task(ps, t); img = Image.open(start).convert('RGB'); t0 = time.time()
        with torch.inference_mode():
            res = pipe(image=[img], prompt=j['instruction'], generator=torch.manual_seed(a.seed), true_cfg_scale=4.0,
                       negative_prompt=' ', num_inference_steps=40, guidance_scale=1.0, num_images_per_prompt=1).images[0]
        raw = res.size; res = res.convert('RGB').resize(img.size, Image.LANCZOS)
        tmp = out / 'edits' / f'{t}.tmp.png'; res.save(tmp); tmp.rename(out / 'edits' / f'{t}.png')
        log.write(json.dumps({'task_id': t, 'raw_size': raw, 'size': img.size, 'seconds': round(time.time() - t0, 1)}) + '\n'); log.flush()
        print(t, raw, round(time.time() - t0, 1), flush=True)


def manifest(a, ps, out):
    split = {r['task_id']: r['class'] for r in csv.DictReader(open(C.MOT / 'benchmark_audit/split_full.csv')) if r['benchmark'] == 'PSBench'}
    ident = out / 'identity'; ident.mkdir(parents=True, exist_ok=True); rows = []
    for t in tasks(ps):
        j, start, end = task(ps, t); p = ident / f'{t}.png'
        if not p.exists(): Image.open(start).convert('RGB').save(p)   # PNG copy: the judge reads every candidate the same way
        base = {'task_id': t, 'group': j['type'], 'e1_class': split.get(t, ''), 'difficulty': j['difficulty_level']}
        if (out / 'edits' / f'{t}.png').exists(): rows.append(base | {'candidate': 'edit', 'path': str(out / 'edits' / f'{t}.png')})
        rows.append(base | {'candidate': 'identity', 'path': str(p)}); rows.append(base | {'candidate': 'end', 'path': str(end)})
    with (out / 'candidates_manifest.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(json.dumps({'tasks': len(tasks(ps)), 'rows': len(rows), 'edits': sum(r['candidate'] == 'edit' for r in rows)}))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['edit', 'manifest'])
    ap.add_argument('--shard', type=int, default=0); ap.add_argument('--nshards', type=int, default=1); ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--model', default='Qwen/Qwen-Image-Edit-2511'); ap.add_argument('--limit', type=int)
    ap.add_argument('--psbench-data', default=str(C.PSDATA)); ap.add_argument('--out', default=str(C.OUT / 'c1'))
    a = ap.parse_args(); ps, out = Path(a.psbench_data), Path(a.out); out.mkdir(parents=True, exist_ok=True)
    {'edit': edit, 'manifest': manifest}[a.mode](a, ps, out)


if __name__ == '__main__':
    main()
