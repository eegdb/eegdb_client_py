"""EEGDB Protobuf v1 TCP client using the recoverable EDB frame."""

from __future__ import annotations

import logging
import json
import socket
import ssl
import struct
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np

from ..models import DT_FLOAT32, DT_FLOAT64, DT_INT16, DT_INT24, DT_INT64, Event
from ..protocol.v1 import protocol_pb2 as protocol

logger = logging.getLogger(__package__)

PROTOCOL_VERSION = 1
FRAME_MAGIC = b"EDB"
MAX_FRAME_SIZE = 64 << 20
MAX_READ_BATCH = 65536
CONNECT_TIMEOUT = 10
IO_TIMEOUT = 600


class TCPError(RuntimeError):
    def __init__(self, code: int, message: str, retryable: bool = False):
        super().__init__(f"TCP error {code}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable


class EEGDBTCPClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        database: str = "default",
        client_name: str = "eegdb-client",
        username: str = "",
        password: str = "",
        access_token: str = "",
        auth_scope: str = "",
        http_url: str = "",
        tls_verify: bool = True,
    ):
        self.host = host
        self.port = port
        self.database = database.strip()
        if not self.database:
            raise ValueError("database is required")
        self.client_name = client_name
        self.username = username
        self.password = password
        self.access_token = access_token
        self.auth_scope = auth_scope.strip() or self.database
        self.http_url = http_url.rstrip("/")
        self.tls_verify = tls_verify
        self._sock: Optional[socket.socket] = None
        self._next_request_id = 1

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        """建立 TLS TCP 会话，并在服务端要求时提交短期访问 token。"""
        logger.info(
            "connecting to EEGDB host=%s port=%s database=%s",
            self.host,
            self.port,
            self.database,
        )
        self.close()
        if not self.access_token and self.username and self.password:
            self.access_token = self._login()
        raw_sock = socket.create_connection((self.host, self.port), timeout=CONNECT_TIMEOUT)
        context = ssl.create_default_context()
        if not self.tls_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        sock = context.wrap_socket(raw_sock, server_hostname=self.host)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(IO_TIMEOUT)
        self._sock = sock
        try:
            response = self._exchange(
                protocol.Envelope(
                    handshake_request=protocol.HandshakeRequest(client_name=self.client_name)
                )
            )
            if not response.HasField("handshake_response"):
                raise TCPError(0, f"expected handshake_response, got {response.WhichOneof('body')}")
            handshake = response.handshake_response
            if handshake.auth_required:
                if not self.access_token:
                    raise TCPError(0, "server requires auth; log in first to obtain an access token")
                auth = self._exchange(
                    protocol.Envelope(
                        auth_request=protocol.AuthRequest(access_token=self.access_token)
                    )
                )
                if not auth.HasField("auth_response") or not auth.auth_response.authenticated:
                    raise TCPError(0, "authentication failed")
            logger.info(
                "connected to EEGDB host=%s port=%s database=%s auth_required=%s",
                self.host,
                self.port,
                self.database,
                handshake.auth_required,
            )
        except Exception:
            logger.exception(
                "connection failed host=%s port=%s database=%s",
                self.host,
                self.port,
                self.database,
            )
            self.close()
            raise

    def _login(self) -> str:
        if not self.http_url:
            raise TCPError(0, "http_url is required for username/password login")
        if not self.http_url.startswith("https://"):
            raise TCPError(0, "HTTPS is required for username/password login")
        body = json.dumps({"username": self.username, "password": self.password}).encode("utf-8")
        if self.auth_scope == "process":
            login_path = "/api/v1/process/auth/login"
        else:
            login_path = f"/api/v1/databases/{quote(self.auth_scope, safe='')}/auth/login"
        url = f"{self.http_url}{login_path}"
        context = ssl.create_default_context()
        if not self.tls_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        try:
            with urlopen(Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST"), timeout=CONNECT_TIMEOUT, context=context) as response:
                token = json.loads(response.read().decode("utf-8")).get("access_token", "")
        except Exception as exc:
            raise TCPError(0, f"login failed: {exc}") from exc
        if not isinstance(token, str) or not token:
            raise TCPError(0, "login response did not contain access_token")
        return token

    def close(self) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            request = self._request(protocol.Envelope(close_request=protocol.CloseRequest()))
            self._write_envelope(request)
        except (OSError, ConnectionError, TCPError):
            pass
        try:
            sock.close()
        except OSError:
            pass
        self._sock = None
        logger.info("connection closed host=%s port=%s", self.host, self.port)

    def __enter__(self) -> "EEGDBTCPClient":
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def create_study(
        self,
        name: str,
        channels: List[Dict[str, Any]],
        attrs: Optional[Dict[str, Any]] = None,
        source_file: Optional[Dict[str, Any]] = None,
    ) -> str:
        response = self._exchange(
            protocol.Envelope(
                create_study_request=protocol.CreateStudyRequest(
                    name=name,
                    channels=[self._channel_to_proto(channel) for channel in channels],
                    attributes=self._attrs_to_proto(attrs or {}),
                    source_file=self._source_to_proto(source_file) if source_file else None,
                )
            )
        )
        if not response.HasField("create_study_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")
        return response.create_study_response.study.study_id

    def write_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        data: Union[np.ndarray, List],
    ) -> None:
        arr = np.asarray(data, dtype=self._numpy_dtype(data_type))
        response = self._exchange(
            protocol.Envelope(
                write_batch_request=protocol.WriteBatchRequest(
                    study_id=study_id,
                    channel_id=channel_id,
                    data_type=data_type,
                    start_index=start_index,
                    sample_count=len(arr),
                    samples_le=arr.astype(arr.dtype.newbyteorder("<"), copy=False).tobytes(),
                )
            )
        )
        if not response.HasField("write_batch_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")

    def write_events(self, study_id: str, events: List[Event]) -> None:
        response = self._exchange(
            protocol.Envelope(
                write_events_request=protocol.WriteEventsRequest(
                    study_id=study_id,
                    events=[self._event_to_proto(event) for event in events],
                )
            )
        )
        if not response.HasField("write_events_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")

    def write_events_json(self, study_id: str, events: List[Event]) -> None:
        """Compatibility name retained for upload pipelines; transport is Protobuf."""
        self.write_events(study_id, events)

    def flush_study(self, study_id: str) -> None:
        response = self._exchange(
            protocol.Envelope(
                flush_study_request=protocol.FlushStudyRequest(study_id=study_id)
            )
        )
        if not response.HasField("flush_study_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")

    def list_studies(self) -> List[Dict[str, Any]]:
        response = self._exchange(
            protocol.Envelope(list_studies_request=protocol.ListStudiesRequest())
        )
        if not response.HasField("list_studies_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")
        return [self._study_to_dict(study) for study in response.list_studies_response.studies]

    def get_study(self, study_id: str) -> Dict[str, Any]:
        response = self._exchange(
            protocol.Envelope(
                get_study_request=protocol.GetStudyRequest(study_id=study_id)
            )
        )
        if not response.HasField("get_study_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")
        return self._study_to_dict(response.get_study_response.study)

    def search_studies(self, attrs: Dict[str, str]) -> List[Dict[str, Any]]:
        response = self._exchange(
            protocol.Envelope(
                search_studies_request=protocol.SearchStudiesRequest(attributes=attrs)
            )
        )
        if not response.HasField("search_studies_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")
        return [self._study_to_dict(study) for study in response.search_studies_response.studies]

    def read_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        sample_count: int,
    ) -> Tuple[int, np.ndarray]:
        self._validate_read_count(sample_count)
        response = self._exchange(
            protocol.Envelope(
                read_batch_request=protocol.ReadBatchRequest(
                    study_id=study_id,
                    channel_id=channel_id,
                    data_type=data_type,
                    start_index=start_index,
                    sample_count=sample_count,
                )
            )
        )
        if not response.HasField("read_batch_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")
        batch = response.read_batch_response
        dtype = np.dtype(self._numpy_dtype(batch.data_type)).newbyteorder("<")
        values = np.frombuffer(batch.samples_le, dtype=dtype, count=batch.sample_count).copy()
        return batch.start_index, values

    def read_compressed_batch(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        start_index: int,
        sample_count: int,
        block_codec: int,
    ) -> Tuple[int, int, int, bytes]:
        self._validate_read_count(sample_count)
        if not 0 <= int(block_codec) <= 4:
            raise ValueError(f"block_codec must be 0..4, got {block_codec}")
        response = self._exchange(
            protocol.Envelope(
                read_compressed_batch_request=protocol.ReadCompressedBatchRequest(
                    study_id=study_id,
                    channel_id=channel_id,
                    data_type=data_type,
                    start_index=start_index,
                    sample_count=sample_count,
                    block_codec=int(block_codec) + 1,
                )
            )
        )
        if not response.HasField("read_compressed_batch_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")
        batch = response.read_compressed_batch_response
        return (
            batch.start_index,
            batch.sample_count,
            batch.compression_algorithm,
            bytes(batch.compressed_data),
        )

    def read_events(
        self, study_id: str, filter_json: Optional[Dict[str, Any]] = None
    ) -> List[Event]:
        event_filter = self._event_filter_to_proto(filter_json or {})
        response = self._exchange(
            protocol.Envelope(
                read_events_request=protocol.ReadEventsRequest(
                    study_id=study_id, filter=event_filter
                )
            )
        )
        if not response.HasField("read_events_response"):
            raise TCPError(0, f"unexpected response {response.WhichOneof('body')}")
        return [self._event_from_proto(event) for event in response.read_events_response.events]

    def read_channel_all(
        self,
        study_id: str,
        channel_id: int,
        data_type: int,
        total_samples: int,
        batch_size: int = 8192,
        *,
        local_decode: bool = False,
        block_codec: int = 4,
        codec: Any = None,
    ) -> np.ndarray:
        chunks: List[np.ndarray] = []
        start = 0
        while start < total_samples:
            count = min(batch_size, total_samples - start)
            if local_decode:
                if codec is None:
                    raise ValueError("local_decode requires a LocalCodec instance")
                _, got, algorithm, compressed = self.read_compressed_batch(
                    study_id, channel_id, data_type, start, count, block_codec
                )
                if got == 0:
                    break
                chunks.append(codec.decode(data_type, algorithm, got, compressed))
                start += got
            else:
                _, values = self.read_batch(study_id, channel_id, data_type, start, count)
                if len(values) == 0:
                    break
                chunks.append(values)
                start += len(values)
        if not chunks:
            return np.array([], dtype=self._numpy_dtype(data_type))
        return np.concatenate(chunks)

    def _exchange(self, envelope: protocol.Envelope) -> protocol.Envelope:
        """发送一个请求并校验响应是否属于同一请求和同一数据库。"""
        request = self._request(envelope)
        logger.debug(
            "TCP request id=%s body=%s database=%s",
            request.request_id,
            request.WhichOneof("body"),
            self.database,
        )
        self._write_envelope(request)
        response = self._read_envelope()
        if response.request_id != request.request_id:
            raise TCPError(
                0,
                f"request_id mismatch: got {response.request_id}, want {request.request_id}",
            )
        if response.database_id != self.database:
            raise TCPError(
                0,
                f"database_id mismatch: got {response.database_id}, want {self.database}",
            )
        if response.HasField("error_response"):
            error = response.error_response
            logger.warning(
                "TCP error response id=%s code=%s retryable=%s message=%s",
                response.request_id,
                error.code,
                error.retryable,
                error.message,
            )
            raise TCPError(error.code, error.message, error.retryable)
        logger.debug(
            "TCP response id=%s body=%s",
            response.request_id,
            response.WhichOneof("body"),
        )
        return response

    def _request(self, envelope: protocol.Envelope) -> protocol.Envelope:
        # Envelope 的公共路由字段集中在这里填充，业务方法只构造 oneof 消息体。
        envelope.protocol_version = PROTOCOL_VERSION
        envelope.request_id = self._next_request_id
        envelope.database_id = self.database
        self._next_request_id += 1
        return envelope

    def _write_envelope(self, envelope: protocol.Envelope) -> None:
        if self._sock is None:
            raise RuntimeError("not connected")
        payload = envelope.SerializeToString(deterministic=True)
        if not payload or len(payload) > MAX_FRAME_SIZE:
            raise TCPError(0, f"invalid envelope length {len(payload)}")
        length = struct.pack("<I", len(payload))
        # CRC 覆盖 magic、长度和 protobuf，服务端可在解析消息前发现传输损坏。
        checksum_input = FRAME_MAGIC + length + payload
        self._sock.sendall(checksum_input + struct.pack("<I", _crc32c(checksum_input)))

    def _read_envelope(self) -> protocol.Envelope:
        if self._sock is None:
            raise RuntimeError("not connected")
        self._read_magic()
        encoded_length = self._recv_exact(4)
        length = struct.unpack("<I", encoded_length)[0]
        if length == 0 or length > MAX_FRAME_SIZE:
            raise TCPError(0, f"invalid envelope length {length}")
        payload = self._recv_exact(length)
        expected_crc = struct.unpack("<I", self._recv_exact(4))[0]
        actual_crc = _crc32c(FRAME_MAGIC + encoded_length + payload)
        if actual_crc != expected_crc:
            raise TCPError(0, f"crc32c mismatch: got {actual_crc:08x}, want {expected_crc:08x}")
        envelope = protocol.Envelope()
        envelope.ParseFromString(payload)
        if envelope.protocol_version != PROTOCOL_VERSION:
            raise TCPError(0, f"unsupported protocol version {envelope.protocol_version}")
        if envelope.WhichOneof("body") is None:
            raise TCPError(0, "envelope body is required")
        return envelope

    def _read_magic(self) -> None:
        # 丢帧或读到脏字节时滑动搜索 EDB magic，使后续合法帧仍有机会恢复同步。
        matched = 0
        while matched < len(FRAME_MAGIC):
            value = self._recv_exact(1)[0]
            if value == FRAME_MAGIC[matched]:
                matched += 1
            elif value == FRAME_MAGIC[0]:
                matched = 1
            else:
                matched = 0

    def _recv_exact(self, size: int) -> bytes:
        assert self._sock is not None
        data = bytearray()
        while len(data) < size:
            chunk = self._sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("connection closed")
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _numpy_dtype(data_type: int) -> np.dtype:
        return {
            DT_INT16: np.int16,
            DT_INT24: np.int32,
            DT_FLOAT32: np.float32,
            DT_FLOAT64: np.float64,
            DT_INT64: np.int64,
        }[data_type]

    @staticmethod
    def _validate_read_count(sample_count: int) -> None:
        if sample_count <= 0 or sample_count > MAX_READ_BATCH:
            raise ValueError(f"sample_count must be 1..{MAX_READ_BATCH}")

    @staticmethod
    def _channel_to_proto(value: Dict[str, Any]) -> protocol.ChannelDefinition:
        return protocol.ChannelDefinition(
            channel_id=int(value.get("channel_id", 0)),
            label=str(value.get("label", "")),
            type=str(value.get("type", "")),
            unit=str(value.get("unit", "")),
            sample_rate=float(value.get("sample_rate", 0)),
            data_type=int(value.get("data_type", DT_INT16)),
            physical_min=float(value.get("physical_min", 0)),
            physical_max=float(value.get("physical_max", 0)),
            digital_min=int(value.get("digital_min", 0)),
            digital_max=int(value.get("digital_max", 0)),
            prefilter=str(value.get("prefilter", "")),
            transducer=str(value.get("transducer", "")),
        )

    @staticmethod
    def _attrs_to_proto(value: Dict[str, Any]) -> protocol.StudyAttributes:
        known = {
            "lab",
            "paradigm",
            "device_type",
            "population",
            "condition",
            "session",
            "pi",
            "principal_investigator",
            "device_serial",
            "sampling_rate",
            "ethics_approval",
            "custom",
        }
        custom = {str(k): str(v) for k, v in (value.get("custom") or {}).items()}
        custom.update({str(k): str(v) for k, v in value.items() if k not in known})
        return protocol.StudyAttributes(
            lab=str(value.get("lab", "")),
            paradigm=str(value.get("paradigm", "")),
            device_type=str(value.get("device_type", "")),
            population=str(value.get("population", "")),
            condition=str(value.get("condition", "")),
            session=str(value.get("session", "")),
            principal_investigator=str(
                value.get("principal_investigator", value.get("pi", ""))
            ),
            device_serial=str(value.get("device_serial", "")),
            sampling_rate=str(value.get("sampling_rate", "")),
            ethics_approval=str(value.get("ethics_approval", "")),
            custom=custom,
        )

    @staticmethod
    def _source_to_proto(value: Dict[str, Any]) -> protocol.SourceFileMetadata:
        return protocol.SourceFileMetadata(
            original_name=str(value.get("original_name", "")),
            source_uri=str(value.get("source_uri", "")),
            stored_path=str(value.get("stored_path", "")),
            format=str(value.get("format", "")),
            sha256=str(value.get("sha256", "")),
            size_bytes=int(value.get("size_bytes", 0)),
            imported_by=str(value.get("imported_by", "")),
            software_version=str(value.get("software_version", "")),
            imported_at_unix_ms=int(value.get("imported_at_unix_ms", 0)),
            modified_at_unix_ms=int(value.get("modified_at_unix_ms", 0)),
        )

    @staticmethod
    def _event_to_proto(value: Event) -> protocol.Event:
        return protocol.Event(
            event_id=value.event_id,
            type=value.type,
            onset_us=value.onset,
            duration_us=value.duration,
            channel_id=value.channel_id,
            code=value.code,
            description=value.description,
            trial_id=value.trial_id,
            source=value.source,
            confidence=value.confidence,
            attributes=value.attributes,
        )

    @staticmethod
    def _event_from_proto(value: protocol.Event) -> Event:
        return Event(
            event_id=value.event_id,
            type=value.type,
            onset=value.onset_us,
            duration=value.duration_us,
            channel_id=value.channel_id,
            code=value.code,
            description=value.description,
            trial_id=value.trial_id,
            source=value.source,
            confidence=value.confidence,
            attributes=dict(value.attributes),
        )

    @staticmethod
    def _event_filter_to_proto(value: Dict[str, Any]) -> protocol.EventFilter:
        result = protocol.EventFilter(
            code_prefix=str(value.get("code_prefix", "")),
            type=str(value.get("type", "")),
            trial_id=str(value.get("trial_id", "")),
            source=str(value.get("source", "")),
        )
        if "start_us" in value:
            result.start_us = int(value["start_us"])
        if "end_us" in value:
            result.end_us = int(value["end_us"])
        if "channel_id" in value and value["channel_id"] is not None:
            result.channel_id = int(value["channel_id"])
        return result

    @classmethod
    def _study_to_dict(cls, value: protocol.Study) -> Dict[str, Any]:
        return {
            "study_id": value.study_id,
            "name": value.name,
            "attributes": {
                "lab": value.attributes.lab,
                "pi": value.attributes.principal_investigator,
                "device_type": value.attributes.device_type,
                "device_serial": value.attributes.device_serial,
                "sampling_rate": value.attributes.sampling_rate,
                "paradigm": value.attributes.paradigm,
                "population": value.attributes.population,
                "condition": value.attributes.condition,
                "session": value.attributes.session,
                "ethics_approval": value.attributes.ethics_approval,
                "custom": dict(value.attributes.custom),
            },
            "channels": [
                {
                    "channel_id": channel.channel_id,
                    "label": channel.label,
                    "type": channel.type,
                    "unit": channel.unit,
                    "sample_rate": channel.sample_rate,
                    "data_type": channel.data_type,
                    "physical_min": channel.physical_min,
                    "physical_max": channel.physical_max,
                    "digital_min": channel.digital_min,
                    "digital_max": channel.digital_max,
                    "prefilter": channel.prefilter,
                    "transducer": channel.transducer,
                }
                for channel in value.channels
            ],
            "start_index": value.start_index,
            "end_index": value.end_index,
            "num_samples": value.num_samples,
            "created_at_unix_ms": value.created_at_unix_ms,
            "updated_at_unix_ms": value.updated_at_unix_ms,
        }


_CRC32C_TABLE: Optional[Tuple[int, ...]] = None


def _crc32c(data: bytes) -> int:
    global _CRC32C_TABLE
    if _CRC32C_TABLE is None:
        polynomial = 0x82F63B78
        table = []
        for value in range(256):
            crc = value
            for _ in range(8):
                crc = (crc >> 1) ^ polynomial if crc & 1 else crc >> 1
            table.append(crc)
        _CRC32C_TABLE = tuple(table)
    crc = 0xFFFFFFFF
    for value in data:
        crc = _CRC32C_TABLE[(crc ^ value) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF
