import asyncio
import json
import struct
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_MAIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_MAIN))
import dynamic_server  # noqa: E402
import websockets  # noqa: E402


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append((time.perf_counter(), data))


class FakeStdin:
    def __init__(self):
        self.closed = asyncio.Event()

    def write(self, _data):
        pass

    async def drain(self):
        pass

    def is_closing(self):
        return self.closed.is_set()

    def close(self):
        self.closed.set()

    async def wait_closed(self):
        pass


class FakeStdout:
    def __init__(self, stdin, pcm):
        self.stdin = stdin
        self.pcm = pcm

    async def read(self, _size):
        await self.stdin.closed.wait()
        if self.pcm is None:
            return b""
        pcm, self.pcm = self.pcm, None
        return pcm


class FakeProcess:
    def __init__(self, pcm):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(self.stdin, pcm)
        self.returncode = None

    async def wait(self):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


class FakeCommunicate:
    def __init__(self, _text, voice=None):
        self.voice = voice

    async def stream(self):
        yield {"type": "audio", "data": b"fake mp3"}


class FakeEdgeTTS:
    Communicate = FakeCommunicate


class FakeOpusEncoder:
    def __init__(self, _sample_rate, _channels, _application):
        pass

    def encode(self, pcm_frame, _frame_size):
        return b"opus:" + pcm_frame[:4]


class RobotAudioTransportTests(unittest.IsolatedAsyncioTestCase):
    def test_protocol_audio_frames_round_trip(self):
        payload = b"opus-frame-payload"
        for version in (1, 2, 3):
            with self.subTest(version=version):
                wire_frame = dynamic_server.encode_robot_audio_frame(payload, version)
                self.assertEqual(dynamic_server.decode_robot_audio_frame(wire_frame, version), payload)

    def test_protocol_audio_frames_reject_bad_lengths(self):
        with self.assertRaises(ValueError):
            dynamic_server.decode_robot_audio_frame(b"\x00", 2)
        with self.assertRaises(ValueError):
            dynamic_server.decode_robot_audio_frame(b"\x00\x00\x00\x05x", 3)

    async def test_tts_stream_yields_opus_without_waiting_for_full_mp3(self):
        pcm = struct.pack("<h", 900) * (960 * 3)
        fake_process = FakeProcess(pcm)

        async def create_fake_process(*_args, **_kwargs):
            return fake_process

        with patch.object(dynamic_server, "edge_tts", FakeEdgeTTS), patch.object(
            dynamic_server.asyncio, "create_subprocess_exec", create_fake_process
        ), patch.object(dynamic_server.shutil, "which", return_value="ffmpeg"), patch.dict(
            sys.modules,
            {"opuslib_next": types.SimpleNamespace(Encoder=FakeOpusEncoder, APPLICATION_AUDIO=1)},
        ):
            frames = [frame async for frame in dynamic_server.stream_tts_opus("Xin chào")]

        self.assertEqual(len(frames), 3)
        self.assertTrue(all(frames))
        self.assertEqual(dynamic_server.LIVE_DIAGNOSTICS["last_tts_frame_count"], 3)
        self.assertEqual(dynamic_server.LIVE_DIAGNOSTICS["last_tts_error"], "")

    async def test_tts_is_started_only_when_audio_frame_exists(self):
        ws = FakeWebSocket()
        sent = await dynamic_server.send_dynamic_tts_response(
            ws, "empty-tts-test", "xin chào", "tôi đây", "neutral", []
        )
        self.assertFalse(sent)
        self.assertFalse(any(b'"state": "start"' in item for _, item in ws.sent if isinstance(item, bytes)))
        self.assertEqual(ws.sent, [])

    async def test_tts_frames_are_paced_at_sixty_milliseconds(self):
        ws = FakeWebSocket()
        sent = await dynamic_server.send_dynamic_tts_response(
            ws, "paced-tts-test", "xin chào", "tôi đây", "neutral", [b"one", b"two", b"three"]
        )
        self.assertTrue(sent)
        frame_times = [at for at, item in ws.sent if isinstance(item, bytes)]
        self.assertEqual(len(frame_times), 3)
        self.assertAlmostEqual(frame_times[1] - frame_times[0], 0.060, delta=0.025)
        self.assertAlmostEqual(frame_times[2] - frame_times[1], 0.060, delta=0.025)
        self.assertEqual(dynamic_server.LIVE_DIAGNOSTICS["last_tts_frame_count"], 3)

    async def test_tts_response_uses_the_robot_binary_protocol(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                ws = FakeWebSocket()
                dynamic_server.CONNECTED_ROBOT_PROTOCOLS[id(ws)] = version
                try:
                    sent = await dynamic_server.send_dynamic_tts_response(
                        ws, f"wire-test-{version}", "xin chào", "tôi đây", "neutral", [b"opus"]
                    )
                    self.assertTrue(sent)
                    binary = next(item for _, item in ws.sent if isinstance(item, bytes))
                    self.assertEqual(dynamic_server.decode_robot_audio_frame(binary, version), b"opus")
                finally:
                    dynamic_server.CONNECTED_ROBOT_PROTOCOLS.pop(id(ws), None)

    async def test_stream_failure_sends_stop_after_playback_started(self):
        async def broken_stream():
            yield b"first-frame"
            raise RuntimeError("test stream failure")

        ws = FakeWebSocket()
        sent = await dynamic_server.send_dynamic_tts_response(
            ws, "failed-stream-test", "xin chào", "tôi đây", "neutral", broken_stream()
        )
        self.assertFalse(sent)
        states = [json.loads(item).get("state") for _, item in ws.sent if isinstance(item, str)]
        self.assertIn("start", states)
        self.assertIn("stop", states)

    async def test_robot_handshake_negotiates_supported_protocol_versions(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                async with websockets.serve(dynamic_server.ws_handler, "127.0.0.1", 0, ping_interval=None) as server:
                    port = server.sockets[0].getsockname()[1]
                    async with websockets.connect(
                        f"ws://127.0.0.1:{port}/xiaozhi/v1/",
                        additional_headers={"Protocol-Version": str(version)},
                    ) as ws:
                        await ws.send('{"type":"hello","version":%d,"features":{}}' % version)
                        hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
                        self.assertEqual(hello["version"], version)
                        self.assertEqual(hello["transport"], "websocket")

                        packet = b"not-real-opus"
                        await ws.send(dynamic_server.encode_robot_audio_frame(packet, version))
                        await asyncio.sleep(0.02)
                        self.assertEqual(dynamic_server.LIVE_DIAGNOSTICS["protocol_version"], version)
                        self.assertGreater(dynamic_server.LIVE_DIAGNOSTICS["last_packet_time"], 0)


if __name__ == "__main__":
    unittest.main()
