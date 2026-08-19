"""Slicer project payload: printer / process / filament settings for the 3MF.

Creality Cloud, Creality Print (5.0+), OrcaSlicer (1.4+) and Bambu Studio
(1.07+) all share the same project-3MF convention: alongside the geometry,
the package carries

* ``Metadata/project_settings.config`` - a flat JSON bundle of printer,
  process and filament settings (OrcaSlicer key names),
* ``Metadata/model_settings.config``  - which object sits on which plate,
* BBS-style metadata in the model XML.

A plain geometry 3MF (what this generator wrote before) is still valid for
"other types of 3MF" uploads, but the "Print Settings" upload path on
Creality Cloud rejects it because it contains no machine model.  Embedding
one of the profiles below fixes that.

The profiles here are deliberately conservative defaults for each machine
(0.4 mm nozzle, 0.2 mm layers, 3 walls, 15 % infill, generic PLA); any
slicer that opens the project can adjust them afterwards.
"""

from __future__ import annotations

import json

from .colors import parse_color

#: Machines the generator can target.  "none" produces a plain geometry 3MF.
PRINTERS: dict[str, dict] = {
    "creality-k1-max": dict(
        model="Creality K1 Max",
        printer_settings_id="Creality K1 Max 0.4 nozzle",
        process_id="0.20mm Standard @Creality K1 Max",
        filament_id="Creality Generic PLA",
        bed=(300, 300), height=300, gcode_flavor="klipper",
        start_gcode="START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]",
        end_gcode="END_PRINT",
        aux_fan=True,
    ),
    "creality-k1": dict(
        model="Creality K1",
        printer_settings_id="Creality K1 0.4 nozzle",
        process_id="0.20mm Standard @Creality K1",
        filament_id="Creality Generic PLA",
        bed=(220, 220), height=250, gcode_flavor="klipper",
        start_gcode="START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]",
        end_gcode="END_PRINT",
        aux_fan=True,
    ),
    "creality-ender3-v3-ke": dict(
        model="Creality Ender-3 V3 KE",
        printer_settings_id="Creality Ender-3 V3 KE 0.4 nozzle",
        process_id="0.20mm Standard @Creality Ender-3 V3 KE",
        filament_id="Creality Generic PLA",
        bed=(220, 220), height=240, gcode_flavor="klipper",
        start_gcode="START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]",
        end_gcode="END_PRINT",
        aux_fan=False,
    ),
}

PRINTER_CHOICES = tuple(PRINTERS) + ("none",)


def build_project_settings(printer_key: str, filament_color: str) -> str:
    """The ``Metadata/project_settings.config`` JSON for one machine.

    OrcaSlicer-family slicers treat this as a config bundle: keys they know
    are applied, missing ones fall back to the preset defaults, so this
    stays at the settings that matter rather than the full ~600-key dump a
    slicer would write.  All values are strings (or string arrays for
    per-filament settings) per the config serialisation convention.
    """
    m = PRINTERS[printer_key]
    w, d = m["bed"]
    cfg = {
        "version": "1.9.0.2",
        "curr_bed_type": "Textured PEI Plate",

        # ---- printer ----------------------------------------------------
        "printer_settings_id": m["printer_settings_id"],
        "printer_model": m["model"],
        "printer_variant": "0.4",
        "printer_technology": "FFF",
        "gcode_flavor": m["gcode_flavor"],
        "nozzle_diameter": ["0.4"],
        "printable_area": [f"0x0", f"{w}x0", f"{w}x{d}", f"0x{d}"],
        "printable_height": str(m["height"]),
        "auxiliary_fan": "1" if m["aux_fan"] else "0",
        "machine_start_gcode": m["start_gcode"],
        "machine_end_gcode": m["end_gcode"],
        "retraction_length": ["0.5"],
        "retraction_speed": ["40"],
        "z_hop": ["0.2"],

        # ---- process ----------------------------------------------------
        "print_settings_id": m["process_id"],
        "layer_height": "0.2",
        "initial_layer_print_height": "0.2",
        "line_width": "0.42",
        "wall_loops": "3",
        "top_shell_layers": "4",
        "bottom_shell_layers": "3",
        "sparse_infill_density": "15%",
        "sparse_infill_pattern": "grid",
        "enable_support": "0",
        "brim_type": "auto_brim",
        "seam_position": "aligned",
        "elefant_foot_compensation": "0.15",
        "outer_wall_speed": "200",
        "inner_wall_speed": "300",
        "travel_speed": "400",
        "initial_layer_speed": "50",

        # ---- filament (arrays: one entry per extruder) -------------------
        "filament_settings_id": [m["filament_id"]],
        "filament_type": ["PLA"],
        "filament_vendor": ["Generic"],
        "filament_diameter": ["1.75"],
        "filament_colour": [parse_color(filament_color)],
        "nozzle_temperature_initial_layer": ["220"],
        "nozzle_temperature": ["220"],
        "hot_plate_temp_initial_layer": ["55"],
        "hot_plate_temp": ["55"],
        "textured_plate_temp_initial_layer": ["55"],
        "textured_plate_temp": ["55"],
        "cool_plate_temp_initial_layer": ["50"],
        "cool_plate_temp": ["50"],
        "fan_min_speed": ["60"],
        "fan_max_speed": ["100"],
        "filament_max_volumetric_speed": ["20"],
    }
    return json.dumps(cfg, indent=1)


def build_model_settings(object_id: int, name: str) -> str:
    """``Metadata/model_settings.config``: one object on plate 1."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="{object_id}">
    <metadata key="name" value="{name}"/>
    <metadata key="extruder" value="1"/>
  </object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <metadata key="locked" value="false"/>
    <model_instance>
      <metadata key="object_id" value="{object_id}"/>
      <metadata key="instance_id" value="0"/>
      <metadata key="identify_id" value="100"/>
    </model_instance>
  </plate>
</config>
"""


def bed_center(printer_key: str) -> tuple[float, float]:
    w, d = PRINTERS[printer_key]["bed"]
    return w / 2.0, d / 2.0
