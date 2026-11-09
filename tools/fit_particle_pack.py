"""Fit the motion-fixed Dropbox SCP to the existing engine, without engine changes.

Input must be particle-sekai-motion-fixed.scp. Keeps textures, durations,
random-variable coefficients, and emitter multiplicities, except skin-owned stamps.
"""

import argparse
import copy
import gzip
import hashlib
import json
import math
import zipfile
from pathlib import Path

# Indices verified against this export's atlas: yellow/green floor outlines and
# glowing square slot stamps. These are not the diamond/spark/star particles.
SKIN_SLOT_SPRITES = {74, 75, 81, 98}


def identity():
    return {axis + str(i): {axis + str(i): 1} for axis in ("x", "y") for i in range(1, 5)}


def billboard_transform():
    # Engine/Sonolus corner order: BL, TL, TR, BR. Reconstruct the upper
    # corners using a perpendicular to the bottom edge. All expressions are
    # linear in the input corners, so no lane, camera or stage constants are
    # needed; the anchor, rotation, and effect-size setting are retained.
    result = identity()
    result.update(
        x2={"x1": 1, "y1": 1, "y4": -1},
        y2={"y1": 1, "x4": 1, "x1": -1},
        x3={"x4": 1, "y1": 1, "y4": -1},
        y3={"y4": 1, "x4": 1, "x1": -1},
    )
    return result


def lane_transform():
    # The current engine trims the top for a legacy 1.07 height overshoot.
    # This pack's lane particles use h=1 throughout. Undo that trim in the
    # custom lane bindings only; #LANE_LINEAR uses the uncompensated fallback.
    result = identity()
    for axis in ("x", "y"):
        result[axis + "2"] = {axis + "2": 1.07, axis + "1": -0.07}
        result[axis + "3"] = {axis + "3": 1.07, axis + "4": -0.07}
    return result


def fit(data):
    report = []
    effects = {effect["name"]: effect for effect in data["effects"]}
    # The original export copied a central Good Gen into its per-lane binding.
    for slot, center in [
        ("Sekai Good Normal Note Slot Linear", "Sekai Good Normal Note Linear"),
        ("Sekai Slot Linear Tap Cyan Good", "Sekai Linear Tap Cyan Good"),
    ]:
        central = effects[center]["groups"]
        before = effects[slot]["groups"]
        effects[slot]["groups"] = [g for g in before if g not in central]
        report.append({"effect": slot, "removed_duplicate_groups": len(before) - len(effects[slot]["groups"])})
    for effect in data["effects"]:
        name = effect["name"]
        removed = 0
        groups = []
        for group in effect["groups"]:
            # Preserve shared-atlas particles in Fever and other screen effects.
            if name.startswith(("#NOTE_", "Sekai ")) and "Fever" not in name:
                kept = [p for p in group["particles"] if p["sprite"] not in SKIN_SLOT_SPRITES]
                removed += len(group["particles"]) - len(kept)
                group["particles"] = kept
            if group["particles"]:
                groups.append(group)
        effect["groups"] = groups
        if removed:
            report.append({"effect": name, "removed_skin_stamp_segments": removed})
        if "Lane Linear" in name:
            effect["transform"] = lane_transform()
            report.append({"effect": name, "transform": "restore lane top"})
        elif (
            ("Linear" in name or name.startswith("#NOTE_LINEAR") or "Directional" in name)
            and not any(word in name for word in ("Lane", "Fever", "Super"))
            and name != "#LANE_LINEAR"
        ):
            effect["transform"] = billboard_transform()
            report.append({"effect": name, "transform": "rectangular billboard"})
        # Circular effects deliberately keep their existing projected quad.
        for group in effect["groups"]:
            previous = None
            offset = 0.0
            for particle in group["particles"]:
                angle = particle["r"]
                contiguous = (
                    previous is not None
                    and previous["sprite"] == particle["sprite"]
                    and abs(previous["start"] + previous["duration"] - particle["start"]) < 1e-5
                )
                if not contiguous:
                    offset = 0.0
                for endpoint in ("from", "to"):
                    if offset:
                        angle[endpoint]["c"] = angle[endpoint].get("c", 0) + offset
                delta = angle["to"].get("c", 0) - angle["from"].get("c", 0)
                if particle["duration"] < 0.1 and 1.9 * math.pi < abs(delta) < 2.1 * math.pi:
                    shift = -math.copysign(2 * math.pi, delta)
                    angle["to"]["c"] = angle["to"].get("c", 0) + shift
                    offset += shift
                    report.append({"effect": name, "rotation": "unwrap short atan2 boundary"})
                previous = particle
    return report


def package(source, target):
    with zipfile.ZipFile(source) as archive:
        files = {entry.filename: archive.read(entry) for entry in archive.infolist()}
    descriptor = json.loads(files["sonolus/particles/particle"])
    item = descriptor.get("item", descriptor)
    old_hash = item["data"]["hash"]
    if old_hash != "3b6089816fd3ac1ceef51e05a140255cfee1fb78":
        raise ValueError("Source data differs from the inspected motion-fixed export")
    data = json.loads(gzip.decompress(files["sonolus/repository/" + old_hash]))
    # Fail on a different atlas rather than silently removing unrelated sprites.
    if len(data["sprites"]) != 119 or len(data["effects"]) != 100:
        raise ValueError("Expected the verified 119-sprite / 100-effect motion-fixed pack")
    fixed = copy.deepcopy(data)
    report = fit(fixed)
    encoded = gzip.compress(json.dumps(fixed, separators=(",", ":")).encode(), mtime=0)
    digest = hashlib.sha1(encoded).hexdigest()
    files["sonolus/repository/" + digest] = encoded
    for path, content in files.items():
        if not path.startswith("sonolus/repository/"):
            files[path] = content.replace(old_hash.encode(), digest.encode())
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    Path(target).with_suffix(".report.json").write_text(json.dumps(report, indent=2))
    print(f"{len(report)} corrections; {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()
    package(args.source, args.target)
