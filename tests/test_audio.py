"""Regression tests for recorded audio and realtime completion, without a microphone/API."""
import queue
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from translator_app import App, MicStream, RealtimeSession, SR, RT_RATE, has_audio_signal
from audio_meter import AudioMeter, spectrum_levels


def speech_signal():
    t = np.arange(SR, dtype=np.float32) / SR
    return (0.08 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class AudioSignalTests(unittest.TestCase):
    def test_sustained_signal_is_available_for_recovery(self):
        self.assertTrue(has_audio_signal(speech_signal()))

    def test_silence_dc_and_one_loud_click_are_not_sustained_signal(self):
        click = np.zeros(SR, dtype=np.float32)
        click[SR // 2] = 0.512
        for audio in (np.zeros(SR), np.full(SR, 0.512), click, np.zeros(0)):
            with self.subTest(kind=str(audio.shape)):
                self.assertFalse(has_audio_signal(audio))

    def test_manual_gain_does_not_flatten_loud_voice(self):
        app = SimpleNamespace(cfg={"gain": 4})
        original = np.array([0.1, 0.3, 0.512, -0.512], dtype=np.float32)
        amplified, peak = App.apply_gain(app, original)
        self.assertAlmostEqual(peak, 0.512, places=5)
        self.assertLessEqual(float(np.max(np.abs(amplified))), 0.951)
        self.assertTrue(np.allclose(amplified / original, amplified[0] / original[0]))

    def test_realtime_pcm_limits_gain_before_clipping(self):
        session = SimpleNamespace(gain=4)
        pcm = RealtimeSession._pcm(session, np.array([0.3, 0.512, -0.512]), 24000)
        samples = np.frombuffer(pcm, dtype="<i2") / 32767
        self.assertLessEqual(float(np.max(np.abs(samples))), 0.951)
        self.assertLess(float(samples[0]), float(samples[1]))

    def test_permanent_microphone_updates_monitor_between_recordings(self):
        app = SimpleNamespace(update_audio_monitor=Mock())
        mic = MicStream(app)
        chunk = speech_signal()[:320, None]
        mic.cb(chunk, len(chunk), None, None)
        app.update_audio_monitor.assert_called_once_with(chunk, SR)
        self.assertFalse(mic.capturing)


class RealtimeCompletionTests(unittest.TestCase):
    def make_session(self):
        session = RealtimeSession.__new__(RealtimeSession)
        session.done = threading.Event()
        session.error = None
        session.text = None
        session.translate = True
        session.parts = []
        # These values reproduced the old premature "no voice" decision.
        session.t_finished = time.time() - 3
        session.last_delta_t = None
        session.last_el = 0
        session.sent_ms = 1000
        return session

    def test_late_first_text_waits_for_actual_completion(self):
        session = self.make_session()

        def finish():
            session.text = "The recorded voice was received."
            session.done.set()

        timer = threading.Timer(0.05, finish)
        timer.start()
        try:
            self.assertEqual(session.result(timeout=1), "The recorded voice was received.")
        finally:
            timer.join()

    def test_partial_text_is_not_used_as_a_final_result(self):
        session = self.make_session()
        session.parts = ["First sentence."]
        session.last_delta_t = time.time() - 2
        session.last_el = 1000
        with self.assertRaises(RuntimeError):
            session.result(timeout=0.02)


class TextOnlyRealtimeTests(unittest.TestCase):
    def make_session(self, events=()):
        session = RealtimeSession.__new__(RealtimeSession)
        session.translate = True
        session.parts = []
        session.text = session.error = None
        session.done = threading.Event()
        session.ready = threading.Event()
        session.conn = iter(events)
        return session

    def test_translation_requests_text_without_synthesized_audio(self):
        session = self.make_session()
        session.client = Mock()
        cm = Mock()
        connection = Mock()
        cm.__enter__ = Mock(return_value=connection)
        session.client.realtime.connect.return_value = cm
        with patch("translator_app.threading.Thread"):
            session._open()
        config = connection.send.call_args.args[0]["session"]
        self.assertEqual(config["output_modalities"], ["text"])
        self.assertEqual(config["audio"]["input"]["format"]["rate"], RT_RATE)
        self.assertIsNone(config["audio"]["input"]["turn_detection"])
        session.client.realtime.translations.connect.assert_not_called()

    def test_finishing_audio_commits_and_requests_a_text_response(self):
        session = self.make_session()
        session.conn = Mock()
        session.gain, session.peak = 1, 0.02
        session.q = queue.Queue()
        session.q.put((np.zeros(2400, dtype=np.float32), RT_RATE))
        session.q.put(None)
        session.ready.set()
        session._sender()
        sent = [call.args[0] for call in session.conn.send.call_args_list]
        self.assertEqual([item["type"] for item in sent[-2:]],
                         ["input_audio_buffer.commit", "response.create"])
        self.assertEqual(sent[-1]["response"]["output_modalities"], ["text"])
        self.assertNotIn("session.close", [item["type"] for item in sent])

    def test_result_finishes_on_completed_text_without_waiting_for_socket_close(self):
        response = SimpleNamespace(status="completed", output=[SimpleNamespace(content=[
            SimpleNamespace(type="output_text", text="Hi, how are you?")])])

        def events():
            yield SimpleNamespace(type="response.output_text.delta", delta="Hi,")
            yield SimpleNamespace(type="response.output_text.done", text="Hi, how are you?")
            yield SimpleNamespace(type="response.done", response=response)
            raise AssertionError("Reader must not wait for connection closure")

        session = self.make_session(events())
        session._reader()
        self.assertEqual(session.result(timeout=0), "Hi, how are you?")

    def test_disconnect_after_partial_text_is_not_success(self):
        session = self.make_session([
            SimpleNamespace(type="response.output_text.done", text="Only a partial sentence")])
        session._reader()
        with self.assertRaises(RuntimeError):
            session.result(timeout=0)

    def test_incomplete_response_is_not_pasted(self):
        session = self.make_session([
            SimpleNamespace(type="response.output_text.done", text="Only part"),
            SimpleNamespace(type="response.done",
                            response=SimpleNamespace(status="incomplete", output=None))])
        session._reader()
        with self.assertRaises(RuntimeError):
            session.result(timeout=0)


class RealtimeRecoveryTests(unittest.TestCase):
    def make_app(self):
        app = App.__new__(App)
        app.q = queue.Queue()
        app.transcribe_openai = Mock(return_value="Recovered text")
        app.rt_prepare = Mock()
        return app

    def test_empty_and_whitespace_responses_retry_the_recording(self):
        for empty in ("", "  "):
            app = self.make_app()
            session = Mock()
            session.result.return_value = empty
            self.assertEqual(app.transcribe_realtime(session, speech_signal(), "es", "translate"),
                             "Recovered text")
            app.transcribe_openai.assert_called_once()
            session.close.assert_called_once()
            app.rt_prepare.assert_called_once()

    def test_successful_realtime_response_is_not_sent_twice(self):
        app = self.make_app()
        session = Mock()
        session.result.return_value = "Realtime text"
        self.assertEqual(app.transcribe_realtime(session, speech_signal(), "es", "translate"),
                         "Realtime text")
        app.transcribe_openai.assert_not_called()

    def test_empty_response_with_silence_does_not_send_an_http_request(self):
        app = self.make_app()
        session = Mock()
        session.result.return_value = ""
        self.assertEqual(app.transcribe_realtime(session, np.zeros(SR), "es", "translate"), "")
        app.transcribe_openai.assert_not_called()

    def test_connection_error_recovers_and_cleans_up(self):
        app = self.make_app()
        session = Mock()
        session.result.side_effect = RuntimeError("Connection interrupted")
        self.assertEqual(app.transcribe_realtime(session, speech_signal(), "es", "translate"),
                         "Recovered text")
        session.close.assert_called_once()
        app.rt_prepare.assert_called_once()


class AudioMeterTests(unittest.TestCase):
    def test_real_frequencies_light_different_bands(self):
        t = np.arange(4096) / SR
        low = spectrum_levels(0.1 * np.sin(2 * np.pi * 440 * t), SR)
        high = spectrum_levels(0.1 * np.sin(2 * np.pi * 3000 * t), SR)
        self.assertGreater(float(np.max(low)), 0)
        self.assertNotEqual(int(np.argmax(low)), int(np.argmax(high)))

    def test_silence_and_dc_leave_spectrum_empty(self):
        for samples in (np.zeros(4096), np.full(4096, 0.512), np.array([np.nan])):
            self.assertTrue(np.all(spectrum_levels(samples, SR) == 0))

    def test_live_signal_then_stale_signal_updates_widget(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            meter = AudioMeter(root)
            meter.pack()
            root.update_idletasks()
            with patch("audio_meter.time.monotonic", return_value=10.0):
                worker = threading.Thread(target=meter.feed, args=(speech_signal(), SR))
                worker.start()
                worker.join()
                meter.update_meter(active=True)
            self.assertIn("audio presente", meter.status.cget("text"))
            self.assertTrue(np.any(meter._levels > 0))
            with patch("audio_meter.time.monotonic", return_value=11.0):
                meter.update_meter(active=True)
            self.assertTrue(np.all(meter._levels == 0))
            meter.update_meter(active=False)
            self.assertEqual(meter.status.cget("text"), "Micrófono inactivo")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
