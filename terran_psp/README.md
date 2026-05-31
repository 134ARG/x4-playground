# Terran Point Singularity Projector

Standalone X4 extension adding a Terran L Point Singularity Projector turret.

- Requires Cradle of Humanity.
- Reuses the Terran L laser projectile structure with a cloned PSP component for a detached white-blue singularity lance, plus a bundled medium distortion-sphere mesh for the singularity lens.
- Reuses the Terran L laser turret model with a PSP-specific component and macro.
- Adds the ware for player use only via `factions="player"` and does not patch NPC loadouts.
- Places the turret component under `assets/props/weaponsystems/highpower` and marks the equipment connection as `highpower`, matching the Terran Meson Stream compatibility pattern.
- Registers and bundles an `upgrade_turret_ter_l_psp_01_mk1_macro` icon for the equipment configuration menu while leaving the ware preview video unset like vanilla Terran turrets.
- Uses equipment text page `{20105,9901-9903}` for the name, description, and short name, with English fallback text files for the extracted game languages.
