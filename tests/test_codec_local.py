"""Unit tests for compressed-batch framing and block-codec IDs."""

from __future__ import annotations

import unittest

from eegdb_client.codec_local import (
    BLOCK_CODEC_BALANCED,
    BLOCK_CODEC_FAST,
    BLOCK_CODEC_FLAC,
    BLOCK_CODEC_LZ4,
    BLOCK_CODEC_SMALLEST,
    BLOCK_CODEC_WAVPACK,
    BLOCK_CODEC_ZSTD,
    parse_block_codec,
)
from eegdb_client.protocol.v1 import protocol_pb2 as protocol


class BlockCodecParseTests(unittest.TestCase):
    def test_names(self) -> None:
        self.assertEqual(parse_block_codec("lz4"), BLOCK_CODEC_LZ4)
        self.assertEqual(parse_block_codec("zstd"), BLOCK_CODEC_ZSTD)
        self.assertEqual(parse_block_codec("flac"), BLOCK_CODEC_FLAC)
        self.assertEqual(parse_block_codec("wavpack"), BLOCK_CODEC_WAVPACK)
        self.assertEqual(parse_block_codec("fast"), BLOCK_CODEC_FAST)
        self.assertEqual(parse_block_codec("balanced"), BLOCK_CODEC_BALANCED)
        self.assertEqual(parse_block_codec("smallest"), BLOCK_CODEC_SMALLEST)
        self.assertEqual(parse_block_codec(""), BLOCK_CODEC_BALANCED)

    def test_unknown(self) -> None:
        with self.assertRaises(ValueError):
            parse_block_codec("gzip")


class CompressedBatchWireTests(unittest.TestCase):
    def test_request_uses_generated_type_and_maps_codec_enum(self) -> None:
        request = protocol.ReadCompressedBatchRequest(
            study_id="abc",
            channel_id=7,
            data_type=protocol.DATA_TYPE_INT16,
            start_index=100,
            sample_count=64,
            block_codec=BLOCK_CODEC_ZSTD + 1,
        )
        self.assertEqual(request.study_id, "abc")
        self.assertEqual(request.channel_id, 7)
        self.assertEqual(request.data_type, protocol.DATA_TYPE_INT16)
        self.assertEqual(request.start_index, 100)
        self.assertEqual(request.sample_count, 64)
        self.assertEqual(request.block_codec, protocol.BLOCK_CODEC_ZSTD)

    def test_generated_response_exposes_compressed_payload(self) -> None:
        payload = b"\x01\x02\x03\x04"
        response = protocol.ReadCompressedBatchResponse(
            study_id="s1",
            channel_id=1,
            data_type=protocol.DATA_TYPE_INT16,
            start_index=10,
            sample_count=4,
            compression_algorithm=0x11,
            compressed_data=payload,
        )
        self.assertEqual(response.start_index, 10)
        self.assertEqual(response.sample_count, 4)
        self.assertEqual(response.compression_algorithm, 0x11)
        self.assertEqual(response.compressed_data, payload)


if __name__ == "__main__":
    unittest.main()
