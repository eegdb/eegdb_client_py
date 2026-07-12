"""Unit tests for compressed-batch framing and block-codec IDs."""

from __future__ import annotations

import struct
import unittest

from eegdb_client.codec_local import (
    BLOCK_CODEC_BEST,
    BLOCK_CODEC_FLAC,
    BLOCK_CODEC_LZ4,
    BLOCK_CODEC_WAVPACK,
    BLOCK_CODEC_ZSTD,
    parse_block_codec,
)
from eegdb_client.transport.tcp_client import EEGDBTCPClient


class BlockCodecParseTests(unittest.TestCase):
    def test_names(self) -> None:
        self.assertEqual(parse_block_codec("lz4"), BLOCK_CODEC_LZ4)
        self.assertEqual(parse_block_codec("zstd"), BLOCK_CODEC_ZSTD)
        self.assertEqual(parse_block_codec("flac"), BLOCK_CODEC_FLAC)
        self.assertEqual(parse_block_codec("wavpack"), BLOCK_CODEC_WAVPACK)
        self.assertEqual(parse_block_codec("best"), BLOCK_CODEC_BEST)
        self.assertEqual(parse_block_codec(""), BLOCK_CODEC_BEST)

    def test_unknown(self) -> None:
        with self.assertRaises(ValueError):
            parse_block_codec("gzip")


class CompressedBatchWireTests(unittest.TestCase):
    def test_encode_req(self) -> None:
        raw = EEGDBTCPClient._encode_read_compressed_batch_req(
            "abc", 7, 0x01, 100, 64, BLOCK_CODEC_ZSTD
        )
        self.assertEqual(raw[0], 3)
        self.assertEqual(raw[1:4], b"abc")
        channel_id, data_type, start = struct.unpack_from("<HBQ", raw, 4)
        self.assertEqual(channel_id, 7)
        self.assertEqual(data_type, 0x01)
        self.assertEqual(start, 100)
        count, codec = struct.unpack_from("<IB", raw, 4 + 11)
        self.assertEqual(count, 64)
        self.assertEqual(codec, BLOCK_CODEC_ZSTD)

    def test_decode_resp(self) -> None:
        sid = b"s1"
        payload = b"\x01\x02\x03\x04"
        body = (
            struct.pack("<B", len(sid))
            + sid
            + struct.pack("<HBQ", 1, 0x01, 10)
            + struct.pack("<I", 4)
            + struct.pack("<B", 0x11)  # algo zstd
            + struct.pack("<I", len(payload))
            + payload
        )
        start, count, algo, compressed = EEGDBTCPClient._decode_read_compressed_batch(body)
        self.assertEqual(start, 10)
        self.assertEqual(count, 4)
        self.assertEqual(algo, 0x11)
        self.assertEqual(compressed, payload)


if __name__ == "__main__":
    unittest.main()
