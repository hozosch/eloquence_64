"""Client side helper for communicating with the 32-bit Eloquence host."""

from __future__ import annotations

import functools
import itertools
import logging
import os
import struct

import queue
import shlex
import subprocess
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from . import _eci_engine as _engine
from . import _eloquence_ipc as _ipc
from . import _eloquence_job as _job
import config
import nvwave
from buildVersion import version_year

LOGGER = logging.getLogger(__name__)

HOST_EXECUTABLE = "eloquence_host32.exe"
# The PyInstaller onedir tree the Eloquence Host Process ships as.  The exe sits
# at its root beside an _internal directory it resolves relative to itself, so
# the tree has to stay intact -- the exe alone will not run.
HOST_DIRECTORY = "eloquence_host32"
HOST_SCRIPT = "host_eloquence32.py"
# How long to wait for the Eloquence Host Process to open the Host Channel.
HOST_CONNECT_TIMEOUT = 10.0
# Seconds to let the host exit on its own before we terminate it.  A onefile
# build needed this to clean up its _MEI temp directory; the onedir build has
# nothing to unpack, but a cooperative exit still lets the Eloquence Engine shut
# down through eciDelete rather than dying mid-call.
HOST_EXIT_TIMEOUT = 3.0


# Audio handling -----------------------------------------------------------------
# Compact native-rate build: no external upsampler DLL.
_ECI_BASE_RATE_MAP = {
	0: 8000,
	1: 11025,
	4: 16000,  # release reference: v21 EQ, 4 kHz Q1.5 and low bass
}
_current_sample_rate_mode = 1
_current_variant = 0
_presence_contour_enabled = True
_ECI_SAMPLE_RATE_PARAM = 5
_UTTERANCE_START_FADE_SECONDS = 0.002

_RATE_MARKER_PATH = os.path.join(os.path.dirname(__file__), "eloquence", "nativeRateMode.txt")


def _normalize_rate_mode(mode, default=1):
	try:
		mode = int(mode)
	except (TypeError, ValueError):
		return default
	# Migrate every retired native-16 comparison to the release reference.
	if 2 <= mode <= 22:
		return 4
	return mode if mode in _ECI_BASE_RATE_MAP else default


def _read_persisted_rate_mode(default=1):
	try:
		with open(_RATE_MARKER_PATH, "r", encoding="ascii") as f:
			return _normalize_rate_mode(f.read().strip(), default)
	except Exception:
		pass
	return default


def persist_rate_mode(mode):
	mode = _normalize_rate_mode(mode)
	try:
		with open(_RATE_MARKER_PATH, "w", encoding="ascii") as f:
			f.write(str(mode))
	except Exception:
		LOGGER.exception("Could not persist Eloquence sample-rate marker")
	return mode


_ENGINE_VARIANTS = ("chs", "DEU", "ENG", "ENU", "ESM", "ESP", "FIN", "FRA", "FRC", "ITA", "jpn", "kor", "PTB")

@functools.lru_cache(maxsize=256)
def _load_p16_patch(path):
	with open(path, "rb") as f:
		data = f.read()
	if len(data) < 16 or data[:4] != b"P16D":
		raise ValueError("invalid P16 patch")
	orig_size, new_size, count = struct.unpack_from("<III", data, 4)
	pos = 16
	runs = []
	for _ in range(count):
		off, old_len, new_len = struct.unpack_from("<III", data, pos)
		pos += 12
		old = data[pos:pos + old_len]
		pos += old_len
		new = data[pos:pos + new_len]
		pos += new_len
		runs.append((off, old, new))
	return orig_size, new_size, runs


def _apply_p16_to_data(data, patch_path, enable):
	"""Return *data* with one reversible P16 patch applied or removed."""
	orig_size, new_size, runs = _load_p16_patch(patch_path)
	data = bytearray(data)
	want_size = new_size if enable else orig_size
	if enable and len(data) < new_size:
		data.extend(b"\0" * (new_size - len(data)))
	for off, old, new in runs:
		src = old if enable else new
		dst = new if enable else old
		if src and data[off:off + len(src)] != src:
			if dst and data[off:off + len(dst)] == dst:
				continue
			raise RuntimeError("unexpected SYN bytes at 0x%X" % off)
		data[off:off + len(dst)] = dst
	if len(data) > want_size:
		del data[want_size:]
	elif len(data) < want_size:
		data.extend(b"\0" * (want_size - len(data)))
	return bytes(data)


def _apply_p16(path, patch_path, enable):
	with open(path, "rb") as f:
		data = f.read()
	data = _apply_p16_to_data(data, patch_path, enable)
	with open(path, "wb") as f:
		f.write(data)


def _p16_matches_data(data, patch_path, enabled):
	orig_size, new_size, runs = _load_p16_patch(patch_path)
	want_size = new_size if enabled else orig_size
	if len(data) != want_size:
		return False
	for off, old, new in runs:
		b = new if enabled else old
		if b and data[off:off + len(b)] != b:
			return False
	return True


def _p16_matches(path, patch_path, enabled):
	try:
		with open(path, "rb") as f:
			data = f.read()
	except Exception:
		return False
	return _p16_matches_data(data, patch_path, enabled)


def _prepare_syn_engines(mode, presence_enabled=None):
	"""Switch active SYN files between pristine 8/11 and compact native-16 variants."""
	base = os.path.join(os.path.dirname(__file__), "eloquence")
	mode = _normalize_rate_mode(mode)
	if presence_enabled is None:
		presence_enabled = get_presence_contour()
	target_ext = (".p16s1" if presence_enabled else ".p16s0") if mode == 4 else None
	for stem in _ENGINE_VARIANTS:
		candidates = (stem + ".SYN", stem.lower() + ".syn", stem.upper() + ".SYN")
		dst = next((os.path.join(base, n) for n in candidates if os.path.exists(os.path.join(base, n))), None)
		if not dst:
			LOGGER.warning("Could not locate active SYN for %s", stem)
			continue
		patches = [
			os.path.join(base, stem + ext)
			# Check derived variants before their base patches: a derived patch
			# contains every run from .p16n and would otherwise be mistaken for it.
			for ext in (
				".p16s1",
				".p16s0",
				".p16st",
				".p16fu",
				".p16fs",
				".p16c6",
				".p16b40",
				".p16b30",
				".p16b20",
				".p16b15",
				".p16b5",
				".p16n",
				".p16",
			)
			if os.path.exists(os.path.join(base, stem + ext))
		]
		try:
			# The old implementation reopened and reread the complete SYN module
			# once for every possible patch variant.  Keep the bytes in memory so
			# startup and native-rate changes need one read and at most one write
			# per language module instead.
			with open(dst, "rb") as f:
				original_data = f.read()
			data = original_data
			# Revert whichever compact native variant is currently active.
			for pp in patches:
				if _p16_matches_data(data, pp, True):
					data = _apply_p16_to_data(data, pp, False)
					break
			if target_ext:
				data = _apply_p16_to_data(data, os.path.join(base, stem + target_ext), True)
			if data != original_data:
				with open(dst, "wb") as f:
					f.write(data)
		except Exception:
			LOGGER.exception("Could not switch %s SYN engine", stem)
	labels = {4: "v21 EQ, 4 kHz +8 dB Q1.5 and low bass +2 dB"}
	LOGGER.info("Prepared Eloquence SYN engines for %s", labels.get(mode, "original 8/11 kHz"))


def get_sample_rate() -> int:
	return _current_sample_rate_mode


def get_presence_contour() -> bool:
	return _presence_contour_enabled


def set_presence_contour(enabled) -> bool:
	"""Select which native 16 kHz patch the next engine load should use."""
	global _presence_contour_enabled
	enabled = bool(enabled)
	changed = enabled != _presence_contour_enabled
	_presence_contour_enabled = enabled
	LOGGER.info("Eloquence 16 kHz presence contour %s", "enabled" if enabled else "disabled")
	return changed


def set_sample_rate(mode) -> None:
	"""Select an original-rate engine or the native 16 kHz reference."""
	global _current_sample_rate_mode, _current_variant
	mode = _normalize_rate_mode(mode)
	_current_sample_rate_mode = mode
	eci_value = 0 if mode == 0 else (2 if mode >= 2 else 1)
	LOGGER.info("Setting Eloquence sample-rate mode %d (ECI parameter 5 = %d)", mode, eci_value)
	try:
		response = _active.send_command("setParam", paramId=_ECI_SAMPLE_RATE_PARAM, value=eci_value)
		params.update(response.get("params", {}))
	except Exception:
		LOGGER.exception("Failed to set Eloquence sample rate")


def _fade_pcm16_start(data: bytes, position: int, total_samples: int) -> Tuple[bytes, int]:
	"""Apply the remaining part of a short linear fade to mono PCM16 audio."""
	if not data or position >= total_samples:
		return data, position
	if len(data) % 2:
		raise ValueError("PCM16 audio chunk has an odd byte length")

	output = bytearray(data)
	fade_samples = min(len(output) // 2, total_samples - position)
	denominator = max(1, total_samples - 1)
	for index in range(fade_samples):
		sample = struct.unpack_from("<h", output, index * 2)[0]
		gain = (position + index) / denominator
		struct.pack_into("<h", output, index * 2, round(sample * gain))
	return bytes(output), position + fade_samples


class AudioWorker(threading.Thread):
	def __init__(
		self,
		player: nvwave.WavePlayer,
		queue: "queue.Queue[Optional[AudioChunk]]",
		pipeline: "AudioPipeline",
	):
		super().__init__(daemon=True)
		self._player = player
		self._queue = queue
		self._pipeline = pipeline
		self._running = True
		self._stopping = False
		self._player_lock = threading.RLock()
		base_rate = _ECI_BASE_RATE_MAP.get(get_sample_rate(), _engine.SAMPLE_RATE)
		self._start_fade_samples = max(2, round(base_rate * _UTTERANCE_START_FADE_SECONDS))
		self._start_fade_position = 0
		self._last_audio_sequence: Optional[int] = None

	def run(self) -> None:
		pending_audio: Optional[AudioChunk] = None
		while self._running:
			try:
				chunk = self._queue.get(timeout=0.1)
			except queue.Empty:
				continue
			if chunk is None:
				break
			data, index, is_final, seq = chunk
			if pending_audio and pending_audio[3] < self._pipeline.sequence:
				pending_audio = None
			if seq < self._pipeline.sequence:
				self._queue.task_done()
				continue

			if data:
				# A two-millisecond ramp suppresses a discontinuity left by a cancelled
				# utterance or persistent native-EQ history. It is applied only at a
				# real utterance boundary, never at phoneme or audio-chunk boundaries.
				if seq != self._last_audio_sequence:
					self._start_fade_position = 0
					self._last_audio_sequence = seq
				data, self._start_fade_position = _fade_pcm16_start(
					data,
					self._start_fade_position,
					self._start_fade_samples,
				)
				chunk = (data, index, is_final, seq)
				# Hold one real Audio Chunk so a following index-only event can use
				# WavePlayer's completion callback without feeding a synthetic sample.
				if pending_audio:
					self._feed_audio(*pending_audio[:3])
				pending_audio = chunk
				if is_final:
					self._start_fade_position = 0
				self._queue.task_done()
				continue

			# The Eloquence Host Process reports Speech Indexes as index-only
			# events. Attach the notification to the preceding real Audio Chunk so
			# NVDA receives it only after that audio finishes playing.
			if pending_audio:
				pending_data, pending_index, pending_final, _pending_seq = pending_audio
				self._feed_audio(
					pending_data,
					index if index is not None else pending_index,
					pending_final,
				)
				pending_audio = None
				index = None
			if not self._stopping:
				if index is not None:
					self._sync_and_invoke_index(index)
				if is_final:
					self._start_fade_position = 0
					self._schedule_idle()
			self._queue.task_done()

	def _feed_audio(self, data: bytes, index: Optional[int], is_final: bool) -> None:
		"""Feed a real Audio Chunk and attach its Speech Progress Notification."""

		on_done = None
		if index is not None:

			def _callback(i=index):
				self._invoke_index_callback(i)

			on_done = _callback

		wrapped_on_done = self._make_on_done(on_done, is_final) if on_done or is_final else None

		# Early exit if stopping - avoids unnecessary lock acquisition
		if self._stopping:
			return

		# Feed directly - blocks if buffer is full
		try:
			with self._player_lock:
				if not self._stopping and self._player:
					self._player.feed(data, onDone=wrapped_on_done)
		except FileNotFoundError:
			LOGGER.warning("Sound device not found during feed")
		except Exception:
			LOGGER.exception("WavePlayer feed failed")

	def _sync_and_invoke_index(self, index: int) -> None:
		"""Report a Speech Index that has no real Audio Chunk to carry it."""
		try:
			with self._player_lock:
				if not self._stopping and self._player:
					self._player.sync()
		except Exception:
			LOGGER.exception("WavePlayer sync failed")
		if not self._stopping:
			self._invoke_index_callback(index)

	def stop(self) -> None:
		self._stopping = True
		self._running = False
		self._queue.put(None)

	def _make_on_done(self, callback, is_final: bool):
		def _on_done() -> None:
			try:
				if callback:
					callback()
			except Exception:
				LOGGER.exception("Index callback failed")
			if is_final:
				self._schedule_idle()

		return _on_done

	def _schedule_idle(self) -> None:
		"""Signal the player that playback is complete."""
		try:
			with self._player_lock:
				if not self._stopping and self._player:
					self._player.idle()
		except Exception:
			LOGGER.exception("WavePlayer idle failed")
		if not self._stopping:
			self._invoke_index_callback(None)

	def _invoke_index_callback(self, value: Optional[int]) -> None:
		global lastindex
		if value is not None:
			lastindex = value
		if onIndexReached:
			try:
				onIndexReached(value)
			except Exception:
				LOGGER.exception("Index callback failed")


AudioChunk = Tuple[bytes, Optional[int], bool, int]


# RPC client ---------------------------------------------------------------------
@dataclass
class HostProcess:
	process: subprocess.Popen
	connection: Any
	listener: _ipc.PipeListener


class AudioPipeline:
	"""The one Audio Playback Pipeline every backend feeds.

	There is deliberately a single instance of this even when both backends are
	live at once, which happens whenever openevv serves English and the Eloquence
	Host Process serves a language openevv does not have.  Two pipelines would
	mean two WavePlayers competing for the output device and two Speech
	Generation counters, so ordering and cancellation both live here instead of
	in either backend.
	"""

	def __init__(self) -> None:
		self.queue: "queue.Queue[Optional[AudioChunk]]" = queue.Queue()
		self.player: Optional[nvwave.WavePlayer] = None
		self.worker: Optional[AudioWorker] = None
		# Speech Generation.  Advanced on every cancellation; Audio Chunks stamped
		# with an older generation are discarded rather than played.
		self.sequence = 0
		self.current_seq = 0
		self.speaking = False
		self.stop_lock = threading.RLock()

	# ------------------------------------------------------------------
	def initialize_audio(self) -> None:
		if self.player:
			return
		sample_rate = _ECI_BASE_RATE_MAP.get(get_sample_rate(), _engine.SAMPLE_RATE)
		if version_year >= 2025:
			device = config.conf["audio"]["outputDevice"]
			player = nvwave.WavePlayer(
				_engine.CHANNELS, sample_rate, _engine.BITS_PER_SAMPLE, outputDevice=device
			)
		else:
			device = config.conf["speech"]["outputDevice"]
			nvwave.WavePlayer.MIN_BUFFER_MS = 1500
			player = nvwave.WavePlayer(
				_engine.CHANNELS,
				sample_rate,
				_engine.BITS_PER_SAMPLE,
				outputDevice=device,
				buffered=True,
			)
		self.player = player
		self.worker = AudioWorker(player, self.queue, self)
		self.worker.start()
		LOGGER.info("Eloquence audio initialized at %d Hz", sample_rate)

	# ------------------------------------------------------------------
	def close_audio(self) -> None:
		if self.worker:
			self.worker.stop()
			self.worker.join(timeout=1)
			self.worker = None
		if self.player:
			try:
				self.player.close()
			except Exception:
				LOGGER.exception("WavePlayer close failed")
			self.player = None
		# A rate switch creates a new worker.  Do not let its first read see the
		# previous worker's stop sentinel or late Audio Chunks from a backend that
		# was being shut down at the same time.
		self.queue = queue.Queue()

	# ------------------------------------------------------------------
	def handle_event(self, event: str, payload: Dict[str, Any]) -> None:
		if event == "audio":
			data = payload.get("data", b"")
			index = payload.get("index")
			is_final = bool(payload.get("final", False))
			self.queue.put((data, index, is_final, self.current_seq))
		elif event == "stopped":
			# Don't call player.stop() from this thread to avoid race conditions
			# The stop() method will handle player cleanup properly
			LOGGER.debug("Engine reported stopped event")
			self.speaking = False
		else:
			LOGGER.debug("Unhandled engine event %s", event)

	# ------------------------------------------------------------------
	def stop_player(self) -> None:
		if self.player:
			try:
				self.player.stop()
			except Exception:
				LOGGER.exception("WavePlayer stop failed")

	def cancel(self) -> None:
		"""Advance the Speech Generation and silence the device immediately."""
		self.sequence += 1
		self.stop_player()
		self.speaking = False


class EngineClient:
	"""One way of reaching an Eloquence Engine.

	Subclasses provide only transport: how a Host Command gets to an engine and
	how that engine's events come back.  Everything about what NVDA actually
	hears belongs to the shared AudioPipeline, so the backends cannot drift
	apart on any of it.
	"""

	def __init__(self, pipeline: AudioPipeline) -> None:
		self.pipeline = pipeline

	@property
	def started(self) -> bool:
		raise NotImplementedError

	def ensure_started(self) -> None:
		raise NotImplementedError

	def send_command(self, command: str, wait: bool = True, **payload: Any) -> Dict[str, Any]:
		raise NotImplementedError

	def stop(self) -> None:
		raise NotImplementedError

	def shutdown(self) -> None:
		raise NotImplementedError


class EloquenceHostClient(EngineClient):
	"""Drives the Eloquence Engine in a 32-bit Eloquence Host Process."""

	def __init__(self, pipeline: AudioPipeline) -> None:
		super().__init__(pipeline)
		self._host: Optional[HostProcess] = None
		# Outlives every Eloquence Host Process we spawn; closed only when NVDA exits.
		self._job: Optional[_job.HostJob] = None
		self._pending: Dict[int, threading.Event] = {}
		self._responses: Dict[int, Dict[str, Any]] = {}
		self._receiver: Optional[threading.Thread] = None
		self._id_counter = itertools.count(1)
		self._command_lock = threading.Lock()

	@property
	def started(self) -> bool:
		return self._host is not None

	# ------------------------------------------------------------------
	def ensure_started(self) -> None:
		if self._host:
			return
		addon_dir = os.path.abspath(os.path.dirname(__file__))
		listener = _ipc.create_listener()
		cmd = list(self._resolve_host_executable(addon_dir))
		cmd.extend(
			[
				"--pipe",
				listener.name,
				"--log-dir",
				addon_dir,
			]
		)
		LOGGER.info("Launching Eloquence host: %s", cmd)
		proc = subprocess.Popen(cmd, cwd=addon_dir)
		# Must precede accept(): the Host Channel identifies its peer by asking
		# whether that process is in this job.
		self._adopt_into_job(proc)
		try:
			conn = listener.accept(self._job, HOST_CONNECT_TIMEOUT)
		except (_ipc.HostChannelError, OSError) as exc:
			LOGGER.error("Eloquence host failed to connect: %s", exc)
			exit_code = proc.poll()
			if exit_code is not None:
				LOGGER.error("Host process already exited with code %s", exit_code)
			try:
				proc.terminate()
				proc.wait(timeout=2)
			except Exception:
				try:
					proc.kill()
				except Exception:
					pass
			try:
				listener.close()
			except Exception:
				pass
			raise RuntimeError(f"Eloquence host process failed to start: {exc}") from exc
		self._host = HostProcess(process=proc, connection=conn, listener=listener)
		self._receiver = threading.Thread(target=self._receiver_loop, daemon=True)
		self._receiver.start()

	def _adopt_into_job(self, proc: subprocess.Popen) -> None:
		"""Put a freshly spawned Eloquence Host Process into the kill-on-close Job Object.

		Called before the Host Channel is accepted so that an Eloquence Host Process
		that never connects is covered too.  Purely a backstop: shutdown() still drives the
		cooperative exit, and the job only decides what happens when NVDA dies
		without getting to run it.
		"""
		if self._job is None:
			self._job = _job.HostJob.create()
		if self._job is None:
			return
		try:
			handle = int(proc._handle)
		except Exception:
			LOGGER.warning(
				"Eloquence Host Process exposes no handle; skipping Job Object",
				exc_info=True,
			)
			return
		self._job.assign(handle)

	def _resolve_host_executable(self, addon_dir: str) -> Sequence[str]:
		override = os.environ.get("ELOQUENCE_HOST_COMMAND")
		if override:
			return shlex.split(override)
		exe_path = os.path.join(addon_dir, HOST_DIRECTORY, HOST_EXECUTABLE)
		if os.path.exists(exe_path):
			return [exe_path]
		# A onefile build from before the onedir switch, left over in a
		# development tree that has not re-run build_host.cmd.
		legacy_path = os.path.join(addon_dir, HOST_EXECUTABLE)
		if os.path.exists(legacy_path):
			LOGGER.warning("Using legacy onefile host at %s; re-run build_host.cmd", legacy_path)
			return [legacy_path]
		script_path = os.path.join(addon_dir, HOST_SCRIPT)
		if os.path.exists(script_path):
			raise RuntimeError(
				"Eloquence helper executable was not found."
				" Provide a 32-bit host via the ELOQUENCE_HOST_COMMAND environment"
				" variable when developing the add-on."
			)
		raise RuntimeError("Eloquence helper resources missing from add-on package")

	# ------------------------------------------------------------------
	def _receiver_loop(self) -> None:
		connection = self._host.connection if self._host else None
		if connection is None:
			return
		while True:
			try:
				message = connection.recv()
			except (EOFError, ConnectionAbortedError, OSError):
				# A dead Eloquence Host Process breaks the pipe immediately, so
				# this covers the exit the socket transport needed a poll to spot.
				LOGGER.info("Host connection closed")
				for msg_id, event in list(self._pending.items()):
					self._responses[msg_id] = {"error": "connectionClosed"}
					event.set()
				self._pending.clear()
				break
			except Exception:
				LOGGER.exception("Unexpected error in receiver loop")
				for msg_id, event in list(self._pending.items()):
					self._responses[msg_id] = {"error": "receiverException"}
					event.set()
				self._pending.clear()
				break
			msg_type = message.get("type")
			if msg_type == "response":
				msg_id = message["id"]
				# MEMORY LEAK PATCH: Only save if an event is waiting
				event = self._pending.pop(msg_id, None)
				if event:
					self._responses[msg_id] = message
					event.set()
			elif msg_type == "event":
				self.pipeline.handle_event(message["event"], message.get("payload", {}))
			else:
				LOGGER.warning("Unknown message type %s", msg_type)

	# ------------------------------------------------------------------
	def stop(self) -> None:
		if not self._host:
			return
		self.pipeline.cancel()
		# Tell the host to stop without blocking
		try:
			self.send_command("stop", wait=False)
		except Exception:
			pass

	# ------------------------------------------------------------------
	def send_command(self, command: str, wait: bool = True, **payload: Any) -> Dict[str, Any]:
		if not self._host:
			raise RuntimeError("Host not started")
		with self._command_lock:
			msg_id = next(self._id_counter)
			event = threading.Event() if wait else None
			if wait:
				self._pending[msg_id] = event
			try:
				self._host.connection.send(
					{
						"type": "command",
						"id": msg_id,
						"command": command,
						"payload": payload,
					}
				)
			except (ConnectionResetError, BrokenPipeError, OSError):
				# Patch for termination errors
				if wait:
					self._pending.pop(msg_id, None)
				return {}
			except Exception:
				if wait:
					self._pending.pop(msg_id, None)
				raise

			# If we are not going to wait for the response (e.g. stop command), return blank immediately
			if not wait:
				return {}

			# Wait for response with timeout to avoid infinite blocking
			if not event.wait(timeout=5.0):
				self._pending.pop(msg_id, None)
				LOGGER.error("Command %s timed out after 5 seconds", command)
				raise RuntimeError(f"Command {command} timed out")
			response = self._responses.pop(msg_id, {"error": "no response received"})
			if "error" in response:
				raise RuntimeError(response["error"])
			return response.get("payload", {})

	def set_param(self, param: int, value: int) -> None:
		"""Send a non-blocking ECI parameter change to the host."""
		if not self._host:
			return
		try:
			self.send_command("setParam", wait=False, paramId=int(param), value=int(value))
		except Exception:
			LOGGER.exception("Failed to send ECI parameter to host")

	# ------------------------------------------------------------------
	def shutdown(self) -> None:
		if not self._host:
			return
		# Send delete command to host (this will cause receiver to get EOFError)
		try:
			self.send_command("delete")
		except Exception:
			LOGGER.exception("Failed to delete host cleanly")
		# Let the host exit on its own before touching the socket. Closing the
		# connection first resets it underneath the host, which turns every
		# in-flight send into a ConnectionResetError; those escape the host's
		# serve loop as an unhandled exception and, in a --noconsole build,
		# surface as an error dialog.
		exited = False
		try:
			self._host.process.wait(timeout=HOST_EXIT_TIMEOUT)
			exited = True
		except Exception:
			LOGGER.warning(
				"Eloquence host did not exit within %ss; terminating",
				HOST_EXIT_TIMEOUT,
			)
		# Wait for receiver thread to finish (it will get EOFError and exit)
		if self._receiver:
			self._receiver.join(timeout=2)
			self._receiver = None
		# Now close connections, and terminate the process only if it is still up.
		try:
			self._host.connection.close()
		except Exception:
			pass
		try:
			self._host.listener.close()
		except Exception:
			pass
		if not exited:
			# terminate() is TerminateProcess on Windows and cannot be blocked, so
			# the bootloader never gets to clean up its _MEI directory. Only
			# reached when the graceful wait above timed out.
			try:
				self._host.process.terminate()
				self._host.process.wait(timeout=2)
			except Exception:
				LOGGER.exception("Failed to terminate host process")
				try:
					self._host.process.kill()
				except Exception:
					pass
		self._host = None


class DirectEngineClient(EngineClient):
	"""Drives an ECI-compatible engine inside NVDA's own process.

	Used for openevv's 64-bit eci.dll, which needs no Eloquence Host Process and
	no Host Channel.  It speaks the same Host Command protocol as the host
	backend, executed by the shared EciDispatcher, so both backends answer every
	command through one implementation.

	Commands run synchronously on the caller's thread.  That is the same shape
	the host has in practice -- the Eloquence Host Process serves its Host
	Channel single threaded, so a synthesize() there also blocks until the engine
	runs dry -- and the Synth Driver side only ever issues them from the
	EloquenceSynthWorker thread, never NVDA's UI thread.
	"""

	def __init__(self, pipeline: AudioPipeline, eci_path: str) -> None:
		super().__init__(pipeline)
		self._eci_path = eci_path
		self._dispatcher: Optional[_engine.EciDispatcher] = None
		self._command_lock = threading.RLock()
		# Set by stop() on NVDA's thread, acted on by the next command on the
		# synthesis worker, so the engine is only ever touched from one thread.
		self._reset_pending = False

	@property
	def started(self) -> bool:
		return self._dispatcher is not None

	@property
	def eci_path(self) -> str:
		return self._eci_path

	def ensure_started(self) -> None:
		if self._dispatcher is not None:
			return
		if not os.path.exists(self._eci_path):
			raise RuntimeError(f"openevv engine not found at {self._eci_path}")
		LOGGER.info("Loading the Eloquence Engine in process from %s", self._eci_path)
		self._dispatcher = _engine.EciDispatcher(self._handle_event_kwargs)

	def _handle_event_kwargs(self, event: str, **payload: Any) -> None:
		"""Adapt the engine's sink signature to the shared event handler.

		The host backend receives these as a pickled payload dict off the Host
		Channel; here they arrive as keyword arguments from the engine's own
		callback, on whichever thread the engine happens to be synthesizing on.
		"""
		self.pipeline.handle_event(event, payload)

	def send_command(self, command: str, wait: bool = True, **payload: Any) -> Dict[str, Any]:
		if self._dispatcher is None:
			raise RuntimeError("Engine not started")
		if not self._dispatcher.knows(command):
			raise RuntimeError("unknownCommand")
		# The lock serialises commands the way the Eloquence Host Process's single
		# threaded serve loop does, so a following utterance's addText cannot
		# reach the engine while the previous synthesize() is still running.
		with self._command_lock:
			self._apply_pending_reset()
			return self._dispatcher.handle(command, payload)

	def stop(self) -> None:
		if self._dispatcher is None:
			return
		# What makes cancellation audible is the same thing that makes it audible
		# on the host path: the Speech Generation advances, so Audio Chunks already
		# queued are dropped, and the player is stopped right now.
		self.pipeline.cancel()
		# The engine's own reset is only about not carrying state into the next
		# utterance, so it is left for the next command to perform on the synthesis
		# worker thread.  Doing it here would either block NVDA waiting for the
		# command lock that an in-flight synthesize() holds, or need a thread of
		# its own; both were tried, and every engine call belonging to one thread
		# is worth more than either.
		self._reset_pending = True

	def _apply_pending_reset(self) -> None:
		"""Reset the engine after a cancellation, on the calling worker thread."""
		if not self._reset_pending:
			return
		self._reset_pending = False
		engine = self._dispatcher.engine if self._dispatcher else None
		if engine is None:
			return
		try:
			engine.stop()
		except Exception:
			LOGGER.exception("Engine reset after cancellation failed")

	def shutdown(self) -> None:
		if self._dispatcher is None:
			return
		try:
			self.send_command("delete")
		except Exception:
			LOGGER.exception("Failed to delete the in-process engine cleanly")
		self._dispatcher = None


def openevv_engine_path() -> str:
	"""Where fetch_eci.py installs the openevv engine inside the add-on."""
	return os.path.join(os.path.abspath(os.path.dirname(__file__)), "openevv", "eci.dll")


def openevv_version() -> Optional[str]:
	"""The openevv release the add-on was built against, for the settings panel."""
	path = os.path.join(os.path.dirname(openevv_engine_path()), "openevv-version.txt")
	try:
		with open(path, encoding="utf-8") as f:
			return f.read().strip() or None
	except OSError:
		return None


_pipeline = AudioPipeline()
_client = EloquenceHostClient(_pipeline)
# Created only when openevv is selected; both backends can be live at once, since
# openevv serves the languages it has and the host serves the rest.
_direct_client: Optional[DirectEngineClient] = None
# The backend the next Host Command goes to.  Switched per fragment by
# set_voice(), which is the only place a Voice Identity changes.
_active: EngineClient = _client
# Voice IDs the in-process engine reported through eciGetAvailableLanguages.
# Empty means "use the host for everything", so a failed enumeration degrades to
# today's behaviour rather than to silence.
_direct_languages: frozenset = frozenset()
_engine_initialize_payload: Dict[str, Any] = {}
synth_queue = queue.Queue()
params: Dict[int, int] = {}
voice_params: Dict[int, int] = {}
lastindex: Optional[int] = None
onIndexReached = None
_synth_worker: Optional[threading.Thread] = None
_synth_worker_lock = threading.Lock()
_synth_worker_stop = threading.Event()


# Backend routing ----------------------------------------------------------------
def openevv_enabled() -> bool:
	"""Whether the user asked for the in-process openevv engine.

	The Eloquence Host Process is the default, and stays the default for any
	value this cannot read as an explicit yes.  NVDA stores this section without
	a confspec, so the value comes back as a string: ``bool("False")`` is True,
	which would have turned the engine on for a user who had just turned it off.
	"""
	raw = config.conf.get("eloquence", {}).get("use_openevv", False)
	if isinstance(raw, str):
		return raw.strip().lower() in {"true", "yes", "on", "1"}
	return bool(raw)


def openevv_available() -> bool:
	return os.path.exists(openevv_engine_path())


def direct_languages() -> frozenset:
	"""Voice IDs the in-process engine can serve, as the engine itself reports them.

	Queried rather than hardcoded so that an openevv release which adds a
	language starts serving it with no change here.
	"""
	return _direct_languages


def backend_for_voice(voice_id) -> EngineClient:
	"""Pick the backend that can speak *voice_id*.

	openevv currently ships US English only, so anything else falls back to the
	Eloquence Host Process.  The host is started lazily: a user who only ever
	speaks a language openevv has never pays for the process at all.
	"""
	# The native 8/16 kHz modes and all SYN corrections belong to the proprietary
	# engine.  openevv currently produces 11.025 kHz audio and must never be fed
	# into a player configured for another rate.
	if get_sample_rate() != 1 or _direct_client is None:
		return _client
	try:
		numeric_voice = int(voice_id)
	except (TypeError, ValueError):
		return _client
	if numeric_voice in _direct_languages:
		return _direct_client
	return _client


def current_generation() -> int:
	"""The Speech Generation to stamp newly queued synthesis work with.

	Public because the Synth Driver needs it when queueing an utterance.  It used
	to reach into the host client's private counter, which broke silently the
	moment that counter moved to the shared Audio Playback Pipeline.
	"""
	return _pipeline.sequence


def voice_uses_direct_backend(voice_id) -> bool:
	"""Whether *voice_id* will be spoken by the in-process engine.

	The Eloquence Text Builder needs this per fragment, because the openevv
	bracket workaround must not be applied to text bound for the proprietary
	engine, which does not have the bug.
	"""
	if _direct_client is None:
		return False
	return backend_for_voice(voice_id) is _direct_client


def _activate(backend: EngineClient) -> None:
	"""Make *backend* the target of following Host Commands.

	Called on the EloquenceSynthWorker thread, in the order fragments were
	queued, so switching here is what keeps a mixed-language utterance in
	order: the outgoing backend has already returned from its synthesize()
	before the incoming one is given any text.
	"""
	global _active
	if backend is _active:
		return
	previous = _active
	_active = backend
	LOGGER.debug(
		"Switching Eloquence backend from %s to %s",
		type(previous).__name__,
		type(backend).__name__,
	)
	if not backend.started:
		backend.ensure_started()
		if _engine_initialize_payload:
			payload = dict(_engine_initialize_payload)
			if backend is _direct_client:
				payload = _direct_initialize_payload(payload)
			response = backend.send_command("initialize", **payload)
			params.update(response.get("params", {}))
			voice_params.update(response.get("voiceParams", {}))


def _direct_initialize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
	"""Retarget an initialize payload at the in-process openevv engine.

	openevv resolves its own data relative to the DLL and ships an eci.ini that
	needs none of the C:\\dummy\\ rewriting the proprietary ECI.INI does.

	``dataDirectory`` is cleared deliberately, and it is a real feature gap rather
	than a tidy-up: openevv's eciLoadDict rejects the pronunciation dictionaries
	the add-on ships and the ones users add, so a custom dictionary only takes
	effect on the Eloquence Host Process backend.  See _load_dictionaries().
	"""
	payload = dict(payload)
	payload["eciPath"] = openevv_engine_path()
	payload["dataDirectory"] = ""
	payload["rewriteIni"] = False
	# openevv v0.3's eciStop wedges the engine and then crashes it; see
	# EciEngine.stop() for the measurements.  Nothing is lost by not calling it.
	payload["supportsEciStop"] = False
	return payload


# Public API ---------------------------------------------------------------------
hsz = 1
pitch = 2
fluctuation = 3
rgh = 4
bth = 5
rate = 6
vlm = 7
PARAM_MAX = {
	rate: 250,
	pitch: 100,
	vlm: 100,
	hsz: 100,
	fluctuation: 100,
	rgh: 100,
	bth: 100,
}
# Temporary prosody changes (e.g. raised pitch for a capital letter) that are
# currently in effect, as {param: (multiplier, offset)}.  set_voice() re-applies
# these after a language change; without that, the base-param restore it does
# would silently cancel a caps pitch raise queued just before the voice switch
# (issue #130).
_active_temp_prosody: Dict[int, Tuple[float, int]] = {}
eciPath = os.path.abspath(os.path.join(os.path.dirname(__file__), "eloquence", "eci.dll"))
langs = {
	"esm": (131073, "Latin American Spanish"),
	"esp": (131072, "Castilian Spanish"),
	"ptb": (458752, "Brazilian Portuguese"),
	"frc": (196609, "French Canadian"),
	"fra": (196608, "French"),
	"fin": (589824, "Finnish"),
	"deu": (262144, "German"),
	"ita": (327680, "Italian"),
	"enu": (65536, "American English"),
	"eng": (65537, "British English"),
	"chs": (393216, "Mandarin Chinese"),  # 0x00060000
	"jpn": (524288, "Japanese"),  # 0x00080000
	"kor": (655360, "Korean"),
}  # 0x000A0000


def _ascii_safe_dir(directory):
	"""Return *directory* as an ASCII path the ANSI ECI engine can open, or ``None``.

	The 32-bit ECI engine opens the ``.syn`` voice files named in ECI.INI with
	ANSI file APIs, and we rewrite those entries through a latin-1 round-trip.
	Both break when the add-on lives under a folder whose name contains
	characters outside Latin-1/the system code page (e.g. ``C:\\Users\\测试``):
	the latin-1 write raises ``UnicodeEncodeError`` and, even if it didn't, the
	engine could not open the path.  A folder that is non-ASCII yet latin-1
	encodable (e.g. ``café``) is just as unsafe: the latin-1 write succeeds but
	produces bytes the UTF-8 host cannot decode.  For such folders we substitute
	the Windows 8.3 short path, which is pure ASCII and therefore safe for both
	the write and the engine's ANSI open.  Pure-ASCII folders (the common case)
	are returned unchanged.  When no ASCII form is available -- 8.3 short names
	disabled on the volume, or a short name that is itself non-ASCII -- we return
	``None`` so the caller can leave ECI.INI untouched rather than write a file
	the UTF-8 host cannot read.
	"""
	try:
		directory.encode("ascii")
		return directory
	except UnicodeEncodeError:
		pass
	import ctypes
	from ctypes import wintypes

	get_short_path = ctypes.windll.kernel32.GetShortPathNameW
	get_short_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
	get_short_path.restype = wintypes.DWORD
	needed = get_short_path(directory, None, 0)
	if needed:
		buffer = ctypes.create_unicode_buffer(needed)
		if get_short_path(directory, buffer, needed):
			short_path = buffer.value
			try:
				short_path.encode("ascii")
			except UnicodeEncodeError:
				return None
			return short_path
	return None


def _sync_eci_ini_paths(eloquence_dir):
	"""Rewrite the absolute ``Path=`` entries in ECI.INI to the current location.

	The ECI engine reads each language's ``.syn`` voice file via an absolute
	path stored in ECI.INI.  When the add-on is copied to a portable NVDA, a
	different Windows account, or any other folder, those baked-in paths no
	longer exist and Eloquence fails to load.  Rewriting them on every start
	makes the add-on self-healing regardless of where it lives or who runs it.
	"""
	import re

	ini_path = os.path.join(eloquence_dir, "ECI.INI")
	if not os.path.isfile(ini_path):
		return
	# Match "Path=<anything>\<name>.syn", keeping only the file name so we can
	# re-anchor it to the real add-on directory.
	path_re = re.compile(r"(?im)^(\s*Path\s*=\s*).*?[\\/]?([^\\/\r\n]+\.syn)\s*$")

	# Anchor to an ASCII-only form of the directory.  ASCII is a subset of both
	# latin-1 (our lossless write encoding) and UTF-8 (how host_eloquence32.py
	# reads ECI.INI back), so an ASCII path is safe for the write, the ANSI ECI
	# engine's open, and the host's later UTF-8 read alike.  When no ASCII form
	# is available -- a non-ASCII add-on folder on a volume with 8.3 short names
	# disabled -- leave ECI.INI untouched and continue startup rather than write
	# a latin-1 file the UTF-8 host could not read.
	safe_dir = _ascii_safe_dir(eloquence_dir)
	if safe_dir is None:
		LOGGER.warning(
			"Skipping ECI.INI voice path update: no ASCII-safe form of %s is "
			"available (enable 8.3 short name creation or move the add-on to an "
			"ASCII path)",
			eloquence_dir,
		)
		return

	# Past the guard above, safe_dir is guaranteed non-None; bind it to a local
	# the _replace closure can use without it re-widening to ``str | None``.
	anchor_dir = safe_dir

	def _replace(match):
		filename = match.group(2)
		new_path = os.path.join(anchor_dir, filename)
		return f"{match.group(1)}{new_path}"

	try:
		# latin-1 is a lossless byte<->char mapping, so we never corrupt the
		# binary-ish ECI.INI content while editing only the Path lines, and
		# because safe_dir is ASCII every rewritten Path line stays UTF-8-clean.
		with open(ini_path, "r", encoding="latin-1") as f:
			original = f.read()
		updated = path_re.sub(_replace, original)
		if updated != original:
			# Encode before opening for write so any unexpected encoding failure
			# raises *before* we truncate and destroy the existing ECI.INI,
			# leaving the prior file intact.
			data = updated.encode("latin-1")
			with open(ini_path, "wb") as f:
				f.write(data)
			LOGGER.info("Updated ECI.INI voice paths for current location: %s", eloquence_dir)
	except (OSError, UnicodeError):
		# Read-only locations (e.g. secure screen systemConfig) are best-effort;
		# never abort initialize() over a failed INI rewrite.  UnicodeError stays
		# a defensive backstop -- the ASCII safe_dir makes the write encodable,
		# but a best-effort rewrite must never crash startup.
		LOGGER.exception("Could not update ECI.INI voice paths")


def initialize(indexCallback=None, prepare_engines=True):
	global onIndexReached, _current_sample_rate_mode, _current_variant, _presence_contour_enabled
	global _direct_client, _direct_languages, _active, _engine_initialize_payload
	config_default = _normalize_rate_mode(config.conf.get("eloquence", {}).get("sampleRate", 1))
	configured_mode = _read_persisted_rate_mode(config_default)
	_current_sample_rate_mode = configured_mode
	if prepare_engines:
		_presence_contour_enabled = bool(
			config.conf.get("speech", {}).get("eci", {}).get("presenceContour", True)
		)
		_prepare_syn_engines(configured_mode)
	eci_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "eloquence", "eci.dll"))
	# Repair ECI.INI before the host loads the engine so voices resolve no
	# matter where this add-on folder was copied from.
	_sync_eci_ini_paths(os.path.dirname(eci_path))
	_pipeline.initialize_audio()
	_ensure_synth_worker()
	onIndexReached = indexCallback
	voice_conf = config.conf.get("speech", {}).get("eci", {})
	try:
		_current_variant = int(voice_conf.get("variant", 0) or 0)
	except (TypeError, ValueError):
		_current_variant = 0
	payload = {
		"eciPath": eci_path,
		"dataDirectory": os.path.join(os.path.dirname(eci_path)),
		"language": voice_conf.get("voice", "enu"),
		"enableAbbreviationDict": config.conf.get("speech", {}).get("eci", {}).get("ABRDICT", False),
		"enablePhrasePrediction": config.conf.get("speech", {}).get("eci", {}).get("phrasePrediction", False),
		"voiceVariant": _current_variant,
	}
	_engine_initialize_payload = dict(payload)

	# Ask the in-process engine what it can actually speak before routing
	# anything to it.  An engine that cannot be loaded or enumerated leaves
	# _direct_languages empty, which routes everything to the host.
	_direct_client = None
	_direct_languages = frozenset()
	if openevv_enabled():
		if not openevv_available():
			LOGGER.warning(
				"openevv was selected but no engine is present at %s; using the "
				"Eloquence Host Process instead",
				openevv_engine_path(),
			)
		else:
			languages = _engine.available_languages(openevv_engine_path())
			if languages:
				_direct_client = DirectEngineClient(_pipeline, openevv_engine_path())
				_direct_languages = languages
				LOGGER.info(
					"openevv reports %d language(s): %s",
					len(languages),
					", ".join(sorted(_engine.LANG_BY_ID.get(i, hex(i)) for i in languages)),
				)
			else:
				LOGGER.warning(
					"openevv at %s reported no languages; using the Eloquence "
					"Host Process instead",
					openevv_engine_path(),
				)

	# Start on whichever backend owns the configured voice, so an English-only
	# user never spawns the Eloquence Host Process at all.
	initial_voice = _engine.LANGS.get(payload["language"], _engine.LANGS["enu"])
	_active = backend_for_voice(initial_voice)
	_active.ensure_started()
	active_payload = payload
	if _active is _direct_client:
		active_payload = _direct_initialize_payload(payload)
	response = _active.send_command("initialize", **active_payload)
	params.update(response.get("params", {}))
	voice_params.update(response.get("voiceParams", {}))
	# The ECI engine must be initialized before parameter 5 can be applied.
	# This also makes a persisted experimental mode survive an NVDA restart.
	set_sample_rate(_current_sample_rate_mode)


def restart_for_sample_rate(mode, indexCallback=None, variant=None):
	"""Restart both backends after changing the engine and playback sample rate."""
	global _current_sample_rate_mode, _current_variant
	mode = _normalize_rate_mode(mode)
	persist_rate_mode(mode)
	# Save the current voice, voice variant (synthesis model), and user voice
	# parameters before the host goes away.  eciSetParam(9) can reset a copied
	# voice model, so the variant must survive independently of the parameters.
	saved_voice = params.get(9)
	saved_vparams = dict(voice_params)
	try:
		saved_variant = int(_current_variant if variant is None else variant)
	except (TypeError, ValueError):
		saved_variant = 0
	# The v22 audio pipeline is shared by the proprietary host and openevv.  A
	# rate change therefore needs one clean backend and player restart; it also
	# guarantees that Windows has released every mapped SYN before we patch it.
	stop()
	terminate()
	_prepare_syn_engines(mode)
	_current_sample_rate_mode = mode
	initialize(indexCallback, prepare_engines=False)
	# Restore the selected synthesis model before restoring the language voice.
	# set_voice() re-applies _current_variant immediately after eciSetParam(9),
	# because changing language can otherwise drop copied variants such as the
	# female Shelly/Sandy/Grandma models.
	_current_variant = saved_variant
	if saved_voice is not None:
		try:
			set_voice(int(saved_voice))
		except Exception:
			LOGGER.exception("Could not restore Eloquence voice after sample-rate reload")
	elif saved_variant:
		try:
			setVariant(saved_variant)
		except Exception:
			LOGGER.exception("Could not restore Eloquence voice variant after sample-rate reload")
	for pr, value in saved_vparams.items():
		try:
			setVParam(int(pr), int(value))
		except Exception:
			LOGGER.exception("Could not restore Eloquence voice parameter %s", pr)
	LOGGER.info("Reloaded Eloquence engine for sample-rate mode %d", mode)


def speak(text_bytes):
	try:
		_active.send_command("addText", text=text_bytes, wait=False)
	except Exception:
		LOGGER.exception("Failed to send text to synthesizer")


def index(idx):
	try:
		_active.send_command("insertIndex", value=int(idx), wait=False)
	except Exception:
		LOGGER.exception("Failed to insert index")


def cmdProsody(pr, multiplier, offset=0):
	"""
	Apply a prosody change using the current base value from voice_params.

	Called at synthesis time so voice_params[pr] reflects the latest base.
	Computes: value = base * multiplier + offset
	For caps pitch: NVDA sends multiplier=1, offset=30 (or similar).
	For revert: NVDA sends multiplier=1, offset=0.
	Uses temporary=True so voice_params is never corrupted.
	"""
	if multiplier == 1 and offset == 0:
		_active_temp_prosody.pop(pr, None)
	else:
		_active_temp_prosody[pr] = (multiplier, offset)
	base = getVParam(pr)
	value = int(base * multiplier + offset)
	# Clamp to valid ECI parameter range.
	value = max(0, min(value, PARAM_MAX.get(pr, 100)))
	setVParam(pr, value, temporary=True)


def synth():
	try:
		_active.send_command("synthesize")
	except Exception:
		LOGGER.exception("Failed to start synthesis")


def stop():
	# NVDA re-sends any still-applicable prosody commands with the next
	# utterance, so pending temporary prosody dies with the cancelled speech.
	_active_temp_prosody.clear()
	# Cancel every backend that is live, not just the active one: a mixed-language
	# utterance may have left audio queued from the other.
	for backend in (_client, _direct_client):
		if backend is not None and backend.started:
			backend.stop()


def pause(switch):
	if _pipeline.player:
		_pipeline.player.pause(switch)


def close_audio():
	_pipeline.close_audio()


def terminate():
	global _direct_client, _active
	_pipeline.close_audio()
	for backend in (_client, _direct_client):
		if backend is not None and backend.started:
			try:
				backend.shutdown()
			except Exception:
				LOGGER.exception("Failed to shut down %s", type(backend).__name__)
	_direct_client = None
	_active = _client
	_stop_synth_worker()


def set_voice(vl):
	try:
		voice_id = int(vl)
		# Save the user-configured voice params before the language change.
		# The host re-reads all voice params from the DLL after eciSetParam(9),
		# but the DLL may still hold temporary prosody values (e.g. elevated
		# pitch for a capital letter).  If we blindly accept those re-read
		# values, the temporary pitch becomes the new permanent base and the
		# pitch never reverts -- the "stuck pitch on language change" bug.
		saved_vparams = dict(voice_params)
		# Route this Voice Identity to whichever backend has it before any
		# further command is sent.  _activate() starts and initializes the
		# incoming backend on first use.
		_activate(backend_for_voice(voice_id))
		response = _active.send_command("setParam", paramId=9, value=voice_id)
		params.update(response.get("params", {}))
		# Selecting a language can reset eciCopyVoice's synthesis model.  Re-apply
		# the active variant before restoring the user's parameter values so female
		# variants (Shelly/Sandy/Grandma) and the other copied models survive both
		# language changes and the native-16 host reload.
		if _current_variant:
			try:
				_active.send_command("copyVoice", variant=int(_current_variant))
			except Exception:
				LOGGER.exception("Failed to re-apply voice variant after language change")
		# Do NOT update voice_params from the setParam/copyVoice responses.  Instead,
		# restore the user's base values and push them to the DLL so the new
		# language uses the correct settings, not stuck temporary ones or variant
		# defaults.
		for pr, val in saved_vparams.items():
			voice_params[pr] = val
			try:
				_active.send_command(
					"setVoiceParam",
					paramId=int(pr),
					value=int(val),
					temporary=False,
				)
			except Exception:
				pass
		# Re-apply any temporary prosody still in effect (e.g. the raised pitch
		# for a capital letter when the language change lands between the pitch
		# raise and its revert).  The base-param restore above would otherwise
		# cancel it and the capital would speak at normal pitch (issue #130).
		for pr, (multiplier, offset) in _active_temp_prosody.items():
			value = int(voice_params.get(pr, 0) * multiplier + offset)
			value = max(0, min(value, PARAM_MAX.get(pr, 100)))
			setVParam(pr, value, temporary=True)
		LOGGER.debug("Voice changed to ID %d", voice_id)
	except Exception:
		LOGGER.exception("Failed to set voice")


def getVParam(pr):
	val = voice_params.get(pr, 0)
	return val


def setVParam(pr, vl, temporary=False):
	try:
		response = _active.send_command(
			"setVoiceParam", paramId=int(pr), value=int(vl), temporary=bool(temporary), wait=False
		)
		if not temporary:
			voice_params[pr] = response.get("voiceParams", {}).get(pr, vl)
	except Exception:
		LOGGER.exception("Failed to set voice parameter")


def setVariant(v):
	global _current_variant
	try:
		_current_variant = int(v)
		response = _active.send_command("copyVoice", variant=_current_variant)
		voice_params.update(response.get("voiceParams", {}))
	except Exception:
		LOGGER.exception("Failed to set variant")
	# Keep an already-started idle backend in step, so switching language later
	# does not silently revert the variant the user chose.
	for backend in (_client, _direct_client):
		if backend is None or backend is _active or not backend.started:
			continue
		try:
			backend.send_command("copyVoice", variant=int(v))
		except Exception:
			LOGGER.exception("Failed to mirror variant onto %s", type(backend).__name__)


def process():
	_ensure_synth_worker()


def _synth_worker_loop() -> None:
	while True:
		try:
			item = synth_queue.get(timeout=0.1)
		except queue.Empty:
			if _synth_worker_stop.is_set():
				break
			continue
		if item is None:
			synth_queue.task_done()
			break
		lst, seq = item
		if seq < _pipeline.sequence:
			synth_queue.task_done()
			continue
		_pipeline.current_seq = seq
		try:
			for func, args in lst:
				try:
					func(*args)
				except Exception:
					LOGGER.exception("Synthesis command failed")
		finally:
			synth_queue.task_done()


def _ensure_synth_worker() -> None:
	global _synth_worker
	with _synth_worker_lock:
		if _synth_worker and _synth_worker.is_alive():
			return
		_synth_worker_stop.clear()
		_synth_worker = threading.Thread(target=_synth_worker_loop, name="EloquenceSynthWorker", daemon=True)
		_synth_worker.start()


def _stop_synth_worker() -> None:
	global _synth_worker
	with _synth_worker_lock:
		if not _synth_worker:
			return
		_synth_worker_stop.set()
		synth_queue.put(None)
		_synth_worker.join(timeout=1)
		if _synth_worker.is_alive():
			LOGGER.warning("Synthesis worker failed to terminate cleanly")
		_synth_worker = None
		_synth_worker_stop.clear()


def eciCheck() -> bool:
	eci_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "eloquence", "eci.dll"))
	return os.path.exists(eci_path)
