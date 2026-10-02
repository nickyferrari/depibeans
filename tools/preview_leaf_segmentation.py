"""Generate a local, read-only leaf-segmentation review from one TIFF."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from depibeans.leaf_segmentation import inset_labels, segment_leaves


def _heatmap(image):
    import numpy as np

    finite = np.isfinite(image)
    values = image[finite]
    low, high = np.percentile(values, [1, 99])
    if high <= low:
        high = low + 1
    normalized = np.clip((np.where(finite, image, low) - low) / (high - low), 0, 1)
    stops = np.array([[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]], dtype=float)
    rgb = np.stack([np.interp(normalized, np.linspace(0, 1, len(stops)), stops[:, channel]) for channel in range(3)], axis=-1).astype(np.uint8)
    rgb[~finite] = 0
    return rgb, float(low), float(high)


def _overlay(rgb, labels, measurement_labels, regions):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from scipy import ndimage as ndi
    from skimage.segmentation import find_boundaries

    detected_boundary = find_boundaries(labels, mode="inner")
    measurement_boundary = ndi.binary_dilation(find_boundaries(measurement_labels, mode="inner"), iterations=2)
    result = rgb.copy()
    result[detected_boundary] = [235, 243, 238]
    result[measurement_boundary] = [255, 153, 31]
    rendered = Image.fromarray(result, "RGB")
    draw = ImageDraw.Draw(rendered)
    size = max(14, round(rendered.width / 55))
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    for region in regions:
        y, x = region["centroid"]
        value = str(region["id"])
        draw.text((x, y), value, anchor="mm", font=font, fill="white", stroke_width=max(1, size // 6), stroke_fill="#713800")
    return rendered


def build_review(source, output, *, min_area=None, smoothing_sigma=1.4, separation_prominence=0.12, inset_pixels=8):
    import numpy as np
    from PIL import Image
    import tifffile

    source = Path(source).resolve()
    output = Path(output).resolve()
    if not source.is_file():
        raise ValueError("Input TIFF does not exist")
    image = tifffile.imread(source).squeeze()
    labels, result = segment_leaves(
        image,
        min_area=min_area,
        smoothing_sigma=smoothing_sigma,
        separation_prominence=separation_prominence,
    )
    measurement_labels = inset_labels(labels, inset_pixels)
    output.mkdir(parents=True, exist_ok=True)
    rgb, display_min, display_max = _heatmap(image)
    Image.fromarray(rgb, "RGB").save(output / "heatmap.png")
    _overlay(rgb, labels, measurement_labels, result.get("regions", [])).save(output / "leaf-overlay.png")
    tifffile.imwrite(output / "leaf-labels.tif", labels.astype(np.uint16 if int(labels.max()) <= 65535 else np.uint32), photometric="minisblack")
    inset_name = f"leaf-labels-inset-{float(inset_pixels):g}px.tif"
    tifffile.imwrite(output / inset_name, measurement_labels.astype(np.uint16 if int(labels.max()) <= 65535 else np.uint32), photometric="minisblack")
    result["measurement_inset_pixels"] = float(inset_pixels)
    result["measurement_label_file"] = inset_name
    for region in result.get("regions", []):
        identifier = int(region["id"])
        original_area = int((labels == identifier).sum())
        measurement_area = int((measurement_labels == identifier).sum())
        region["measurement_area_pixels"] = measurement_area
        region["retained_fraction"] = float(measurement_area / original_area) if original_area else 0.0
    result.update(source_file=source.name, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), display_min=display_min, display_max=display_max)
    (output / "segmentation.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    rows = "".join(f"<tr><td>{region['id']}</td><td>{region['area_pixels']}</td><td>{region['measurement_area_pixels']}</td><td>{region['retained_fraction']:.1%}</td><td>{region['centroid'][0]:.1f}, {region['centroid'][1]:.1f}</td><td>{html.escape(' · '.join(region['warnings']) or 'None')}</td></tr>" for region in result.get("regions", []))
    page = f"""<!doctype html><html><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>Leaf segmentation review</title><style>body{{font:16px/1.5 system-ui;max-width:1200px;margin:32px auto;padding:0 20px;color:#183d27}}.images{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}img{{width:100%;background:#000}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border-bottom:1px solid #d8e2dc;text-align:left}}code{{background:#eef3ef;padding:2px 5px}}.key{{display:flex;gap:18px;align-items:center}}.swatch{{display:inline-block;width:22px;height:4px;margin-right:6px;vertical-align:middle}}@media(max-width:760px){{.images{{grid-template-columns:1fr}}}}</style><h1>Local leaf segmentation review</h1><p><code>{html.escape(source.name)}</code> · {len(result.get('regions', []))} regions · {html.escape(result.get('status', 'unavailable'))}</p><p class=\"key\"><span><i class=\"swatch\" style=\"background:#ebf3ee\"></i>detected edge</span><span><i class=\"swatch\" style=\"background:#ff991f\"></i>{float(inset_pixels):g}-pixel measurement inset</span></p><div class=\"images\"><figure><img src=\"heatmap.png\" alt=\"Source heat map\"><figcaption>Unmodified values rendered as a heat map</figcaption></figure><figure><img src=\"leaf-overlay.png\" alt=\"Candidate leaf boundaries and measurement inset\"><figcaption>Detected edge in white; conservative measurement edge in orange</figcaption></figure></div><h2>Candidate regions</h2><table><thead><tr><th>ID</th><th>Detected px</th><th>Measured px</th><th>Retained</th><th>Centroid y, x</th><th>Warnings</th></tr></thead><tbody>{rows}</tbody></table><p>This local review does not alter the DEPI portal or the source TIFF.</p></html>"""
    (output / "index.html").write_text(page)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Background-corrected Fm or other two-dimensional TIFF")
    parser.add_argument("--output", type=Path, help="Review directory; defaults beside the input")
    parser.add_argument("--min-area", type=int, help="Minimum accepted region area in pixels")
    parser.add_argument("--smoothing-sigma", type=float, default=1.4)
    parser.add_argument("--separation-prominence", type=float, default=0.12, help="Watershed peak prominence from 0 to 1")
    parser.add_argument("--inset-pixels", type=float, default=8, help="Conservative measurement inset from every leaf edge")
    args = parser.parse_args()
    destination = args.output or args.source.with_name(args.source.stem + "-segmentation-review")
    result = build_review(
        args.source,
        destination,
        min_area=args.min_area,
        smoothing_sigma=args.smoothing_sigma,
        separation_prominence=args.separation_prominence,
        inset_pixels=args.inset_pixels,
    )
    print(f"{result.get('status', 'unavailable')}: {len(result.get('regions', []))} regions")
    print(destination.resolve() / "index.html")


if __name__ == "__main__":
    main()
