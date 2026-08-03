# EEGDB Python 客户端代码调用链

本文聚焦 Python 客户端内部流程。工作区全貌见上级目录的 `PROJECT_STRUCTURE.md`。

## 1. 入口

- GUI：`app.py` → `eegdb_client.ui.main_window.run_app`
- 模块入口：`python -m eegdb_client` → `eegdb_client/__main__.py`
- CLI：`eegdb_client/cli.py` 分派 health、upload、list、download
- 库调用：直接使用 `EEGDBTCPClient`、`EEGDBQueryClient` 或 `EEGDBEpochs`

## 2. 文件上传

```text
CLI/GUI 选择文件
  → readers.edf_reader / fif_reader / cdt_reader
  → models.SourceFile
      ├── ChannelDef 列表
      ├── 每通道 NumPy 数组
      └── Event 列表
  → upload.pipeline.upload_source_file
  → TCP create_study
  → TCP write_batch（按时间窗、逐通道）
  → TCP write_events
  → TCP flush_study
```

上传按时间窗交错通道，而不是先传完整通道 0 再传通道 1。这样服务端 MemTable flush 得到的块形状与多通道时间查询一致。混合采样率文件会按通道采样率换算窗口。

## 3. TCP 请求

```text
业务方法构造 Envelope oneof body
  → _exchange
  → _request 填 protocol_version/request_id/database_id
  → _write_envelope 序列化并添加 EDB 帧头、长度和 CRC32C
  → socket
  → _read_envelope 校验长度、CRC、协议版本
  → _exchange 校验 request_id/database_id 和 error_response
```

连接时先发送 handshake。若服务端返回 nonce 且要求认证，客户端发送 `SHA256(SHA256(secret) || nonce)` 证明，不在网络上传输 token 明文。

## 4. 下载

```text
download.fetcher
  → get_study 获取通道和总范围
  → 分批 read_batch
  → 可选 read_compressed_batch + codec_local
  → writers.edf_writer / fif_writer / npz_writer
```

本地解码需要安装兄弟仓库 `eegdb-codec` 生成的 Python wheel 或设置 native library 路径。

## 5. HTTP 分析查询

```text
EEGDBQueryClient
  → 业务方法生成 /api/v1/... 相对路径
  → _request 插入 /databases/{database} 作用域
  → urllib.request
  → JSON 响应
```

Epoch 还可通过 `EEGDBEpochs.from_http` 或 `from_server` 获取，结果组织为 `(epochs, channels, samples)` NumPy 数组，并可转换成 MNE `EpochsArray`。

## 6. GUI 线程关系

`ui/pages/` 只管理界面状态和用户输入，耗时的连接、上传、查询和下载交给 `ui/workers.py` 中的后台 worker，完成后通过 Qt signal 更新页面，避免阻塞 UI 事件循环。

## 7. 生成文件

`eegdb_client/protocol/v1/protocol_pb2.py` 来自服务端 Protobuf schema，不应手工编辑。协议升级时必须同步服务端 schema、Go/Python 生成物和帧兼容性测试。

