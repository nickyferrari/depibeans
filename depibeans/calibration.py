"""Legacy calibration JSON interoperability and offline quadratic fitting."""
import json
import math
from .lighting import integer, finite


def load_points(text):
    try:
        return _load_points(text)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Malformed legacy calibration document") from exc


def _load_points(text):
    root = json.loads(text)
    if not isinstance(root, dict) or not isinstance(root.get('calibration_data'), list):
        raise ValueError('Expected calibration_data array')
    points = []
    for point in root['calibration_data']:
        finite(point['intensity'])
        intensity = point['intensity']
        if intensity < 0:
            raise ValueError('Intensity cannot be negative')
        rails = {}
        for setting in point['settings']:
            address = integer(setting['I2Caddress'], 1, 127, 'rail address')
            if address in rails:
                raise ValueError('Duplicate rail address')
            zones = setting['zones']
            if not isinstance(zones, list) or not 1 <= len(zones) <= 7:
                raise ValueError('Expected 1 to 7 zones')
            rails[address] = tuple(integer(v, 0, 65535, 'raw output') for v in zones)
        if not rails:
            raise ValueError('A calibration point needs at least one rail')
        points.append((intensity, rails))
    return points


def dump_points(points):
    text = json.dumps({'calibration_data': [
        {'intensity': intensity, 'settings': [
            {'I2Caddress': address, 'zones': list(zones)} for address, zones in rails.items()
        ]} for intensity, rails in points
    ]}, indent=2, allow_nan=False)
    load_points(text)
    return text


def quadratic_fit(samples):
    """QR least squares with centered/scaled x; coefficient order c,b,a.

    Fitting is offline. A fit is never uploaded or deemed physically valid here.
    """
    samples = [(finite(x), finite(y)) for x, y in samples]
    if len({x for x, y in samples}) < 3:
        raise ValueError('At least three distinct measured intensities are required')
    center = sum(x for x, _ in samples) / len(samples)
    scale = max(abs(x - center) for x, _ in samples)
    xs = [(x - center) / scale for x, _ in samples]
    columns = [[1.0]*len(xs), xs, [x*x for x in xs]]
    q, r = [], [[0.0]*3 for _ in range(3)]
    for j, column in enumerate(columns):
        v = list(column)
        for i in range(j):
            r[i][j] = sum(a*b for a,b in zip(q[i], v))
            v = [a-r[i][j]*b for a,b in zip(v,q[i])]
        r[j][j] = sum(a*a for a in v)**0.5
        if r[j][j] < 1e-12:
            raise ValueError('Calibration points are numerically degenerate')
        q.append([a/r[j][j] for a in v])
    rhs = [sum(a*y for a,(_,y) in zip(col,samples)) for col in q]
    c = [0.0]*3
    for i in (2,1,0):
        c[i] = (rhs[i]-sum(r[i][j]*c[j] for j in range(i+1,3))) / r[i][i]
    result = [c[0]-c[1]*center/scale+c[2]*center**2/scale**2,
              c[1]/scale-2*c[2]*center/scale**2, c[2]/scale**2]
    if not all(math.isfinite(v) for v in result):
        raise ValueError('Unrepresentable fit')
    rmse = (sum((result[0]+result[1]*x+result[2]*x*x-y)**2 for x,y in samples)/len(samples))**0.5
    return {'coefficients': result, 'rmse': rmse, 'domain': [min(x for x,_ in samples),max(x for x,_ in samples)]}
