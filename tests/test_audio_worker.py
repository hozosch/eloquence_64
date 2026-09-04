import importlib.util
import queue
import struct
import sys
import types
import unittest
from unittest import mock
from pathlib import Path


def _load_client_module():
	config_module = types.ModuleType("config")
	config_module.conf = {}
	nvwave_module = types.ModuleType("nvwave")
	nvwave_module.WavePlayer = object
	build_version_module = types.ModuleType("buildVersion")
	build_version_module.version_year = 2026
	ipc_module = types.ModuleType("addon.synthDrivers._eloquence_ipc")
	job_module = types.ModuleType("addon.synthDrivers._eloquence_job")

	stubs = {
		"config": config_module,
		"nvwave": nvwave_module,
		"buildVersion": build_version_module,
		"addon.synthDrivers._eloquence_ipc": ipc_module,
		"addon.synthDrivers._eloquence_job": job_module,
	}
	previous = {name: sys.modules.get(name) for name in stubs}
	sys.modules.update(stubs)
	module_name = "addon.synthDrivers._eloquence_audio_test"
	try:
		path = Path(__file__).parents[1] / "addon" / "synthDrivers" / "_eloquence.py"
		spec = importlib.util.spec_from_file_location(module_name, path)
		module = importlib.util.module_from_spec(spec)
		sys.modules[module_name] = module
		spec.loader.exec_module(module)
		return module
	finally:
		sys.modules.pop(module_name, None)
		for name, old_module in previous.items():
			if old_module is None:
				sys.modules.pop(name, None)
			else:
				sys.modules[name] = old_module


class FakePlayer:
	def __init__(self, events):
		self.events = events
		self.on_done = []

	def feed(self, data, onDone=None):
		self.events.append(("feed", data))
		if onDone:
			self.on_done.append(onDone)

	def sync(self):
		self.events.append(("sync", None))
		while self.on_done:
			self.on_done.pop(0)()

	def idle(self):
		self.events.append(("idle", None))
		self.sync()


class FakeClient:
	_sequence = 0


class FakeHostProcess:
	def poll(self):
		return None


class SampleRateModeTests(unittest.TestCase):
	def test_release_keeps_only_one_native16_mode(self):
		module = _load_client_module()
		self.assertEqual(
			module._ECI_BASE_RATE_MAP,
			{
				0: 8000,
				1: 11025,
				4: 16000,
			},
		)

	def test_retired_native16_modes_migrate_to_the_release_reference(self):
		module = _load_client_module()
		self.assertEqual(module._normalize_rate_mode(4), 4)
		for old_mode in set(range(2, 23)) - {4}:
			with self.subTest(old_mode=old_mode):
				self.assertEqual(module._normalize_rate_mode(old_mode), 4)
		self.assertEqual(module._normalize_rate_mode(0), 0)
		self.assertEqual(module._normalize_rate_mode(1), 1)
		self.assertEqual(module._normalize_rate_mode(23), 1)

	def test_audio_worker_does_not_apply_a_client_side_eq(self):
		module = _load_client_module()
		module._current_sample_rate_mode = 4
		events = []
		worker = module.AudioWorker(FakePlayer(events), queue.Queue(), FakeClient())
		data = b"\x00\x00\x34\x12\xff\x7f"
		worker._feed_audio(data, None, False)
		self.assertEqual(events, [("feed", data)])
		self.assertFalse(hasattr(worker, "_bandwidth_filter"))

	def test_presence_contour_selects_a_native_patch_variant(self):
		module = _load_client_module()
		self.assertTrue(module.get_presence_contour())
		self.assertTrue(module.set_presence_contour(False))
		self.assertFalse(module.get_presence_contour())
		self.assertFalse(module.set_presence_contour(False))
		self.assertTrue(module.set_presence_contour(True))


class WarmEngineReloadTests(unittest.TestCase):
	def test_unload_engine_keeps_supported_host(self):
		module = _load_client_module()
		client = module.EloquenceHostClient()
		client._host = types.SimpleNamespace(process=FakeHostProcess())
		client.close_audio = mock.Mock()
		client.send_command = mock.Mock(return_value={"status": "ok"})

		self.assertTrue(client.unload_engine())
		client.close_audio.assert_called_once_with()
		client.send_command.assert_called_once_with("unload")

	def test_unload_engine_rejects_legacy_host(self):
		module = _load_client_module()
		client = module.EloquenceHostClient()
		client._host = types.SimpleNamespace(process=FakeHostProcess())
		client.close_audio = mock.Mock()
		client.send_command = mock.Mock(side_effect=RuntimeError("unknownCommand"))

		self.assertFalse(client.unload_engine())


class AudioWorkerTests(unittest.TestCase):
	def test_pcm16_start_fade_is_continuous_across_chunks(self):
		module = _load_client_module()
		first, position = module._fade_pcm16_start(struct.pack("<2h", 1000, 1000), 0, 4)
		last, position = module._fade_pcm16_start(struct.pack("<3h", 1000, 1000, 1000), position, 4)

		self.assertEqual(struct.unpack("<2h", first), (0, 333))
		self.assertEqual(struct.unpack("<3h", last), (667, 1000, 1000))
		self.assertEqual(position, 4)

	def test_audio_worker_uses_a_two_millisecond_fade_at_the_current_rate(self):
		module = _load_client_module()
		module._current_sample_rate_mode = 4
		worker = module.AudioWorker(FakePlayer([]), queue.Queue(), FakeClient())
		self.assertEqual(worker._start_fade_samples, 32)

		module._current_sample_rate_mode = 1
		worker = module.AudioWorker(FakePlayer([]), queue.Queue(), FakeClient())
		self.assertEqual(worker._start_fade_samples, 22)

	def test_new_sequence_restarts_the_start_fade(self):
		module = _load_client_module()
		events = []
		audio_queue = queue.Queue()
		audio_queue.put((struct.pack("<2h", 1000, 1000), None, False, 0))
		audio_queue.put((struct.pack("<2h", 1000, 1000), None, False, 1))
		audio_queue.put((b"", None, False, 1))
		audio_queue.put(None)

		module.AudioWorker(FakePlayer(events), audio_queue, FakeClient()).run()

		feeds = [data for event, data in events if event == "feed"]
		self.assertEqual(len(feeds), 2)
		self.assertEqual([struct.unpack_from("<h", data)[0] for data in feeds], [0, 0])

	def test_index_notification_waits_for_preceding_audio(self):
		# Index-only chunks must never reach WavePlayer.feed: degenerate tiny
		# buffers can cause audible clicks on some devices (see #127). Attach the
		# Speech Progress Notification to the preceding real Audio Chunk instead.
		module = _load_client_module()
		events = []
		module.onIndexReached = lambda index: events.append(("index", index))
		audio_queue = queue.Queue()
		audio = b"\x00\x00\x00\x00"
		audio_queue.put((audio, None, False, 0))
		audio_queue.put((b"", 42, False, 0))
		audio_queue.put(None)
		player = FakePlayer(events)
		worker = module.AudioWorker(player, audio_queue, FakeClient())

		worker.run()

		self.assertEqual(events, [("feed", audio)])
		self.assertEqual(len(player.on_done), 1)

		player.on_done[0]()

		self.assertEqual(events, [("feed", audio), ("index", 42)])

	def test_index_notification_is_attached_to_last_preceding_audio_chunk(self):
		module = _load_client_module()
		events = []
		module.onIndexReached = lambda index: events.append(("index", index))
		audio_queue = queue.Queue()
		first = b"\x00\x00"
		last = b"\x00\x00\x00\x00"
		audio_queue.put((first, None, False, 0))
		audio_queue.put((last, None, False, 0))
		audio_queue.put((b"", 42, False, 0))
		audio_queue.put(None)
		player = FakePlayer(events)

		module.AudioWorker(player, audio_queue, FakeClient()).run()

		self.assertEqual(events, [("feed", first), ("feed", last)])
		self.assertEqual(len(player.on_done), 1)
		player.on_done[0]()
		self.assertEqual(events[-1], ("index", 42))

	def test_completion_follows_preceding_index_and_audio(self):
		module = _load_client_module()
		events = []
		module.onIndexReached = lambda index: events.append(("index", index))
		audio_queue = queue.Queue()
		audio = b"\x00\x00\x00\x00"
		audio_queue.put((audio, None, False, 0))
		audio_queue.put((b"", 42, False, 0))
		audio_queue.put((b"", None, True, 0))
		audio_queue.put(None)
		player = FakePlayer(events)

		module.AudioWorker(player, audio_queue, FakeClient()).run()

		self.assertLess(events.index(("feed", audio)), events.index(("index", 42)))
		self.assertLess(events.index(("index", 42)), events.index(("index", None)))


if __name__ == "__main__":
	unittest.main()
