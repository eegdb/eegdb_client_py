"""Binary TCP client for EEGDB upload and query/download."""

from __future__ import annotations

import json
import socket
import struct
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from ..auth_proof import compute_proof
from ..codec import EEGDBCodec
from ..models import DT_FLOAT32, DT_FLOAT64, DT_INT16, DT_INT24, DT_INT64, Event

PROTOCOL_VERSION = 2

MSG_HANDSHAKE_REQ = 0x01
MSG_HANDSHAKE_RESP = 0x02
MSG_AUTH_PROOF = 0x03
MSG_AUTH_RESP = 0x04
MSG_WRITE_BATCH = 0x11
MSG_CREATE_STUDY = 0x12
MSG_WRITE_EVENTS = 0x13
MSG_FLUSH_STUDY = 0x14
MSG_HEARTBEAT_REQ = 0x20
MSG_HEARTBEAT_RESP = 0x21
MSG_ERROR = 0x30
MSG_LIST_STUDIES_REQ = 0x40
MSG_LIST_STUDIES_RESP = 0x41
MSG_GET_STUDY_REQ = 0x42
MSG_GET_STUDY_RESP = 0x43
MSG_SEARCH_STUDIES_REQ = 0x44
MSG_SEARCH_STUDIES_RESP = 0x45
MSG_READ_BATCH_REQ = 0x46
MSG_READ_BATCH_RESP = 0x47
MSG_READ_EVENTS_REQ = 0x48
MSG_READ_EVENTS_RESP = 0x49
MSG_READ_COMPRESSED_BATCH_REQ = 0x4A
MSG_READ_COMPRESSED_BATCH_RESP = 0x4B
MSG_STATS_REQ = 0x4C
MSG_STATS_RESP = 0x4D
MSG_DELETE_STUDY_REQ = 0x4E
MSG_DELETE_STUDY_RESP = 0x4F
MSG_UPDATE_STUDY_REQ = 0x50
MSG_UPDATE_STUDY_RESP = 0x51
MSG_QUERY_CHANNEL_REQ = 0x52
MSG_QUERY_CHANNEL_RESP = 0x53
MSG_WRITE_EVENTS_JSON = 0x54
MSG_READ_EVENTS_JSON_REQ = 0x55
MSG_READ_EVENTS_JSON_RESP = 0x56
MSG_CLOSE = 0xFF

MAX_READ_BATCH = 65536
CONNECT_TIMEOUT = 3

BLOCK_CODEC = {
    "lz4": 0,
    "zstd": 1,
    "flac": 2,
    "wavpack": 3,
    "best": 4,
}


class TCPError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(f"TCP error {code:#04x}: {message}")
        self.code = code
        self.message = message


class EEGDBTCPClient:
    def __init__(
        self,
        host: str,
        port: int,
        client_name: str = "eegdb-client",
        token_name: str = "",
        api_token: str = "",
    ):
        self.host = host
        self.port = port
        self.client_name = client_name
        self.token_name = token_name
        self.api_token = api_token
        self._sock: Optional[socket.socket] = None
        self._codec: Optional[EEGDBCodec] = None

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        self.close()
        sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self._write_frame(MSG_HANDSHAKE_REQ, self._encode_handshake(self.client_name))
        msg_type, payload = self._read_frame()
        if msg_type != MSG_HANDSHAKE_RESP:
            raise TCPError(0, f"expected handshake resp, got {msg_type:#04x}")
        status, _, nonce = self._decode_handshake_resp(payload)
        if status != 0:
            raise TCPError(status, "handshake failed")
        if nonce:
            if not self.api_token or not self.token_name:
                raise TCPError(0, "server requires auth; provide token_name and api_token")
            proof = compute_proof(self.api_token, nonce)
            auth_payload = self._encode_auth_proof(self.token_name, proof)
            self._write_frame(MSG_AUTH_PROOF, auth_payload)
            auth_type, auth_resp = self._read_frame()
            if auth_type != MSG_AUTH_RESP:
                raise TCPError(0, f"expected auth resp, got {auth_type:#04x}")
            if not auth_resp or auth_resp[0] != 0:
                code = auth_resp[0] if auth_resp else 0
                raise TCPError(code, "auth failed")

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._write_frame(MSG_CLOSE, b"")
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> "EEGDBTCPClient":
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    def create_study(
        self, name: str, channels: List[Dict[str, Any]], attrs: Optional[Dict[str, Any]] = None
    ) -> str:
        ch_json = json.dumps(channels).encode("utf-8")
        attrs_json = json.dumps(attrs or {}).encode("utf-8")
        name_b = name.encode("utf-8")
        payload = (
            struct.pack("<B", len(name_b))
            + name_b
            + struct.pack("<I", len(ch_json))
            + ch_json
            + struct.pack("<I", len(attrs_json))
            + attrs_json
        )
        self._write_frame(MSG_CREATE_STUDY, payload)
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_CREATE_STUDY:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return self._decode_study_id(resp)

    def write_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        data: Union[np.ndarray, List],
    ) -> None:
        payload = self._encode_write_batch(study_id, channel_id, data_type, start_index, data)
        self._write_frame(MSG_WRITE_BATCH, payload)

    def write_events(self, study_id: str, events: List[Event]) -> None:
        event_bytes = self._encode_events(events)
        sid = study_id.encode("utf-8")
        payload = struct.pack("<B", len(sid)) + sid + struct.pack("<I", len(event_bytes)) + event_bytes
        self._write_frame(MSG_WRITE_EVENTS, payload)

    def write_events_json(self, study_id: str, events: List[Union[Event, Dict[str, Any]]]) -> None:
        event_dicts = [e.to_dict() if isinstance(e, Event) else dict(e) for e in events]
        body = json.dumps({"events": event_dicts}).encode("utf-8")
        sid = study_id.encode("utf-8")
        payload = struct.pack("<B", len(sid)) + sid + struct.pack("<I", len(body)) + body
        self._write_frame(MSG_WRITE_EVENTS_JSON, payload)

    def flush_study(self, study_id: str) -> None:
        sid = study_id.encode("utf-8")
        self._write_frame(MSG_FLUSH_STUDY, struct.pack("<B", len(sid)) + sid)

    def health(self) -> Dict[str, Any]:
        self._write_frame(MSG_HEARTBEAT_REQ, b"")
        msg_type, payload = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(payload)
        if msg_type != MSG_HEARTBEAT_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return {"status": "ok", "transport": "tcp"}

    def stats(self) -> Dict[str, Any]:
        self._write_frame(MSG_STATS_REQ, b"")
        msg_type, payload = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(payload)
        if msg_type != MSG_STATS_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        db_json, tcp_json = self._decode_stats_response(payload)
        return {
            "db": json.loads(db_json) if db_json else {},
            "tcp": json.loads(tcp_json) if tcp_json else {},
        }

    # ------------------------------------------------------------------
    # Query / download
    # ------------------------------------------------------------------
    def list_studies(self) -> List[Dict[str, Any]]:
        self._write_frame(MSG_LIST_STUDIES_REQ, b"")
        msg_type, payload = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(payload)
        if msg_type != MSG_LIST_STUDIES_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        data = json.loads(self._decode_json_payload(payload))
        return data.get("studies", [])

    def get_study(self, study_id: str) -> Dict[str, Any]:
        payload = self._encode_study_id(study_id)
        self._write_frame(MSG_GET_STUDY_REQ, payload)
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_GET_STUDY_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return json.loads(self._decode_json_payload(resp))

    def delete_study(self, study_id: str) -> Dict[str, Any]:
        self._write_frame(MSG_DELETE_STUDY_REQ, self._encode_delete_study_request(study_id))
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_DELETE_STUDY_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return self._decode_delete_study_response(resp)

    def update_study(
        self,
        study_id: str,
        name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        channels: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        req: Dict[str, Any] = {"study_id": study_id}
        if name is not None:
            req["name"] = name
        if attributes is not None:
            req["attributes"] = attributes
        if channels is not None:
            req["channels"] = channels
        self._write_frame(MSG_UPDATE_STUDY_REQ, self._encode_update_study_request(req))
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_UPDATE_STUDY_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return self._decode_update_study_response(resp)

    def search_studies(self, attrs: Dict[str, str]) -> List[Dict[str, Any]]:
        attrs_json = json.dumps(attrs).encode("utf-8")
        self._write_frame(MSG_SEARCH_STUDIES_REQ, self._encode_json_payload(attrs_json))
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_SEARCH_STUDIES_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        data = json.loads(self._decode_json_payload(resp))
        return data.get("studies", [])

    def read_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        sample_count: int,
    ) -> Tuple[int, np.ndarray]:
        if sample_count <= 0 or sample_count > MAX_READ_BATCH:
            raise ValueError(f"sample_count must be 1..{MAX_READ_BATCH}")
        payload = self._encode_read_batch_req(study_id, channel_id, data_type, start_index, sample_count)
        self._write_frame(MSG_READ_BATCH_REQ, payload)
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_READ_BATCH_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return self._decode_write_batch(resp)

    def read_compressed_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        sample_count: int,
        codec: str = "lz4",
    ) -> Tuple[int, np.ndarray]:
        if sample_count <= 0 or sample_count > MAX_READ_BATCH:
            raise ValueError(f"sample_count must be 1..{MAX_READ_BATCH}")
        codec_id = BLOCK_CODEC.get(codec)
        if codec_id is None:
            raise ValueError(f"unsupported codec {codec!r}; choose one of {sorted(BLOCK_CODEC)}")
        payload = self._encode_read_compressed_batch_req(
            study_id, channel_id, data_type, start_index, sample_count, codec_id
        )
        self._write_frame(MSG_READ_COMPRESSED_BATCH_REQ, payload)
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_READ_COMPRESSED_BATCH_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        start, dtype, count, algo, compressed = self._decode_read_compressed_batch_resp(resp)
        if self._codec is None:
            self._codec = EEGDBCodec()
        arr = self._codec.decode(dtype, algo, count, compressed)
        return start, arr

    def read_events(self, study_id: str, filter_json: Optional[Dict[str, Any]] = None) -> List[Event]:
        fj = json.dumps(filter_json or {}).encode("utf-8")
        sid = study_id.encode("utf-8")
        payload = struct.pack("<B", len(sid)) + sid + struct.pack("<I", len(fj)) + fj
        self._write_frame(MSG_READ_EVENTS_REQ, payload)
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_READ_EVENTS_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return self._decode_events(resp)

    def read_events_json(self, study_id: str, filter_json: Optional[Dict[str, Any]] = None) -> List[Event]:
        fj = json.dumps(filter_json or {}).encode("utf-8")
        sid = study_id.encode("utf-8")
        payload = struct.pack("<B", len(sid)) + sid + struct.pack("<I", len(fj)) + fj
        self._write_frame(MSG_READ_EVENTS_JSON_REQ, payload)
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_READ_EVENTS_JSON_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        data = json.loads(self._decode_json_payload(resp))
        return [Event.from_dict(item) for item in data.get("events", [])]

    def query_channel(
        self,
        study_id: str,
        channel_id: int,
        *,
        idx_start: Optional[int] = None,
        idx_end: Optional[int] = None,
        start_us: Optional[int] = None,
        end_us: Optional[int] = None,
        physical: bool = False,
        downsample: Optional[int] = None,
        method: Optional[str] = None,
        reference: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        req: Dict[str, Any] = {
            "study_id": study_id,
            "channel_id": channel_id,
        }
        if idx_start is not None:
            req["idx_start"] = idx_start
        if idx_end is not None:
            req["idx_end"] = idx_end
        if start_us is not None:
            req["start_us"] = start_us
        if end_us is not None:
            req["end_us"] = end_us
        if physical:
            req["physical"] = True
        if downsample is not None:
            req["downsample"] = downsample
        if method:
            req["method"] = method
        if reference:
            req["reference"] = list(reference)
        self._write_frame(MSG_QUERY_CHANNEL_REQ, self._encode_query_channel_request(req))
        msg_type, resp = self._read_frame()
        if msg_type == MSG_ERROR:
            raise self._parse_error(resp)
        if msg_type != MSG_QUERY_CHANNEL_RESP:
            raise TCPError(0, f"unexpected msg {msg_type:#04x}")
        return self._decode_query_channel_response(resp)

    def read_channel_all(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        total_samples: int,
        batch_size: int = 8192,
    ) -> np.ndarray:
        chunks: List[np.ndarray] = []
        start = 0
        while start < total_samples:
            count = min(batch_size, total_samples - start)
            _, arr = self.read_batch(study_id, channel_id, data_type, start, count)
            chunks.append(arr)
            start += count
        if not chunks:
            return np.array([], dtype=self._numpy_dtype(data_type))
        return np.concatenate(chunks)

    def read_channel_all_compressed(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        total_samples: int,
        batch_size: int = 8192,
        codec: str = "lz4",
    ) -> np.ndarray:
        chunks: List[np.ndarray] = []
        start = 0
        while start < total_samples:
            count = min(batch_size, total_samples - start)
            _, arr = self.read_compressed_batch(study_id, channel_id, data_type, start, count, codec)
            chunks.append(arr)
            start += count
        if not chunks:
            return np.array([], dtype=self._numpy_dtype(data_type))
        return np.concatenate(chunks)

    # ------------------------------------------------------------------
    # Wire helpers
    # ------------------------------------------------------------------
    def _write_frame(self, msg_type: int, payload: bytes) -> None:
        if self._sock is None:
            raise RuntimeError("not connected")
        wire = self._encode_envelope(msg_type, payload)
        self._sock.sendall(struct.pack("<I", len(wire)) + wire)

    def _read_frame(self) -> Tuple[int, bytes]:
        if self._sock is None:
            raise RuntimeError("not connected")
        frame_len = struct.unpack("<I", self._recv_exact(4))[0]
        if frame_len <= 0:
            raise TCPError(0, f"invalid frame length {frame_len}")
        wire = self._recv_exact(frame_len)
        return self._decode_envelope(wire)

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("connection closed")
            buf.extend(chunk)
        return bytes(buf)

    @staticmethod
    def _encode_handshake(client_name: str) -> bytes:
        name = client_name.encode("utf-8")
        return struct.pack("<BB", PROTOCOL_VERSION, len(name)) + name

    @staticmethod
    def _encode_envelope(msg_type: int, payload: bytes) -> bytes:
        out = bytearray()
        EEGDBTCPClient._append_proto_varint_field(out, 1, PROTOCOL_VERSION)
        EEGDBTCPClient._append_proto_varint_field(out, 2, msg_type)
        if payload:
            EEGDBTCPClient._append_proto_bytes_field(out, 4, payload)
        return bytes(out)

    @staticmethod
    def _decode_envelope(data: bytes) -> Tuple[int, bytes]:
        msg_type = 0
        payload = b""
        index = 0
        while index < len(data):
            tag, consumed = EEGDBTCPClient._consume_proto_varint(data, index)
            index += consumed
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num in (1, 2, 3):
                value, used = EEGDBTCPClient._consume_proto_varint(data, index)
                index += used
                if field_num == 2:
                    msg_type = int(value)
            elif field_num == 4:
                if wire_type != 2:
                    raise TCPError(0, f"invalid envelope payload wire type {wire_type}")
                payload, used = EEGDBTCPClient._consume_proto_bytes(data, index)
                index += used
            else:
                index += EEGDBTCPClient._consume_unknown_proto_field(data, index, wire_type)
        if msg_type == 0:
            raise TCPError(0, "envelope missing message type")
        return msg_type, payload

    @staticmethod
    def _append_proto_varint_field(out: bytearray, field_num: int, value: int) -> None:
        EEGDBTCPClient._append_proto_uvarint(out, field_num << 3)
        EEGDBTCPClient._append_proto_uvarint(out, value)

    @staticmethod
    def _append_proto_svarint_field(out: bytearray, field_num: int, value: int) -> None:
        EEGDBTCPClient._append_proto_uvarint(out, field_num << 3)
        EEGDBTCPClient._append_proto_uvarint(out, EEGDBTCPClient._zigzag_encode(value))

    @staticmethod
    def _append_proto_bool_field(out: bytearray, field_num: int, value: bool) -> None:
        EEGDBTCPClient._append_proto_varint_field(out, field_num, 1 if value else 0)

    @staticmethod
    def _append_proto_bytes_field(out: bytearray, field_num: int, value: bytes) -> None:
        EEGDBTCPClient._append_proto_uvarint(out, (field_num << 3) | 2)
        EEGDBTCPClient._append_proto_uvarint(out, len(value))
        out.extend(value)

    @staticmethod
    def _append_proto_string_field(out: bytearray, field_num: int, value: str) -> None:
        EEGDBTCPClient._append_proto_bytes_field(out, field_num, value.encode("utf-8"))

    @staticmethod
    def _append_proto_fixed32_field(out: bytearray, field_num: int, value: int) -> None:
        EEGDBTCPClient._append_proto_uvarint(out, (field_num << 3) | 5)
        out.extend(struct.pack("<I", value))

    @staticmethod
    def _append_proto_fixed64_field(out: bytearray, field_num: int, value: int) -> None:
        EEGDBTCPClient._append_proto_uvarint(out, (field_num << 3) | 1)
        out.extend(struct.pack("<Q", value))

    @staticmethod
    def _append_proto_uvarint(out: bytearray, value: int) -> None:
        while value >= 0x80:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value & 0x7F)

    @staticmethod
    def _consume_proto_varint(data: bytes, start: int) -> Tuple[int, int]:
        value = 0
        shift = 0
        index = start
        while index < len(data) and shift < 70:
            b = data[index]
            index += 1
            value |= (b & 0x7F) << shift
            if b < 0x80:
                return value, index - start
            shift += 7
        raise TCPError(0, "invalid protobuf varint")

    @staticmethod
    def _consume_proto_bytes(data: bytes, start: int) -> Tuple[bytes, int]:
        size, consumed = EEGDBTCPClient._consume_proto_varint(data, start)
        value_start = start + consumed
        value_end = value_start + size
        if value_end > len(data):
            raise TCPError(0, "truncated protobuf bytes field")
        return data[value_start:value_end], consumed + size

    @staticmethod
    def _consume_proto_string(data: bytes, start: int) -> Tuple[str, int]:
        value, consumed = EEGDBTCPClient._consume_proto_bytes(data, start)
        return value.decode("utf-8"), consumed

    @staticmethod
    def _consume_proto_bool(data: bytes, start: int) -> Tuple[bool, int]:
        value, consumed = EEGDBTCPClient._consume_proto_varint(data, start)
        return value != 0, consumed

    @staticmethod
    def _consume_proto_svarint(data: bytes, start: int) -> Tuple[int, int]:
        value, consumed = EEGDBTCPClient._consume_proto_varint(data, start)
        return EEGDBTCPClient._zigzag_decode(value), consumed

    @staticmethod
    def _consume_proto_fixed32(data: bytes, start: int) -> Tuple[int, int]:
        end = start + 4
        if end > len(data):
            raise TCPError(0, "truncated protobuf fixed32 field")
        return struct.unpack("<I", data[start:end])[0], 4

    @staticmethod
    def _consume_proto_fixed64(data: bytes, start: int) -> Tuple[int, int]:
        end = start + 8
        if end > len(data):
            raise TCPError(0, "truncated protobuf fixed64 field")
        return struct.unpack("<Q", data[start:end])[0], 8

    @staticmethod
    def _consume_unknown_proto_field(data: bytes, start: int, wire_type: int) -> int:
        if wire_type == 0:
            _, consumed = EEGDBTCPClient._consume_proto_varint(data, start)
            return consumed
        if wire_type == 1:
            if start + 8 > len(data):
                raise TCPError(0, "truncated protobuf fixed64 field")
            return 8
        if wire_type == 2:
            _, consumed = EEGDBTCPClient._consume_proto_bytes(data, start)
            return consumed
        if wire_type == 5:
            if start + 4 > len(data):
                raise TCPError(0, "truncated protobuf fixed32 field")
            return 4
        raise TCPError(0, f"unsupported protobuf wire type {wire_type}")

    @staticmethod
    def _zigzag_encode(value: int) -> int:
        return (value << 1) ^ (value >> 63)

    @staticmethod
    def _zigzag_decode(value: int) -> int:
        return (value >> 1) ^ -(value & 1)

    @staticmethod
    def _decode_handshake_resp(payload: bytes) -> Tuple[int, str, bytes]:
        status = payload[0]
        ver_len = payload[1]
        ver = payload[2 : 2 + ver_len].decode("utf-8")
        off = 2 + ver_len
        nonce = b""
        if off < len(payload):
            nonce_len = payload[off]
            nonce = payload[off + 1 : off + 1 + nonce_len]
        return status, ver, nonce

    @staticmethod
    def _encode_auth_proof(token_name: str, proof: bytes) -> bytes:
        name = token_name.encode("utf-8")
        return struct.pack("<B", len(name)) + name + proof

    @staticmethod
    def _encode_study_id(study_id: str) -> bytes:
        sid = study_id.encode("utf-8")
        return struct.pack("<B", len(sid)) + sid

    @staticmethod
    def _encode_delete_study_request(study_id: str) -> bytes:
        out = bytearray()
        EEGDBTCPClient._append_proto_string_field(out, 1, study_id)
        return bytes(out)

    @staticmethod
    def _decode_delete_study_response(data: bytes) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        index = 0
        while index < len(data):
            tag, consumed = EEGDBTCPClient._consume_proto_varint(data, index)
            index += consumed
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num == 1:
                value, used = EEGDBTCPClient._consume_proto_string(data, index)
                out["status"] = value
                index += used
            elif field_num == 2:
                value, used = EEGDBTCPClient._consume_proto_string(data, index)
                out["study_id"] = value
                index += used
            else:
                index += EEGDBTCPClient._consume_unknown_proto_field(data, index, wire_type)
        return out

    @staticmethod
    def _decode_stats_response(data: bytes) -> Tuple[bytes, bytes]:
        db_json = b""
        tcp_json = b""
        index = 0
        while index < len(data):
            tag, consumed = EEGDBTCPClient._consume_proto_varint(data, index)
            index += consumed
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num == 1:
                db_json, used = EEGDBTCPClient._consume_proto_bytes(data, index)
                index += used
            elif field_num == 2:
                tcp_json, used = EEGDBTCPClient._consume_proto_bytes(data, index)
                index += used
            else:
                index += EEGDBTCPClient._consume_unknown_proto_field(data, index, wire_type)
        return db_json, tcp_json

    @staticmethod
    def _encode_update_study_request(req: Dict[str, Any]) -> bytes:
        out = bytearray()
        EEGDBTCPClient._append_proto_string_field(out, 1, req["study_id"])
        if "name" in req:
            EEGDBTCPClient._append_proto_string_field(out, 2, req["name"])
            EEGDBTCPClient._append_proto_bool_field(out, 3, True)
        attrs = req.get("attributes")
        if attrs:
            for key in sorted(attrs):
                entry = bytearray()
                EEGDBTCPClient._append_proto_string_field(entry, 1, str(key))
                EEGDBTCPClient._append_proto_string_field(entry, 2, str(attrs[key]))
                EEGDBTCPClient._append_proto_bytes_field(out, 4, bytes(entry))
        channels = req.get("channels")
        if channels is not None:
            EEGDBTCPClient._append_proto_bytes_field(out, 5, json.dumps(channels).encode("utf-8"))
        return bytes(out)

    @staticmethod
    def _decode_update_study_response(data: bytes) -> Dict[str, Any]:
        study_json = b""
        index = 0
        while index < len(data):
            tag, consumed = EEGDBTCPClient._consume_proto_varint(data, index)
            index += consumed
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num == 1:
                study_json, used = EEGDBTCPClient._consume_proto_bytes(data, index)
                index += used
            else:
                index += EEGDBTCPClient._consume_unknown_proto_field(data, index, wire_type)
        return json.loads(study_json) if study_json else {}

    @staticmethod
    def _encode_query_channel_request(req: Dict[str, Any]) -> bytes:
        out = bytearray()
        EEGDBTCPClient._append_proto_string_field(out, 1, req["study_id"])
        EEGDBTCPClient._append_proto_varint_field(out, 2, int(req["channel_id"]))
        if "start_us" in req:
            EEGDBTCPClient._append_proto_svarint_field(out, 3, int(req["start_us"]))
            EEGDBTCPClient._append_proto_bool_field(out, 4, True)
        if "end_us" in req:
            EEGDBTCPClient._append_proto_svarint_field(out, 5, int(req["end_us"]))
            EEGDBTCPClient._append_proto_bool_field(out, 6, True)
        if "idx_start" in req:
            EEGDBTCPClient._append_proto_varint_field(out, 7, int(req["idx_start"]))
            EEGDBTCPClient._append_proto_bool_field(out, 8, True)
        if "idx_end" in req:
            EEGDBTCPClient._append_proto_varint_field(out, 9, int(req["idx_end"]))
            EEGDBTCPClient._append_proto_bool_field(out, 10, True)
        if req.get("physical"):
            EEGDBTCPClient._append_proto_bool_field(out, 11, True)
        if "downsample" in req:
            EEGDBTCPClient._append_proto_svarint_field(out, 12, int(req["downsample"]))
            EEGDBTCPClient._append_proto_bool_field(out, 13, True)
        if req.get("method"):
            EEGDBTCPClient._append_proto_string_field(out, 14, req["method"])
        for ref in req.get("reference", []):
            EEGDBTCPClient._append_proto_varint_field(out, 15, int(ref))
        return bytes(out)

    @staticmethod
    def _decode_query_channel_response(data: bytes) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "study_id": "",
            "channel_id": 0,
            "sample_count": 0,
            "data_type": "",
        }
        int16_samples: List[int] = []
        int24_samples: List[int] = []
        float32_samples: List[float] = []
        float64_samples: List[float] = []
        int64_samples: List[int] = []
        index = 0
        while index < len(data):
            tag, consumed = EEGDBTCPClient._consume_proto_varint(data, index)
            index += consumed
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num == 1:
                out["study_id"], used = EEGDBTCPClient._consume_proto_string(data, index)
                index += used
            elif field_num == 2:
                out["channel_id"], used = EEGDBTCPClient._consume_proto_varint(data, index)
                index += used
            elif field_num == 3:
                out["sample_count"], used = EEGDBTCPClient._consume_proto_varint(data, index)
                index += used
            elif field_num == 4:
                out["data_type"], used = EEGDBTCPClient._consume_proto_string(data, index)
                index += used
            elif field_num == 5:
                out["unit"], used = EEGDBTCPClient._consume_proto_string(data, index)
                index += used
            elif field_num == 6:
                value, used = EEGDBTCPClient._consume_proto_varint(data, index)
                out.setdefault("references", []).append(value)
                index += used
            elif field_num == 7:
                out["downsample_factor"], used = EEGDBTCPClient._consume_proto_varint(data, index)
                index += used
            elif field_num == 8:
                bits, used = EEGDBTCPClient._consume_proto_fixed64(data, index)
                out["effective_sample_rate"] = struct.unpack("<d", struct.pack("<Q", bits))[0]
                index += used
            elif field_num == 9:
                value, used = EEGDBTCPClient._consume_proto_svarint(data, index)
                int16_samples.append(value)
                index += used
            elif field_num == 10:
                value, used = EEGDBTCPClient._consume_proto_svarint(data, index)
                int24_samples.append(value)
                index += used
            elif field_num == 11:
                bits, used = EEGDBTCPClient._consume_proto_fixed32(data, index)
                float32_samples.append(struct.unpack("<f", struct.pack("<I", bits))[0])
                index += used
            elif field_num == 12:
                bits, used = EEGDBTCPClient._consume_proto_fixed64(data, index)
                float64_samples.append(struct.unpack("<d", struct.pack("<Q", bits))[0])
                index += used
            elif field_num == 13:
                value, used = EEGDBTCPClient._consume_proto_svarint(data, index)
                int64_samples.append(value)
                index += used
            else:
                index += EEGDBTCPClient._consume_unknown_proto_field(data, index, wire_type)
        data_type = out.get("data_type")
        if data_type == "int16":
            out["samples"] = int16_samples
        elif data_type == "int24":
            out["samples"] = int24_samples
        elif data_type == "float32":
            out["samples"] = float32_samples
        elif data_type in ("float64", "physical", "rereferenced"):
            out["samples"] = float64_samples
        elif data_type == "int64":
            out["samples"] = int64_samples
        else:
            out["samples"] = []
        return out

    @staticmethod
    def _encode_json_payload(data: bytes) -> bytes:
        return struct.pack("<I", len(data)) + data

    @staticmethod
    def _decode_json_payload(data: bytes) -> bytes:
        n = struct.unpack("<I", data[:4])[0]
        return data[4 : 4 + n]

    @staticmethod
    def _decode_study_id(data: bytes) -> str:
        n = data[0]
        return data[1 : 1 + n].decode("utf-8")

    @staticmethod
    def _parse_error(payload: bytes) -> TCPError:
        code = payload[0]
        msg_len = struct.unpack("<H", payload[1:3])[0]
        msg = payload[3 : 3 + msg_len].decode("utf-8", errors="replace")
        return TCPError(code, msg)

    @staticmethod
    def _numpy_dtype(data_type: int) -> np.dtype:
        return {
            DT_INT16: np.int16,
            DT_INT24: np.int32,
            DT_FLOAT32: np.float32,
            DT_FLOAT64: np.float64,
            DT_INT64: np.int64,
        }[data_type]

    def _encode_write_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        data: Union[np.ndarray, List],
    ) -> bytes:
        arr = np.asarray(data)
        sid = study_id.encode("utf-8")
        header = struct.pack("<B", len(sid)) + sid + struct.pack("<HBQ", channel_id, data_type, start_index)
        if data_type == DT_INT16:
            body = arr.astype(np.int16).tobytes()
        elif data_type == DT_INT24:
            body = arr.astype(np.int32).tobytes()
        elif data_type == DT_FLOAT32:
            body = arr.astype(np.float32).tobytes()
        elif data_type == DT_FLOAT64:
            body = arr.astype(np.float64).tobytes()
        elif data_type == DT_INT64:
            body = arr.astype(np.int64).tobytes()
        else:
            raise ValueError(f"unsupported data_type {data_type:#x}")
        return header + struct.pack("<I", len(arr)) + body

    @staticmethod
    def _encode_read_batch_req(
        study_id: str, channel_id: int, data_type: int, start_index: int, sample_count: int
    ) -> bytes:
        sid = study_id.encode("utf-8")
        return (
            struct.pack("<B", len(sid))
            + sid
            + struct.pack("<HBQ", channel_id, data_type, start_index)
            + struct.pack("<I", sample_count)
        )

    @staticmethod
    def _encode_read_compressed_batch_req(
        study_id: str, channel_id: int, data_type: int, start_index: int, sample_count: int, codec_id: int
    ) -> bytes:
        sid = study_id.encode("utf-8")
        return (
            struct.pack("<B", len(sid))
            + sid
            + struct.pack("<HBQ", channel_id, data_type, start_index)
            + struct.pack("<IB", sample_count, codec_id)
        )

    def _decode_write_batch(self, data: bytes) -> Tuple[int, np.ndarray]:
        off = 0
        id_len = data[off]
        off += 1 + id_len
        channel_id, data_type, start_index = struct.unpack_from("<HBQ", data, off)
        off += 11
        sample_count = struct.unpack_from("<I", data, off)[0]
        off += 4
        raw = data[off:]
        dtype = self._numpy_dtype(data_type)
        arr = np.frombuffer(raw, dtype=dtype, count=sample_count)
        return start_index, arr.copy()

    @staticmethod
    def _decode_read_compressed_batch_resp(data: bytes) -> Tuple[int, int, int, int, bytes]:
        off = 0
        id_len = data[off]
        off += 1 + id_len
        _channel_id, data_type, start_index = struct.unpack_from("<HBQ", data, off)
        off += 11
        sample_count = struct.unpack_from("<I", data, off)[0]
        off += 4
        algo = data[off]
        off += 1
        payload_len = struct.unpack_from("<I", data, off)[0]
        off += 4
        payload = data[off : off + payload_len]
        return start_index, data_type, sample_count, algo, payload

    @staticmethod
    def _encode_events(events: List[Event]) -> bytes:
        parts = []
        for e in events:
            code = e.code.encode("utf-8")
            desc = e.description.encode("utf-8")
            parts.append(
                struct.pack("<QQH", e.onset, e.duration, e.channel_id)
                + struct.pack("<H", len(code))
                + code
                + struct.pack("<H", len(desc))
                + desc
            )
        return b"".join(parts)

    @staticmethod
    def _decode_events(data: bytes) -> List[Event]:
        events: List[Event] = []
        off = 0
        while off + 20 <= len(data):
            onset, duration, ch_id = struct.unpack_from("<QQH", data, off)
            off += 18
            code_len = struct.unpack_from("<H", data, off)[0]
            off += 2
            code = data[off : off + code_len].decode("utf-8")
            off += code_len
            desc_len = struct.unpack_from("<H", data, off)[0]
            off += 2
            desc = data[off : off + desc_len].decode("utf-8")
            off += desc_len
            events.append(Event(onset=onset, duration=duration, channel_id=ch_id, code=code, description=desc))
        return events
