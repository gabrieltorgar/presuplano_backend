"""RED tests for iteracion-5 — lo que la IA trazó, ordenado antes de llegar al editor.

Un boceto nunca es exacto: la esquina está, pero sus dos muros paran a unos
píxeles; un tabique se queda corto del muro al que llega, y una habitación con
puerta queda abierta justo donde está la puerta. Aquí se une lo que debe tocarse
y se cierra cada habitación sobre sus puertas, sin rellenar el hueco del muro.

La foto mide 1000 × 1000 px y la escala provisional es 1 px = 1 cm, así que
15 cm son 15 px y 1,20 m son 120 px.
"""

import math

from apps.planner import photo_conversion

SIDE = 1000


def wall(x1: float, y1: float, x2: float, y2: float) -> dict:
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def room(name: str, *points: tuple[float, float]) -> dict:
    return {"name": name, "points": [{"x": x, "y": y} for x, y in points]}


def reading(walls: list[dict], rooms: list[dict] | None = None) -> dict:
    return {
        "is_floor_plan": True,
        "image_width": SIDE,
        "image_height": SIDE,
        "walls": walls,
        "rooms": rooms or [],
    }


def px(point: dict) -> tuple[float, float]:
    """Un punto relativo de vuelta en píxeles, para leer los tests en cm."""
    return (round(point["x"] * SIDE, 1), round(point["y"] * SIDE, 1))


def area_px(points: list[dict]) -> float:
    pairs = zip(points, points[1:] + points[:1], strict=True)
    total = sum(a["x"] * b["y"] - b["x"] * a["y"] for a, b in pairs)
    return round(abs(total) / 2 * SIDE * SIDE)


# Dos cuartos de 4 × 4 m lado a lado: el contorno y un tabique al centro.
OUTLINE = [
    wall(0, 0, 800, 0),
    wall(800, 0, 800, 400),
    wall(800, 400, 0, 400),
    wall(0, 400, 0, 0),
]


class TestRoomsCloseOverDoors:
    """Bug iteracion-5 - La habitación cierra sobre la puerta."""

    def test_a_door_in_the_partition_still_gives_two_rooms(self) -> None:
        # El tabique tiene el hueco de una puerta de 1 m entre y=150 y y=250.
        door = [wall(400, 0, 400, 150), wall(400, 250, 400, 400)]

        result = photo_conversion.to_plan(reading(OUTLINE + door))

        rooms = result["rooms"]
        assert len(rooms) == 2
        assert [area_px(r["points"]) for r in rooms] == [160_000, 160_000]

    def test_the_doorway_stays_open_in_the_walls(self) -> None:
        """Bug iteracion-5 - El hueco de una puerta no se rellena."""
        door = [wall(400, 0, 400, 150), wall(400, 250, 400, 400)]

        result = photo_conversion.to_plan(reading(OUTLINE + door))

        walls = [(px(w["start"]), px(w["end"])) for w in result["walls"]]
        assert len(walls) == 6
        assert ((400.0, 0.0), (400.0, 150.0)) in walls
        assert ((400.0, 250.0), (400.0, 400.0)) in walls

    def test_a_partition_that_stops_short_leaves_a_passage_and_closes(self) -> None:
        # El tabique para a 90 cm del muro de abajo: un paso sin puerta.
        partition = [wall(400, 0, 400, 310)]

        result = photo_conversion.to_plan(reading(OUTLINE + partition))

        assert [area_px(r["points"]) for r in result["rooms"]] == [160_000, 160_000]
        assert ((400.0, 0.0), (400.0, 310.0)) in [
            (px(w["start"]), px(w["end"])) for w in result["walls"]
        ]

    def test_a_gap_wider_than_a_door_is_not_closed(self) -> None:
        # 2 m de hueco ya no es una puerta: es un solo espacio.
        partition = [wall(400, 0, 400, 100), wall(400, 300, 400, 400)]

        result = photo_conversion.to_plan(reading(OUTLINE + partition))

        assert [area_px(r["points"]) for r in result["rooms"]] == [320_000]

    def test_the_name_read_inside_a_room_stays_with_it(self) -> None:
        door = [wall(400, 0, 400, 150), wall(400, 250, 400, 400)]
        # La IA dio el cuarto de la izquierda abierto y torcido, pero con nombre.
        sala = room("Sala", (10, 10), (390, 15), (380, 390), (5, 380))

        result = photo_conversion.to_plan(reading(OUTLINE + door, [sala]))

        names = {r["name"] for r in result["rooms"]}
        assert names == {"Sala", None}
        sala_room = next(r for r in result["rooms"] if r["name"] == "Sala")
        assert max(px(p)[0] for p in sala_room["points"]) == 400.0

    def test_a_room_the_walls_do_not_close_is_kept_as_read(self) -> None:
        walls = [wall(0, 0, 400, 0), wall(400, 0, 400, 400)]
        cocina = room("Cocina", (0, 0), (400, 0), (400, 400), (0, 400))

        result = photo_conversion.to_plan(reading(walls, [cocina]))

        assert [r["name"] for r in result["rooms"]] == ["Cocina"]
        assert area_px(result["rooms"][0]["points"]) == 160_000

    def test_a_tiny_closed_box_is_not_a_room(self) -> None:
        # 50 × 50 cm: un ducto o un pilar, no un cuarto.
        box = [
            wall(100, 100, 150, 100),
            wall(150, 100, 150, 150),
            wall(150, 150, 100, 150),
            wall(100, 150, 100, 100),
        ]

        result = photo_conversion.to_plan(reading(box))

        assert result["rooms"] == []
        assert len(result["walls"]) == 4


class TestCornersTouch:
    """Bug iteracion-5 - Las esquinas se tocan."""

    def test_two_ends_a_few_centimetres_apart_become_one_corner(self) -> None:
        walls = [wall(100, 100, 500, 100), wall(508, 106, 508, 400)]

        result = photo_conversion.to_plan(reading(walls))

        top, side = result["walls"]
        assert top["end"] == side["start"]
        # La esquina queda donde se cruzan los dos muros: siguen rectos.
        assert px(top["end"]) == (508.0, 100.0)

    def test_a_partition_that_stops_short_reaches_the_wall(self) -> None:
        walls = [wall(0, 400, 800, 400), wall(300, 100, 300, 390)]

        result = photo_conversion.to_plan(reading(walls))

        assert px(result["walls"][1]["end"]) == (300.0, 400.0)

    def test_a_partition_that_overshoots_is_trimmed_to_the_wall(self) -> None:
        walls = [wall(0, 400, 800, 400), wall(300, 100, 300, 410)]

        result = photo_conversion.to_plan(reading(walls))

        assert px(result["walls"][1]["end"]) == (300.0, 400.0)

    def test_ends_farther_apart_are_left_alone(self) -> None:
        walls = [wall(100, 100, 500, 100), wall(540, 100, 540, 400)]

        result = photo_conversion.to_plan(reading(walls))

        assert px(result["walls"][0]["end"]) == (500.0, 100.0)
        assert px(result["walls"][1]["start"]) == (540.0, 100.0)

    def test_a_better_scale_changes_what_is_close(self) -> None:
        # Si 1 px son 5 cm, 10 px son 50 cm: ya no es la misma esquina.
        walls = [wall(100, 100, 500, 100), wall(508, 106, 508, 400)]

        result = photo_conversion.to_plan(reading(walls), metres_per_pixel=0.05)

        assert result["walls"][0]["end"] != result["walls"][1]["start"]


def angle(w: dict) -> float:
    """El ángulo del muro en grados, de 0 a 180, en píxeles de la foto."""
    (x1, y1), (x2, y2) = px(w["start"]), px(w["end"])
    return round(math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180, 3)


class TestSquareWalls:
    """Bug iteracion-5 - Muros a escuadra."""

    def test_an_almost_level_wall_comes_out_level(self) -> None:
        # 5° de la horizontal: la hoja estaba pandeada.
        result = photo_conversion.to_plan(reading([wall(100, 100, 500, 135)]))

        assert angle(result["walls"][0]) == 0.0

    def test_an_almost_upright_wall_comes_out_upright(self) -> None:
        result = photo_conversion.to_plan(reading([wall(300, 100, 330, 500)]))

        assert angle(result["walls"][0]) == 90.0

    def test_an_almost_diagonal_wall_comes_out_at_45(self) -> None:
        result = photo_conversion.to_plan(reading([wall(100, 100, 400, 450)]))

        assert angle(result["walls"][0]) == 45.0

    def test_a_wall_slanted_on_purpose_keeps_its_angle(self) -> None:
        # 20° no es un descuido del dibujo: se respeta.
        result = photo_conversion.to_plan(reading([wall(100, 100, 476, 237)]))

        assert 19 < angle(result["walls"][0]) < 21

    def test_a_squared_wall_keeps_its_place(self) -> None:
        result = photo_conversion.to_plan(reading([wall(100, 100, 500, 135)]))

        start, end = (px(p) for p in result["walls"][0].values())
        # Gira sobre su centro: a la altura media de lo dibujado, y a lo ancho
        # cubre lo mismo que cubría, para seguir llegando a sus esquinas.
        assert start[1] == end[1] == 117.5
        assert (start[0], end[0]) == (100.0, 500.0)

    def test_a_rectangular_room_comes_out_rectangular(self) -> None:
        # Un cuarto de 4 × 3 m con la perspectiva leve de una foto de lado.
        skewed = [
            wall(100, 100, 503, 112),
            wall(503, 112, 497, 405),
            wall(497, 405, 104, 398),
            wall(104, 398, 100, 100),
        ]

        result = photo_conversion.to_plan(reading(skewed))

        assert [angle(w) for w in result["walls"]] == [0.0, 90.0, 0.0, 90.0]
        ends = [(px(w["start"]), px(w["end"])) for w in result["walls"]]
        # Las esquinas se siguen tocando: cada muro empieza donde acaba el anterior.
        assert all(ends[i][1] == ends[(i + 1) % 4][0] for i in range(4))
        assert len(result["rooms"]) == 1
