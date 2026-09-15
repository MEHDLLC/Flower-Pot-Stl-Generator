#!/usr/bin/env python3
"""Render the documentation images (styles and textures grids).

    python tools/render_previews.py [outdir]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flowerpot import PotParams, STYLES, build_pot          # noqa: E402
from flowerpot.colors import hex_to_rgb01                   # noqa: E402
from flowerpot.params import TEXTURES                       # noqa: E402
from flowerpot.preview import render_to_axes                # noqa: E402

FAST = dict(segments=120, vertical_step=2.5)


def grid(cases: list[tuple[str, PotParams]], path: Path) -> None:
    fig = plt.figure(figsize=(4 * len(cases), 4.6), dpi=110)
    for i, (label, params) in enumerate(cases):
        mesh = build_pot(params)
        ax = fig.add_subplot(1, len(cases), i + 1, projection="3d")
        render_to_axes(ax, mesh, hex_to_rgb01(params.color))
        ax.set_title(label, fontsize=13, pad=-2)
        print(f"rendered {label}")
    fig.subplots_adjust(left=0.01, right=0.99, top=1.0, bottom=0.0, wspace=0.02)
    fig.savefig(path, facecolor="white")
    print(f"-> {path}")


def mesh_grid(cases, path: Path, elev: float = 22.0, azim: float = -58.0) -> None:
    """Like grid(), but for prebuilt meshes."""
    fig = plt.figure(figsize=(4 * len(cases), 4.6), dpi=110)
    for i, (label, mesh, color) in enumerate(cases):
        ax = fig.add_subplot(1, len(cases), i + 1, projection="3d")
        render_to_axes(ax, mesh, hex_to_rgb01(color), elev=elev, azim=azim)
        ax.set_title(label, fontsize=13, pad=-2)
        print(f"rendered {label}")
    fig.subplots_adjust(left=0.01, right=0.99, top=1.0, bottom=0.0, wspace=0.02)
    fig.savefig(path, facecolor="white")
    print(f"-> {path}")


def selfwatering_figure(out: Path) -> None:
    from flowerpot.selfwatering import (build_self_watering_inner,
                                        build_self_watering_outer)
    p = PotParams(self_watering=True, **FAST)
    outer = build_self_watering_outer(p)
    inner = build_self_watering_inner(p)
    cases = [("outer: reservoir + refill tube", outer, "teal"),
             ("inner: wick-cup liner", inner, "teal")]
    try:                    # the cutaway needs shapely+rtree; skip if absent
        import trimesh
        half = trimesh.intersections.slice_mesh_plane(
            inner, plane_normal=[0, -1, 0], plane_origin=[0, 0, 0], cap=True)
        cases.append(("inner, cut open", half, "sand"))
    except BaseException as exc:
        print(f"skipping cutaway ({exc})")
    mesh_grid(cases, out / "selfwatering.png")


def insert_figure(out: Path) -> None:
    from flowerpot.insert import build_insert_platform, build_insert_tube
    cases = []
    for shape in ("round", "square", "hexagonal"):
        p = PotParams(reservoir_insert=True, insert_shape=shape, **FAST)
        cases.append((f"platform ({shape})", build_insert_platform(p), "charcoal"))
    cases.append(("fill tube",
                  build_insert_tube(PotParams(reservoir_insert=True, **FAST)),
                  "charcoal"))
    mesh_grid(cases, out / "insert.png")


def hydro_figure(out: Path) -> None:
    import trimesh
    from flowerpot.hydro import (_SPIGOT_H, build_hydro_cap, build_hydro_cup,
                                 build_hydro_segment)
    p = PotParams(hydro_tower=True, **FAST)
    seg = build_hydro_segment(p)
    upper = seg.copy()
    upper.apply_translation((0, 0, p.segment_height - _SPIGOT_H))
    mesh_grid([
        ("segment", seg, "sage"),
        ("two stacked", trimesh.util.concatenate([seg, upper]), "sage"),
        ("net cup", build_hydro_cup(p), "sand"),
        ("cap", build_hydro_cap(p), "sage"),
    ], out / "hydro.png")


def jar_figure(out: Path) -> None:
    import trimesh
    from flowerpot.jar import build_jar_ring
    p = PotParams(jar_greenhouse=True, **FAST)
    pot = build_pot(p)
    half = trimesh.intersections.slice_mesh_plane(
        pot, plane_normal=[0, -1, 0], plane_origin=[0, 0, 0], cap=True)
    ring = build_jar_ring(PotParams(jar_greenhouse=True,
                                    reservoir_insert=True, **FAST))
    mesh_grid([
        ("classic pot + jar seat", pot, "terracotta"),
        ("cut open: neck, groove, shaft", half, "sand"),
        ("jar collar (for the insert)", ring, "charcoal"),
    ], out / "jar.png")


def modular_figure(out: Path) -> None:
    import math
    import trimesh
    from flowerpot.modular import (_BOSS_OUT, _HUB_R, _HUB_WALL, _hub_height,
                                   build_flower_center, build_flower_petal,
                                   build_seed_tray, build_stack_hub,
                                   build_stack_pod)
    p = PotParams(modular_kit="seed_cubes", **FAST)

    tray = build_seed_tray(p, 2)
    cube = build_seed_tray(p, 1)
    W1, W2 = p.cube_size + 2.4, 2 * p.cube_size + 2.4
    c = cube.copy()
    c.apply_translation((W2 / 2 + _BOSS_OUT + W1 / 2, p.cube_size / 2, 0))
    seed = trimesh.util.concatenate([tray, c])

    parts = [build_flower_center(p)]
    petal = build_flower_petal(p)
    for k in range(5):
        q = petal.copy()
        q.apply_transform(trimesh.transformations.rotation_matrix(
            2 * math.pi * k / 5, [0, 0, 1]))
        parts.append(q)
    flower = trimesh.util.concatenate(parts)

    hub = build_stack_hub(p)
    pod = build_stack_pod(p)
    zu = _hub_height(p) + _HUB_WALL + 0.2
    pieces = [hub]
    upper = hub.copy()
    upper.apply_transform(trimesh.transformations.rotation_matrix(
        math.radians(45), [0, 0, 1]))
    upper.apply_translation((0, 0, zu))
    pieces.append(upper)
    for level, angles in ((0.0, (0, 90, 180, 270)), (zu, (45, 135))):
        for a in angles:
            q = pod.copy()
            q.apply_transform(trimesh.transformations.rotation_matrix(
                math.pi, [0, 0, 1]))
            q.apply_translation((_HUB_R + _BOSS_OUT + p.stack_pod_diameter / 2,
                                 0, 0))
            q.apply_transform(trimesh.transformations.rotation_matrix(
                math.radians(a), [0, 0, 1]))
            q.apply_translation((0, 0, level))
            pieces.append(q)
    stack = trimesh.util.concatenate(pieces)

    mesh_grid([
        ("seed tray 2x2 + docked single", seed, "terracotta"),
        ("flower: centre + 5 petals", flower, "blush"),
        ("rotating stack, level 2 at 45\u00b0", stack, "sage"),
    ], out / "modular.png")


def drainage_figure(out: Path) -> None:
    """Underside views: this is where the drainage options actually live."""
    cases = []
    for pattern in ("center", "ring", "grid", "none"):
        p = PotParams(drainage_pattern=pattern, num_drainage_holes=5, **FAST)
        cases.append((f"drainage: {pattern}", build_pot(p), "clay"))
    mesh_grid(cases, out / "drainage.png", elev=-38, azim=-58)


def extras_figure(out: Path) -> None:
    from flowerpot import build_saucer
    with_rim = PotParams(**FAST)
    no_rim = PotParams(add_top_rim=False, **FAST)
    saucer_p = PotParams(generate_saucer=True, **FAST)
    mesh_grid([
        ("rim (default)", build_pot(with_rim), "terracotta"),
        ("no rim", build_pot(no_rim), "terracotta"),
        ("drip saucer", build_saucer(saucer_p), "terracotta"),
    ], out / "extras.png")


def colors_figure(out: Path) -> None:
    from flowerpot.colors import PALETTE
    p = PotParams(height=70, top_diameter=80, bottom_diameter=60,
                  drainage_hole_radius=3.0, rim_width=4.0, rim_height=6.0,
                  segments=80, vertical_step=3.0)
    mesh = build_pot(p)
    names = sorted(PALETTE)
    fig = plt.figure(figsize=(2.1 * 6, 2.4 * 2), dpi=110)
    for i, name in enumerate(names):
        ax = fig.add_subplot(2, 6, i + 1, projection="3d")
        render_to_axes(ax, mesh, hex_to_rgb01(name))
        ax.set_title(name, fontsize=10, pad=-4)
        print(f"rendered color {name}")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.0,
                        wspace=0.02, hspace=0.05)
    fig.savefig(out / "colors.png", facecolor="white")
    print(f"-> {out / 'colors.png'}")


def nursery_figure(out: Path) -> None:
    import trimesh
    thin = dict(wall_thickness=1.4, base_thickness=2.0, rim_width=2.5,
                rim_height=5.0, num_side_holes=6, segments=110,
                vertical_step=2.5)
    cases = []
    for style, label in (("classic_tapered", "nursery round"),
                         ("square", "nursery square"),
                         ("hexagonal", "nursery hexagon")):
        p = PotParams(pot_style=style, **thin)
        cases.append((f"{label} (1.4 mm wall)", build_pot(p), "charcoal"))
    # the same design at three scales, walls identical
    family = []
    for i, sc in enumerate((1.0, 0.7, 0.45)):
        p = PotParams(pot_style="classic_tapered", **thin)
        q = build_pot(PotParams(**{**p.to_dict(),
                                   "height": 145 * sc, "top_diameter": 150 * sc,
                                   "bottom_diameter": 105 * sc,
                                   "rim_width": 2.5 * sc, "rim_height": 5 * sc,
                                   "drainage_hole_radius": 6 * sc}))
        q.apply_translation((sum(150 * s_ * 0.55 for s_ in (1.0, 0.7, 0.45)[:i]), 0, 0))
        family.append(q)
    cases.append(("scale 1.0 / 0.7 / 0.45 - same walls",
                  trimesh.util.concatenate(family), "charcoal"))
    mesh_grid(cases, out / "nursery.png")


def vase_figure(out: Path) -> None:
    base = dict(drainage_pattern="none", add_top_rim=False, **FAST)
    cases = [
        ("bud vase + stem", PotParams(vase_profile="bud", stem=True,
                                      height=180, top_diameter=120, **base), "sage"),
        ("classic amphora", PotParams(vase_profile="classic", height=220,
                                      top_diameter=110, **base), "clay"),
        ("bottle, honeycomb", PotParams(vase_profile="bottle",
                                        surface_texture="honeycomb", height=240,
                                        top_diameter=110, **base), "teal"),
        ("gourd", PotParams(vase_profile="gourd", height=220,
                            top_diameter=110, **base), "blush"),
        ("wave, hexagonal", PotParams(vase_profile="wave", pot_style="hexagonal",
                                      height=200, top_diameter=110, **base), "mustard"),
    ]
    mesh_grid([(label, build_pot(p), c) for label, p, c in cases],
              out / "vases.png")


def planted_figure(out: Path) -> None:
    import math
    import trimesh
    from flowerpot.profile import build_profiles
    from flowerpot.stem import (_SOCKET_H, _STUB_H, _THREAD_CLEAR,
                                build_soil_cap, build_stem_piece)
    p = PotParams(pot_style="classic_tapered", drainage_pattern="ring",
                  stem=True, stem_mount="screw", soil_cap=True,
                  stem_length=90.0, **FAST)
    prof = build_profiles(p)
    vessel = build_pot(p)
    piece = build_stem_piece(p, prof.floor_top_z)
    cap = build_soil_cap(p)

    # assembled: stem screwed home, soil cap resting just below the rim
    dz = prof.floor_top_z + _SOCKET_H - ((_STUB_H - 1.0) + _THREAD_CLEAR * 1.15)
    stem_in = piece.copy()
    stem_in.apply_translation((0, 0, dz))
    cap_in = cap.copy()
    cap_in.apply_translation((0, 0, p.height - 8.0 - cap.extents[2]))
    assembled = trimesh.util.concatenate([vessel, stem_in, cap_in])

    mesh_grid([("pot with threaded socket", vessel, "terracotta"),
               ("screw-in stem (water holes)", piece, "sage"),
               ("raked-soil cap", cap, "clay"),
               ("assembled: the planted look", assembled, "terracotta")],
              out / "planted.png")


def leaves_figure(out: Path) -> None:
    import math
    import trimesh
    from flowerpot.profile import build_profiles
    from flowerpot.stem import (_centerline, _leaf_sites, _main_leaf_piece,
                                _taper, build_leaf_inserts, build_stem_piece,
                                leaf_pose, _SOCKET_H, _STEM_R_BASE,
                                _STEM_R_TIP, _STUB_H, _THREAD_CLEAR)
    p = PotParams(vase_profile="classic", stem=True, stem_mount="screw",
                  leaf_mount="insert", leaf_angle=40.0, stem_length=110.0,
                  drainage_pattern="none", add_top_rim=False, **FAST)
    prof = build_profiles(p)
    piece = build_stem_piece(p, prof.floor_top_z)
    plate = build_leaf_inserts(p)

    z_seat = (_STUB_H - 1.0) + _THREAD_CLEAR * 1.15
    z_rim = z_seat + (p.height - (prof.floor_top_z + _SOCKET_H))
    top = z_rim + p.stem_length
    z_f2 = (_STUB_H - 1.0) + (15.0 - 10.0) * 1.15 + 1.5
    r_fn = _taper(_STEM_R_BASE, z_f2, _STEM_R_TIP, top)
    cl = _centerline(p, z_rim, top)
    posed = [piece]
    for z_att, length, azim, tilt in _leaf_sites(p, z_rim, top):
        leaf = _main_leaf_piece(p, z_att, length, azim, tilt, r_fn, cl)
        cx, cy = cl(z_att)
        leaf.apply_transform(leaf_pose(r_fn(z_att), azim, cx, cy, z_att))
        posed.append(leaf)

    mesh_grid([("stem with leaf slots", piece, "clay"),
               ("push-in leaf plate", plate, "sage"),
               ("leaves clicked in", trimesh.util.concatenate(posed), "sage")],
              out / "leaves.png")


def split_figure(out: Path) -> None:
    import trimesh
    from flowerpot.profile import build_profiles
    from flowerpot.stem import (build_stem_piece, stem_section_bounds,
                                _NODE_ENGAGE)
    p = PotParams(vase_profile="bud", stem=True, stem_mount="screw",
                  height=220, top_diameter=110, stem_length=130,
                  drainage_pattern="none", add_top_rim=False,
                  printer="creality-k1-max", **FAST)
    floor_z = build_profiles(p).floor_top_z
    bounds = stem_section_bounds(p, floor_z)
    lower = build_stem_piece(p, floor_z, 0)
    upper = build_stem_piece(p, floor_z, 1)
    posed = upper.copy()
    posed.apply_translation((0.0, 0.0, bounds[1][0] - _NODE_ENGAGE))
    mesh_grid([(f"part 1 ({lower.extents[2]:.0f} mm)", lower, "sage"),
               (f"part 2 ({upper.extents[2]:.0f} mm)", upper, "sage"),
               ("screwed together at the node", 
                trimesh.util.concatenate([lower, posed]), "sage")],
              out / "stem_split.png")


def bouquet_figure(out: Path) -> None:
    import trimesh
    cases = []
    for flower, color in (("tulip", "blush"), ("rose", "clay")):
        p = PotParams(bouquet=True, bouquet_flower=flower, height=190,
                      top_diameter=115, drainage_pattern="ring",
                      add_top_rim=False, **FAST)
        cases.append((f"{flower} bouquet planter", build_pot(p), color))
    p = PotParams(bouquet=True, bouquet_count=3, height=190, top_diameter=115,
                  drainage_pattern="ring", add_top_rim=False, **FAST)
    pot = build_pot(p)
    half = trimesh.intersections.slice_mesh_plane(
        pot, plane_normal=[0, -1, 0], plane_origin=[0, 0, 0], cap=True)
    cases.append(("cut open: one hollow, blooms drain in", half, "sand"))
    mesh_grid(cases, out / "bouquet.png")


def hitch_figure(out: Path) -> None:
    import trimesh
    from flowerpot.hitch import (build_hitch_cap, build_hitch_collar,
                                 build_hitch_cover, solve, thread_core)
    cases = []
    p = PotParams(hitch_mount="cover", hitch_ball="2", **FAST)
    cover = build_hitch_cover(p)
    cases.append(('snap-on cover, 2" ball', cover, "teal"))

    # cut away, with the ball it grips shown seated in it
    k = solve(p)
    ball = trimesh.creation.icosphere(subdivisions=4, radius=k["r_ball"])
    ball.apply_translation((0.0, 0.0, k["z_ball"]))
    shank = trimesh.creation.cylinder(radius=0.44 * k["r_ball"], height=40.0,
                                      sections=48)
    shank.apply_translation((0.0, 0.0, k["z_ball"] - k["r_ball"] - 18.0))
    both = trimesh.util.concatenate([cover, ball, shank])
    half = trimesh.intersections.slice_mesh_plane(
        both, plane_normal=[0, -1, 0], plane_origin=[0, 0, 0], cap=True)
    cases.append(("cut open: the mouth grips under the equator", half, "sand"))

    q = PotParams(hitch_mount="screw", hitch_ball="2", **FAST)
    cap = build_hitch_cap(q)
    cap.apply_translation((0.0, 0.0, thread_core(q)[1] + 18.0))
    cases.append(("collar + screw-on cap",
                  trimesh.util.concatenate([build_hitch_collar(q), cap]),
                  "teal"))
    mesh_grid(cases, out / "hitch.png", elev=18.0, azim=-52.0)


def yard_figure(out: Path) -> None:
    import trimesh
    from flowerpot.yard import (build_yard_body, build_yard_face,
                                build_yard_head, head_pose, plan)

    def assembled(p):
        body = build_yard_body(p)
        if p.yard_plant == "cactus":
            return body
        head = build_yard_head(p)
        face = build_yard_face(p)
        face.apply_translation((0.0, 0.0, 0.45 * plan(p)["thick"]))
        head = trimesh.util.concatenate([head, face])
        head.apply_transform(head_pose(p))
        return trimesh.util.concatenate([body, head])

    cases = []
    for kind, face, hands, color in (
            ("sunflower", "angry", ("bird", "bird"), "mustard"),
            ("daisy", "grin", ("wave", "thumbs"), "blush"),
            ("cactus", "smug", ("bird", "shrug"), "olive")):
        p = PotParams(yard_plant=kind, yard_face=face, hitch_mount="fused",
                      yard_left_hand=hands[0], yard_right_hand=hands[1], **FAST)
        cases.append((f"{kind}, {face}", assembled(p), color))
    mesh_grid(cases, out / "yard.png", elev=10.0, azim=-90.0)


def yard_parts_figure(out: Path) -> None:
    from flowerpot.yard import (build_yard_body, build_yard_face,
                                build_yard_head)
    p = PotParams(yard_plant="sunflower", hitch_mount="fused", **FAST)
    mesh_grid([("body: standing", build_yard_body(p), "sage"),
               ("head: flat, face up", build_yard_head(p), "mustard"),
               ("face: flat, face up", build_yard_face(p), "clay")],
              out / "yard-parts.png", elev=34.0, azim=-90.0)


def yard_hands_figure(out: Path) -> None:
    import trimesh
    from flowerpot.stem import _tube
    from flowerpot.yard import GESTURES, _hand, arm_path, plan
    p = PotParams(yard_plant="sunflower", hitch_mount="none", **FAST)
    lay = plan(p)
    cases = []
    for g in (g for g in GESTURES if g != "none"):
        scale = 0.62 if g == "shrug" else 1.0
        path, radii, rw = arm_path(p, lay, 1, scale)
        arm = trimesh.util.concatenate(
            [_tube(path, radii, nt=44)] + _hand(p, path, rw, g, 1))
        arm = arm.slice_plane(plane_origin=[0, 0, path[-1][2] - 7.0 * rw],
                              plane_normal=[0, 0, 1], cap=True)
        arm.apply_translation(-arm.bounds.mean(axis=0))
        cases.append((g, arm, "sage"))
    mesh_grid(cases, out / "yard-hands.png", elev=16.0, azim=-90.0)


def replica_figure(out: Path) -> None:
    import trimesh
    from flowerpot.replica import (build_replica_pot, build_replica_reservoir,
                                   build_replica_wick, reservoir_plan,
                                   seated_pot)
    p = PotParams(replica="set", **FAST)
    k = reservoir_plan(p)
    cup = build_replica_wick(p)
    cup.apply_translation((0.0, 0.0, k["floor"]))
    whole = trimesh.util.concatenate(
        [build_replica_reservoir(p), seated_pot(p), cup])
    half = trimesh.intersections.slice_mesh_plane(
        whole, plane_normal=[0, 1, 0], plane_origin=[0, 0, 0], cap=True)
    mesh_grid([("the pot", build_replica_pot(p), "clay"),
               ("the reservoir", build_replica_reservoir(p), "white"),
               ("the wick cup", build_replica_wick(p), "sage")],
              out / "replica.png", elev=16.0, azim=-60.0)
    mesh_grid([("cut open: the pot on its ribs, the wick in the water",
                half, "sand")],
              out / "replica-cut.png", elev=5.0, azim=-90.0)


def cradle_figure(out: Path) -> None:
    import trimesh
    from flowerpot.cradle import (BOWLS, build_cradle_dish, build_cradle_pot,
                                  seated_pot)
    p = PotParams(cradle="set", **FAST)
    whole = trimesh.util.concatenate([seated_pot(p), build_cradle_dish(p)])
    half = trimesh.intersections.slice_mesh_plane(
        whole, plane_normal=[0, 1, 0], plane_origin=[0, 0, 0], cap=True)
    mesh_grid([("assembled", whole, "clay"),
               ("the pot, on its keel", build_cradle_pot(p), "clay"),
               ("the dish", build_cradle_dish(p), "sage")],
              out / "cradle.png", elev=14.0, azim=-62.0)
    mesh_grid([("cut open: the keel in the water, the notch at the seam",
                half, "sand")],
              out / "cradle-cut.png", elev=4.0, azim=-90.0)
    from flowerpot.cradle import water_millilitres
    bowls = []
    for b in BOWLS:
        q = PotParams(cradle="set", cradle_bowl=b, **FAST)
        bowls.append((f"{b}: {water_millilitres(q):.0f} ml",
                      build_cradle_dish(q), "teal"))
    mesh_grid(bowls, out / "cradle-bowls.png", elev=16.0, azim=-62.0)


def mosspole_figure(out: Path) -> None:
    from flowerpot.mosspole import (build_pole_base, build_pole_cap,
                                    build_pole_segment, stacked)
    p = PotParams(moss_pole="set", **FAST)
    mesh_grid([("three segments, base and cap", stacked(p), "sage"),
               ("one segment", build_pole_segment(p), "sage"),
               ("the base", build_pole_base(p), "clay"),
               ("the cap", build_pole_cap(p), "clay")],
              out / "mosspole.png", elev=14.0, azim=-58.0)
    cases = []
    for shape, pattern in (("square", "lattice"), ("hex", "slots"),
                           ("round", "lattice")):
        q = PotParams(moss_pole="segment", pole_shape=shape,
                      pole_pattern=pattern, **FAST)
        cases.append((f"{shape} / {pattern}", build_pole_segment(q), "teal"))
    mesh_grid(cases, out / "mosspole-walls.png", elev=10.0, azim=-55.0)
    import trimesh
    w = PotParams(moss_pole="set", pole_reservoir=40.0, pole_wick=True, **FAST)
    cut = lambda m: trimesh.intersections.slice_mesh_plane(
        m, plane_normal=[0, 1, 0], plane_origin=[0, 0, 0], cap=True)
    mesh_grid([("the sump, cut open: post, overflow, pierced flange",
                cut(build_pole_base(w)), "sand"),
               ("a segment, cut open: barbs at the crossings",
                cut(build_pole_segment(w)), "sand"),
               ("the cap, with the eyes the string ties off to",
                build_pole_cap(w), "clay")],
              out / "mosspole-wick.png", elev=8.0, azim=-90.0)


def underpot_figure(out: Path) -> None:
    from flowerpot.underpot import (build_under_mesh, build_under_riser,
                                    build_under_tray)
    p = PotParams(underpot="set", **FAST)
    mesh_grid([("tray: the pot stands on the ribs", build_under_tray(p), "teal"),
               ("riser: print three", build_under_riser(p), "clay"),
               ("mesh disc: prints legs up", build_under_mesh(p), "sage")],
              out / "underpot.png", elev=26.0, azim=-58.0)


def sleeve_figure(out: Path) -> None:
    import trimesh
    from flowerpot.sleeve import build_sleeve
    cases = []
    for kw, col in ((dict(), "clay"), (dict(pot_style="hexagonal"), "sage"),
                    (dict(surface_texture="honeycomb"), "teal")):
        q = PotParams(sleeve=True, **FAST, **kw)
        label = "plain" if not kw else " ".join(str(v) for v in kw.values())
        cases.append((label, build_sleeve(q), col))
    mesh_grid(cases, out / "sleeve.png", elev=16.0, azim=-58.0)
    half = trimesh.intersections.slice_mesh_plane(
        build_sleeve(PotParams(sleeve=True, **FAST)),
        plane_normal=[0, 1, 0], plane_origin=[0, 0, 0], cap=True)
    mesh_grid([("cut open: the step the pot lands on, and the well under it",
                half, "sand")],
              out / "sleeve-cut.png", elev=6.0, azim=-90.0)


def hanger_figure(out: Path) -> None:
    import trimesh
    from flowerpot.build import lathe
    from flowerpot.hanger import (_round, assembled, build_hanger_arm,
                                  build_hanger_base, build_hanger_top, plan)
    p = PotParams(hanger="set", **FAST)
    k = plan(p)
    pot = lathe([(k["pot"]["base_r"], 0.0),
                 (k["pot"]["top_r"], k["pot"]["height"])], _round(p), False)
    pot.apply_translation((0.0, 0.0, k["t_base"]))
    mesh_grid([("hanging, with the pot in it",
                trimesh.util.concatenate([assembled(p), pot]), "sage")],
              out / "hanger.png", elev=8.0, azim=-62.0)
    mesh_grid([("base: the pot stands on it", build_hanger_base(p), "clay"),
               ("arm: print three, flat", build_hanger_arm(p), "clay"),
               ("top ring", build_hanger_top(p), "clay")],
              out / "hanger-parts.png", elev=42.0, azim=-60.0)


def main(outdir: str = "docs/img") -> None:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    grid([(s, PotParams(pot_style=s, **FAST)) for s in STYLES], out / "styles.png")
    grid(
        [(t, PotParams(surface_texture=t, **FAST))
         for t in TEXTURES if t != "none"],
        out / "textures.png",
    )
    selfwatering_figure(out)
    insert_figure(out)
    hydro_figure(out)
    jar_figure(out)
    modular_figure(out)
    drainage_figure(out)
    extras_figure(out)
    colors_figure(out)
    nursery_figure(out)
    vase_figure(out)
    planted_figure(out)
    leaves_figure(out)
    split_figure(out)
    bouquet_figure(out)
    hitch_figure(out)
    yard_figure(out)
    yard_parts_figure(out)
    yard_hands_figure(out)
    replica_figure(out)
    cradle_figure(out)
    mosspole_figure(out)
    underpot_figure(out)
    sleeve_figure(out)
    hanger_figure(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
