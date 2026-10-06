"""From the photo of a paper plan to walls and rooms (US-129).

Claude reads the photo and answers in pixels of the image it saw; the plan gets
them back relative to the photo (0 to 1 on each side), because the editor lays
them over the photo as its background and gives them a real scale later, from
two points the architect marks (US-41). Nothing here knows metres.
"""

import base64
import io
import json
import logging

import anthropic
import numpy as np
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.planner import photo_cleanup
from apps.planner.models import PhotoConversion

logger = logging.getLogger(__name__)

# Lo que el navegador entrega de una foto o un escaneo; un GIF o un HEIC no.
SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}
# El escenario «El servicio no responde» espera un minuto y se rinde.
TIMEOUT_SECONDS = 60
ROOM_NAME_MAX = 60

PROMPT = """\
This is a floor plan on paper — printed, or sketched by hand — photographed and \
cleaned up: straightened, cropped and turned black and white. The image is \
{width} × {height} pixels.

Trace the plan so an architect can keep editing it:
- walls: one straight segment per wall, centred on the drawn wall, from end to \
end. Split a wall where another wall meets it. Follow the walls that are drawn; \
do not trace furniture, dimension lines, text, hatching or the paper's edge.
- rooms: each space closed by walls, as the polygon of its inner corners in \
order. If the space has a name written inside it, give the name exactly as \
written; otherwise give an empty string.

Use pixel coordinates of this image, x to the right and y downwards. Doors and \
windows are gaps in a wall: trace the wall straight through them.
If the photo is not a floor plan, or it is too blurry to see the walls, set \
is_floor_plan to false and leave walls and rooms empty."""

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
    "required": ["is_floor_plan", "walls", "rooms"],
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


def read_plan(image: bytes, media_type: str) -> dict:
    """Ask Claude for the walls and rooms of the photo, in pixels.

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
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": READING_SCHEMA},
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
                            "text": PROMPT.format(width=width, height=height),
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


def to_plan(reading: dict) -> dict:
    """Claude's pixels → the walls and rooms the editor places over the photo.

    What has no length or no area is dropped: the architect would only have to
    find it and delete it.
    """
    if not reading.get("is_floor_plan"):
        return {"walls": [], "rooms": []}

    width = reading["image_width"]
    height = reading["image_height"]
    walls = []
    for wall in reading.get("walls", []):
        start = _relative(wall["x1"], wall["y1"], width, height)
        end = _relative(wall["x2"], wall["y2"], width, height)
        if start != end:
            walls.append({"start": start, "end": end})

    rooms = []
    for room in reading.get("rooms", []):
        points = [
            _relative(p["x"], p["y"], width, height) for p in room.get("points", [])
        ]
        if len(points) < 3 or _area(points) == 0:
            continue
        name = " ".join((room.get("name") or "").split())[:ROOM_NAME_MAX].strip()
        rooms.append({"name": name or None, "points": points})

    return {"walls": walls, "rooms": rooms}


def conversions_today(owner) -> int:
    """How many photos this account had read since midnight."""
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return PhotoConversion.objects.filter(owner=owner, created_at__gte=midnight).count()


def convert_photo(*, owner, data: bytes) -> dict:
    """Read the photo and count it against today's cap.

    Only what Claude actually read is counted: a failure costs nothing, so it
    does not take a photo away from the architect.
    """
    image, media_type = prepare_photo(data)
    reading = read_plan(image, media_type)
    plan = to_plan(reading)
    PhotoConversion.objects.create(
        owner=owner, walls=len(plan["walls"]), rooms=len(plan["rooms"])
    )
    remaining = settings.PHOTO_PLAN_DAILY_LIMIT - conversions_today(owner)
    # La foto pulida vuelve para quedar de fondo: es la que leyó Claude, así
    # que los muros caen exactos sobre ella.
    width, height = Image.open(io.BytesIO(image)).size
    src = f"data:{media_type};base64,{base64.standard_b64encode(image).decode()}"
    return {
        **plan,
        "image": {"src": src, "width": width, "height": height},
        "remaining_today": max(remaining, 0),
    }
