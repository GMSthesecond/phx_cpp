import colorsys
import json
import os

# A curated, mutually-distinguishable palette (based on the well-known Kelly/Glasbey-style
# "maximally distinct" color sets) — handed out in this order before falling back to
# generated colors once an area has more operators than the palette has entries.
# Reds/maroons from the original set are excluded: DI draws layer borders in red, and a
# red-ish fill made the border hard to pick out against it.
_PALETTE = [
    (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48),
    (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60), (190, 230, 250),
    (0, 128, 128), (220, 190, 255), (170, 110, 40), (0, 150, 130), (170, 255, 195),
    (128, 128, 0), (255, 215, 180), (0, 0, 128), (128, 128, 128), (0, 100, 0), (90, 90, 200),
]


def _color_file(maps_dir):
    return os.path.join(maps_dir, 'operator_colors.json')


def load_colors(maps_dir):
    """Returns {operator: (r, g, b)} previously assigned, so the same operator always
    gets the same color across runs."""
    path = _color_file(maps_dir)
    if os.path.isfile(path):
        with open(path) as f:
            return {k: tuple(v) for k, v in json.load(f).items()}
    return {}


def save_colors(maps_dir, colors):
    with open(_color_file(maps_dir), 'w') as f:
        json.dump({k: list(v) for k, v in colors.items()}, f, indent=2, sort_keys=True)


# The red band excluded around hue 0/360 (true red) is asymmetric: the low side stops
# short of orange (hue ~25-32, which several kept palette colors sit at and which reads
# as clearly distinct from a red border), while the high side reaches further to also
# catch reddish-pink/magenta-red hues (~335-360) that are just as easy to mistake for red.
_RED_LOW_DEGREES = 15
_RED_HIGH_DEGREES = 335


def _generate_color(index):
    """Golden-angle hue stepping once the curated palette is exhausted — still
    deterministic for a given index, and still reasonably well-spaced/contrasting. The
    red band around hue 0 is skipped and the rest of the hue circle stretched to fill the
    gap, so generated colors stay distinguishable from DI's red layer borders."""
    hue_fraction = (index * 0.6180339887) % 1.0
    low = _RED_LOW_DEGREES / 360
    span = (_RED_HIGH_DEGREES - _RED_LOW_DEGREES) / 360
    hue = low + hue_fraction * span
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 0.85)
    return (round(r * 255), round(g * 255), round(b * 255))


def _pick_unused_color(used):
    for c in _PALETTE:
        if c not in used:
            return c
    i = len(used)
    while True:
        c = _generate_color(i)
        if c not in used:
            return c
        i += 1


def color_for_operator(operator, colors):
    """Returns the RGB tuple for an operator, assigning (and recording into `colors`) a
    new one if this operator hasn't been seen before. Caller is responsible for
    persisting `colors` via save_colors() once done."""
    if operator in colors:
        return colors[operator]
    c = _pick_unused_color(set(colors.values()))
    colors[operator] = c
    return c


def _is_reddish(rgb):
    """True for a color close enough to true red (hue near 0/360) to be mistaken for
    DI's red layer borders. Greys and near-blacks (very low saturation/value) are exempt
    since they don't read as red regardless of hue."""
    r, g, b = (c / 255 for c in rgb)
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    if saturation < 0.1 or value < 0.1:
        return False
    hue_degrees = hue * 360
    return hue_degrees <= _RED_LOW_DEGREES or hue_degrees >= _RED_HIGH_DEGREES


def scrub_red_colors(colors):
    """One-time cleanup for colors saved before the palette started avoiding red: finds
    any operator still assigned a reddish color and reassigns it to a fresh non-red one.
    Mutates `colors` in place and returns the list of operators that were changed;
    caller is responsible for persisting via save_colors()."""
    used = set(colors.values())
    changed = []
    for operator, rgb in colors.items():
        if not _is_reddish(rgb):
            continue
        used.discard(rgb)
        new_color = _pick_unused_color(used)
        used.add(new_color)
        colors[operator] = new_color
        changed.append(operator)
    return changed
