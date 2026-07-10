"""Binary TCP client for EEGDB upload and query/download."""

from __future__ import annotations

import json
import socket
import struct
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from ..auth_proof import compute_proof
from ..models import DT_FLOAT32, DT_FLOAT64, DT_INT16, DT_INT24, DT_INT64, Event

PROTOCOL_VERSION = 2
MAX_FRAME_SIZE = 64 << 20

MSG_HANDSHAKE_REQ = 0x01
MSG_HANDSHAKE_RESP = 0x02
MSG_AUTH_PROOF = 0x03
MSG_AUTH_RESP = 0x04
MSG_WRITE_BATCH = 0x11
MSG_CREATE_STUDY = 0x12
MSG_WRITE_EVENTS = 0x13
MSG_FLUSH_STUDY = 0x14
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
MSG_CLOSE = 0xFF

MAX_READ_BATCH = 65536
CONNECT_TIMEOUT = 10
IO_TIMEOUT = 600


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

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        self.close()
        sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(IO_TIMEOUT)
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
        self,
        name: str,
        channels: List[Dict[str, Any]],
        attrs: Optional[Dict[str, Any]] = None,
        source_file: Optional[Dict[str, Any]] = None,
    ) -> str:
        ch_json = json.dumps(channels).encode("utf-8")
        attrs_json = json.dumps(attrs or {}).encode("utf-8")
        source_json = json.dumps(source_file).encode("utf-8") if source_file else b""
        name_b = name.encode("utf-8")
        payload = (
            struct.pack("<B", len(name_b))
            + name_b
            + struct.pack("<I", len(ch_json))
            + ch_json
            + struct.pack("<I", len(attrs_json))
            + attrs_json
            + struct.pack("<I", len(source_json))
            + source_json
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

    def flush_study(self, study_id: str) -> None:
        sid = study_id.encode("utf-8")
        self._write_frame(MSG_FLUSH_STUDY, struct.pack("<B", len(sid)) + sid)

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

    # ------------------------------------------------------------------
    # Wire helpers (protobuf envelope: [len:4 LE][version][msg_type][payload])
    # ------------------------------------------------------------------
    def _write_frame(self, msg_type: int, payload: bytes) -> None:
        if self._sock is None:
            raise RuntimeError("not connected")
        envelope = self._encode_envelope(msg_type, payload)
        self._sock.sendall(struct.pack("<I", len(envelope)) + envelope)

    def _read_frame(self) -> Tuple[int, bytes]:
        if self._sock is None:
            raise RuntimeError("not connected")
        frame_len = struct.unpack("<I", self._recv_exact(4))[0]
        if frame_len == 0 or frame_len > MAX_FRAME_SIZE:
            raise TCPError(0, f"invalid frame length {frame_len}")
        return self._decode_envelope(self._recv_exact(frame_len))

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
    def _encode_uvarint(value: int) -> bytes:
        out = bytearray()
        while value >= 0x80:
            out.append((value & 0x7F) | 0x80)
            value >>= 7
        out.append(value & 0x7F)
        return bytes(out)

    @classmethod
    def _encode_envelope(cls, msg_type: int, payload: bytes) -> bytes:
        out = bytearray()
        # field 1 = protocol version (varint)
        out.extend(cls._encode_uvarint(1 << 3))
        out.extend(cls._encode_uvarint(PROTOCOL_VERSION))
        # field 2 = message type (varint)
        out.extend(cls._encode_uvarint(2 << 3))
        out.extend(cls._encode_uvarint(msg_type))
        if payload:
            # field 4 = payload (bytes)
            out.extend(cls._encode_uvarint((4 << 3) | 2))
            out.extend(cls._encode_uvarint(len(payload)))
            out.extend(payload)
        return bytes(out)

    @staticmethod
    def _decode_uvarint(data: bytes, off: int) -> Tuple[int, int]:
        value = 0
        shift = 0
        while True:
            if off >= len(data):
                raise TCPError(0, "truncated protobuf varint")
            b = data[off]
            off += 1
            value |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                return value, off
            shift += 7
            if shift > 63:
                raise TCPError(0, "protobuf varint too long")

    @classmethod
    def _decode_envelope(cls, data: bytes) -> Tuple[int, bytes]:
        msg_type = 0
        payload = b""
        off = 0
        while off < len(data):
            tag, off = cls._decode_uvarint(data, off)
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num in (1, 2, 3):
                if wire_type != 0:
                    raise TCPError(0, f"field {field_num} invalid wire type {wire_type}")
                value, off = cls._decode_uvarint(data, off)
                if field_num == 2:
                    msg_type = value
            elif field_num == 4:
                if wire_type != 2:
                    raise TCPError(0, f"payload invalid wire type {wire_type}")
                n, off = cls._decode_uvarint(data, off)
                end = off + n
                if end > len(data):
                    raise TCPError(0, "truncated protobuf bytes field")
                payload = data[off:end]
                off = end
            else:
                if wire_type == 0:
                    _, off = cls._decode_uvarint(data, off)
                elif wire_type == 2:
                    n, off = cls._decode_uvarint(data, off)
                    off += n
                else:
                    raise TCPError(0, f"unsupported wire type {wire_type}")
        if msg_type == 0:
            raise TCPError(0, "envelope missing message type")
        return msg_type, payload

    @staticmethod
    def _encode_handshake(client_name: str) -> bytes:
        name = client_name.encode("utf-8")
        return struct.pack("<BB", PROTOCOL_VERSION, len(name)) + name

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
