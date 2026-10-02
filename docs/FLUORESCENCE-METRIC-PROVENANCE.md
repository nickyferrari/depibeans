# Fluorescence metric provenance

How every number on the portal's fluorescence tiles is produced by
`depibeans/fluorescence.py::analyze_run` (line numbers refer to commit 9ff9ac8)
and how per-leaf values are added by `depibeans/leaf_segmentation.py`
(`ALGORITHM_VERSION = "2.0.0"`). This document contains methods only; it holds
no experiment results.

## The short version

The tiles do **not** share one pixel population, so they do not reconcile by
hand arithmetic:

| Tile | Pixels averaged | Statistic |
|---|---|---|
| Background, F0, Fm, Fm′, Fs, Measuring | every finite pixel of the full frame, background included | mean of the image |
| Fv | dark-reference signal mask | mean of per-pixel `Fm − F0` |
| Fv/Fm | dark-reference signal mask | mean of per-pixel ratios (average of ratios) |
| NPQ, ΦII | dark-reference signal mask AND `Fm′ > 16` | mean of per-pixel ratios (average of ratios) |

Consequences: `Fv` tile > `Fm` tile − `F0` tile whenever the frame contains
background; ratios recomputed from the raw tiles are whole-frame
ratio-of-averages and differ from the displayed average-of-ratios both by
region and by averaging order. `tools/compare_metric_regions.py` quantifies
each part for a saved observation.

## Common pipeline (all metrics)

1. **Which captures.** Each `capture-NNNNNN/metadata.json` not yet listed in
   `analysis-state.json` is processed in name order (l. 80–82). Captures that
   are not `completed` only produce a quality entry (l. 84–87). Captures
   without `protocol_fields`, or whose frame count differs from
   `sum(FramesPerLoop)`, are skipped silently and retried next time (l. 88, 91).
2. **Phases.** `FramesPerLoop`, `SaturationFlash`, `MeasuringLight` are
   expanded per loop (l. 90); consecutive frames are cut into one stack per
   loop/phase (l. 97–98). Frames are read as float32 (l. 66).
3. **Phase image.**
   - Non-saturating phase: arithmetic mean of all frames of the phase (l. 102).
   - Saturating phase: per-frame whole-image mean is computed, a moving average
     of width `min(3, frames)` is taken, and the brightest contiguous window is
     averaged (l. 101). The window is chosen by whole-frame brightness, not per
     pixel and not per leaf. No claim of physiological saturation is made (l. 59).
4. **Clipping.** A pixel is clipped if ANY frame of the phase stack (the whole
   phase, not only the chosen window) is `>= 4095` (l. 99). Clipped pixels are
   set to NaN in the background-corrected phase image (l. 103) and a quality
   note is added (l. 140). The Background image uses the uncorrected phase
   (`rawphases`), so clipped pixels are not removed from it (l. 107).
5. **Background subtraction.** `phase − background` when a stored background
   has the same compatibility signature, otherwise `phase − 0` and the method
   text says "Uncorrected" (l. 95, 103–104).
   **Signature** (l. 94) = JSON of `{exposure: first Exposure entry in seconds,
   gain: preview_feature_readback.Gain, serial: camera serial,
   width: shape of the first frame}`. Frame interval, frame count, measuring
   light and binning are not part of it (shape is).
6. **Reported number** (`image_point`, l. 69–79): the image is written as
   float32 TIFF `analysis/{seq:06d}-{key}.tif`; `value` = float64 mean of all
   finite pixels of that image; `valid_pixels` = number of finite pixels of
   that image. There is no other mask at this stage: any masking must already
   be in the image as NaN. `display_min/max` are the running 1st/99th
   percentiles.
7. **Time.** `stamp = metadata.actual_trigger`, falling back to the mtime of
   `metadata.json` when absent/zero (l. 92). `time_s = stamp − origin` (l. 78).
   `origin` is `run_start` when the caller supplies it (`time_origin =
   "run_start"`), otherwise the stamp of the first processed capture
   (`"first_capture"`) (l. 61–62, 93). `actual_trigger` is a software timestamp
   of the FPGA start command (see `timing_source` in the metadata); the physical
   edge is not measured. The same stamp is used for every metric of a capture,
   i.e. F0 and Fm (and Fs and Fm′) carry the identical `time_s` although the
   saturating phase is acquired after the measuring phase. `completed_at` is
   the stamp of the last processed capture (l. 142).

## Per metric

`bg` = matching background present. "finite" = not clipped-NaN.

### Background
- Capture: `measurement_type == "background"` with every phase non-saturating
  and `MeasuringLight == 0` (l. 106). Image: mean of all frames of the first
  phase, **not** background-subtracted and **without** clip NaNs (l. 107).
- Pixels: every pixel. Formula: mean. `valid_pixels` = frame size.
- Side effects: becomes the stored background with the capture's signature and
  clears the dark reference (l. 108).

### F0 and Fm
- Capture: `dark-reference`, exactly two phases, `SaturationFlash == [0, 1]`,
  `MeasuringLight == [1, 1]` (l. 109). F0 = phase 1 (mean of frames);
  Fm = phase 2 (brightest ≤3-frame window), both background-subtracted when
  `bg`, clipped → NaN (l. 110).
- Pixels: **every finite pixel of the full frame, background included.**
  Formula: mean. `valid_pixels` = frame size minus clipped pixels.
- They are emitted even without a matching background (then uncorrected).

### Fv
- Only when `bg` (l. 111). Mask (l. 112):
  `isfinite(F0) & isfinite(Fm) & (F0 > 16) & (Fm > F0)` (camera units after
  background subtraction). Image: `Fm − F0` inside the mask, NaN outside (l. 113, 115).
- Reported: mean of per-pixel differences over the mask; `valid_pixels` = mask size.
- The masked Fm is also written to `analysis/{seq:06d}-reference-Fm.tif`
  (l. 114) and becomes the dark reference, stored with the signature, the
  background file name and a saturation signature = JSON of the saturating
  phase's `Exposure, FrameInterval, FramesPerLoop, MeasuringLight,
  ActinicShutter` (l. 117–118). Without `bg` the reference is cleared and a
  note is added (l. 119).

### Fv/Fm
- Same capture and mask as Fv. Image: per-pixel `(Fm − F0) / Fm` (l. 116).
- Reported: **average of per-pixel ratios** over the mask. `valid_pixels` =
  mask size. Because `Fm > F0 > 16` inside the mask, every per-pixel value lies
  in (0, 1).

### Fm′ and Fs
- Capture: `light-adapted` with two phases `[0, 1]` / measuring `[1, 1]`
  ("paired", l. 121), or `saturation` with one saturating phase ("single",
  l. 122). Fm′ = last phase (brightest ≤3-frame window) (l. 124); Fs = first
  phase mean, paired only (l. 125). Fs is never inferred.
- Pixels: **every finite pixel of the full frame.** Formula: mean.

### NPQ
- Requires `bg` and a dark reference with equal signature, equal background
  file and equal saturation signature (l. 126–127); otherwise withheld with a
  note (l. 135).
- Mask (l. 129): `isfinite(reference Fm) & isfinite(Fm′) & (Fm′ > 16)`. Since
  the reference Fm is NaN outside the dark-reference mask, this is the
  dark-reference mask further restricted by `Fm′ > 16` at this time point, so
  it can differ by a few pixels between time points.
- Image: per-pixel `(Fm_ref − Fm′) / Fm′` (l. 130). Reported: **average of
  per-pixel ratios**; `valid_pixels` = mask size. Negative per-pixel values are
  kept. No image registration is applied between the dark reference and the
  light capture; leaf movement between them is not corrected.

### ΦII
- Paired captures only. With a valid reference: same mask as NPQ; per-pixel
  `(Fm′ − Fs) / Fm′` (l. 131). Without a valid reference but with `bg`: local
  mask `isfinite(Fs) & isfinite(Fm′) & (Fs > 16)` (l. 133–134). The method text
  of the metric says which mask was used, but only the last processed capture's
  text is kept per metric (l. 76).
- Reported: **average of per-pixel ratios**; `valid_pixels` = mask size.

### Measuring
- Capture: `measuring`, one non-saturating phase with `MeasuringLight == 1`
  (l. 137). Image: mean of frames, background-subtracted when `bg`.
- Pixels: every finite pixel of the full frame. Adaptation state unclassified.

## Per-leaf values (`update_observation`)

Run after every `analyze_run` (l. 145–151 of `fluorescence.py`); failure leaves
the whole-image analysis intact and records `segmentation.state = "unavailable"`.

1. **Reference image** (`_reference_point`, `leaf_segmentation.py` l. 330–338):
   the first point, in preference order, of `Fm`, `Fm_prime`, `Fv_Fm`, `NPQ`,
   `F0`. In v2.0.0 this is therefore the **unmasked, full-frame Fm image**
   (`analysis/{seq}-Fm.tif`), not `reference-Fm.tif`. Because its finite
   fraction is ≥ 0.95, `_foreground` thresholds it (l. 42–61): Gaussian
   smoothing σ = 1.4, threshold = `min(Otsu, max(dark level + 8·MAD-noise,
   0.06 · P99.5))` applied to both the smoothed and the unsmoothed image. An
   image that already has > 5 % NaN uses its finite mask as foreground instead.
2. **Reuse rule** (l. 360–372): stored labels are reused only if
   `algorithm_version`, the SHA-256 of the reference file and the inset all
   match and both label files exist; otherwise labels are recomputed and
   overwritten. Label files written by an older algorithm version stay on disk,
   and keep being shown, until `update_observation` runs again for that
   observation. Check `segmentation.algorithm_version` and
   `segmentation.reference_metric` in `fluorescence.json` before interpreting
   per-leaf values.
3. **Labels**: `segment_leaves` → `analysis/leaf-labels-detected.tif`;
   `inset_labels(labels, 8)` keeps pixels whose Euclidean distance to the
   outside of their own region is > 8 px →
   `analysis/leaf-labels-inset-8px.tif` (l. 222–244, 386–389). Identifiers are
   assigned top-to-bottom by row group, then left-to-right (`_stable_labels`),
   from the geometry of that one segmentation only.
4. **Values** (`summarize_by_leaf`, l. 247–273): for every metric image of the
   observation and every inset region: mean, median, standard deviation over
   pixels that are inside the inset region AND finite in that image;
   `valid_pixels`, `masked_fraction = 1 − valid/area`, with a warning above
   20 %. For ratio images this is again an average of per-pixel ratios, and for
   masked images the effective region is inset region ∩ signal mask. One label
   image is applied to every time point without registration.

## Verifying an observation

```sh
python tools/compare_metric_regions.py /local/copy/of/observation /output/dir --strict
```

recomputes every value with the rules above, checks it against
`fluorescence.json` (including `valid_pixels`, the reference-Fm file and
`time_s = actual_trigger − origin`), and reports each metric for the regions
`production`, `production_tiles`, `whole_frame`, `signal_mask`, `leaf_union`,
`leaf_union_inset`, with `average_of_ratios` and `ratio_of_averages` on
identical pixels. Work on a local copy; write data-bearing output under
`.runtime/`, never into tracked paths.

Decomposition used in reports: `production − tile arithmetic =
(AoR − RoA on the signal mask) [averaging order] + (RoA signal mask − RoA whole
frame) [region]`. The split is path dependent; the alternative path goes
through whole-frame average-of-ratios, which is ill-conditioned because
background pixels have denominators near zero.
