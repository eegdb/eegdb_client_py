#!/usr/bin/env python3
"""
EEGDB Python Client Demo

功能：
1. 读取本地 EDF 文件
2. 通过 EEGDB HTTP API 上传数据（创建 Study + 导入 EDF 或手动写入通道数据）
3. 通过 API 查询/下载数据
4. 将下载的数据重新组合成 EDF 文件

使用方式：
    python3 eegdb_client.py --server http://localhost:8080 \
                            --edf input.edf \
                            --study-id demo-study \
                            --output output.edf

依赖：
    pip install pyedflib requests numpy
"""

import argparse
import json
import os
import struct
import sys
import time
from typing import List, Dict, Any, Optional

import numpy as np
import requests

from eegdb_client.auth_proof import compute_proof


class _ProofSession(requests.Session):
    def __init__(self, base_url: str, token_name: str, api_token: str):
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._token_name = token_name
        self._api_token = api_token

    def request(self, method, url, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        if self._api_token and self._token_name:
            path = url[len(self._base_url) :] if url.startswith(self._base_url) else url
            if path not in ("/health", "/api/v1/auth/nonce"):
                nonce_resp = super().request(
                    "GET", f"{self._base_url}/api/v1/auth/nonce", timeout=30
                )
                nonce_resp.raise_for_status()
                nonce_data = nonce_resp.json()
                if nonce_data.get("auth_enabled"):
                    nonce_hex = nonce_data["nonce"]
                    nonce = bytes.fromhex(nonce_hex)
                    proof = compute_proof(self._api_token, nonce)
                    headers["X-EEGDB-Nonce"] = nonce_hex
                    headers["Authorization"] = f"EEGDB-Proof {self._token_name}:{proof.hex()}"
        return super().request(method, url, headers=headers, **kwargs)


class EEGDBClient:
    """EEGDB HTTP API 客户端"""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        token_name: str = "",
        api_token: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.session = _ProofSession(self.base_url, token_name, api_token)

    # ------------------------------------------------------------------
    # 健康检查 / 统计
    # ------------------------------------------------------------------
    def health(self) -> dict:
        """健康检查"""
        resp = self.session.get(f"{self.base_url}/health")
        resp.raise_for_status()
        return resp.json()

    def stats(self) -> dict:
        """数据库统计"""
        resp = self.session.get(f"{self.base_url}/api/v1/stats")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Study 管理
    # ------------------------------------------------------------------
    def create_study(self, name: str, channels: List[dict],
                     attributes: Optional[dict] = None,
                     study_id: Optional[str] = None) -> dict:
        """创建研究
        
        Args:
            name: Study name
            channels: List of channel definitions
            attributes: Optional study attributes
            study_id: Optional custom study ID. If not provided, server auto-generates one.
        
        Returns:
            The created study dict (contains server-generated study_id if not provided)
        """
        payload = {
            "name": name,
            "channels": channels,
        }
        if study_id:
            payload["study_id"] = study_id
        if attributes:
            payload["attributes"] = attributes
        resp = self.session.post(
            f"{self.base_url}/api/v1/studies",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def get_study(self, study_id: str) -> dict:
        """获取研究详情"""
        resp = self.session.get(f"{self.base_url}/api/v1/studies/{study_id}")
        resp.raise_for_status()
        return resp.json()

    def list_studies(self) -> dict:
        """列出所有研究"""
        resp = self.session.get(f"{self.base_url}/api/v1/studies")
        resp.raise_for_status()
        return resp.json()

    def delete_study(self, study_id: str) -> dict:
        """删除研究"""
        resp = self.session.delete(f"{self.base_url}/api/v1/studies/{study_id}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # EDF 导入 / 导出
    # ------------------------------------------------------------------
    def import_edf(self, study_id: str, edf_path: str,
                   lab: str = "", device_type: str = "", paradigm: str = "") -> dict:
        """导入 EDF 文件到指定 Study"""
        with open(edf_path, "rb") as f:
            files = {"file": (os.path.basename(edf_path), f, "application/octet-stream")}
            data = {}
            if lab:
                data["lab"] = lab
            if device_type:
                data["device_type"] = device_type
            if paradigm:
                data["paradigm"] = paradigm
            resp = self.session.post(
                f"{self.base_url}/api/v1/studies/{study_id}/import",
                files=files,
                data=data,
            )
        resp.raise_for_status()
        return resp.json()

    def export_edf(self, study_id: str, output_path: str):
        """导出 Study 为 EDF 文件"""
        resp = self.session.post(
            f"{self.base_url}/api/v1/studies/{study_id}/export",
            stream=True,
        )
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    # ------------------------------------------------------------------
    # 通道数据操作
    # ------------------------------------------------------------------
    def query_channel(self, study_id: str, channel_id: int,
                      idx_start: Optional[int] = None,
                      idx_end: Optional[int] = None,
                      start_time_us: Optional[int] = None,
                      end_time_us: Optional[int] = None) -> dict:
        """查询通道数据"""
        params: Dict[str, Any] = {}
        if idx_start is not None:
            params["idx_start"] = idx_start
        if idx_end is not None:
            params["idx_end"] = idx_end
        if start_time_us is not None:
            params["start"] = start_time_us
        if end_time_us is not None:
            params["end"] = end_time_us
        resp = self.session.get(
            f"{self.base_url}/api/v1/studies/{study_id}/channels/{channel_id}/data",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def write_sample(self, study_id: str, channel_id: int,
                     sample_index: int, value: int) -> dict:
        """写入单个采样点"""
        payload = {
            "sample_index": sample_index,
            "value": value,
        }
        resp = self.session.post(
            f"{self.base_url}/api/v1/studies/{study_id}/channels/{channel_id}/data",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def write_batch(self, study_id: str, channel_id: int,
                    start_index: int, values: List[int]) -> dict:
        """批量写入采样点（连续模式）"""
        payload = {
            "start_index": start_index,
            "values": values,
        }
        resp = self.session.post(
            f"{self.base_url}/api/v1/studies/{study_id}/batch?channel={channel_id}",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def flush(self, study_id: str) -> dict:
        """刷新 MemTable 到磁盘"""
        resp = self.session.post(
            f"{self.base_url}/api/v1/studies/{study_id}/flush"
        )
        resp.raise_for_status()
        return resp.json()


# ====================================================================
# EDF 读写辅助函数
# ====================================================================

def read_edf(edf_path: str) -> dict:
    """
    读取 EDF 文件，返回包含 header 和 signals 的字典。
    使用 pyedflib 库。
    """
    import pyedflib

    f = pyedflib.EdfReader(edf_path)
    try:
        n_signals = f.signals_in_file
        n_records = f.datarecords_in_file
        duration = f.datarecord_duration  # 秒（浮点）

        signals = []
        for i in range(n_signals):
            sig = {
                "label": f.getLabel(i).strip(),
                "sample_rate": f.getSampleFrequency(i),
                "physical_dimension": f.getPhysicalDimension(i).strip(),
                "physical_min": f.getPhysicalMinimum(i),
                "physical_max": f.getPhysicalMaximum(i),
                "digital_min": f.getDigitalMinimum(i),
                "digital_max": f.getDigitalMaximum(i),
                "transducer": f.getTransducer(i).strip(),
                "prefilter": f.getPrefilter(i).strip(),
                "samples_per_record": f.getNSamples()[i],
                "data": f.readSignal(i),
            }
            signals.append(sig)

        header = {
            "patient_id": f.getPatientCode().strip(),
            "recording_id": f.getRecordingAdditional().strip(),
            "startdate": f.getStartdatetime(),
            "datarecord_duration": duration,
            "datarecords_in_file": n_records,
        }
    finally:
        f.close()

    return {"header": header, "signals": signals}


def write_edf(output_path: str, signals: List[dict], header: dict):
    """
    将信号数据写入 EDF 文件。
    signals: 每个元素包含 label, sample_rate, data, physical_min, physical_max 等
    header: 包含 patient_id, recording_id, startdate 等
    """
    import pyedflib
    from datetime import datetime

    n_signals = len(signals)
    if n_signals == 0:
        raise ValueError("No signals to write")

    # 确定 samples_per_record（取整）
    # EDF 要求每个 data record 的持续时间相同，这里统一用 1 秒
    record_duration = 1  # 秒
    samples_per_record = [int(round(s["sample_rate"] * record_duration)) for s in signals]

    writer = pyedflib.EdfWriter(output_path, n_channels=n_signals, file_type=pyedflib.FILETYPE_EDFPLUS)
    try:
        # 设置文件头信息
        file_header = {
            "technician": "",
            "recording_additional": header.get("recording_id", ""),
            "patientname": "",
            "patient_additional": "",
            "patientcode": header.get("patient_id", ""),
            "equipment": "",
            "admincode": "",
            "gender": "",
            "sex": "",
            "startdate": header.get("startdate") or datetime.now(),
            "birthdate": "",
        }
        writer.setHeader(file_header)

        # 设置通道信息
        channel_info = []
        data_buffers = []
        for i, sig in enumerate(signals):
            # 将数据缩放到 digital 范围
            phys_min = sig.get("physical_min", float(np.min(sig["data"])))
            phys_max = sig.get("physical_max", float(np.max(sig["data"])))
            dig_min = sig.get("digital_min", -32768)
            dig_max = sig.get("digital_max", 32767)

            ch_dict = {
                "label": sig["label"][:16].ljust(16),
                "dimension": sig.get("physical_dimension", "uV")[:8].ljust(8),
                "sample_frequency": samples_per_record[i],
                "physical_min": phys_min,
                "physical_max": phys_max,
                "digital_min": dig_min,
                "digital_max": dig_max,
                "transducer": sig.get("transducer", "")[:80].ljust(80),
                "prefilter": sig.get("prefilter", "")[:80].ljust(80),
            }
            channel_info.append(ch_dict)
            data_buffers.append(sig["data"].astype(np.float64))

        writer.setSignalHeaders(channel_info)
        writer.writeSamples(data_buffers)
    finally:
        writer.close()


# ====================================================================
# 主流程
# ====================================================================

def upload_edf_via_import(client: EEGDBClient, study_id: str, edf_path: str,
                          lab: str = "", paradigm: str = "") -> dict:
    """
    方式一：通过 /import 接口直接上传 EDF 文件（服务器端解析导入）
    """
    print(f"[Upload] Importing EDF '{edf_path}' -> study '{study_id}' ...")
    study = client.import_edf(study_id, edf_path, lab=lab, paradigm=paradigm)
    print(f"[Upload] Import OK. channels={len(study.get('channels', []))}, "
          f"num_samples={study.get('num_samples', 'N/A')}")
    return study


def _convert_physical_to_digital(data: np.ndarray, sig: dict) -> np.ndarray:
    """将浮点物理值转换为 digital int16"""
    phys_min, phys_max = sig["physical_min"], sig["physical_max"]
    dig_min, dig_max = sig["digital_min"], sig["digital_max"]
    if phys_max == phys_min:
        return np.zeros_like(data, dtype=np.int16)
    digital = ((data - phys_min) / (phys_max - phys_min) * (dig_max - dig_min) + dig_min)
    return np.clip(digital, dig_min, dig_max).astype(np.int16)


def _convert_digital_to_physical(digital: np.ndarray, ch: dict) -> np.ndarray:
    """将 digital int16 转换回物理值"""
    phys_min = ch.get("physical_min", -32768.0)
    phys_max = ch.get("physical_max", 32767.0)
    dig_min = ch.get("digital_min", -32768)
    dig_max = ch.get("digital_max", 32767)
    if dig_max == dig_min:
        return np.zeros_like(digital, dtype=np.float64)
    scale = (phys_max - phys_min) / (dig_max - dig_min)
    offset = phys_min - scale * dig_min
    return digital.astype(np.float64) * scale + offset


def upload_edf_via_api(client: EEGDBClient, edf_data: dict,
                        study_name: Optional[str] = None) -> dict:
    """
    手动创建 Study，然后通过 API 逐通道按 1 秒批次写入采样数据。
    如果未提供 study_name，则使用 EDF 文件名或默认名称。
    返回创建的 study（包含服务器生成的 study_id）。
    """
    signals = edf_data["signals"]
    header = edf_data["header"]

    # 构建 ChannelDef
    channels = []
    for i, sig in enumerate(signals):
        scale_factor = 1.0
        offset = 0.0
        if sig["digital_max"] != sig["digital_min"]:
            scale_factor = (sig["physical_max"] - sig["physical_min"]) / (
                sig["digital_max"] - sig["digital_min"]
            )
            offset = sig["physical_min"] - scale_factor * sig["digital_min"]

        ch = {
            "label": sig["label"],
            "type": "EEG",
            "unit": sig["physical_dimension"],
            "channel_id": i,
            "data_type": 0x01,  # ADC_RAW_INT16
            "sample_rate": sig["sample_rate"],
            "physical_min": sig["physical_min"],
            "physical_max": sig["physical_max"],
            "digital_min": sig["digital_min"],
            "digital_max": sig["digital_max"],
            "scale_factor": scale_factor,
            "offset": offset,
            "transducer": sig.get("transducer", ""),
            "prefilter": sig.get("prefilter", ""),
        }
        channels.append(ch)

    # 创建 Study（不指定 study_id，让服务器自动生成）
    name = study_name or "edf-import"
    print(f"[Upload] Creating study '{name}' with {len(channels)} channels ...")
    study = client.create_study(
        name=name,
        channels=channels,
        attributes={"paradigm": "imported_via_api", "lab": "eegdb_client_py"},
    )
    study_id = study["study_id"]
    print(f"[Upload] Study created with ID: {study_id}")

    # 逐通道按 1 秒批次写入数据
    for ch_idx, sig in enumerate(signals):
        sample_rate = sig["sample_rate"]
        samples_per_sec = int(round(sample_rate))
        data = sig["data"]

        # 将浮点物理值转回 digital int16
        digital = _convert_physical_to_digital(data, sig)

        total = len(digital)
        print(f"[Upload] Writing channel {ch_idx} ({sig['label']}): {total} samples "
              f"(sample_rate={sample_rate}, {samples_per_sec} samples/sec) ...")

        written = 0
        start_idx = 0
        sec_count = 0
        while start_idx < total:
            end_idx = min(start_idx + samples_per_sec, total)
            batch = digital[start_idx:end_idx].tolist()
            resp = client.write_batch(study_id, ch_idx, start_idx, batch)
            written += resp.get("written", len(batch))
            start_idx = end_idx
            sec_count += 1

        print(f"[Upload] Channel {ch_idx} written: {written}/{total} "
              f"(in {sec_count} batches of ~{samples_per_sec} samples)")

    # 刷新到磁盘
    print(f"[Upload] Flushing study '{study_id}' ...")
    client.flush(study_id)
    print(f"[Upload] Done.")
    return study


def download_and_rebuild_edf(client: EEGDBClient, study_id: str, output_path: str,
                             original_header: dict = None):
    """
    从 API 下载 Study 的通道数据，并重新组合成 EDF 文件。
    支持分块查询大样本数据，可保留原始 EDF header 信息。
    """
    print(f"[Download] Fetching study '{study_id}' ...")
    study = client.get_study(study_id)
    channels = study.get("channels", [])
    if not channels:
        raise ValueError("Study has no channels")

    signals = []
    for ch in channels:
        ch_id = ch["channel_id"]
        label = ch["label"]
        print(f"[Download] Querying channel {ch_id} ({label}) ...")

        # 先查询一次获取总样本数
        data_resp = client.query_channel(study_id, ch_id)
        total_samples = data_resp.get("sample_count", 0)
        all_samples = data_resp.get("samples", [])

        # 如果一次没返回完，按块查询剩余数据
        chunk_size = 10000
        if total_samples > len(all_samples):
            print(f"[Download] Channel {ch_id}: fetching remaining "
                  f"{total_samples - len(all_samples)} samples in chunks ...")
            for start in range(len(all_samples), total_samples, chunk_size):
                end = min(start + chunk_size - 1, total_samples - 1)
                chunk_resp = client.query_channel(study_id, ch_id, idx_start=start, idx_end=end)
                chunk_samples = chunk_resp.get("samples", [])
                all_samples.extend(chunk_samples)
                print(f"[Download]   fetched [{start}:{end}] = {len(chunk_samples)} samples")

        print(f"[Download] Channel {ch_id}: {len(all_samples)}/{total_samples} samples received")

        # 将 digital int16 转回物理值
        digital = np.array(all_samples, dtype=np.int16)
        physical = _convert_digital_to_physical(digital, ch)

        sig = {
            "label": label,
            "sample_rate": ch.get("sample_rate", 256.0),
            "physical_dimension": ch.get("unit", "uV"),
            "physical_min": ch.get("physical_min", -32768.0),
            "physical_max": ch.get("physical_max", 32767.0),
            "digital_min": ch.get("digital_min", -32768),
            "digital_max": ch.get("digital_max", 32767),
            "transducer": ch.get("transducer", ""),
            "prefilter": ch.get("prefilter", ""),
            "data": physical,
        }
        signals.append(sig)

    # 构建 header：优先使用原始 header，否则从 study 中提取
    header = {
        "patient_id": original_header.get("patient_id", "") if original_header else study.get("patient_id", ""),
        "recording_id": original_header.get("recording_id", "") if original_header else study_id,
        "startdate": original_header.get("startdate") if original_header else None,
    }

    print(f"[Download] Writing EDF to '{output_path}' ...")
    write_edf(output_path, signals, header)
    print(f"[Download] EDF saved: {output_path}")


def compare_edf(path1: str, path2: str, tolerance: float = 1e-3) -> bool:
    """
    比较两个 EDF 文件的内容是否一致（在容差范围内）。
    """
    print(f"[Compare] Comparing '{path1}' vs '{path2}' ...")
    d1 = read_edf(path1)
    d2 = read_edf(path2)

    sigs1 = d1["signals"]
    sigs2 = d2["signals"]

    if len(sigs1) != len(sigs2):
        print(f"[Compare] FAIL: channel count mismatch ({len(sigs1)} vs {len(sigs2)})")
        return False

    all_ok = True
    for i, (s1, s2) in enumerate(zip(sigs1, sigs2)):
        if s1["label"] != s2["label"]:
            print(f"[Compare] Channel {i}: label mismatch '{s1['label']}' vs '{s2['label']}'")
            all_ok = False
            continue
        if len(s1["data"]) != len(s2["data"]):
            print(f"[Compare] Channel {i}: sample count mismatch {len(s1['data'])} vs {len(s2['data'])}")
            all_ok = False
            continue
        diff = np.max(np.abs(s1["data"] - s2["data"]))
        if diff > tolerance:
            print(f"[Compare] Channel {i} ({s1['label']}): max diff = {diff:.6f} > tolerance {tolerance}")
            all_ok = False
        else:
            print(f"[Compare] Channel {i} ({s1['label']}): OK (max diff = {diff:.6f})")

    if all_ok:
        print("[Compare] All channels match!")
    else:
        print("[Compare] Some channels differ.")
    return all_ok

def main():
    parser = argparse.ArgumentParser(
        description="EEGDB Python Client - EDF upload/download via API"
    )
    parser.add_argument("--server", default="http://localhost:8080",
                        help="EEGDB server URL")
    parser.add_argument("--token-name", default="",
                        help="API token name (when server auth enabled)")
    parser.add_argument("--api-token", default="",
                        help="API token secret (when server auth enabled)")
    parser.add_argument("--edf", required=True,
                        help="Input EDF file path")
    parser.add_argument("--study-name", default="edf-api-demo",
                        help="Study name (server auto-generates study_id if not provided)")
    parser.add_argument("--output", default="downloaded.edf",
                        help="Output EDF file path")
    parser.add_argument("--gen-test", action="store_true",
                        help="Generate a test EDF file instead of reading --edf")
    parser.add_argument("--delete-after", action="store_true",
                        help="Delete study after download")
    parser.add_argument("--no-compare", action="store_true",
                        help="Skip comparing original and downloaded EDF")
    args = parser.parse_args()

    client = EEGDBClient(args.server, token_name=args.token_name, api_token=args.api_token)

    # 健康检查
    try:
        health = client.health()
        print(f"[Info] Server health: {health}")
    except requests.exceptions.ConnectionError as e:
        print(f"[Error] Cannot connect to server {args.server}: {e}")
        sys.exit(1)

    if not os.path.exists(args.edf):
        print(f"[Error] EDF file not found: {args.edf}")
        sys.exit(1)

    edf_data = read_edf(args.edf)
    print(f"[Info] Input EDF: {len(edf_data['signals'])} channels, "
          f"{edf_data['header']['datarecords_in_file']} records, "
          f"duration={edf_data['header']['datarecords_in_file'] * edf_data['header']['datarecord_duration']:.1f}s")

    # Step 1 & 2: 创建 Study 并按 1 秒分块上传数据
    study = upload_edf_via_api(client, edf_data, study_name=args.study_name)
    study_id = study["study_id"]

    # Step 3: 下载并重建 EDF
    download_and_rebuild_edf(client, study_id, args.output,
                             original_header=edf_data["header"])

    # 比较原始和下载的 EDF
    # 注意：由于 EDF 是 digital 格式（int16），physical 值经过
    # physical->digital->physical 转换后会有量化误差（约 ±2 digital steps）
    if not args.no_compare:
        compare_edf(args.edf, args.output, tolerance=0.02)

    # 清理
    if args.delete_after:
        print(f"[Cleanup] Deleting study '{study_id}' ...")
        client.delete_study(study_id)
        print("[Cleanup] Done.")

    print("[Done] All operations completed successfully.")


if __name__ == "__main__":
    main()
