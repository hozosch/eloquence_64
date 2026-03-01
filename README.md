# eloquence_threshold
Eloquence synthesizer NVDA add-on compatible with 64-bit NVDA. Supports Python 3 and new NVDA speech framework.

## 64-bit support

As NVDA migrates to a 64-bit runtime, the Eloquence synthesizer DLL must be
loaded from a 32-bit process.  This add-on now launches a dedicated helper
process that hosts the original 32-bit DLL and streams synthesized audio back
to NVDA using a lightweight RPC channel.  The integration is transparent to the
user—no additional Python installation or manual steps are required.

For development scenarios where the prebuilt helper executable is unavailable
the `ELOQUENCE_HOST_COMMAND` environment variable can be set to the command that
launches a compatible 32-bit Python interpreter with `host_eloquence32.py`.

## Getting Eloquence to Work on Secure, Log-on, and Start-up Screens

With NVDA 64-bit, you may notice that Eloquence is not available when NVDA enters log-on, start-up, or other secure screens.

When NVDA copies add-ons for use on secure screens, it does **not** copy any `*.exe` files for security reasons. For Eloquence, the specific file that is **not** copied when selecting **"Use currently saved settings during sign-in and on secure screens"** from the General pane of NVDA's Settings dialog is:

```
eloquence_host32.exe
```

By default, this file is located at:

```
C:\Users\YourUsername\AppData\Roaming\nvda\addons\Eloquence\synthDrivers\
```

To enable Eloquence on  start-up, secure, and log-on screens in NVDA 64-bit, manually copy the file `eloquence_host32.exe` to:

```
C:\Program Files\NVDA\systemConfig\addons\Eloquence\synthDrivers\
```

If you have an admin-level user account, the correct source path may instead be:

```
C:\Users\admin_your-username\AppData\Roaming\nvda\addons\Eloquence\synthDrivers\
```

After copying the file, Eloquence should load normally on secure and log-on screens.

## Building

• have the Python Install Manager installed and working from: https://www.python.org/ftp/python/pymanager/python-manager-25.0.msix

• Install Python 3.13-32 using py install 3.13-32

• Install pyinstaller using py -3.13-32 -m pip install pyinstaller

• run git submodule init

• run build.cmd

• You should then have a fully built NVDA addon

