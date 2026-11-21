"""Where the paper scripts find data that is not part of the benchmark itself (all restored from the logs dataset
VanWang/GoldiBench-logs by scripts/restore_runs.sh):
  runs                 <data>/bench_b1_<app>[_gui]/runs/<run>/        (restore_runs.sh)
  agent renders        the same folders, as WebP                        (restore_runs.sh --images <unit>)
  Sec. 2 / Sec. 4      <data>/motivation, <data>/e3, <data>/e3x, <data>/v5  (restore_runs.sh --supporting)
<data> is GOLDIBENCH_DATA (gbpaths.DATA); GOLDIBENCH_MOTIVATION overrides the motivation folder.
Paths stored inside the logs (manifests, pairs files) start with <ROOT>/visual_effect_data/, the research storage the
experiments ran on; local() maps them to <data> and falls back to the WebP copy when the PNG is absent."""
import os
import gbpaths

DATA = str(gbpaths.DATA)
MOT = os.environ.get('GOLDIBENCH_MOTIVATION', os.path.join(DATA, 'motivation'))


def local(p):
    p = str(p).replace('<ROOT>/visual_effect_data', DATA)
    if not os.path.exists(p) and p.endswith('.png') and os.path.exists(p[:-4] + '.webp'):
        p = p[:-4] + '.webp'
    return p
