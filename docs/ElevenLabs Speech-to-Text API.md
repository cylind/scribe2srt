# 📝 ElevenLabs Speech-to-Text API — Convert Endpoint

## 接口概览

**POST** `https://api.elevenlabs.io/v1/speech-to-text`

用于将音频或视频文件转换为文字转录。

---

## 📋 请求头

| 参数        | 类型   | 必填 | 说明 |
|-------------|--------|------|------|
| `xi-api-key` | string | ✅   | 必需。你的 API Key |

---

## 🔍 查询参数（Query）

- `enable_logging` (boolean, 默认 `true`)  
  是否启用日志记录。若设为 `false`，启用零保留模式，不保留历史记录及 stitching，仅限企业客户使用。

---

## 📦 请求体（multipart/form-data 或 JSON）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `model_id` | string | ✅ | — | 使用的模型 ID，目前支持：`scribe_v1`、`scribe_v1_experimental` |
| `file` | file | *条件* | — | 上传音频/视频文件， ≤1 GB，或与 `cloud_storage_url` 二选一上传 |
| `cloud_storage_url` | string 或 null | *条件* | — | 云存储链接，支持 AWS S3 / GCS / Cloudflare R2 ≤2 GB，二选一上传 |
| `language_code` | string 或 null | 否 | `null` | ISO‑639‑1/3 语言码，若不提供自动识别 |
| `tag_audio_events` | boolean | 否 | `true` | 是否标注非语音事件（如笑声） |
| `num_speakers` | integer 或 null | 否 | `null` | 最大说话人数，1–32 |
| `timestamps_granularity` | enum | 否 | `word` | 时间戳粒度：`word` 或 `character` |
| `diarize` | boolean | 否 | `false` | 是否添加说话人标注 |
| `additional_formats` | array | 否 | — | 额外导出格式 |
| `file_format` | enum | 否 | `other` | 输入格式：`pcm_s16le_16` 或 `other` |
| `webhook` | boolean | 否 | `false` | 如果 `true`，请求异步执行且通过 webhook 返回结果 |
| `temperature` | double 或 null | 否 | 参考模型 | 控制输出随机性（0–2） |

---

## 📤 返回示例（200 成功）

```json
{
  "language_code": "en",
  "language_probability": 0.98,
  "text": "Hello world!",
  "words": [
    {
      "text": "Hello",
      "type": "word",
      "logprob": 42,
      "start": 0.0,
      "end": 0.5,
      "speaker_id": "speaker_1"
    },
    {
      "text": " ",
      "type": "spacing",
      "logprob": 42,
      "start": 0.5,
      "end": 0.5,
      "speaker_id": "speaker_1"
    },
    {
      "text": "world!",
      "type": "word",
      "logprob": 42,
      "start": 0.5,
      "end": 1.2,
      "speaker_id": "speaker_1"
    }
  ],
  "additional_formats": [ /* 如请求即返回对应导出格式 */ ]
}
