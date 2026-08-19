"""Minimal 3MF writer with material colors and slicer project settings.

STL carries no color, so for a colored pot we write 3MF - a zip package
holding one XML model.  This writer is deliberately small and dependency
free: vertices, triangles, one or two basematerials, and an optional
package thumbnail that slicers show in their file pickers.

Two-tone pots: pass ``accent_mask`` (a boolean per face) and those faces
get the accent material - the CLI uses it to color the rim.

Pass ``printer`` (a key from :mod:`flowerpot.printers`) to also embed the
OrcaSlicer / Bambu Studio / Creality Print project payload - machine,
process and filament settings plus plate assignment - which is what the
"Print Settings" upload path on Creality Cloud requires.  The geometry
stays inline in the standard ``3D/3dmodel.model``, so the file remains a
perfectly ordinary 3MF for everything else.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import trimesh

from .colors import parse_color
from .printers import (bed_center, build_model_settings,
                       build_project_settings, build_slice_info)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
</Types>
"""

_RELS_MODEL = ('<Relationship Target="/3D/3dmodel.model" Id="rel0" '
               'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>')
_RELS_THUMB = ('<Relationship Target="/Metadata/thumbnail.png" Id="rel1" '
               'Type="http://schemas.openxmlformats.org/package/2006/relationships/'
               'metadata/thumbnail"/>')


def write_3mf(
    path: str | Path,
    mesh: trimesh.Trimesh,
    *,
    name: str = "pot",
    color: str = "terracotta",
    accent_color: str | None = None,
    accent_mask: np.ndarray | None = None,
    thumbnail_png: bytes | None = None,
    printer: str | None = None,
) -> Path:
    """Write ``mesh`` to ``path`` as a colored 3MF.  Returns the path."""
    path = Path(path)
    body_hex = parse_color(color)

    materials = [f'<base name="body" displaycolor="{body_hex}FF"/>']
    use_accent = (
        accent_color is not None
        and accent_mask is not None
        and bool(np.any(accent_mask))
    )
    if use_accent:
        materials.append(
            f'<base name="accent" displaycolor="{parse_color(accent_color)}FF"/>'
        )

    # with a printer profile the object is dropped at the middle of that
    # machine's plate (project coordinates are plate-absolute); otherwise the
    # build item carries no transform and consumers place it themselves
    item_attrs = ""
    slicer_meta = ""
    transform = ""
    if printer is not None:
        cx, cy = bed_center(printer)
        transform = f"1 0 0 0 1 0 0 0 1 {cx:.3f} {cy:.3f} 0"
        item_attrs = f' transform="{transform}" printable="1"'
        slicer_meta = (
            ' <metadata name="Application">OrcaSlicer-V2.1.1</metadata>\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
            f' <metadata name="Title">{name}</metadata>\n'
            ' <metadata name="Designer"></metadata>\n'
            ' <metadata name="Description">flower pot generator</metadata>\n'
        )

    xml = io.StringIO()
    xml.write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
        f'{slicer_meta}'
        ' <resources>\n'
        f'  <basematerials id="1">{"".join(materials)}</basematerials>\n'
        f'  <object id="2" name="{name}" type="model" pid="1" pindex="0">\n'
        '   <mesh>\n    <vertices>\n'
    )
    for x, y, z in mesh.vertices:
        xml.write(f'     <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>\n')
    xml.write('    </vertices>\n    <triangles>\n')
    if use_accent:
        for (a, b, c), acc in zip(mesh.faces, accent_mask):
            extra = ' pid="1" p1="1"' if acc else ""
            xml.write(f'     <triangle v1="{a}" v2="{b}" v3="{c}"{extra}/>\n')
    else:
        for a, b, c in mesh.faces:
            xml.write(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n')
    xml.write(
        '    </triangles>\n   </mesh>\n  </object>\n </resources>\n'
        f' <build>\n  <item objectid="2"{item_attrs}/>\n </build>\n</model>\n'
    )

    rels = _RELS_MODEL + (_RELS_THUMB if thumbnail_png else "")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rels}</Relationships>",
        )
        zf.writestr("3D/3dmodel.model", xml.getvalue())
        if printer is not None:
            zf.writestr("Metadata/project_settings.config",
                        build_project_settings(printer, color))
            zf.writestr("Metadata/model_settings.config",
                        build_model_settings(2, name, transform,
                                             thumbnail_png is not None))
            zf.writestr("Metadata/slice_info.config", build_slice_info())
        if thumbnail_png:
            zf.writestr("Metadata/thumbnail.png", thumbnail_png)
            if printer is not None:
                # the names the slicer family uses for the plate previews
                zf.writestr("Metadata/plate_1.png", thumbnail_png)
                zf.writestr("Metadata/plate_no_light_1.png", thumbnail_png)
    return path


def rim_accent_mask(mesh: trimesh.Trimesh, rim_start_z: float) -> np.ndarray:
    """Faces whose centroid sits at or above the foot of the rim chamfer."""
    if not np.isfinite(rim_start_z):
        return np.zeros(len(mesh.faces), dtype=bool)
    return mesh.triangles[:, :, 2].mean(axis=1) >= rim_start_z - 1e-6
