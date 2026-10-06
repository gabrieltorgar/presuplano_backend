"""RED tests for US-129 (iteracion-4 #3) — la foto se pule antes de la IA.

foto → corrección de perspectiva → recorte → escala → corrección de iluminación
→ reducción de ruido → contraste → binarización → IA.

Las fotos son sintéticas: una hoja blanca con un plano dibujado, fotografiada
en ángulo sobre una mesa oscura, con sombra y con ruido. Así se sabe dónde
están las esquinas de verdad y se puede medir cada paso.
"""

import cv2
import numpy as np
import pytest

from apps.planner import photo_cleanup

SHEET_W, SHEET_H = 800, 600


def flat_sheet() -> np.ndarray:
    """La hoja vista de frente: un plano de dos cuartos al centro y marcas en
    las esquinas, sobre papel blanco."""
    sheet = np.full((SHEET_H, SHEET_W), 255, np.uint8)
    cv2.rectangle(sheet, (200, 150), (600, 450), 0, 6)
    cv2.line(sheet, (400, 150), (400, 450), 0, 6)
    for x, y in [
        (20, 20),
        (SHEET_W - 50, 20),
        (20, SHEET_H - 50),
        (SHEET_W - 50, SHEET_H - 50),
    ]:
        cv2.rectangle(sheet, (x, y), (x + 30, y + 30), 0, -1)
    return sheet


# Dónde cae cada esquina de la hoja en la foto: tomada en ángulo.
PHOTO_CORNERS = np.float32([[180, 120], [1010, 170], [1060, 820], [130, 760]])


def angled_photo(sheet: np.ndarray | None = None) -> np.ndarray:
    """La hoja fotografiada en ángulo sobre una mesa oscura (1200 × 900)."""
    sheet = flat_sheet() if sheet is None else sheet
    source = np.float32([[0, 0], [SHEET_W, 0], [SHEET_W, SHEET_H], [0, SHEET_H]])
    matrix = cv2.getPerspectiveTransform(source, PHOTO_CORNERS)
    return cv2.warpPerspective(
        sheet, matrix, (1200, 900), borderMode=cv2.BORDER_CONSTANT, borderValue=50
    )


def shadowed(image: np.ndarray) -> np.ndarray:
    """Luz dispareja: la mitad izquierda queda en sombra."""
    gradient = np.linspace(0.45, 1.0, image.shape[1], dtype=np.float32)
    return (image.astype(np.float32) * gradient[np.newaxis, :]).astype(np.uint8)


def noisy(image: np.ndarray, sigma: float = 18) -> np.ndarray:
    rng = np.random.default_rng(7)
    grain = rng.normal(0, sigma, image.shape)
    return np.clip(image.astype(np.float32) + grain, 0, 255).astype(np.uint8)


class TestPerspective:
    """Corrección de perspectiva: la hoja en ángulo vuelve a ser un rectángulo."""

    def test_the_sheet_is_found_by_its_four_corners(self) -> None:
        corners = photo_cleanup.find_sheet(angled_photo())

        assert corners is not None
        for found, real in zip(corners, PHOTO_CORNERS, strict=True):
            assert np.hypot(*(found - real)) < 15

    def test_the_corners_come_in_order(self) -> None:
        """Arriba-izquierda, arriba-derecha, abajo-derecha, abajo-izquierda."""
        corners = photo_cleanup.find_sheet(angled_photo())

        top_left, top_right, bottom_right, bottom_left = corners
        assert top_left[0] < top_right[0] and top_left[1] < bottom_left[1]
        assert bottom_right[0] > bottom_left[0] and bottom_right[1] > top_right[1]

    def test_a_scan_has_no_sheet_border(self) -> None:
        """Caso alternativo - La hoja llena toda la foto: no hay borde que buscar."""
        assert photo_cleanup.find_sheet(flat_sheet()) is None

    def test_a_blank_table_has_no_sheet(self) -> None:
        assert photo_cleanup.find_sheet(np.full((600, 800), 50, np.uint8)) is None

    def test_straightening_puts_the_sheet_corners_at_the_image_corners(self) -> None:
        photo = angled_photo()

        straight = photo_cleanup.straighten(photo, photo_cleanup.find_sheet(photo))

        # La proporción de la hoja vuelve (4:3) y las marcas de las esquinas de
        # la hoja quedan en las esquinas de la imagen.
        height, width = straight.shape
        assert abs(width / height - SHEET_W / SHEET_H) < 0.08
        # Cada marca (30 px a 20 px del borde de la hoja) cae en su octavo de
        # esquina: ni mesa oscura alrededor ni papel vacío.
        cw, ch = width // 8, height // 8
        for patch in (
            straight[:ch, :cw],
            straight[:ch, -cw:],
            straight[-ch:, :cw],
            straight[-ch:, -cw:],
        ):
            dark = (patch < 128).mean()
            assert 0.05 < dark < 0.3


class TestCrop:
    """Recorte: sólo el dibujo, con un margen."""

    def test_the_drawing_is_kept_with_a_margin(self) -> None:
        sheet = np.full((600, 800), 255, np.uint8)
        cv2.rectangle(sheet, (300, 200), (500, 400), 0, 4)

        cropped = photo_cleanup.crop_to_drawing(sheet)

        height, width = cropped.shape
        assert 200 < width < 260 and 200 < height < 260
        assert cropped[0, :].min() == 255  # hay margen arriba

    def test_a_blank_sheet_is_not_cropped(self) -> None:
        blank = np.full((600, 800), 255, np.uint8)

        assert photo_cleanup.crop_to_drawing(blank).shape == (600, 800)

    def test_a_shadow_is_not_mistaken_for_drawing(self) -> None:
        sheet = np.full((600, 800), 255, np.uint8)
        cv2.rectangle(sheet, (300, 200), (500, 400), 0, 4)

        cropped = photo_cleanup.crop_to_drawing(shadowed(sheet))

        assert cropped.shape[1] < 300


class TestScale:
    """Escala: un tamaño de trabajo estándar, el lado mayor a 1568 px."""

    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            ((3000, 4000), (1176, 1568)),
            ((300, 400), (1176, 1568)),
            ((900, 600), (1568, 1045)),
        ],
    )
    def test_the_longer_side_becomes_standard(self, size, expected) -> None:
        image = np.full(size, 255, np.uint8)

        assert photo_cleanup.scale_to_standard(image).shape == expected


class TestLighting:
    """Corrección de iluminación: la sombra desaparece, las líneas no."""

    def test_the_paper_comes_out_even(self) -> None:
        sheet = flat_sheet()
        paper = sheet == 255

        evened = photo_cleanup.even_lighting(shadowed(sheet))

        assert shadowed(sheet)[paper].std() > 30
        assert evened[paper].std() < 12
        assert evened[sheet == 0].mean() < 100


class TestNoise:
    def test_grain_is_reduced(self) -> None:
        sheet = flat_sheet()
        paper = sheet == 255
        grainy = noisy(sheet)

        cleaned = photo_cleanup.reduce_noise(grainy)

        assert cleaned[paper].std() < grainy[paper].std() / 2


class TestContrast:
    def test_faint_lines_stand_out_more(self) -> None:
        faint = np.full((600, 800), 200, np.uint8)
        cv2.rectangle(faint, (200, 150), (600, 450), 160, 6)
        line = faint == 160

        boosted = photo_cleanup.boost_contrast(faint)

        before = faint[~line].mean() - faint[line].mean()
        after = boosted[~line].mean() - boosted[line].mean()
        assert after > before * 1.3


class TestBinarize:
    def test_only_black_and_white_remain(self) -> None:
        binary = photo_cleanup.binarize(noisy(flat_sheet(), 8))

        assert set(np.unique(binary)) <= {0, 255}

    def test_lines_are_black_and_paper_white(self) -> None:
        sheet = flat_sheet()

        binary = photo_cleanup.binarize(sheet)

        assert binary[sheet == 0].mean() < 30
        assert binary[sheet == 255].mean() > 240


class TestCleanPhoto:
    """El camino completo, en el orden pedido."""

    def test_an_angled_shadowed_noisy_photo_comes_out_clean(self) -> None:
        photo = noisy(shadowed(angled_photo()), 10)

        result = photo_cleanup.clean_photo(photo)

        assert result.straightened is True
        assert set(np.unique(result.image)) <= {0, 255}
        assert max(result.image.shape) == photo_cleanup.STANDARD_SIDE
        # El muro de arriba del plano quedó horizontal: sus píxeles negros caen
        # en una franja angosta de filas, no en diagonal.
        top = result.image[: result.image.shape[0] // 3]
        rows = np.where((top == 0).sum(axis=1) > top.shape[1] * 0.3)[0]
        assert len(rows) > 0
        assert rows.max() - rows.min() < 40

    def test_a_scan_is_cleaned_without_straightening(self) -> None:
        result = photo_cleanup.clean_photo(noisy(flat_sheet(), 8))

        assert result.straightened is False
        assert set(np.unique(result.image)) <= {0, 255}

    def test_the_steps_run_in_the_requested_order(self, mocker) -> None:
        calls = []
        for step in (
            "find_sheet",
            "straighten",
            "crop_to_drawing",
            "scale_to_standard",
            "even_lighting",
            "reduce_noise",
            "boost_contrast",
            "binarize",
        ):
            original = getattr(photo_cleanup, step)
            mocker.patch.object(
                photo_cleanup,
                step,
                side_effect=lambda *a, _n=step, _o=original, **k: (
                    calls.append(_n) or _o(*a, **k)
                ),
            )

        photo_cleanup.clean_photo(angled_photo())

        assert calls == [
            "find_sheet",
            "straighten",
            "crop_to_drawing",
            "scale_to_standard",
            "even_lighting",
            "reduce_noise",
            "boost_contrast",
            "binarize",
        ]
