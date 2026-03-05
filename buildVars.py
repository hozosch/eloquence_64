# Build customizations
# Change this file instead of SConstruct or manifest files, whenever possible.

import os


def _get_version():
	"""Read version from VERSION file, use it, then increment for next build.

	Version format: major.minor.patch (e.g. "16.0.0").
	Patch increments by 2 each build (0, 2, 4, 6, 8).
	When patch reaches 10, minor increments by 1 and patch resets to 0.
	"""
	version_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
	if not os.path.exists(version_path):
		with open(version_path, "w") as f:
			f.write("16.0.0")
		return "16.0.0"
	with open(version_path, "r") as f:
		version_str = f.read().strip()
	major, minor, patch = (int(x) for x in version_str.split("."))
	current_version = f"{major}.{minor}.{patch}"
	next_patch = patch + 2
	next_minor = minor
	if next_patch >= 10:
		next_minor += 1
		next_patch = 0
	next_version = f"{major}.{next_minor}.{next_patch}"
	with open(version_path, "w") as f:
		f.write(next_version)
	return current_version


addon_info = {
	"addon_name": "Eloquence",
	"addon_summary": "Eloquence Synthesizer",
	"addon_description": "Eloquence synthesizer for NVDA with 64-bit support",
	"addon_version": _get_version(),
	"addon_author": "NVDA User",
	"addon_url": "https://github.com/pumper42nickel/eloquence_threshold",
	"addon_lastTestedNVDAVersion": "2034.1",
}
