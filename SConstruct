# Eloquence NVDA add-on SConstruct
# Generates manifest.ini from template + buildVars, then zips addon/ into .nvda-addon.

import glob
import os
import sys
from pathlib import Path

from SCons.Script import Environment, EnsurePythonVersion

EnsurePythonVersion(3, 8)

sys.dont_write_bytecode = True

import buildVars  # noqa: E402

env = Environment(ENV=os.environ, tools=["NVDATool"])
env.Append(addon_info=buildVars.addon_info)
env.Append(**buildVars.addon_info)

addonDir = Path("addon")

# --- Compile translations (.po -> .mo) -------------------------------------

poFiles = glob.glob("addon/locale/*/LC_MESSAGES/*.po")
moFiles = []
for po in poFiles:
	mo = po[:-3] + ".mo"
	moFile = env.Command(target=mo, source=po, action="msgfmt -o $TARGET $SOURCE")
	moFiles.append(moFile)

# --- Validate required binaries and native-16 patches ----------------------

eci_dir = addonDir / "synthDrivers" / "eloquence"
host_exes = (
	addonDir / "synthDrivers" / "eloquence_host32" / "eloquence_host32.exe",
	addonDir / "synthDrivers" / "eloquence_host32.exe",
)
voice_names = ("DEU", "ENG", "ENU", "ESM", "ESP", "FIN", "FRA", "FRC", "ITA", "PTB")
patch_names = ("DEU", "ENG", "ENU", "ESM", "ESP", "FIN", "FRA", "FRC", "ITA", "PTB", "chs", "jpn", "kor")
required_proprietary = [eci_dir / "ECI.DLL"] + [eci_dir / f"{name}.SYN" for name in voice_names]
required_patches = [
	eci_dir / f"{name}{extension}"
	for name in patch_names
	for extension in (".p16st", ".p16all", ".p16a6", ".p16a7")
]

missing = [str(p) for p in required_proprietary if not p.exists()]
if missing:
	print(
		"ERROR: Missing proprietary Eloquence files:\n  "
		+ "\n  ".join(missing)
		+ "\n\nRun `python fetch_eci.py` to download them.",
		file=sys.stderr,
	)
	Exit(1)

missing_patches = [str(p) for p in required_patches if not p.exists()]
if missing_patches:
	print(
		"ERROR: Missing native 16 kHz patch files:\n  "
		+ "\n  ".join(missing_patches),
		file=sys.stderr,
	)
	Exit(1)

if not any(host_exe.exists() for host_exe in host_exes):
	print(
		"ERROR: No 32-bit Eloquence host found.\n"
		"Run `build_host.cmd` to compile the host directory first.",
		file=sys.stderr,
	)
	Exit(1)

# --- Generate manifest ----------------------------------------------------

manifest = env.NVDAManifest(env.File(str(addonDir / "manifest.ini")), "manifest.ini.tpl")
env.Depends(manifest, "buildVars.py")
env.Depends(manifest, env.Value(buildVars.addon_info["addon_version"]))

# --- Build addon bundle ----------------------------------------------------

addonFile = env.File("${addon_name}-${addon_version}.nvda-addon")
addon = env.NVDAAddon(addonFile, env.Dir(str(addonDir)))
env.Depends(addon, moFiles)
env.Depends(addon, manifest)

for p in Path("addon").rglob("*"):
	if p.is_file():
		env.Depends(addon, str(p))

# --- Generate POT template --------------------------------------------------

potFile = Path(f"{env['addon_name']}.pot")
pySources = [str(p) for p in addonDir.rglob("*.py")]
pySources.append("buildVars.py")

pot = env.Command(
	target=str(potFile),
	source=pySources,
	action=(
		"xgettext "
		"--language=Python "
		"--keyword=_ "
		"--keyword=pgettext:1c,2 "
		"--from-code=UTF-8 "
		"--add-comments=Translators "
		"--package-name=${addon_name} "
		"--package-version=${addon_version} "
		"-o $TARGET $SOURCES"
	),
)

env.Alias("pot", pot)
env.Default(addon)
env.Clean(addon, [".sconsign.dblite"])
