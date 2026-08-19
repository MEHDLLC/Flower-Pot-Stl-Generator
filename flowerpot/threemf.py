"""Minimal 3MF writer with material colors and slicer project settings.

STL carries no color, so for a colored pot we write 3MF - a zip package
holding one XML model.  This writer is deliberately small and dependency
free: vertices, triangles, one or two basematerials, and an optional
package thumbnail that slicers show in their file pickers.

Two-tone pots: pass ``accent_mask`` (a boolean per face) and those faces
get the accent material - the CLI uses it to color the rim.

Pass ``printer`` (a key from :mod:`flowerpot.printers`) to write the
OrcaSlicer / Bambu Studio / Creality Print *project* form of the package
instead - the layout those slicers actually save, which is also what the
"Print Settings" upload path on Creality Cloud expects:

* geometry lives in ``3D/Objects/object_1.model`` and the root
  ``3D/3dmodel.model`` only references it through a production-extension
  component (viewers in this family load meshes from ``3D/Objects/`` and
  render an empty plate when the mesh is inline in the root file);
* ``Metadata/project_settings.config`` carries machine, process and
  filament settings, ``model_settings.config`` the plate assignment;
* the ``Application`` metadata says Bambu Studio, whose projects Creality
  Cloud documents as auto-converted.

Without ``printer`` the writer emits a plain, single-file, spec-core 3MF.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import trimesh

from .colors import parse_color
from .printers import (bed_center, build_model_settings,
                       build_project_settings)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
</Types>
"""

_RELS_MODEL = ('<Relationship Target="/3D/3dmodel.model" Id="rel0" '
               'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>')
_RELS_OBJECT = ('<Relationship Target="/3D/Objects/object_1.model" Id="rel1" '
                'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>')
_P_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"

# fixed, valid UUIDs in the style the Bambu Studio family stamps on
# objects, components, builds and items (any stable UUID is acceptable)
_UUID_OBJECT = "00000002-81cb-4c03-9d28-80fed5dfa1dc"
_UUID_COMPONENT = "00010000-b206-40ff-9872-83e8017abed1"
_UUID_MESH = "00010000-81cb-4c03-9d28-80fed5dfa1dc"
_UUID_BUILD = "2c7c17d8-22b5-4d84-8835-1976022ea369"
_UUID_ITEM = "00000002-b1ec-4553-aec9-835e5b724bb4"
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

    def mesh_xml(out: io.StringIO, object_id: int, extra_attrs: str) -> None:
        """Emit one <object> with the mesh, materials and accent overrides."""
        out.write(
            f'  <basematerials id="1">{"".join(materials)}</basematerials>\n'
            f'  <object id="{object_id}" name="{name}"{extra_attrs} '
            'type="model" pid="1" pindex="0">\n'
            '   <mesh>\n    <vertices>\n'
        )
        for x, y, z in mesh.vertices:
            out.write(f'     <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>\n')
        out.write('    </vertices>\n    <triangles>\n')
        if use_accent:
            for (a, b, c), acc in zip(mesh.faces, accent_mask):
                extra = ' pid="1" p1="1"' if acc else ""
                out.write(f'     <triangle v1="{a}" v2="{b}" v3="{c}"{extra}/>\n')
        else:
            for a, b, c in mesh.faces:
                out.write(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n')
        out.write('    </triangles>\n   </mesh>\n  </object>\n')

    transform = ""
    object_xml = None
    root = io.StringIO()
    if printer is not None:
        # project form: root model only references 3D/Objects/object_1.model
        cx, cy = bed_center(printer)
        transform = f"1 0 0 0 1 0 0 0 1 {cx:.3f} {cy:.3f} 0"
        root.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            f'xmlns:p="{_P_NS}" requiredextensions="p">\n'
            ' <metadata name="Application">BambuStudio-02.01.01.52</metadata>\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
            f' <metadata name="Title">{name}</metadata>\n'
            ' <metadata name="Designer"></metadata>\n'
            ' <metadata name="Description"></metadata>\n'
            ' <resources>\n'
            f'  <object id="2" p:UUID="{_UUID_OBJECT}" type="model">\n'
            '   <components>\n'
            f'    <component p:path="/3D/Objects/object_1.model" objectid="1" '
            f'p:UUID="{_UUID_COMPONENT}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
            '   </components>\n'
            '  </object>\n'
            ' </resources>\n'
            f' <build p:UUID="{_UUID_BUILD}">\n'
            f'  <item objectid="2" p:UUID="{_UUID_ITEM}" '
            f'transform="{transform}" printable="1"/>\n'
            ' </build>\n</model>\n'
        )
        obj = io.StringIO()
        obj.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            f'xmlns:p="{_P_NS}">\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
            ' <resources>\n'
        )
        mesh_xml(obj, 1, f' p:UUID="{_UUID_MESH}"')
        obj.write(' </resources>\n <build/>\n</model>\n')
        object_xml = obj.getvalue()
    else:
        # plain form: one spec-core file, mesh inline
        root.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
            ' <resources>\n'
        )
        mesh_xml(root, 2, "")
        root.write(' </resources>\n <build>\n  <item objectid="2"/>\n </build>\n</model>\n')

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
        zf.writestr("3D/3dmodel.model", root.getvalue())
        if object_xml is not None:
            zf.writestr("3D/Objects/object_1.model", object_xml)
            zf.writestr(
                "3D/_rels/3dmodel.model.rels",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f"{_RELS_OBJECT}</Relationships>",
            )
        if printer is not None:
            zf.writestr("Metadata/project_settings.config",
                        build_project_settings(printer, color))
            zf.writestr("Metadata/model_settings.config",
                        build_model_settings(2, name, transform,
                                             thumbnail_png is not None))
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
