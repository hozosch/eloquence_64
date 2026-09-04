# Eloquence for NVDA

Eloquence synthesizer add-on for NVDA with full 64-bit support.

## 64-bit support

The Eloquence DLL is 32-bit only. This add-on launches the Eloquence Host
Process (`eloquence_host32.exe`) to load the Eloquence Engine and stream audio
back to 64-bit NVDA. The integration is transparent — no additional Python
installation or manual steps are required.

For development scenarios where the prebuilt Eloquence Host Process executable is unavailable,
the `ELOQUENCE_HOST_COMMAND` environment variable can be set to the command that
launches a compatible 32-bit Python interpreter with `host_eloquence32.py`.

## Native 16 kHz mode

Starting with v20, the add-on provides a native 16 kHz Eloquence mode. It
replaces the external 11.025→22.05 kHz output upsampler used by earlier releases.
The release build exposes exactly one 16 kHz setting alongside the original 8
and 11.025 kHz settings; experimental comparison modes are not user-selectable.

The 8 kHz and 11.025 kHz modes still use the original Eloquence voice data and
can be switched live through Eloquence's normal sample-rate parameter. The 16
kHz mode is different: it applies a compact reversible patch to the active
`.SYN` synthesis module before that module is loaded. Changing the file on disk
does not change the already-loaded engine in memory, so entering or leaving 16
kHz requires restarting the **32-bit Eloquence Host Process**. NVDA itself is
not restarted. After the host reload, the add-on restores the selected language,
voice variant/synthesis model, and user voice parameters. Switching back to 8
or 11 kHz restores the original `.SYN` bytes before the host is reloaded.

A live 16 kHz switch like the native 8/11 kHz switch is therefore not used: it
would require modifying the loaded proprietary synthesis module in process
memory, whereas restarting the isolated host lets Eloquence load the patched
module normally and keeps the change reversible.

The final 16 kHz tuning exposes one reference mode. Exact synthesis target flags
keep the dedicated `s`, voiced `s`, and `t` path separate from the spectral
pivot used for the selected consonants, so filter state cannot spill from one
class into the next. Bass +2 dB, the measured v21 reference shelf, and the
optional 4 kHz/Q1.5 presence contour run in the injected native float path
before Eloquence converts its output to PCM16. Earlier in that native pipeline,
the still-separate cascade/voicing buffer receives a fixed -1.5 dB multiplier
before direct and parallel frication are mixed in. The gain itself has no
detector, envelope, or phoneme-specific exception; the independent frication
routing continues to protect the spectral shape of s/t/z. A separate 2 ms ramp
is applied only at the beginning of each utterance to prevent start clicks.

Presence on and off are two internal native patch variants, not additional
sample-rate modes. Changing the checkbox while 16 kHz is active therefore uses
the warm ECI reload, while changing it at 8 or 11 kHz is deferred until 16 kHz
is selected. See [the native-16 design record](docs/adr/0002native16.md) for
details.

## Traditional Chinese Script Conversion

When the Mandarin Chinese voice is selected, Text Preprocessing applies Script
Conversion before text is sent to the Eloquence Engine. Traditional Chinese
text is read via Traditional→Simplified conversion with the Mandarin Chinese
voice.

This is not zh-TW support, a Traditional Chinese voice, or Cantonese support.
The add-on's Chinese Voice Identity still advertises only `zh-CN`.

Known limitations:

- Hong Kong (`zh-HK`) users get Mandarin readings, not Cantonese.
- Colloquial written-Cantonese characters, such as `嘅`, `哋`, and `咗`,
  are unpronounceable.
- A zh-TW-localized NVDA install does not auto-select the Chinese voice on
  first run. Users need to pick the Chinese voice once manually.

## Eloquence on secure screens (logon, UAC, start-up)

NVDA does **not** copy `*.exe` files to its Secure Screen configuration for
security reasons, so the Eloquence Host Process is missing after you click
**"Use currently saved settings during sign-in"** in NVDA's General settings.

The easiest way to fix this is the built-in button in the add-on:

1. Open **NVDA Settings > Eloquence**.
2. Click **"Copy Helper to System Config (for Logon Screen)"**.
3. Accept the UAC elevation prompt.

Eloquence should now load on Secure Screens. You only need to do this
once per add-on update.

## Troubleshooting

### "Could not load the synthesizer" after upgrading

If you upgraded from v16 (or earlier) to v17+ and NVDA reports **"Could not load
the synthesizer"** when you select Eloquence, the NVDA log most likely shows:

```
AttributeError: module 'synthDrivers._ipc' has no attribute 'create_listener'
```

This is caused by one or more of:

- Stale Python bytecode (`__pycache__`) left over from the previous version.
- A half-finished NVDA upgrade leaving an `Eloquence.delete` folder alongside
  the new install.
- The IBMTTS add-on also being installed — running both at the same time is
  not supported.

To recover, do a clean reinstall:

1. In NVDA, open **Tools → Manage Add-ons**, disable Eloquence, and restart
   NVDA so the disable takes effect.
2. In File Explorer, open `%APPDATA%\nvda\addons\` and delete the entire
   `Eloquence` folder. While you're there, delete any sibling folders whose
   names end in `.delete`.
3. If the IBMTTS add-on is installed, disable or remove it as well.
4. Restart NVDA, then install the latest Eloquence release fresh.
5. As a last resort, back up `%APPDATA%\nvda` and remove it to start with a
   clean NVDA config.

See [issue #101](https://github.com/fastfinge/eloquence_64/issues/101) for the
background.

## Building

### Prerequisites

- [Python Install Manager](https://www.python.org/ftp/python/pymanager/python-manager-25.0.msix) (`.msix`)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 32-bit Python 3.13: `py install 3.13-32`

### Build steps

```bash
git submodule init && git submodule update   # fetch pronunciation dictionaries
python fetch_eci.py                          # one-time: download proprietary ECI.DLL + voice data
build_host.cmd                               # compile Eloquence Host Process (only needed if host_eloquence32.py changes)
scons.bat                                    # package everything into the .nvda-addon file
```

The compact native-16 patch files are stored in the repository and are applied
at run time; no separate upsampler DLL build is required.

**Note:** `scons.bat` validates that the proprietary files, Eloquence Host
Process executable, and native-16 patch files exist, but does not fetch or build
the proprietary files or host executable — steps 2 and 3 must be done first.

### Development checks

```bash
runlint.bat      # run Ruff using the locked uv environment
runpytest.bat    # run pytest using the locked uv environment
```

Tooling dependencies are pinned in `pyproject.toml` and `uv.lock`, following
NVDA's current dependency-group pattern. The Eloquence Host Process build uses a
separate `.venv32` environment so PyInstaller can run under 32-bit Python
without replacing the normal development `.venv`.
