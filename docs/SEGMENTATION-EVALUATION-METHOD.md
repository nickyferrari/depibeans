# Repeating the leaf-segmentation evaluation

Method only; no run data belongs in this file. It evaluates the deployed
`depibeans/leaf_segmentation.py` exactly as imported from the repository, on
saved observations, offline.

## Rules

- Read-only on the chamber computer: copy with `tar cf -` over SSH, nothing
  else. Do not call the chamber API. Keep `tar` alone in its remote command so
  its stdout stays clean.
- Work on local copies under the git-ignored `.runtime/<name>/`. Figures,
  label TIFFs and data-bearing reports stay there; never in tracked paths.
- Do not edit the segmentation code while evaluating it.

## Steps

```sh
RUN=/home/chamber/DepiBeans/data/captures/<observation>
OUT=.runtime/science-YYYYMMDD
mkdir -p $OUT/data/<short>
dssh "cd $RUN && tar cf - fluorescence.json analysis-state.json analysis capture-*/metadata.json" \
  | tar xf - -C $OUT/data/<short>

python tools/evaluate_segmentation.py $OUT/data/<a> $OUT/data/<b> \
  --output $OUT/segmentation --sensitivity
python tools/compare_metric_regions.py $OUT/data/<a> $OUT/metrics/<a>
```

`evaluate_segmentation.py` writes per observation:

- `segmentation-pipeline-<metric>.png` — the reference `_reference_point`
  would choose; plus `segmentation-Fm.png`, `-first-Fm_prime.png`,
  `-reference-Fm.png` when those are different files. Panels: source with a
  square-root stretch (dim leaves visible, NaN black) | labels, boundaries and
  ids | 8 px inset measurement labels.
- `stored-vs-fresh.png` — the label file stored in the observation next to a
  fresh run of the deployed code.
- `labels-*.tif`, `segmentation-evaluation.json` (regions, warnings, pairwise
  matching, optional parameter sweep) and `cross-observation.json`.

## Before looking

Read `segmentation` in `fluorescence.json`: `algorithm_version`,
`reference_metric`, `reference_file`, `parameters`. If the version differs
from `ALGORITHM_VERSION`, the stored labels (and every `leaf_values` entry) come
from older code; say so in the report. Note the finite fraction in each figure
title: below 95 % the finite mask *is* the foreground and no threshold is
applied, which changes behaviour completely.

## What to look for (open every PNG; zoom where regions are small)

First write down the leaves you can see in the stretched source, with a
location name for each, and the non-leaf objects. Mark anything you cannot
decide as unsure. Then, per figure, count and locate:

| Finding | Meaning |
|---|---|
| missed | a visible leaf (often dim, shaded or at the frame edge) without a region |
| merged | one region covering two or more leaves |
| split | one leaf cut into two or more regions; straight cuts and cuts along a midrib are typical |
| false | region on a non-leaf: pot rim, labels, glare, background haze, sensor banding |
| ragged | fringes, streaks, tails along a neighbour's margin |
| edge | regions touching the frame (`touches_edge`); their area is truncated |
| inset loss | regions that keep little area after the inset (`inset_retained_fraction`) |

Do not count in the algorithm's favour. A second reviewer, or manual outlines
on a few images, is needed before quoting accuracy; Dice against manual masks
is the acceptance measure in `docs/LEAF-SEGMENTATION.md` and this procedure
does not compute it.

## Stability

`match()` pairs regions one-to-one by maximum total IoU and reports region
counts, foreground IoU, per-pair IoU, area change, centroid shift and whether
the pair kept the same id. Compare:

- references within one observation (Fm, Fm′, reference-Fm);
- the pipeline reference between observations of the same plants;
- stored labels against a fresh run.

Agreement is not correctness: two segmentations can agree on the same merged
leaves. Region ids come from row/column ordering within one segmentation
(`_stable_labels`). Treat them as persistent leaf or plant identity only if the
same-id, high-IoU count equals the leaf count across the observations being
compared, and keep in mind that cross-observation differences also include real
leaf movement.

## Reporting

Per-image table (counts and locations), stability table, sensitivity table,
and a Limitations section stating: number of scenes, who reviewed, absence of
ground truth, what was not checked.
