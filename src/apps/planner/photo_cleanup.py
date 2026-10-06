"""Polishing the photo of a paper plan before the AI reads it (US-129).

foto → corrección de perspectiva → recorte → escala → corrección de iluminación
→ reducción de ruido → contraste → binarización → IA

A phone photo of a sheet comes at an angle, with the table around it, a shadow
across it and the camera's grain on top. Each step takes one of those away, in
that order, and what comes out — a straight, cropped, black-and-white drawing —
is what Claude reads and what the editor shows under the walls, so the two
always match. Every step works on one grey channel.
"""

from dataclasses import dataclass

import cv2
import numpy as np

# El lado mayor de la imagen de trabajo: el mismo con el que Claude ve la foto.
STANDARD_SIDE = 1568

# La hoja tiene que ocupar al menos esto de la foto para creer que es la hoja,
# y no tanto que sea la foto entera (un escaneo).
SHEET_MIN_AREA = 0.2
SHEET_MAX_AREA = 0.95


@dataclass(frozen=True)
class CleanPhoto:
    image: np.ndarray
    straightened: bool


def _order_corners(points: np.ndarray) -> np.ndarray:
    """Top-left, top-right, bottom-right, bottom-left."""
    points = points.reshape(4, 2).astype(np.float32)
    total = points.sum(axis=1)
    diff = np.diff(points, axis=1).ravel()
    return np.float32(
        [
            points[np.argmin(total)],
            points[np.argmin(diff)],
            points[np.argmax(total)],
            points[np.argmax(diff)],
        ]
    )


def find_sheet(gray: np.ndarray) -> np.ndarray | None:
    """The four corners of the sheet, or None when there is no border to find.

    The sheet is the large bright shape on a darker table: what is drawn on it
    only makes holes in that shape, so its outer outline is the sheet's edge.
    A scan, where the paper fills the whole picture, has no such edge.
    """
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    _, bright = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    outline = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(outline) / (gray.shape[0] * gray.shape[1])
    if not SHEET_MIN_AREA <= area <= SHEET_MAX_AREA:
        return None

    perimeter = cv2.arcLength(outline, True)
    for tolerance in (0.01, 0.02, 0.03, 0.04, 0.05):
        corners = cv2.approxPolyDP(outline, tolerance * perimeter, True)
        if len(corners) == 4 and cv2.isContourConvex(corners):
            return _order_corners(corners)
    return None


def straighten(gray: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """The sheet seen from the front: its corners become the image's corners.

    The angle shortens the far side and lengthens the near one; their average
    is the best guess of the sheet's real proportion a single photo allows.
    """
    top_left, top_right, bottom_right, bottom_left = corners
    width = int(
        (
            np.linalg.norm(top_right - top_left)
            + np.linalg.norm(bottom_right - bottom_left)
        )
        / 2
    )
    height = int(
        (
            np.linalg.norm(bottom_left - top_left)
            + np.linalg.norm(bottom_right - top_right)
        )
        / 2
    )
    target = np.float32(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
    )
    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(
        gray, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE
    )


def crop_to_drawing(gray: np.ndarray) -> np.ndarray:
    """Only the drawing, with a margin around it.

    Ink is found against its own neighbourhood, so a shadow is not ink; and a
    dark sliver along the border — the table, when the corners were found a
    little short — is not part of the drawing.
    """
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 51, 15
    )
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(ink)
    height, width = gray.shape
    boxes = []
    for x, y, w, h, area in stats[1:count]:
        touches_border = x == 0 or y == 0 or x + w >= width or y + h >= height
        if area >= 20 and not touches_border:
            boxes.append((x, y, x + w, y + h))
    if not boxes:
        return gray

    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    margin = max(10, int(0.05 * max(right - left, bottom - top)))
    return gray[
        max(top - margin, 0) : min(bottom + margin, height),
        max(left - margin, 0) : min(right + margin, width),
    ]


def scale_to_standard(gray: np.ndarray) -> np.ndarray:
    """The longer side at 1568 px, whatever the camera gave."""
    height, width = gray.shape
    ratio = STANDARD_SIDE / max(height, width)
    size = (round(width * ratio), round(height * ratio))
    interpolation = cv2.INTER_AREA if ratio < 1 else cv2.INTER_CUBIC
    return cv2.resize(gray, size, interpolation=interpolation)


def even_lighting(gray: np.ndarray) -> np.ndarray:
    """The paper at one brightness, shadow or not.

    Closing with a kernel wider than any line erases the drawing and leaves the
    light falling on the paper; dividing by it takes that light away.
    """
    side = max(15, (min(gray.shape) // 20) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (side, side))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    return cv2.divide(gray, background, scale=255)


def reduce_noise(gray: np.ndarray) -> np.ndarray:
    """The camera's grain, smoothed without blurring the lines."""
    return cv2.fastNlMeansDenoising(
        gray, None, h=20, templateWindowSize=7, searchWindowSize=21
    )


def boost_contrast(gray: np.ndarray) -> np.ndarray:
    """Faint pencil made darker: stretch to the full range, then local contrast."""
    low, high = np.percentile(gray, (1, 99))
    if high > low:
        stretched = np.clip(
            (gray.astype(np.float32) - low) * 255 / (high - low), 0, 255
        )
        gray = stretched.astype(np.uint8)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def binarize(gray: np.ndarray) -> np.ndarray:
    """Black ink on white paper, nothing in between.

    The local threshold keeps thin lines; the global one keeps the inside of a
    thick, filled wall black, which a local threshold alone would hollow out.
    """
    local = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    _, overall = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.bitwise_and(local, overall)


def clean_photo(gray: np.ndarray) -> CleanPhoto:
    """Every step, in order. Without a sheet border, it goes on unstraightened."""
    corners = find_sheet(gray)
    straightened = corners is not None
    if straightened:
        gray = straighten(gray, corners)
    gray = crop_to_drawing(gray)
    gray = scale_to_standard(gray)
    gray = even_lighting(gray)
    gray = reduce_noise(gray)
    gray = boost_contrast(gray)
    return CleanPhoto(image=binarize(gray), straightened=straightened)
