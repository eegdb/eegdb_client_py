from __future__ import annotations

import struct
import unittest

from eegdb_client.protocol.v1 import protocol_pb2 as protocol
from eegdb_client.transport.tcp_client import (
    FRAME_MAGIC,
    PROTOCOL_VERSION,
    EEGDBTCPClient,
    _crc32c,
)


class RecordingSocket:
    def __init__(self, incoming: bytes = b"") -> None:
        self.incoming = bytearray(incoming)
        self.written = bytearray()

    def sendall(self, data: bytes) -> None:
        self.written.extend(data)

    def recv(self, size: int) -> bytes:
        if not self.incoming:
            return b""
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result


class ProtobufFrameTests(unittest.TestCase):
    def test_edb_frame_round_trip(self) -> None:
        client = EEGDBTCPClient("localhost", 9000)
        request = protocol.Envelope(
            protocol_version=PROTOCOL_VERSION,
            request_id=42,
            heartbeat_request=protocol.HeartbeatRequest(),
        )
        output = RecordingSocket()
        client._sock = output  # type: ignore[assignment]
        client._write_envelope(request)

        wire = bytes(output.written)
        self.assertEqual(wire[:3], FRAME_MAGIC)
        length = struct.unpack("<I", wire[3:7])[0]
        self.assertEqual(len(wire), length + 11)
        self.assertEqual(struct.unpack("<I", wire[-4:])[0], _crc32c(wire[:-4]))

        client._sock = RecordingSocket(wire)  # type: ignore[assignment]
        decoded = client._read_envelope()
        self.assertEqual(decoded.request_id, 42)
        self.assertTrue(decoded.HasField("heartbeat_request"))

    def test_crc32c_known_vector(self) -> None:
        self.assertEqual(_crc32c(b"123456789"), 0xE3069283)


if __name__ == "__main__":
    unittest.main()
