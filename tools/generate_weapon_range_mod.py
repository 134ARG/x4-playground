#!/usr/bin/env python3
"""Generate X4 weapon range enhancement diff XMLs from extracted assets."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


getcontext().prec = 28

DEFAULT_ASSETS_ROOT = Path("x4-assets")
DEFAULT_OUTPUT = Path("weapon_range_enhancement")

DEFAULT_PROJECTILE_FACTOR = Decimal("1.41")
DEFAULT_RANGE_FACTOR = Decimal("2")
DEFAULT_LIGHT_SPEED_THRESHOLD = Decimal("100000000")
OUTPUT_VALUE_QUANTUM = Decimal("0.000001")

KNOWN_EXTENSION_NAMES = {
    "ego_dlc_split": "Split Vendetta",
    "ego_dlc_terran": "Cradle of Humanity",
    "ego_dlc_pirate": "Tides of Avarice",
    "ego_dlc_boron": "Kingdom End",
    "ego_dlc_timelines": "Timelines",
    "ego_dlc_mini_01": "Hyperion Pack",
    "ego_dlc_mini_02": "Envoy Pack",
}


@dataclass(frozen=True)
class Replacement:
    kind: str
    selector: str
    value: str


@dataclass
class PatchFile:
    source: Path
    output: Path
    replacements: list[Replacement] = field(default_factory=list)
    light_speed_bullet: bool = False


@dataclass
class Stats:
    skipped_nonpositive_values: int = 0
    parse_errors: list[str] = field(default_factory=list)


def decimal_arg(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"not a decimal number: {raw}") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than zero: {raw}")
    return value


def parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def is_positive_number(raw: str | None) -> bool:
    value = parse_decimal(raw)
    return value is not None and value > 0


def format_decimal(value: Decimal) -> str:
    if value == value.to_integral():
        return str(value.quantize(Decimal(1)))
    value = value.quantize(OUTPUT_VALUE_QUANTUM)
    if value == value.to_integral():
        return str(value.quantize(Decimal(1)))
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def macro_selector(macro_name: str, element_name: str, attr_name: str) -> str:
    return f"/macros/macro[@name='{macro_name}']/properties/{element_name}/@{attr_name}"


def add_scaled_replacement(
    replacements: list[Replacement],
    stats: Stats,
    macro_name: str,
    element_name: str,
    attr_name: str,
    raw_value: str | None,
    factor: Decimal,
    kind: str,
) -> None:
    value = parse_decimal(raw_value)
    if value is None or value <= 0:
        if raw_value is not None:
            stats.skipped_nonpositive_values += 1
        return
    replacements.append(
        Replacement(
            kind=kind,
            selector=macro_selector(macro_name, element_name, attr_name),
            value=format_decimal(value * factor),
        )
    )


def replacements_for_macro(
    macro: ET.Element,
    stats: Stats,
    projectile_factor: Decimal,
    range_factor: Decimal,
    light_speed_threshold: Decimal,
    include_missiles: bool,
) -> tuple[list[Replacement], bool]:
    macro_name = macro.get("name")
    props = macro.find("properties")
    if not macro_name or props is None:
        return [], False

    replacements: list[Replacement] = []
    light_speed_bullet = False

    bullet = props.find("bullet")
    if bullet is not None:
        speed = parse_decimal(bullet.get("speed"))
        light_speed_bullet = speed is not None and speed >= light_speed_threshold

        if speed is not None and speed > 0 and not light_speed_bullet:
            replacements.append(
                Replacement(
                    kind="speed",
                    selector=macro_selector(macro_name, "bullet", "speed"),
                    value=format_decimal(speed * projectile_factor),
                )
            )
        elif bullet.get("speed") is not None and (speed is None or speed <= 0):
            stats.skipped_nonpositive_values += 1

        lifetime_factor = range_factor if light_speed_bullet else projectile_factor
        add_scaled_replacement(
            replacements,
            stats,
            macro_name,
            "bullet",
            "lifetime",
            bullet.get("lifetime"),
            lifetime_factor,
            "lifetime",
        )
        add_scaled_replacement(
            replacements,
            stats,
            macro_name,
            "bullet",
            "range",
            bullet.get("range"),
            range_factor,
            "range",
        )

    if include_missiles:
        missile = props.find("missile")
        if missile is not None:
            # Missile velocity is supplied by shared engine macros, not by each missile
            # macro. Doubling lifetime/range avoids changing every missile engine user.
            add_scaled_replacement(
                replacements,
                stats,
                macro_name,
                "missile",
                "lifetime",
                missile.get("lifetime"),
                range_factor,
                "lifetime",
            )
            add_scaled_replacement(
                replacements,
                stats,
                macro_name,
                "missile",
                "range",
                missile.get("range"),
                range_factor,
                "range",
            )

            lock = props.find("lock")
            if lock is not None:
                add_scaled_replacement(
                    replacements,
                    stats,
                    macro_name,
                    "lock",
                    "range",
                    lock.get("range"),
                    range_factor,
                    "lock_range",
                )

    return replacements, light_speed_bullet


def discover_patches(
    assets_root: Path,
    output_root: Path,
    projectile_factor: Decimal,
    range_factor: Decimal,
    light_speed_threshold: Decimal,
    include_missiles: bool,
) -> tuple[list[PatchFile], Stats]:
    stats = Stats()
    by_output: dict[Path, PatchFile] = {}

    for source in sorted(assets_root.rglob("*_macro.xml")):
        try:
            root = ET.parse(source).getroot()
        except ET.ParseError as exc:
            stats.parse_errors.append(f"{source}: {exc}")
            continue

        rel = source.relative_to(assets_root)
        output = output_root / rel

        for macro in root.findall("macro"):
            replacements, light_speed = replacements_for_macro(
                macro=macro,
                stats=stats,
                projectile_factor=projectile_factor,
                range_factor=range_factor,
                light_speed_threshold=light_speed_threshold,
                include_missiles=include_missiles,
            )
            if not replacements:
                continue
            patch = by_output.setdefault(output, PatchFile(source=source, output=output))
            patch.replacements.extend(replacements)
            patch.light_speed_bullet = patch.light_speed_bullet or light_speed

    return [by_output[path] for path in sorted(by_output)], stats


def write_patch_file(patch: PatchFile) -> None:
    patch.output.parent.mkdir(parents=True, exist_ok=True)
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<diff>"]
    for replacement in patch.replacements:
        lines.append(f'  <replace sel="{replacement.selector}">{replacement.value}</replace>')
    lines.append("</diff>")
    patch.output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def extension_ids_for_patches(output_root: Path, patches: list[PatchFile]) -> list[str]:
    extension_ids = set()
    for patch in patches:
        rel = patch.output.relative_to(output_root)
        if len(rel.parts) >= 2 and rel.parts[0] == "extensions":
            extension_ids.add(rel.parts[1])
    return sorted(extension_ids)


def write_content_xml(
    output_root: Path,
    mod_id: str,
    mod_name: str,
    description: str,
    author: str,
    version: str,
    date: str,
    extension_ids: list[str],
) -> None:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        (
            f'<content id="{mod_id}" name="{mod_name}" description="{description}" '
            f'author="{author}" version="{version}" date="{date}" save="0">'
        ),
    ]
    for extension_id in extension_ids:
        name = KNOWN_EXTENSION_NAMES.get(extension_id, extension_id)
        lines.append(f'  <dependency id="{extension_id}" optional="true" name="{name}" />')
    lines.append("</content>")
    (output_root / "content.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(
    output_root: Path,
    patches: list[PatchFile],
    stats: Stats,
    range_multiplier: Decimal | None,
    projectile_factor: Decimal,
    range_factor: Decimal,
    light_speed_threshold: Decimal,
    include_missiles: bool,
) -> None:
    replacement_count = sum(len(patch.replacements) for patch in patches)
    bullet_files = sum(
        1 for patch in patches if any(rep.selector.endswith("/properties/bullet/@speed") or "/properties/bullet/" in rep.selector for rep in patch.replacements)
    )
    missile_files = sum(1 for patch in patches if any("/properties/missile/" in rep.selector for rep in patch.replacements))
    explicit_range_replacements = sum(
        1
        for patch in patches
        for rep in patch.replacements
        if rep.selector.endswith("/properties/bullet/@range") or rep.selector.endswith("/properties/missile/@range")
    )
    lock_range_replacements = sum(
        1 for patch in patches for rep in patch.replacements if rep.selector.endswith("/properties/lock/@range")
    )
    light_speed_files = sum(1 for patch in patches if patch.light_speed_bullet)

    lines = [
        "# Weapon Range Enhancement Patch Manifest",
        "",
        "Generated by `tools/generate_weapon_range_mod.py`.",
        "",
        f"- Range multiplier parameter: {range_multiplier if range_multiplier is not None else 'not set'}",
        f"- Projectile speed/lifetime factor: {projectile_factor}",
        f"- Explicit range factor: {range_factor}",
        f"- Light-speed beam threshold: {light_speed_threshold}",
        f"- Include missiles: {'yes' if include_missiles else 'no'}",
        f"- Generated patch files: {len(patches)}",
        f"- Bullet projectile macro files patched: {bullet_files}",
        f"- Light-speed bullet macro files patched with lifetime-only speed handling: {light_speed_files}",
        f"- Missile macro files patched: {missile_files}",
        f"- Attribute replacements: {replacement_count}",
        f"- Explicit projectile/missile range replacements: {explicit_range_replacements}",
        f"- Missile lock range replacements: {lock_range_replacements}",
        f"- Negative/infinite values skipped: {stats.skipped_nonpositive_values}",
        "",
        "## Files",
    ]

    for patch in patches:
        kinds = ", ".join(rep.kind for rep in patch.replacements)
        lines.append(f"- `{patch.output.relative_to(output_root)}`: {kinds}")

    (output_root / "PATCH_MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_output(output_root: Path, assets_root: Path) -> list[str]:
    errors: list[str] = []
    selector_re = re.compile(r"^/macros/macro\[@name='([^']+)'\]/properties/(bullet|missile|lock)/@([A-Za-z0-9_:-]+)$")

    for xml_path in sorted(output_root.rglob("*.xml")):
        try:
            ET.parse(xml_path)
        except ET.ParseError as exc:
            errors.append(f"{xml_path}: invalid XML: {exc}")
            continue

        if xml_path.name == "content.xml":
            continue

        rel = xml_path.relative_to(output_root)
        source = assets_root / rel
        if not source.exists():
            errors.append(f"{xml_path}: source file missing at {source}")
            continue

        try:
            source_root = ET.parse(source).getroot()
        except ET.ParseError as exc:
            errors.append(f"{source}: source XML no longer parses: {exc}")
            continue

        source_macros = {macro.get("name"): macro for macro in source_root.findall("macro") if macro.get("name")}
        for selector, _ in re.findall(r'<replace sel="([^"]+)">([^<]*)</replace>', xml_path.read_text(encoding="utf-8")):
            match = selector_re.match(selector)
            if not match:
                errors.append(f"{xml_path}: unexpected selector {selector}")
                continue
            macro_name, element_name, attr_name = match.groups()
            macro = source_macros.get(macro_name)
            props = macro.find("properties") if macro is not None else None
            element = props.find(element_name) if props is not None else None
            if element is None or element.get(attr_name) is None:
                errors.append(f"{xml_path}: selector has no source attribute {selector}")

    return errors


def prepare_output(output_root: Path, assets_root: Path, force: bool, dry_run: bool) -> None:
    if dry_run:
        return

    resolved_output = output_root.resolve()
    resolved_assets = assets_root.resolve()
    cwd = Path.cwd().resolve()
    if resolved_output in {Path("/").resolve(), cwd, resolved_assets}:
        raise SystemExit(f"refusing to clean unsafe output path: {output_root}")

    if output_root.exists():
        if not force:
            raise SystemExit(f"{output_root} already exists; rerun with --force to regenerate it")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", type=Path, default=DEFAULT_ASSETS_ROOT, help="extracted X4 asset root")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="mod folder to generate")
    parser.add_argument("--force", action="store_true", help="delete and recreate the output folder")
    parser.add_argument("--dry-run", action="store_true", help="scan and report without writing files")
    parser.add_argument(
        "--range-multiplier",
        type=decimal_arg,
        help=(
            "desired weapon range multiplier; when set, projectile speed/lifetime "
            "default to sqrt(multiplier) and explicit ranges default to multiplier"
        ),
    )
    parser.add_argument(
        "--projectile-factor",
        type=decimal_arg,
        help=f"advanced override for normal bullet speed/lifetime scaling; default {DEFAULT_PROJECTILE_FACTOR}",
    )
    parser.add_argument(
        "--range-factor",
        type=decimal_arg,
        help=f"advanced override for explicit range, beam lifetime, and missile scaling; default {DEFAULT_RANGE_FACTOR}",
    )
    parser.add_argument("--light-speed-threshold", type=decimal_arg, default=DEFAULT_LIGHT_SPEED_THRESHOLD)
    parser.add_argument("--no-missiles", action="store_true", help="skip missile macro patches")
    parser.add_argument("--mod-id", default="weapon_range_enhancement")
    parser.add_argument("--mod-name", default="Weapon Range Enhancement")
    parser.add_argument(
        "--description",
        default="Doubles vanilla and DLC weapon projectile range using incremental XML patches.",
    )
    parser.add_argument("--author", default="Codex")
    parser.add_argument("--version", default="100")
    parser.add_argument("--date", default="2026-05-24")
    return parser


def resolve_scaling(args: argparse.Namespace) -> tuple[Decimal, Decimal]:
    if args.range_multiplier is None:
        projectile_factor = args.projectile_factor or DEFAULT_PROJECTILE_FACTOR
        range_factor = args.range_factor or DEFAULT_RANGE_FACTOR
        return projectile_factor, range_factor

    range_factor = args.range_factor or args.range_multiplier
    projectile_factor = args.projectile_factor or args.range_multiplier.sqrt().quantize(OUTPUT_VALUE_QUANTUM)
    return projectile_factor, range_factor


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assets_root = args.assets_root
    output_root = args.output
    include_missiles = not args.no_missiles
    projectile_factor, range_factor = resolve_scaling(args)

    if not assets_root.exists():
        raise SystemExit(f"asset root not found: {assets_root}")

    patches, stats = discover_patches(
        assets_root=assets_root,
        output_root=output_root,
        projectile_factor=projectile_factor,
        range_factor=range_factor,
        light_speed_threshold=args.light_speed_threshold,
        include_missiles=include_missiles,
    )

    print(f"asset root: {assets_root}")
    print(f"output: {output_root}")
    if args.range_multiplier is not None:
        print(f"range multiplier: {args.range_multiplier}")
    print(f"projectile factor: {projectile_factor}")
    print(f"explicit range factor: {range_factor}")
    print(f"patch files: {len(patches)}")
    print(f"attribute replacements: {sum(len(patch.replacements) for patch in patches)}")
    print(f"source parse errors skipped: {len(stats.parse_errors)}")

    if args.dry_run:
        return 0

    prepare_output(output_root, assets_root, force=args.force, dry_run=args.dry_run)
    for patch in patches:
        write_patch_file(patch)

    extension_ids = extension_ids_for_patches(output_root, patches)
    write_content_xml(
        output_root=output_root,
        mod_id=args.mod_id,
        mod_name=args.mod_name,
        description=args.description,
        author=args.author,
        version=args.version,
        date=args.date,
        extension_ids=extension_ids,
    )
    write_manifest(
        output_root=output_root,
        patches=patches,
        stats=stats,
        range_multiplier=args.range_multiplier,
        projectile_factor=projectile_factor,
        range_factor=range_factor,
        light_speed_threshold=args.light_speed_threshold,
        include_missiles=include_missiles,
    )

    validation_errors = validate_output(output_root, assets_root)
    if validation_errors:
        print("validation failed:", file=sys.stderr)
        for error in validation_errors[:25]:
            print(f"  {error}", file=sys.stderr)
        if len(validation_errors) > 25:
            print(f"  ... and {len(validation_errors) - 25} more", file=sys.stderr)
        return 1

    print(f"wrote {output_root}")
    print("validation: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
