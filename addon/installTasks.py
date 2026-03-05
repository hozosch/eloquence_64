import os
import shutil
import sys
from pathlib import Path


def onInstall():
	"""Copy _multiprocessing.pyd into the addon if missing.

	NVDA's frozen Python does not expose the _multiprocessing C extension,
	so the addon bundles its own copy.  The build system (SConstruct) normally
	places it, but this hook acts as a safety net when the addon is installed
	from a pre-built .nvda-addon package.
	"""
	addon_dir = Path(__file__).parent
	dest = addon_dir / "synthDrivers" / "eloquence" / "_multiprocessing.pyd"
	if dest.exists():
		return

	# Try to locate _multiprocessing.pyd from a system Python installation.
	candidates = []

	# 1. sysconfig (works when a full CPython is installed)
	try:
		import sysconfig

		dll_dir = Path(sysconfig.get_path("platlib")).parent / "DLLs"
		candidates.append(dll_dir / "_multiprocessing.pyd")
		# Fallback: stdlib-based path
		dll_dir2 = Path(sysconfig.get_path("stdlib")).parent / "DLLs"
		candidates.append(dll_dir2 / "_multiprocessing.pyd")
	except Exception:
		pass

	# 2. Common default install locations
	for ver in ("313", "312", "311"):
		candidates.append(Path(f"C:\\Python{ver}\\DLLs\\_multiprocessing.pyd"))
		candidates.append(
			Path(
				os.path.expandvars(
					f"%LOCALAPPDATA%\\Programs\\Python\\Python{ver}\\DLLs\\_multiprocessing.pyd"
				)
			)
		)

	for src in candidates:
		if src.exists():
			shutil.copy2(str(src), str(dest))
			return
