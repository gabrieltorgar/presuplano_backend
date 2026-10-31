"""From the photo of a paper plan to walls and rooms (US-129).

Claude reads the photo and answers in pixels of the image it saw; the plan gets
them back relative to the photo (0 to 1 on each side), because the editor lays
them over the photo as its background.

Before that reading, the plan's measures are looked for (iteracion-7): a quick
reading of only its cotas tells whether it has its width and its height
written. When one is missing the architect is asked for it, and with them the
reading comes back with its scale — metres per pixel of the polished photo —
so the plan arrives in real metres.
"""

import base64
import io
import json
import logging
import math
import statistics

import anthropic
import numpy as np
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.planner import photo_cleanup, photo_geometry
from apps.planner.models import PhotoConversion
from common.business_time import business_day_start

logger = logging.getLogger(__name__)

# Lo que el navegador entrega de una foto o un escaneo; un GIF o un HEIC no.
SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}
# El escenario «El servicio no responde» espera un minuto y se rinde.
TIMEOUT_SECONDS = 60
ROOM_NAME_MAX = 60
# La lectura rápida sólo busca las cotas: poco esfuerzo y una respuesta corta.
COTAS_EFFORT = "low"
COTAS_MAX_TOKENS = 4000
# Una cota más inclinada que esto no mide ni el ancho ni el alto del plano.
SIDE_SLOPE = math.tan(math.radians(10))

PROMPT = """\
This is a floor plan on paper — printed, or sketched by hand — photographed and \
cleaned up: straightened, cropped and turned black and white. The image is \
{width} × {height} pixels.

Trace the plan so an architect can keep editing it:
- walls: one straight segment per wall, centred on the drawn wall, from end to \
end. Split a wall where another wall meets it. Follow the walls that are drawn; \
do not trace furniture, dimension lines, text, hatching or the paper's edge.
- rooms: each space enclosed by walls, as the polygon of its corners in order. \
A door or an open doorway does not open a room: close it along the wall. If the \
space has a name written inside it, give the name exactly as written; \
otherwise give an empty string.

- openings: each door and each window drawn on a wall, as the two points where \
it starts and ends along that wall. A door is a leaf with its swing arc, or a \
gap in the wall; a window is a set of thin parallel lines inside the wall.

- dimensions: each dimension written on the plan (a cota), as the two ends of \
its dimension line and the length it states, in metres: 4.5 for «4.50», «4,50» \
or «450» in centimetres.

Use pixel coordinates of this image, x to the right and y downwards. Trace each \
wall straight through its doors and windows: they go in openings, not as gaps.
If the photo is not a floor plan, or it is too blurry to see the walls, set \
is_floor_plan to false and leave every list empty."""

MEASURES_HINT = """

The architect says the whole plan measures {measures}, from outside to outside. \
Use it to judge the proportions of the walls you trace."""

COTAS_PROMPT = """\
This is a floor plan on paper, photographed and cleaned up. The image is \
{width} × {height} pixels.

List only the dimensions written on the plan (its cotas) that you can read \
clearly: for each, the two ends of its dimension line, in pixel coordinates of \
this image (x to the right, y downwards), and the length it states in metres: \
4.5 for «4.50», «4,50» or «450» in centimetres. Leave out any you cannot read \
with certainty. If the photo is not a floor plan, set is_floor_plan to false."""

POINT = {
    "type": "object",
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
    "required": ["x", "y"],
    "additionalProperties": False,
}

READING_SCHEMA = {
    "type": "object",
    "properties": {
        "is_floor_plan": {"type": "boolean"},
        "walls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "x1": {"type": "number"},
                    "y1": {"type": "number"},
                    "x2": {"type": "number"},
                    "y2": {"type": "number"},
                },
                "required": ["x1", "y1", "x2", "y2"],
                "additionalProperties": False,
            },
        },
        "openings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["door", "window"]},
                    "x1": {"type": "number"},
                    "y1": {"type": "number"},
                    "x2": {"type": "number"},
                    "y2": {"type": "number"},
                },
                "required": ["kind", "x1", "y1", "x2", "y2"],
                "additionalProperties": False,
            },
        },
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "x1": {"type": "number"},
                    "y1": {"type": "number"},
                    "x2": {"type": "number"},
                    "y2": {"type": "number"},
                    "metres": {"type": "number"},
                },
                "required": ["x1", "y1", "x2", "y2", "metres"],
                "additionalProperties": False,
            },
        },
        "rooms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "points": {"type": "array", "items": POINT},
                },
                "required": ["name", "points"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["is_floor_plan", "walls", "rooms", "openings", "dimensions"],
    "additionalProperties": False,
}


COTA = READING_SCHEMA["properties"]["dimensions"]

COTAS_SCHEMA = {
    "type": "object",
    "properties": {"is_floor_plan": {"type": "boolean"}, "dimensions": COTA},
    "required": ["is_floor_plan", "dimensions"],
    "additionalProperties": False,
}


class UnsupportedPhoto(Exception):
    """The file is not a PNG, JPG or WEBP image."""


class ConversionUnavailable(Exception):
    """Claude could not read the photo now: no key, no answer, or no usable one."""


def prepare_photo(data: bytes) -> tuple[bytes, str]:
    """The photo as Claude should see it: upright, polished, black and white.

    A phone stores the picture sideways and says how to turn it (EXIF), so it
    is turned first. Then OpenCV straightens, crops, scales and cleans it
    (``photo_cleanup``); the result travels as PNG, which keeps black and white
    exact and weighs little.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image_format = image.format
        image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise UnsupportedPhoto from error
    if image_format not in SUPPORTED_FORMATS:
        raise UnsupportedPhoto

    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        # Lo transparente de un PNG es papel: blanco, no negro.
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, "white")
        image.paste(rgba, mask=rgba.getchannel("A"))

    cleaned = photo_cleanup.clean_photo(np.asarray(image.convert("L")))
    buffer = io.BytesIO()
    Image.fromarray(cleaned.image).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), "image/png"


def _ask_claude(
    image: bytes, media_type: str, prompt: str, schema: dict, **options
) -> dict:
    """One look of Claude at the photo, answered in the JSON of ``schema``.

    The answer comes back with the image size it refers to, so turning it into
    relative coordinates never depends on a size guessed elsewhere.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("Conversión de foto sin ANTHROPIC_API_KEY configurada")
        raise ConversionUnavailable

    width, height = Image.open(io.BytesIO(image)).size
    client = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
    )
    try:
        response = client.beta.messages.create(
            model=settings.PHOTO_PLAN_MODEL,
            max_tokens=options.get("max_tokens", 16000),
            thinking={"type": "adaptive"},
            output_config={
                "effort": options.get("effort", "medium"),
                "format": {"type": "json_schema", "schema": schema},
            },
            # Si un filtro de seguridad rechaza la foto, la API reintenta con
            # el modelo de respaldo dentro de la misma llamada.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.standard_b64encode(image).decode(),
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt.format(width=width, height=height),
                        },
                    ],
                }
            ],
        )
    except anthropic.APIError as error:
        logger.warning("Claude no leyó la foto del plano: %s", type(error).__name__)
        raise ConversionUnavailable from error

    if response.stop_reason != "end_turn":
        logger.warning(
            "Lectura de la foto cortada: stop_reason=%s", response.stop_reason
        )
        raise ConversionUnavailable

    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        reading = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConversionUnavailable from error
    return {**reading, "image_width": width, "image_height": height}


def _measures_text(measures: dict) -> str:
    """{"width_m": 12.5, "height_m": 8} → «12.5 m wide and 8.0 m high»."""
    parts = []
    if "width_m" in measures:
        parts.append(f"{float(measures['width_m'])} m wide (its horizontal side)")
    if "height_m" in measures:
        parts.append(f"{float(measures['height_m'])} m high (its vertical side)")
    return " and ".join(parts)


def read_plan(image: bytes, media_type: str, measures: dict | None = None) -> dict:
    """Ask Claude for the walls and rooms of the photo, in pixels.

    With the measures the architect gave, Claude reads knowing the plan's real
    size, to approximate the walls whose length is not written.
    """
    prompt = PROMPT
    if measures:
        # Las llaves del texto ya resueltas no deben volver a formatearse.
        hint = MEASURES_HINT.format(measures=_measures_text(measures))
        prompt += hint.replace("{", "{{").replace("}", "}}")
    return _ask_claude(image, media_type, prompt, READING_SCHEMA)


def read_cotas(image: bytes, media_type: str) -> dict:
    """The quick reading: only the cotas written on the plan, in pixels."""
    return _ask_claude(
        image,
        media_type,
        COTAS_PROMPT,
        COTAS_SCHEMA,
        effort=COTAS_EFFORT,
        max_tokens=COTAS_MAX_TOKENS,
    )


def missing_sides(reading: dict) -> list[str]:
    """Which of the plan's sides has no legible cota: "width", "height", both.

    A cota along the horizontal gives the width's scale, one along the vertical
    the height's; a slanted one gives neither.
    """
    horizontal = vertical = False
    for (x1, y1), (x2, y2), _metres in _cotas(reading):
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        horizontal = horizontal or dy <= dx * SIDE_SLOPE
        vertical = vertical or dx <= dy * SIDE_SLOPE
    return [
        side
        for side, found in (("width", horizontal), ("height", vertical))
        if not found
    ]


def scale_from_measures(reading: dict, measures: dict) -> float | None:
    """Metres per pixel the architect's width and height give the walls read.

    The width is the span of all the walls from left to right, the height from
    top to bottom; with both, the two scales are averaged.
    """
    width = reading["image_width"]
    height = reading["image_height"]
    points = [
        _inside_photo(wall[f"x{end}"], wall[f"y{end}"], width, height)
        for wall in reading.get("walls", [])
        for end in (1, 2)
    ]
    if not points:
        return None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    spans = {"width_m": max(xs) - min(xs), "height_m": max(ys) - min(ys)}
    scales = [
        float(measures[side]) / spans[side]
        for side in ("width_m", "height_m")
        if side in measures and spans[side] > 0
    ]
    return round(statistics.mean(scales), 8) if scales else None


def _relative(x: float, y: float, width: float, height: float) -> dict:
    """A pixel of the photo as a fraction of its sides, kept inside the photo."""
    return {
        "x": round(min(max(x / width, 0.0), 1.0), 5),
        "y": round(min(max(y / height, 0.0), 1.0), 5),
    }


def _area(points: list[dict]) -> float:
    """Shoelace area, only to tell a room from a line."""
    pairs = zip(points, points[1:] + points[:1], strict=True)
    return abs(sum(a["x"] * b["y"] - b["x"] * a["y"] for a, b in pairs)) / 2


def _inside_photo(x: float, y: float, width: float, height: float) -> tuple:
    """A pixel of Claude's answer, kept inside the photo."""
    return (min(max(x, 0.0), width), min(max(y, 0.0), height))


def _cotas(reading: dict) -> list[tuple[tuple, tuple, float]]:
    """The cotas worth trusting: they measure something and say how much."""
    width = reading["image_width"]
    height = reading["image_height"]
    cotas = []
    for item in reading.get("dimensions", []):
        start = _inside_photo(item["x1"], item["y1"], width, height)
        end = _inside_photo(item["x2"], item["y2"], width, height)
        if item.get("metres", 0) > 0 and start != end:
            cotas.append((start, end, float(item["metres"])))
    return cotas


def read_scale(reading: dict) -> float:
    """Metres per pixel the cotas give the photo; the provisional one without.

    Each cota is a scale on its own. The one in the middle rules, so that a
    cota read wrong — a 9 taken for a 4 — does not drag the rest with it.
    """
    scales = [metres / math.dist(start, end) for start, end, metres in _cotas(reading)]
    if not scales:
        return photo_geometry.PROVISIONAL_METRES_PER_PIXEL
    return round(statistics.median(scales), 8)


def to_plan(reading: dict, *, metres_per_pixel: float | None = None) -> dict:
    """Claude's pixels → the walls and rooms the editor places over the photo.

    On the way the drawing is tidied (``photo_geometry``): walls almost square
    come out square, corners meet, each door and window lands on its wall —
    as where it starts and ends along it — and rooms close over their doors.
    How close is close comes from the cotas read on the plan, when there are. What has
    no length or no area is dropped: the architect would only have to find it
    and delete it.
    """
    if not reading.get("is_floor_plan"):
        return {"walls": [], "rooms": [], "openings": [], "dimensions": []}

    width = reading["image_width"]
    height = reading["image_height"]
    if metres_per_pixel is None:
        metres_per_pixel = read_scale(reading)
    walls = [
        (
            _inside_photo(wall["x1"], wall["y1"], width, height),
            _inside_photo(wall["x2"], wall["y2"], width, height),
        )
        for wall in reading.get("walls", [])
    ]
    walls = photo_geometry.join_walls(
        photo_geometry.square_walls([w for w in walls if w[0] != w[1]]),
        photo_geometry.JOIN_METRES / metres_per_pixel,
    )
    walls, openings = photo_geometry.place_openings(
        walls,
        [
            (
                item["kind"],
                _inside_photo(item["x1"], item["y1"], width, height),
                _inside_photo(item["x2"], item["y2"], width, height),
            )
            for item in reading.get("openings", [])
            if item.get("kind") in ("door", "window")
        ],
        metres_per_pixel=metres_per_pixel,
    )
    read_rooms = [
        (
            " ".join((room.get("name") or "").split())[:ROOM_NAME_MAX].strip(),
            [
                _inside_photo(p["x"], p["y"], width, height)
                for p in room.get("points", [])
            ],
        )
        for room in reading.get("rooms", [])
    ]
    read_rooms = [(name, points) for name, points in read_rooms if len(points) >= 3]
    closed = photo_geometry.close_rooms(
        walls, read_rooms, metres_per_pixel=metres_per_pixel
    )

    rooms = []
    for name, points in closed:
        relative = [_relative(x, y, width, height) for x, y in points]
        if len(relative) < 3 or _area(relative) == 0:
            continue
        rooms.append({"name": name or None, "points": relative})

    return {
        "walls": [
            {
                "start": _relative(*start, width, height),
                "end": _relative(*end, width, height),
            }
            for start, end in walls
        ],
        "rooms": rooms,
        "openings": [
            {"kind": kind, "wall": wall, "from": round(start, 5), "to": round(end, 5)}
            for kind, wall, start, end in openings
        ],
        "dimensions": [
            {
                "start": _relative(*start, width, height),
                "end": _relative(*end, width, height),
                "value": round(metres, 3),
            }
            for start, end, metres in _cotas(reading)
        ],
    }


def conversions_today(owner) -> int:
    """How many photos this account had read since midnight, Mexico time.

    The daily cap follows the business day (iteracion-27 #11): with UTC it
    started over at 18:00 in Mexico.
    """
    midnight = business_day_start()
    return PhotoConversion.objects.filter(owner=owner, created_at__gte=midnight).count()


def _image_payload(image: bytes, media_type: str) -> dict:
    """The polished photo as the editor lays it under the plan."""
    width, height = Image.open(io.BytesIO(image)).size
    src = f"data:{media_type};base64,{base64.standard_b64encode(image).decode()}"
    return {"src": src, "width": width, "height": height}


def _remaining_today(owner) -> int:
    return max(settings.PHOTO_PLAN_DAILY_LIMIT - conversions_today(owner), 0)


def convert_photo(
    *,
    owner,
    data: bytes,
    measures: dict | None = None,
    skip_measures: bool = False,
) -> dict:
    """Read the photo and count it against today's cap.

    Without measures the cotas are looked for first; if the width or the height
    has none legible, the answer asks for it instead of reading the plan, and
    that costs no photo of the day. Only what Claude actually read as a plan
    is counted: a failure costs nothing either.
    """
    image, media_type = prepare_photo(data)

    cotas = None
    if not measures and not skip_measures:
        cotas = read_cotas(image, media_type)
        missing = missing_sides(cotas) if cotas.get("is_floor_plan") else []
        if missing:
            return {
                "needs_measures": True,
                "missing": missing,
                "image": _image_payload(image, media_type),
                "remaining_today": _remaining_today(owner),
            }

    reading = read_plan(image, media_type, measures=measures or None)
    metres_per_pixel, scale = None, None
    if measures:
        metres_per_pixel = scale_from_measures(reading, measures)
        scale = "medidas" if metres_per_pixel else None
    elif cotas is not None and reading.get("is_floor_plan"):
        # Las cotas de la lectura completa mandan; si no trajo, las de la rápida.
        source = reading if _cotas(reading) else cotas
        if _cotas(source):
            metres_per_pixel, scale = read_scale(source), "cotas"

    plan = to_plan(reading, metres_per_pixel=metres_per_pixel)
    PhotoConversion.objects.create(
        owner=owner, walls=len(plan["walls"]), rooms=len(plan["rooms"])
    )
    # La foto pulida vuelve para quedar de fondo: es la que leyó Claude, así
    # que los muros caen exactos sobre ella.
    return {
        **plan,
        "image": _image_payload(image, media_type),
        "remaining_today": _remaining_today(owner),
        "scale": scale,
        "metres_per_pixel": metres_per_pixel,
    }
