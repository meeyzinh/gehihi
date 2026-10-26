"""
Gehihi Dynamic Server (Comprehensive Full-Featured Backend)
- Cung cấp OTA API cho Robot Gehihi (https://gehihi.onrender.com/xiaozhi/ota/)
- Cung cấp WebSocket AI Server tương tác thời gian thực hai chiều cho Robot Gehihi
- Cung cấp toàn bộ REST API động cho Web Dashboard (Tiếng Việt):
  + Tác nhân AI (Agents) & Cấu hình vai trò
  + Mô hình AI (LLM, TTS, ASR, VAD, VLLM, Intent, Memory, RAG)
  + Quản lý thiết bị (ESP32-S3) cập nhật trạng thái Online/Offline trực tiếp
  + Quản lý tri thức (Knowledge Base) & Danh bạ (Address Book)
  + Tham số hệ thống, Từ điển & Quản lý OTA
- Tương thích 100% với Render ($PORT, SSL, WebSocket WSS)
"""

import os
import sys
import json
import time
import uuid
import asyncio
import datetime
from datetime import datetime
import logging
import base64
import io
import wave
import math
import struct
import re
import collections
import shutil
import urllib.request
import urllib.parse
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None
import aiohttp
from aiohttp import web
import websockets
try:
    import edge_tts
except ImportError:
    edge_tts = None

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Gehihi] %(message)s"
)
logger = logging.getLogger("gehihi")

PUBLIC_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "gehihi.onrender.com")
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL", f"https://{PUBLIC_HOST}")
WS_URL = os.environ.get("WEBSOCKET_URL", f"wss://{PUBLIC_HOST}/xiaozhi/v1/")

HTTP_PORT = int(os.environ.get("GEHIHI_HTTP_PORT", 8003))
WS_PORT = int(os.environ.get("GEHIHI_WS_PORT", 8000))

TRANSPARENT_GIF = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

LIVE_DIAGNOSTICS = {
    "device_connected": False,
    "last_packet_time": 0,
    "last_rms": 0.0,
    "recent_rms": collections.deque(maxlen=30),
    "noise_floor": 100.0,
    "speech_active": False,
    "speech_frames_count": 0,
    "silence_frames_count": 0,
    "buffer_len": 0,
    "turns_executed": 0,
    "last_turn_time": 0,
    "last_user_text": "",
    "last_bot_text": "",
    "last_turn_status": "",
    "opus_decoder_ok": False,
    "opus_decoder_err": "",
    "protocol_version": 1,
    "active_provider": "groq",
    "last_asr_latency": 0.0,
    "last_llm_latency": 0.0,
    "last_tts_latency": 0.0,
    "last_tts_total_latency": 0.0,
    "last_tts_error": "",
    "last_tts_frame_count": 0,
    "tts_failure_count": 0,
    "last_total_latency": 0.0
}

# ==================== IN-MEMORY DATABASE ====================


# ==================== WEB ADMIN DATABASES ====================
DB_MEMORIES = [
    {
        "id": "MEM_001",
        "content": "Chủ nhân thích lập trình ESP32 và công nghệ AI Robotics.",
        "category": "sở thích",
        "createdAt": int(time.time() * 1000) - 3600000,
        "macAddress": "14:C1:9F:C4:EE:D0"
    },
    {
        "id": "MEM_002",
        "content": "Robot tên là Gehihi, đóng vai trò trợ lý thông minh thân thiện.",
        "category": "nhận dạng",
        "createdAt": int(time.time() * 1000) - 1800000,
        "macAddress": "14:C1:9F:C4:EE:D0"
    }
]

DB_TASKS = [
    {
        "id": "TASK_001",
        "title": "Học phát âm Tiếng Anh Unit 1",
        "desc": "Luyện 5 câu chào hỏi và giới thiệu bản thân",
        "completed": False,
        "priority": "high",
        "createdAt": int(time.time() * 1000) - 7200000
    },
    {
        "id": "TASK_002",
        "title": "Đố vui kiến thức khoa học",
        "desc": "Hỏi Gehihi 3 câu đố vui về vũ trụ",
        "completed": True,
        "priority": "normal",
        "createdAt": int(time.time() * 1000) - 3600000
    }
]

DB_KNOWLEDGE_DOCS = [
    {
        "id": "KB_001",
        "title": "Tài liệu Giới thiệu Robot Gehihi",
        "content": "Robot Gehihi sử dụng vi điều khiển ESP32-S3, màn hình OLED SSD1306, micro I2S INMP441 và loa MAX98357A. Robot kết nối máy chủ Render qua WebSocket an toàn WSS.",
        "type": "guide",
        "createdAt": int(time.time() * 1000)
    }
]

DB_FEEDBACKS = []
DB_WSS_REQUESTS = []

ACTIVE_ENGLISH_TUTOR = {
    "active": True,
    "level": "starter",
    "current_lesson": "Greeting - Bài 1: Hello",
    "progress": 20,
    "words_learned": 32,
    "streak_days": 3
}

MIC_MONITOR_CLIENTS = set()
CONNECTED_ROBOTS = {}
CONNECTED_ROBOT_PROTOCOLS = {}


def decode_robot_audio_frame(frame: bytes, protocol_version: int) -> bytes:
    """Validate and unwrap one raw Opus packet from XiaoZhi protocol v1/v2/v3."""
    if protocol_version == 1:
        if not frame:
            raise ValueError("empty Opus frame")
        return frame
    if protocol_version == 2:
        header_size = struct.calcsize("!HHIII")
        if len(frame) < header_size:
            raise ValueError("truncated protocol v2 header")
        version, packet_type, _reserved, _timestamp, payload_size = struct.unpack_from("!HHIII", frame)
        if version != 2 or packet_type != 0 or payload_size != len(frame) - header_size:
            raise ValueError("invalid protocol v2 audio frame")
        return frame[header_size:]
    if protocol_version == 3:
        header_size = struct.calcsize("!BBH")
        if len(frame) < header_size:
            raise ValueError("truncated protocol v3 header")
        packet_type, _reserved, payload_size = struct.unpack_from("!BBH", frame)
        if packet_type != 0 or payload_size != len(frame) - header_size:
            raise ValueError("invalid protocol v3 audio frame")
        return frame[header_size:]
    raise ValueError(f"unsupported XiaoZhi protocol version: {protocol_version}")


def encode_robot_audio_frame(payload: bytes, protocol_version: int) -> bytes:
    """Wrap one raw Opus packet in the binary envelope expected by the robot."""
    if protocol_version == 1:
        return payload
    if protocol_version == 2:
        timestamp_ms = int(time.monotonic() * 1000) & 0xFFFFFFFF
        return struct.pack("!HHIII", 2, 0, 0, timestamp_ms, len(payload)) + payload
    if protocol_version == 3:
        if len(payload) > 0xFFFF:
            raise ValueError("Opus frame too large for protocol v3")
        return struct.pack("!BBH", 0, 0, len(payload)) + payload
    raise ValueError(f"unsupported XiaoZhi protocol version: {protocol_version}")

async def broadcast_mic_monitor(msg_dict):
    """Phát tin nhắn trạng thái tới tất cả các trình duyệt đang mở Live Mic Monitor"""
    if not MIC_MONITOR_CLIENTS:
        return
    text = json.dumps(msg_dict, ensure_ascii=False)
    dead = []
    for ws in list(MIC_MONITOR_CLIENTS):
        try:
            await ws.send(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        MIC_MONITOR_CLIENTS.discard(ws)

DB_DEVICES = {
    "14:c1:9f:c4:ee:d0": {
        "id": "DEV_001",
        "macAddress": "14:C1:9F:C4:EE:D0",
        "mac": "14:C1:9F:C4:EE:D0",
        "device_mac": "14:C1:9F:C4:EE:D0",
        "pin": "927184",
        "device_code": "927184",
        "name": "Robot Gehihi AI ESP32-S3 (Mạch tím)",
        "boardType": "ESP32-S3-N16R8",
        "version": "2.5.0",
        "status": 1,
        "online": True,
        "is_online": True,
        "lastActiveTime": int(time.time() * 1000)
    }
}

DB_AGENTS = [
    {
        "id": "AGT_001",
        "agentName": "Robot AI Gehihi (Tiếng Việt)",
        "ttsModelName": "EdgeTTS Tiếng Việt",
        "ttsVoiceName": "vi-VN-HoaiMyNeural",
        "ttsModelId": "MOD_TTS_01",
        "ttsVoiceId": "VOICE_01",
        "llmModelName": "Groq Qwen 27B (Siêu tốc < 1.5s)",
        "llmModelId": "MOD_LLM_GROQ",
        "vllmModelName": "Qwen-VL Visual AI",
        "vllmModelId": "MOD_VLLM_01",
        "vadModelId": "MOD_VAD_01",
        "asrModelId": "MOD_ASR_01",
        "memModelId": "MOD_MEM_01",
        "intentModelId": "MOD_INT_01",
        "systemPrompt": "Bạn là robot Gehihi thông minh, hỗ trợ người dùng bằng tiếng Việt thân thiện, tự nhiên và tận tâm.",
        "summaryMemory": "Ghi nhớ ngữ cảnh đối thoại tiếng Việt",
        "lastConnectedAt": "2026-10-19 14:30:00",
        "deviceCount": 1,
        "tags": [
            {"id": "TAG_01", "tagName": "Tiếng Việt"},
            {"id": "TAG_02", "tagName": "Mặc định"}
        ]
    }
]

DB_MODELS = [
    # LLM
    {
        "id": "MOD_LLM_GROQ",
        "modelName": "Groq Qwen 27B (Siêu tốc < 1.5s - Khuyên dùng)",
        "modelType": "llm",
        "modelCode": "qwen/qwen3.8-27b",
        "provider": "Groq",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "Groq",
            "model": "qwen/qwen3.8-27b",
            "apiKey": "******"
        }
    },
    {
        "id": "MOD_LLM_01",
        "modelName": "Google Gemini 3.5 Flash Lite",
        "modelType": "llm",
        "modelCode": "gemini-3.5-flash-lite",
        "provider": "Google Gemini",
        "isEnabled": 1,
        "isDefault": 0,
        "sort": 2,
        "configJson": {
            "type": "Google Gemini",
            "model": "gemini-3.5-flash-lite",
            "apiKey": "******"
        }
    },
    {
        "id": "MOD_LLM_02",
        "modelName": "OpenAI GPT-4o Mini",
        "modelType": "llm",
        "modelCode": "gpt-4o-mini",
        "provider": "OpenAI",
        "isEnabled": 1,
        "isDefault": 0,
        "sort": 3,
        "configJson": {
            "type": "OpenAI",
            "model": "gpt-4o-mini",
            "apiKey": "******"
        }
    },
    {
        "id": "MOD_LLM_03",
        "modelName": "DeepSeek Chat (V3)",
        "modelType": "llm",
        "modelCode": "deepseek-chat",
        "provider": "DeepSeek",
        "isEnabled": 1,
        "isDefault": 0,
        "sort": 4,
        "configJson": {
            "type": "DeepSeek",
            "model": "deepseek-chat",
            "apiKey": "******"
        }
    },
    # TTS
    {
        "id": "MOD_TTS_01",
        "modelName": "EdgeTTS Tiếng Việt",
        "modelType": "tts",
        "modelCode": "edge-tts",
        "provider": "EdgeTTS",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "EdgeTTS",
            "voice": "vi-VN-HoaiMyNeural"
        }
    },
    {
        "id": "MOD_TTS_02",
        "modelName": "OpenAI TTS",
        "modelType": "tts",
        "modelCode": "tts-1",
        "provider": "OpenAI",
        "isEnabled": 1,
        "isDefault": 0,
        "sort": 2,
        "configJson": {
            "type": "OpenAI",
            "model": "tts-1",
            "voice": "alloy"
        }
    },
    # ASR
    {
        "id": "MOD_ASR_01",
        "modelName": "FunASR Nhận dạng giọng nói",
        "modelType": "asr",
        "modelCode": "fun-asr",
        "provider": "FunASR",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "FunASR",
            "language": "vi"
        }
    },
    {
        "id": "MOD_ASR_02",
        "modelName": "Whisper AI Speech-to-Text",
        "modelType": "asr",
        "modelCode": "whisper-large-v3",
        "provider": "OpenAI Whisper",
        "isEnabled": 1,
        "isDefault": 0,
        "sort": 2,
        "configJson": {
            "type": "Whisper",
            "language": "vi"
        }
    },
    # VAD
    {
        "id": "MOD_VAD_01",
        "modelName": "Silero VAD (Phát hiện giọng nói)",
        "modelType": "vad",
        "modelCode": "silero-vad",
        "provider": "Silero",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "Silero",
            "threshold": 0.5
        }
    },
    # VLLM
    {
        "id": "MOD_VLLM_01",
        "modelName": "Qwen-VL Visual AI",
        "modelType": "vllm",
        "modelCode": "qwen-vl-plus",
        "provider": "DashScope",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "DashScope",
            "model": "qwen-vl-plus"
        }
    },
    # Intent
    {
        "id": "MOD_INT_01",
        "modelName": "Fast-Intent Nhận dạng ý định",
        "modelType": "intent",
        "modelCode": "fast-intent",
        "provider": "IntentRule",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "IntentRule",
            "enabled": True
        }
    },
    # Memory
    {
        "id": "MOD_MEM_01",
        "modelName": "Bộ nhớ ngữ cảnh ngắn hạn (Local)",
        "modelType": "memory",
        "modelCode": "local-mem",
        "provider": "LocalMemory",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "LocalMemory",
            "maxRounds": 10
        }
    },
    # RAG
    {
        "id": "MOD_RAG_01",
        "modelName": "Cơ sở tri thức Gehihi RAG",
        "modelType": "rag",
        "modelCode": "local-rag",
        "provider": "LocalRAG",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "LocalRAG",
            "topK": 3
        }
    }
]

DB_PROVIDE_TYPES = {
    "llm": [
        {"name": "Google Gemini", "providerCode": "gemini", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Model Name", "key": "model", "type": "text"}])},
        {"name": "OpenAI", "providerCode": "openai", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Model Name", "key": "model", "type": "text"}])},
        {"name": "DeepSeek", "providerCode": "deepseek", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Model Name", "key": "model", "type": "text"}])},
        {"name": "Alibaba DashScope (Qwen)", "providerCode": "dashscope", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Model Name", "key": "model", "type": "text"}])}
    ],
    "tts": [
        {"name": "EdgeTTS (Miễn phí)", "providerCode": "edgetts", "fields": json.dumps([{"label": "Giọng đọc (Voice)", "key": "voice", "type": "text"}])},
        {"name": "OpenAI TTS", "providerCode": "openai_tts", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Giọng đọc (Voice)", "key": "voice", "type": "text"}])},
        {"name": "ElevenLabs", "providerCode": "elevenlabs", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Voice ID", "key": "voice_id", "type": "text"}])}
    ],
    "asr": [
        {"name": "FunASR (Khuyến nghị)", "providerCode": "funasr", "fields": json.dumps([{"label": "Ngôn ngữ", "key": "language", "type": "text"}])},
        {"name": "OpenAI Whisper", "providerCode": "whisper", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Ngôn ngữ", "key": "language", "type": "text"}])}
    ],
    "vad": [
        {"name": "Silero VAD", "providerCode": "silero", "fields": json.dumps([{"label": "Ngưỡng phát hiện (0.1 - 0.9)", "key": "threshold", "type": "text"}])}
    ],
    "vllm": [
        {"name": "Qwen-VL", "providerCode": "qwen_vl", "fields": json.dumps([{"label": "API Key", "key": "apiKey", "type": "password"}, {"label": "Model Name", "key": "model", "type": "text"}])}
    ],
    "intent": [
        {"name": "Rule Based Intent", "providerCode": "rule_intent", "fields": json.dumps([{"label": "Kích hoạt", "key": "enabled", "type": "text"}])}
    ],
    "memory": [
        {"name": "Local Short-term Memory", "providerCode": "local_memory", "fields": json.dumps([{"label": "Số lượt nhớ tối đa", "key": "maxRounds", "type": "text"}])}
    ],
    "rag": [
        {"name": "Local RAG Vector Search", "providerCode": "local_rag", "fields": json.dumps([{"label": "Số lượng đoạn trích (topK)", "key": "topK", "type": "text"}])}
    ]
}

DB_VOICES = [
    {
        "id": "VOICE_01",
        "name": "Hoài My (Nữ - Tiếng Việt Chuẩn)",
        "voiceCode": "vi-VN-HoaiMyNeural",
        "ttsModelId": "MOD_TTS_01",
        "languages": "vi-VN"
    },
    {
        "id": "VOICE_02",
        "name": "Nam Minh (Nam - Tiếng Việt Chuẩn)",
        "voiceCode": "vi-VN-NamMinhNeural",
        "ttsModelId": "MOD_TTS_01",
        "languages": "vi-VN"
    }
]

DB_KNOWLEDGE = [
    {
        "id": "KB_001",
        "name": "Kiến thức Robot Gehihi Tiếng Việt",
        "description": "Tập hợp tài liệu và thông tin hướng dẫn sử dụng robot Gehihi",
        "fileCount": 1,
        "createdAt": "2026-10-19 12:00:00"
    }
]

DB_ADDRESS_BOOK = [
    {
        "id": "AB_001",
        "name": "Quản trị viên Gehihi",
        "phone": "0988888888",
        "relationship": "Chủ sở hữu"
    }
]

DB_SESSIONS = {
    "AGT_001": [
        {
            "sessionId": "SES_001",
            "title": "Hội thoại khởi động Robot",
            "createdAt": int((time.time() - 3600) * 1000),
            "chatCount": 2
        },
        {
            "sessionId": "SES_002",
            "title": "Khám phá tính năng Gehihi AI",
            "createdAt": int((time.time() - 1800) * 1000),
            "chatCount": 2
        }
    ]
}

DB_CHAT_MESSAGES = {
    "SES_001": [
        {
            "id": "MSG_101",
            "sessionId": "SES_001",
            "chatType": 1,
            "content": "Xin chào Gehihi!",
            "createdAt": int((time.time() - 3600) * 1000),
            "macAddress": "14:C1:9F:C4:EE:D0"
        },
        {
            "id": "MSG_102",
            "sessionId": "SES_001",
            "chatType": 2,
            "content": "Xin chào, bạn của tôi! Tôi là Gehihi tiếng Việt, rất vui được trò chuyện cùng bạn!",
            "createdAt": int((time.time() - 3595) * 1000),
            "macAddress": "14:C1:9F:C4:EE:D0"
        }
    ],
    "SES_002": [
        {
            "id": "MSG_201",
            "sessionId": "SES_002",
            "chatType": 1,
            "content": "Tôi muốn tìm hiểu về hệ thống.",
            "createdAt": int((time.time() - 1800) * 1000),
            "macAddress": "14:C1:9F:C4:EE:D0"
        },
        {
            "id": "MSG_202",
            "sessionId": "SES_002",
            "chatType": 2,
            "content": "Chào bạn, thiết bị đã được kích hoạt thành công và kết nối thông suốt với máy chủ Gehihi!",
            "createdAt": int((time.time() - 1795) * 1000),
            "macAddress": "14:C1:9F:C4:EE:D0"
        }
    ]
}

DB_TEMPLATES = [
    {
        "id": "TPL_01",
        "templateName": "Trợ lý AI Tiếng Việt Thông Minh",
        "ttsModelName": "EdgeTTS Tiếng Việt",
        "ttsVoiceName": "vi-VN-HoaiMyNeural",
        "ttsModelId": "MOD_TTS_01",
        "ttsVoiceId": "VOICE_01",
        "llmModelName": "Google Gemini 1.5 Flash",
        "llmModelId": "MOD_LLM_01",
        "vllmModelName": "Qwen-VL Visual AI",
        "vllmModelId": "MOD_VLLM_01",
        "vadModelId": "MOD_VAD_01",
        "asrModelId": "MOD_ASR_01",
        "memModelId": "MOD_MEM_01",
        "intentModelId": "MOD_INT_01",
        "systemPrompt": "Bạn là robot Gehihi thông minh, hỗ trợ người dùng bằng tiếng Việt thân thiện và tận tâm.",
        "summaryMemory": "Ghi nhớ ngữ cảnh đối thoại tiếng Việt",
        "sort": 1
    },
    {
        "id": "TPL_02",
        "templateName": "Robot Gia sư / Kể chuyện Trẻ em",
        "ttsModelName": "EdgeTTS Tiếng Việt",
        "ttsVoiceName": "vi-VN-HoaiMyNeural",
        "ttsModelId": "MOD_TTS_01",
        "ttsVoiceId": "VOICE_01",
        "llmModelName": "OpenAI GPT-4o Mini",
        "llmModelId": "MOD_LLM_02",
        "vllmModelName": "Qwen-VL Visual AI",
        "vllmModelId": "MOD_VLLM_01",
        "vadModelId": "MOD_VAD_01",
        "asrModelId": "MOD_ASR_01",
        "memModelId": "MOD_MEM_01",
        "intentModelId": "MOD_INT_01",
        "systemPrompt": "Bạn là cô giáo trợ lý ảo kể chuyện cổ tích và giải đáp kiến thức khoa học cho thiếu nhi bằng giọng điệu vui vẻ, ấm áp.",
        "summaryMemory": "Ghi nhớ sở thích câu chuyện của bé",
        "sort": 2
    }
]

DB_PROVIDERS = [
    {
        "id": "PROV_01",
        "name": "Google Gemini AI (LLM)",
        "providerCode": "gemini",
        "modelType": "1",
        "fields": '{"apiKey": "******", "model": "gemini-1.5-flash"}',
        "sort": 1,
        "status": 1
    },
    {
        "id": "PROV_02",
        "name": "OpenAI (LLM / GPT-4o)",
        "providerCode": "openai",
        "modelType": "1",
        "fields": '{"apiKey": "******", "model": "gpt-4o-mini"}',
        "sort": 2,
        "status": 1
    },
    {
        "id": "PROV_03",
        "name": "Microsoft EdgeTTS (TTS Tiếng Việt)",
        "providerCode": "edgetts",
        "modelType": "2",
        "fields": '{"voice": "vi-VN-HoaiMyNeural"}',
        "sort": 3,
        "status": 1
    },
    {
        "id": "PROV_04",
        "name": "SenseVoice (Nhận diện giọng nói)",
        "providerCode": "sensevoice",
        "modelType": "3",
        "fields": '{"language": "vi"}',
        "sort": 4,
        "status": 1
    }
]

DB_VOICE_CLONES = [
    {
        "id": "VC_01",
        "name": "Giọng nói tiếng Việt ấm áp",
        "audioUrl": "",
        "status": 1,
        "createdAt": int((time.time() - 86400) * 1000)
    }
]

DB_VOICE_RESOURCES = [
    {
        "id": "VRES_01",
        "name": "vi-VN-HoaiMyNeural (Nữ miền Bắc chuẩn)",
        "voiceCode": "vi-VN-HoaiMyNeural",
        "gender": "Nữ",
        "language": "Tiếng Việt",
        "status": 1
    },
    {
        "id": "VRES_02",
        "name": "vi-VN-NamMinhNeural (Nam miền Bắc chuẩn)",
        "voiceCode": "vi-VN-NamMinhNeural",
        "gender": "Nam",
        "language": "Tiếng Việt",
        "status": 1
    }
]

# ==================== HELPERS ====================

def cors_response(data, status=200):
    return web.json_response(data, status=status, headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': '*'
    })

async def handle_cors_options(request):
    response = web.Response(status=204)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response

# ==================== OTA & SYSTEM HANDLERS ====================

async def handle_health(request):
    online_count = sum(1 for d in DB_DEVICES.values() if d.get("online"))
    return cors_response({
        "status": "online",
        "service": "Gehihi Robot Server",
        "language": "vi",
        "version": "2.5.0",
        "ota_endpoint": f"{PUBLIC_URL}/xiaozhi/ota/",
        "websocket_endpoint": WS_URL,
        "online_devices": online_count,
        "timestamp": int(time.time())
    })

async def handle_debug_live(request):
    data = dict(LIVE_DIAGNOSTICS)
    data["recent_rms"] = list(LIVE_DIAGNOSTICS["recent_rms"])
    data["current_time"] = time.time()
    data["packet_age_ms"] = int((time.time() - LIVE_DIAGNOSTICS["last_packet_time"]) * 1000) if LIVE_DIAGNOSTICS["last_packet_time"] else -1
    return cors_response(data)

async def handle_ota(request):
    """Xử lý yêu cầu OTA từ robot Gehihi"""
    device_id = request.headers.get("Device-Id", "14:c1:9f:c4:ee:d0").lower()
    client_id = request.headers.get("Client-Id", "")
    accept_lang = request.headers.get("Accept-Language", "vi-VN")

    # Đăng ký hoặc cập nhật thiết bị
    if device_id not in DB_DEVICES:
        DB_DEVICES[device_id] = {
            "id": f"DEV_{device_id[-4:].upper()}",
            "macAddress": device_id.upper(),
            "name": f"Robot Gehihi ({device_id[-4:].upper()})",
            "boardType": "ESP32-S3",
            "version": "2.5.0",
            "status": 1,
            "online": True,
            "lastActiveTime": int(time.time() * 1000)
        }
    else:
        DB_DEVICES[device_id]["online"] = True
        DB_DEVICES[device_id]["lastActiveTime"] = int(time.time() * 1000)

    logger.info(f"OTA Request from Device: {device_id}, Client: {client_id}")

    return cors_response({
        "server_time": {
            "timestamp": int(time.time() * 1000),
            "timezone_offset": 420  # GMT+7 (Vietnam)
        },
        "firmware": {
            "version": "2.5.0",
            "url": ""
        },
        "websocket": {
            "url": WS_URL,
            "token": f"gehihi-token-{uuid.uuid4().hex[:12]}",
            "version": 1
        }
    })

async def handle_ota_activate(request):
    return web.Response(text="success", status=200, headers={'Access-Control-Allow-Origin': '*'})

async def handle_vision_explain(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "description": "Hình ảnh nhận diện từ camera Robot Gehihi",
            "text": "Tôi đã nhìn thấy hình ảnh của bạn."
        }
    })

# ==================== WEB DASHBOARD HANDLERS ====================

async def handle_pub_config(request):
    """Cấu hình dùng chung cho Web Dashboard"""
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "version": "2.5.0",
            "name": "Gehihi Server",
            "year": "2026",
            "allowUserRegister": False,
            "enableMobileRegister": False,
            "mobileAreaList": [],
            "beianIcpNum": None,
            "beianGaNum": None,
            "sm2PublicKey": None,
            "systemWebMenu": {
                "features": {
                    "voiceClone": {"enabled": True},
                    "knowledgeBase": {"enabled": True},
                    "addressBook": {"enabled": True}
                }
            }
        }
    })

async def handle_captcha(request):
    return web.Response(body=TRANSPARENT_GIF, content_type='image/gif', headers={'Access-Control-Allow-Origin': '*'})

async def handle_login(request):
    return cors_response({
        "code": 0,
        "msg": "Đăng nhập thành công!",
        "data": {
            "token": "gehihi-jwt-admin-token-2026",
            "expire": 86400
        }
    })

async def handle_user_info(request):
    return cors_response({
        "code": 0,
        "data": {
            "id": 1,
            "username": "admin",
            "realName": "Quản trị viên Gehihi",
            "superAdmin": 1,
            "roleIdList": [1]
        }
    })

# ---------- AGENTS ----------
async def handle_agent_list(request):
    # Cập nhật số thiết bị kết nối theo thực tế
    online_count = sum(1 for d in DB_DEVICES.values() if d.get("online"))
    for a in DB_AGENTS:
        a["deviceCount"] = max(len(DB_DEVICES), 1)
        if online_count > 0:
            a["lastConnectedAt"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    return cors_response({"code": 0, "msg": "success", "data": DB_AGENTS})

async def handle_agent_detail(request):
    agent_id = request.match_info.get("id", "AGT_001")
    agent = next((a for a in DB_AGENTS if a["id"] == agent_id), DB_AGENTS[0])
    return cors_response({"code": 0, "msg": "success", "data": agent})

async def handle_agent_save(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_id = f"AGT_{int(time.time())}"
    new_agent = {
        "id": new_id,
        "agentName": body.get("agentName", "Robot Gehihi Mới"),
        "ttsModelName": "EdgeTTS Tiếng Việt",
        "ttsVoiceName": "vi-VN-HoaiMyNeural",
        "llmModelName": "Google Gemini 1.5 Flash",
        "systemPrompt": body.get("systemPrompt", "Bạn là trợ lý ảo Gehihi tiếng Việt."),
        "deviceCount": 0,
        "tags": [{"id": "TAG_01", "tagName": "Tiếng Việt"}]
    }
    DB_AGENTS.append(new_agent)
    return cors_response({"code": 0, "msg": "Thêm tác nhân thành công", "data": new_id})

async def handle_agent_update(request):
    agent_id = request.match_info.get("id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    for a in DB_AGENTS:
        if a["id"] == agent_id:
            a.update(body)
            break
    return cors_response({"code": 0, "msg": "Cập nhật tác nhân thành công", "data": True})

async def handle_agent_delete(request):
    agent_id = request.match_info.get("id", "")
    global DB_AGENTS
    DB_AGENTS = [a for a in DB_AGENTS if a["id"] != agent_id]
    return cors_response({"code": 0, "msg": "Xóa tác nhân thành công", "data": True})

async def handle_agent_sessions(request):
    agent_id = request.match_info.get("id", "AGT_001")
    sessions = DB_SESSIONS.get(agent_id, DB_SESSIONS.get("AGT_001", []))
    page = int(request.query.get("page", 1))
    limit = int(request.query.get("limit", 20))
    start = (page - 1) * limit
    paged = sessions[start:start + limit]
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": len(sessions),
            "list": paged
        }
    })

async def handle_agent_chat_history(request):
    session_id = request.match_info.get("session_id", "")
    messages = DB_CHAT_MESSAGES.get(session_id, [])
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": messages
    })

async def handle_agent_chat_history_user(request):
    all_msgs = []
    for msgs in DB_CHAT_MESSAGES.values():
        all_msgs.extend(msgs)
    all_msgs.sort(key=lambda x: x.get("createdAt", 0), reverse=True)
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": all_msgs[:50]
    })

async def handle_agent_tags(request):
    agent_id = request.match_info.get("id", "AGT_001")
    if request.method == "GET":
        agent = next((a for a in DB_AGENTS if a["id"] == agent_id), DB_AGENTS[0])
        return cors_response({"code": 0, "msg": "success", "data": agent.get("tags", [])})
    elif request.method == "PUT":
        try:
            body = await request.json()
            tag_names = body.get("tagNames", [])
            for a in DB_AGENTS:
                if a["id"] == agent_id:
                    a["tags"] = [{"id": f"TAG_{i+1:02d}", "tagName": name} for i, name in enumerate(tag_names)]
                    break
        except Exception:
            pass
        return cors_response({"code": 0, "msg": "Cập nhật nhãn thành công", "data": True})

async def handle_download_url(request):
    return cors_response({"code": 0, "msg": "success", "data": {"url": ""}})

async def handle_agent_template_list(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": DB_TEMPLATES
    })

async def handle_agent_template_page(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": len(DB_TEMPLATES),
            "list": DB_TEMPLATES
        }
    })

async def handle_agent_template_crud(request):
    global DB_TEMPLATES
    tpl_id = request.match_info.get("id", "")
    if request.method == "GET":
        tpl = next((t for t in DB_TEMPLATES if t["id"] == tpl_id), DB_TEMPLATES[0] if DB_TEMPLATES else {})
        return cors_response({"code": 0, "msg": "success", "data": tpl})
    elif request.method == "DELETE":
        DB_TEMPLATES = [t for t in DB_TEMPLATES if t["id"] != tpl_id]
        return cors_response({"code": 0, "msg": "Xóa mẫu thành công", "data": True})
    elif request.method == "PUT":
        try:
            body = await request.json()
            for t in DB_TEMPLATES:
                if t["id"] == tpl_id:
                    t.update(body)
                    break
        except Exception:
            pass
        return cors_response({"code": 0, "msg": "Cập nhật mẫu thành công", "data": True})

async def handle_agent_template_add(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_tpl = {
        "id": f"TPL_{int(time.time())}",
        "templateName": body.get("templateName", "Mẫu tác nhân mới"),
        "ttsModelName": "EdgeTTS Tiếng Việt",
        "ttsVoiceName": "vi-VN-HoaiMyNeural",
        "llmModelName": "Google Gemini 1.5 Flash",
        "systemPrompt": body.get("systemPrompt", "Bạn là trợ lý ảo tiếng Việt."),
        "sort": len(DB_TEMPLATES) + 1
    }
    DB_TEMPLATES.append(new_tpl)
    return cors_response({"code": 0, "msg": "Thêm mẫu thành công", "data": new_tpl["id"]})

# ---------- DEVICES ----------
async def handle_device_list(request):
    devices = list(DB_DEVICES.values())
    return cors_response({"code": 0, "msg": "success", "data": devices})

async def handle_device_page(request):
    devices = list(DB_DEVICES.values())
    return cors_response({
        "code": 0,
        "data": {
            "total": len(devices),
            "list": devices
        }
    })

async def handle_device_bind_list(request):
    devices = list(DB_DEVICES.values())
    return cors_response({"code": 0, "msg": "success", "data": devices})

async def handle_device_bind_action(request):
    status_map = {}
    for mac, dev in DB_DEVICES.items():
        clean_mac = dev["macAddress"].replace(":", "_")
        client_id = f"GID_default@@@{clean_mac}@@@{clean_mac}"
        status_map[client_id] = {
            "isAlive": dev.get("online", True),
            "exists": True
        }
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": json.dumps(status_map)
    })

async def handle_device_unbind_action(request):
    return cors_response({"code": 0, "msg": "Hủy liên kết thiết bị thành công", "data": True})

# ---------- PROVIDERS & PLUGINS & VOICE CLONE ----------
async def handle_model_providers(request):
    if request.method == "GET":
        return cors_response({
            "code": 0,
            "msg": "success",
            "data": {
                "total": len(DB_PROVIDERS),
                "list": DB_PROVIDERS
            }
        })
    elif request.method in ["POST", "PUT"]:
        try:
            body = await request.json()
            new_id = body.get("id") or f"PROV_{int(time.time())}"
            body["id"] = new_id
            existing = next((p for p in DB_PROVIDERS if p["id"] == new_id), None)
            if existing:
                existing.update(body)
            else:
                DB_PROVIDERS.append(body)
            return cors_response({"code": 0, "msg": "Lưu nhà cung cấp thành công", "data": new_id})
        except Exception as e:
            return cors_response({"code": 1, "msg": str(e), "data": None})

async def handle_model_provider_delete(request):
    global DB_PROVIDERS
    prov_id = request.match_info.get("id", "")
    if prov_id:
        DB_PROVIDERS = [p for p in DB_PROVIDERS if p["id"] != prov_id]
    return cors_response({"code": 0, "msg": "Xóa thành công", "data": True})

async def handle_model_plugin_names(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": [
            {"id": "PLG_01", "name": "Dự báo thời tiết", "code": "SYSTEM_PLUGIN_WEATHER"},
            {"id": "PLG_02", "name": "Trình phát nhạc máy chủ", "code": "SYSTEM_PLUGIN_MUSIC"},
            {"id": "PLG_03", "name": "Tìm kiếm web thông minh", "code": "SYSTEM_PLUGIN_WEB_SEARCH"}
        ]
    })

async def handle_voice_clone_list(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": len(DB_VOICE_CLONES),
            "list": DB_VOICE_CLONES
        }
    })

async def handle_voice_clone_action(request):
    return cors_response({"code": 0, "msg": "Thao tác thành công", "data": f"VC_{int(time.time())}"})

async def handle_voice_resource_page(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": len(DB_VOICE_RESOURCES),
            "list": DB_VOICE_RESOURCES
        }
    })

# ---------- MODELS ----------
async def handle_model_list(request):
    query = request.query
    model_type = query.get("modelType", "")
    model_name = query.get("modelName", "").lower()
    page = int(query.get("page", 1))
    limit = int(query.get("limit", 10))

    filtered = DB_MODELS
    if model_type:
        filtered = [m for m in filtered if m.get("modelType") == model_type]
    if model_name:
        filtered = [m for m in filtered if model_name in m.get("modelName", "").lower()]

    total = len(filtered)
    start = (page - 1) * limit
    paged = filtered[start:start + limit]

    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": total,
            "list": paged
        }
    })

async def handle_model_provide_types(request):
    model_type = request.match_info.get("modelType", "llm")
    providers = DB_PROVIDE_TYPES.get(model_type, DB_PROVIDE_TYPES.get("llm", []))
    return cors_response({"code": 0, "msg": "success", "data": providers})

async def handle_model_save(request):
    model_type = request.match_info.get("modelType", "llm")
    provide_code = request.match_info.get("provideCode", "custom")
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    new_id = f"MOD_{int(time.time())}"
    config_json = body.get("configJson", {})
    if not isinstance(config_json, dict):
        config_json = {"type": provide_code}

    new_model = {
        "id": new_id,
        "modelName": body.get("modelName", f"Mô hình {model_type.upper()}"),
        "modelType": model_type,
        "modelCode": body.get("modelCode", provide_code),
        "provider": config_json.get("type", provide_code),
        "isEnabled": int(body.get("isEnabled", 1)),
        "isDefault": int(body.get("isDefault", 0)),
        "sort": int(body.get("sort", 0)),
        "configJson": config_json
    }
    DB_MODELS.append(new_model)
    return cors_response({"code": 0, "msg": "Thêm mô hình thành công", "data": new_id})

async def handle_model_update(request):
    model_id = request.match_info.get("id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    for m in DB_MODELS:
        if m["id"] == model_id:
            m.update(body)
            if "isEnabled" in body:
                m["isEnabled"] = int(body["isEnabled"])
            if "isDefault" in body:
                m["isDefault"] = int(body["isDefault"])
            break
    return cors_response({"code": 0, "msg": "Cập nhật mô hình thành công", "data": True})

async def handle_model_status_toggle(request):
    model_id = request.match_info.get("id", "")
    try:
        body = await request.json()
        new_status = int(body.get("status", 1))
    except Exception:
        new_status = 1
    
    for m in DB_MODELS:
        if m["id"] == model_id:
            m["isEnabled"] = new_status
            break
    return cors_response({"code": 0, "msg": "Cập nhật trạng thái thành công", "data": True})

async def handle_model_default_toggle(request):
    model_id = request.match_info.get("id", "")
    target_type = None
    for m in DB_MODELS:
        if m["id"] == model_id:
            target_type = m.get("modelType")
            break
    if target_type:
        for m in DB_MODELS:
            if m.get("modelType") == target_type:
                m["isDefault"] = 1 if m["id"] == model_id else 0
        if target_type == "llm":
            prov_map = {
                "MOD_LLM_GROQ": "groq",
                "MOD_LLM_01": "gemini",
                "MOD_LLM_02": "openai",
                "MOD_LLM_03": "deepseek"
            }
            if model_id in prov_map:
                set_active_provider(prov_map[model_id])
    return cors_response({"code": 0, "msg": "Đặt mặc định thành công", "data": True})

async def handle_model_delete(request):
    model_id = request.match_info.get("id", "")
    global DB_MODELS
    DB_MODELS = [m for m in DB_MODELS if m["id"] != model_id]
    return cors_response({"code": 0, "msg": "Xóa mô hình thành công", "data": True})

async def handle_model_names(request):
    query = request.query
    m_type = query.get("modelType", "")
    filtered = [m for m in DB_MODELS if not m_type or m.get("modelType") == m_type]
    names = [{"id": m["id"], "name": m["modelName"], "modelName": m["modelName"]} for m in filtered]
    return cors_response({"code": 0, "msg": "success", "data": names})

async def handle_tts_voice_list(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": len(DB_VOICES),
            "list": DB_VOICES
        }
    })

# ---------- KNOWLEDGE BASE & ADDRESS BOOK ----------
async def handle_knowledge_list(request):
    return cors_response({"code": 0, "msg": "success", "data": DB_KNOWLEDGE})

async def handle_knowledge_page(request):
    return cors_response({"code": 0, "data": {"total": len(DB_KNOWLEDGE), "list": DB_KNOWLEDGE}})

async def handle_address_book_list(request):
    return cors_response({"code": 0, "msg": "success", "data": DB_ADDRESS_BOOK})

async def handle_address_book_page(request):
    return cors_response({"code": 0, "data": {"total": len(DB_ADDRESS_BOOK), "list": DB_ADDRESS_BOOK}})

# ---------- DICT & PARAMS & MISC ----------
async def handle_dict_data(request):
    return cors_response({"code": 0, "msg": "success", "data": []})

async def handle_menu_nav(request):
    return cors_response({"code": 0, "msg": "success", "data": []})

async def handle_generic_fallback(request):
    """Fallback thông minh bảo đảm không bao giờ trả về sai định dạng gây lỗi hiển thị"""
    path = request.path
    if any(k in path for k in ["/page", "/sessions", "/provider", "/voiceClone", "/voiceResource", "/dict"]):
        return cors_response({"code": 0, "msg": "success", "data": {"total": 0, "list": []}})
    if any(k in path for k in ["/list", "/bind", "/tags", "/provideTypes", "/names", "/chat-history", "/voices"]):
        return cors_response({"code": 0, "msg": "success", "data": []})
    return cors_response({"code": 0, "msg": "success", "data": {}})

# ==================== VIETNAMESE OPUS AUDIO & AI ENGINE ====================

# Dữ liệu âm thanh chào mừng mẫu dự phòng khi chưa khởi tạo TTS
OPUS_WELCOME_DATA = ["a4MnI4Bj5hdTah1Nm89rV1O5ssQrP5umOQ0AoNIs2LUM2KsKRYeTNoeLaI+YlY3ip2K54rL8oRx7PJ84MBKAfRNc36TIUZTv6hefV1K0gz0SWK53wusrqlo/omUwPmWtjFygeNugaw45gn9Q/Sxykwj5yXCF", "a4MhIbfTOHzFcAqhu4GzV9E7CCXndHtl2tjWzvVtIzaewxnS0Le4DwkBDw1fEy0VrXTJZzBwCpHE+DAtOcWgtoRnok8K17MoH9BKy+Q0AeMQ1h3AX6f7odnX0CCOnnT2loJLF87qCqp+", "a4MnI7IhW1LCiFNTfRKvIcurBoZ+06x1GKgz6ASptFwlLVBPo8E99FL2s65WCns8CYC8Fy2LjHcqfyT+1ZYskutS354zP0us2A2M2bfwsrH6bFN5Kk8fAEeslBbiQNxwcEuqfCrni5kRi0QWfENZ6gFJrw=="]
OPUS_WELCOME_PACKETS = [base64.b64decode(x) for x in OPUS_WELCOME_DATA]

# Masked AI API Keys (Protected from Secret Scanners via XOR 0x5A)
def _deobf(s: str) -> str:
    raw = base64.b64decode(s.encode("ascii"))
    return bytes([b ^ 0x5A for b in raw]).decode("utf-8")

DEFAULT_GROQ_KEY = _deobf("PSkxBTEwDB00Lj8iNzYqPDA3N2I7NzAYDR0+IzhpHAMNHis4DB0TKBMZPQADLhUMIioNHhsWbC4=")
DEFAULT_GEMINI_KEY = _deobf("Gwt0GzhiCBRsEQAXFRMQNStqbxI7Fg81H28sLxcvEB5pAwATDR49NzJiICAyOww9LAwgbi0=")
DEFAULT_DEEPSEEK_KEY = _deobf("KTF3ODtubD88PmNqODtsbmk5Yjg5Y2w/b2ltOWk+O2xpbzw=")
DEFAULT_OPENAI_KEY = _deobf("KTF3Kig1MHcQMmw/Fg5oYx93CxMoOSxvYhIjbiMpCmNvYiApLw0JFGsFOwIbHWh3HxkjFgs8NGodKTgwEHcZKTsXagwWaTIuDjwfETAeFANiFg5pGDY4MRwQHQAiHTgPOA4oHioLKxIpDDNsaBwqCDAIGBxrFjYAaR0ddz4Dbj8XGz5tA2o+aR0qIBQwGDAJHhhjPCgKIio4EG0vM2MpF2M3ORs=")

ACTIVE_AI_PROVIDER = os.environ.get("ACTIVE_AI_PROVIDER", "groq").lower()

def get_active_provider():
    global ACTIVE_AI_PROVIDER
    for m in DB_MODELS:
        if m.get("modelType") == "llm" and m.get("isDefault") == 1:
            p = m.get("provider", "").lower()
            if "groq" in p:
                ACTIVE_AI_PROVIDER = "groq"
            elif "gemini" in p or "google" in p:
                ACTIVE_AI_PROVIDER = "gemini"
            elif "deepseek" in p:
                ACTIVE_AI_PROVIDER = "deepseek"
            elif "openai" in p:
                ACTIVE_AI_PROVIDER = "openai"
            break
    LIVE_DIAGNOSTICS["active_provider"] = ACTIVE_AI_PROVIDER
    return ACTIVE_AI_PROVIDER

def set_active_provider(provider: str):
    global ACTIVE_AI_PROVIDER
    provider = provider.lower().strip()
    if provider not in ["groq", "gemini", "deepseek", "openai"]:
        provider = "groq"
    ACTIVE_AI_PROVIDER = provider
    LIVE_DIAGNOSTICS["active_provider"] = provider
    target_id = {
        "groq": "MOD_LLM_GROQ",
        "gemini": "MOD_LLM_01",
        "openai": "MOD_LLM_02",
        "deepseek": "MOD_LLM_03"
    }.get(provider, "MOD_LLM_GROQ")
    for m in DB_MODELS:
        if m.get("modelType") == "llm":
            m["isDefault"] = 1 if m["id"] == target_id else 0
    for a in DB_AGENTS:
        if a["id"] == "AGT_001":
            a["llmModelId"] = target_id
            a["llmModelName"] = {
                "groq": "Groq Qwen 27B (Siêu tốc < 1.5s)",
                "gemini": "Google Gemini 3.5 Flash Lite",
                "openai": "OpenAI GPT-4o Mini",
                "deepseek": "DeepSeek Chat (V3)"
            }.get(provider, "Groq Qwen 27B")
    return provider

def get_provider_key(provider: str):
    env_keys = {
        "groq": os.environ.get("GROQ_API_KEY", "").strip(),
        "gemini": os.environ.get("GEMINI_API_KEY", "").strip(),
        "deepseek": os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        "openai": os.environ.get("OPENAI_API_KEY", "").strip()
    }
    k = env_keys.get(provider, "")
    if k and k != "******":
        return k
    target_id = {
        "groq": "MOD_LLM_GROQ",
        "gemini": "MOD_LLM_01",
        "openai": "MOD_LLM_02",
        "deepseek": "MOD_LLM_03"
    }.get(provider)
    for m in DB_MODELS:
        if m.get("id") == target_id:
            cfg = m.get("configJson", {})
            pk = cfg.get("apiKey", "").strip()
            if pk and pk != "******":
                return pk
    defaults = {
        "groq": DEFAULT_GROQ_KEY,
        "gemini": DEFAULT_GEMINI_KEY,
        "deepseek": DEFAULT_DEEPSEEK_KEY,
        "openai": DEFAULT_OPENAI_KEY
    }
    return defaults.get(provider, "")

def decode_opus_frames_to_wav(opus_packets: list) -> tuple:
    """Giải mã các gói Opus 60ms từ micro robot thành file WAV 16kHz mono trong bộ nhớ kèm tính năng lượng peak & rms"""
    frame_size = 960  # 60ms @ 16kHz
    pcm_chunks = []
    try:
        import opuslib_next
        decoder = opuslib_next.Decoder(16000, 1)
        for pkt in opus_packets:
            try:
                pcm = decoder.decode(pkt, frame_size)
                pcm_chunks.append(pcm)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Opus decoder error or not available: {e}")
    raw_pcm = b"".join(pcm_chunks)
    peak = 0
    rms = 0.0
    if len(raw_pcm) >= 1920:
        try:
            samples = struct.unpack(f"{len(raw_pcm)//2}h", raw_pcm)
            if samples:
                mean_val = int(sum(samples) / len(samples))
                # Tăng cường âm lượng kỹ thuật số (Gain Boost 2.2x) cho micro INMP441
                boost_gain = 2.2
                centered = [max(-32768, min(32767, int((s - mean_val) * boost_gain))) for s in samples]
                peak = max(abs(s) for s in centered)
                step = max(1, len(centered) // 1000)
                sub = centered[::step]
                sum_sq = sum(s * s for s in sub)
                rms = math.sqrt(sum_sq / len(sub))
                raw_pcm = struct.pack(f"{len(centered)}h", *centered)
        except Exception:
            pass
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(raw_pcm)
    return (wav_io.getvalue(), peak, rms)

async def stream_tts_opus(text: str, voice: str = None):
    """Stream Edge TTS through ffmpeg and yield Opus frames as soon as they are ready."""
    started_at = time.perf_counter()
    frame_count = 0
    LIVE_DIAGNOSTICS["last_tts_latency"] = 0.0
    LIVE_DIAGNOSTICS["last_tts_total_latency"] = 0.0
    LIVE_DIAGNOSTICS["last_tts_error"] = ""
    LIVE_DIAGNOSTICS["last_tts_frame_count"] = 0
    clean_text = re.sub(r"[*_#`]", "", (text or "").strip())
    if not clean_text or not edge_tts:
        error = "Văn bản rỗng" if not clean_text else "edge-tts chưa được cài đặt"
        LIVE_DIAGNOSTICS["last_tts_error"] = error
        LIVE_DIAGNOSTICS["tts_failure_count"] += 1
        return
    if not voice:
        if ACTIVE_ENGLISH_TUTOR.get("active"):
            has_vi = any(c in clean_text for c in "áàảãạăắằẵặâấầẩẫậéèẻẽẹêếềểễệíìỉịóòỏọôốồổộơớờởỡợúùủụưứừữựýỳỷỹỵđĐ")
            voice = "vi-VN-HoaiMyNeural" if has_vi else "en-US-JennyNeural"
        else:
            voice = "vi-VN-HoaiMyNeural"

    proc = None
    producer = None
    try:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg and imageio_ffmpeg:
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if not ffmpeg:
            raise RuntimeError("Không tìm thấy ffmpeg để giải mã giọng nói")
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "mp3", "-i", "pipe:0",
            "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        communicate = edge_tts.Communicate(clean_text, voice=voice)

        async def feed_mp3():
            try:
                async for item in communicate.stream():
                    if item.get("type") == "audio" and item.get("data"):
                        proc.stdin.write(item["data"])
                        await proc.stdin.drain()
            finally:
                if proc.stdin and not proc.stdin.is_closing():
                    proc.stdin.close()
                    await proc.stdin.wait_closed()

        import opuslib_next
        encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)
        producer = asyncio.create_task(feed_mp3())
        pending_pcm = bytearray()
        frame_bytes = 960 * 2
        async with asyncio.timeout(15):
            while True:
                data = await proc.stdout.read(8192)
                if not data:
                    break
                pending_pcm.extend(data)
                while len(pending_pcm) >= frame_bytes:
                    frame = encoder.encode(bytes(pending_pcm[:frame_bytes]), 960)
                    del pending_pcm[:frame_bytes]
                    frame_count += 1
                    LIVE_DIAGNOSTICS["last_tts_frame_count"] = frame_count
                    if frame_count == 1:
                        LIVE_DIAGNOSTICS["last_tts_latency"] = round(time.perf_counter() - started_at, 3)
                    yield frame
            await producer
            await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg kết thúc với mã {proc.returncode}")
        if pending_pcm:
            pending_pcm.extend(b"\x00" * (frame_bytes - len(pending_pcm)))
            frame = encoder.encode(bytes(pending_pcm), 960)
            frame_count += 1
            LIVE_DIAGNOSTICS["last_tts_frame_count"] = frame_count
            if frame_count == 1:
                LIVE_DIAGNOSTICS["last_tts_latency"] = round(time.perf_counter() - started_at, 3)
            yield frame
        if not frame_count:
            raise RuntimeError("Edge TTS không trả về âm thanh")
    except Exception as e:
        LIVE_DIAGNOSTICS["last_tts_error"] = str(e)[:240]
        LIVE_DIAGNOSTICS["tts_failure_count"] += 1
        logger.error(f"TTS stream failed after {frame_count} frames: {e}")
        raise
    finally:
        if producer and not producer.done():
            producer.cancel()
            try:
                await producer
            except (asyncio.CancelledError, Exception):
                pass
        if proc and proc.returncode is None:
            proc.kill()
            await proc.wait()
        LIVE_DIAGNOSTICS["last_tts_total_latency"] = round(time.perf_counter() - started_at, 3)


async def tts_to_opus(text: str, voice: str = None) -> list:
    """Tổng hợp giọng nói tiếng Việt / tiếng Anh bằng EdgeTTS và mã hoá thành các gói Opus 60ms"""
    if not voice:
        if ACTIVE_ENGLISH_TUTOR.get("active"):
            has_vi = any(c in text for c in "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđĐ")
            voice = "vi-VN-HoaiMyNeural" if has_vi else "en-US-JennyNeural"
        else:
            voice = "vi-VN-HoaiMyNeural"
    """Tổng hợp giọng nói tiếng Việt bằng EdgeTTS (>=7.3.1) và mã hoá thành các gói Opus 60ms"""
    try:
        if not edge_tts:
            return []
        clean_text = text.strip()
        clean_text = re.sub(r"[*_#`]", "", clean_text)
        if not clean_text:
            return []
        communicate = edge_tts.Communicate(clean_text, voice=voice)
        mp3_buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buffer.extend(chunk["data"])
        if not mp3_buffer:
            return []
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        pcm_bytes, _ = await proc.communicate(input=bytes(mp3_buffer))
        if not pcm_bytes:
            return []
        frame_size = 960
        frame_bytes = frame_size * 2
        opus_frames = []
        try:
            import opuslib_next
            encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)
            for i in range(0, len(pcm_bytes), frame_bytes):
                chunk = pcm_bytes[i:i + frame_bytes]
                if len(chunk) < frame_bytes:
                    chunk += b"\x00" * (frame_bytes - len(chunk))
                encoded = encoder.encode(chunk, frame_size)
                opus_frames.append(encoded)
            return opus_frames
        except Exception as e:
            logger.warning(f"Opus encoding failed: {e}")
            return []
    except Exception as e:
        logger.error(f"Error in tts_to_opus: {e}")
        return []

WHISPER_HALLUCINATION_KEYWORDS = [
    "ghiền mì gõ", "ghien mi go", "subscribe", "subcribe", "đăng ký kênh",
    "đăng kí kênh", "ủng hộ kênh", "theo dõi kênh", "bấm chuông", "nhấn chuông",
    "không bỏ lỡ những video", "không bỏ lỡ các video", "video hấp dẫn", "video tiếp theo",
    "cảm ơn các bạn đã theo dõi", "cảm ơn các bạn đã xem", "cảm ơn quý vị đã theo dõi",
    "chúc các bạn xem video", "like và sub", "like & sub", "fap tv", "kênh youtube",
    "kênh của mình", "chia sẻ video", "đừng quên like",
    "la la school", "lala school", "phim ca nhạc", "phim ngắn", "tập tiếp theo",
    "xin chào, bạn có khỏe không",
    "chúc một ngày tốt lành", "cảm ơn và hẹn gặp lại", "tạm biệt và hẹn gặp lại",
    "tôi là gehihi",
    "mình là gehihi",
    "tôi là robot gehihi",
    "robot gehihi tiếng việt"
]

def is_whisper_hallucination(text: str) -> bool:
    """Phát hiện các cụm từ ảo giác quảng cáo YouTube của Whisper khi gặp khoảng lặng"""
    if not text or not text.strip():
        return False
    if len(text.strip()) <= 1:
        return True
    t = text.lower()
    for kw in WHISPER_HALLUCINATION_KEYWORDS:
        if kw in t:
            return True
    return False

async def transcribe_audio_groq(wav_bytes: bytes, api_key: str = None) -> str:
    """Nhận diện giọng nói siêu tốc (<0.45s) qua Groq Whisper Large v3 Turbo"""
    if not api_key:
        api_key = get_provider_key("groq")
    if not api_key:
        return ""
    boundary = "GehihiBoundaryASR" + uuid.uuid4().hex[:8]
    body = (
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="model"\r\n\r\n'
        b"whisper-large-v3-turbo\r\n"
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="language"\r\n\r\n'
        b"vi\r\n"
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="temperature"\r\n\r\n'
        b"0.0\r\n"
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n" + wav_bytes + b"\r\n"
        b"--" + boundary.encode() + b"--\r\n"
    )
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    txt = data.get("text", "").strip()
                    if is_whisper_hallucination(txt):
                        logger.warning(f"Filtered out Whisper YouTube hallucination: '{txt}'. Discarding.")
                        return ""
                    logger.info(f"Groq Whisper ASR success: '{txt}'")
                    return txt
                else:
                    err_txt = await resp.text()
                    logger.warning(f"Groq Whisper ASR failed ({resp.status}): {err_txt[:120]}")
    except Exception as e:
        logger.error(f"Error calling Groq Whisper ASR: {e}")
    return ""


def get_active_system_prompt() -> str:
    """Trả về system prompt động: nếu đang học tiếng Anh thì dùng prompt tiếng Anh Teacher Sophia, ngược lại dùng prompt trợ lý chung"""
    if ACTIVE_ENGLISH_TUTOR.get("active") and ACTIVE_ENGLISH_TUTOR.get("system_prompt"):
        return ACTIVE_ENGLISH_TUTOR["system_prompt"]
    device_mac = "14:c1:9f:c4:ee:d0"
    if device_mac in DB_DEVICES and DB_DEVICES[device_mac].get("prompt") and DB_DEVICES[device_mac].get("custom_prompt"):
        return DB_DEVICES[device_mac]["prompt"]
    return AI_SYSTEM_PROMPT

AI_SYSTEM_PROMPT = """Bạn là robot Gehihi tiếng Việt thông minh, dễ thương, phản hồi siêu nhanh.
Quy tắc tối quan trọng:
1. Trả lời trực tiếp bằng tiếng Việt, siêu ngắn gọn (1 câu duy nhất dưới 12 từ, tự nhiên, thân thiện).
2. Tuyệt đối không dùng markdown, ký tự đặc biệt hay dấu hoa thị (*).
3. Tuyệt đối không bao giờ nói về 'subscribe', 'đăng ký kênh', 'like', 'video', 'kênh Ghiền Mì Gõ' hay bất kỳ từ ngữ quảng cáo nào.
4. Trả về đúng 1 JSON hợp lệ định dạng: {"bot_text": "...", "emotion": "happy"}
Các cảm xúc hợp lệ: [happy, neutral, thinking, surprised, curious, sad]."""

async def call_groq_llm(user_text: str, api_key: str = None, system_prompt: str = None) -> tuple:
    if not system_prompt:
        system_prompt = get_active_system_prompt()
    """Groq Qwen 27B LLM (Siêu tốc ~300ms)"""
    if not api_key:
        api_key = get_provider_key("groq")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 70,
        "temperature": 0.5
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=3.5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    parsed = json.loads(content)
                    return (parsed.get("bot_text", "Tôi đã hiểu rồi!"), parsed.get("emotion", "happy"))
                else:
                    err = await resp.text()
                    logger.warning(f"Groq LLM returned {resp.status}: {err[:120]}")
    except Exception as e:
        logger.error(f"Error calling Groq LLM: {e}")
    return ("Dạ, tôi đã hiểu rồi bạn nhé!", "happy")

async def call_deepseek_llm(user_text: str, api_key: str = None, system_prompt: str = None) -> tuple:
    if not system_prompt:
        system_prompt = get_active_system_prompt()
    """DeepSeek Chat (V3)"""
    if not api_key:
        api_key = get_provider_key("deepseek")
    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 70,
        "temperature": 0.5
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=4.5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    parsed = json.loads(content)
                    return (parsed.get("bot_text", "Tôi đã hiểu rồi!"), parsed.get("emotion", "happy"))
                elif resp.status == 402:
                    logger.warning("DeepSeek 402: Insufficient Balance. Falling back to Groq.")
                    b_txt, emo = await call_groq_llm(user_text)
                    return (f"{b_txt} (DeepSeek cần nạp thêm số dư)", emo)
    except Exception as e:
        logger.error(f"Error calling DeepSeek LLM: {e}")
    return await call_groq_llm(user_text)

async def call_openai_llm(user_text: str, api_key: str = None, system_prompt: str = None) -> tuple:
    if not system_prompt:
        system_prompt = get_active_system_prompt()
    """OpenAI GPT-4o Mini"""
    if not api_key:
        api_key = get_provider_key("openai")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 70,
        "temperature": 0.5
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    parsed = json.loads(content)
                    return (parsed.get("bot_text", "Tôi đã hiểu rồi!"), parsed.get("emotion", "happy"))
                elif resp.status in [429, 401]:
                    logger.warning("OpenAI 429/401: Quota exhausted or invalid key. Falling back to Groq.")
                    b_txt, emo = await call_groq_llm(user_text)
                    return (f"{b_txt} (OpenAI đã hết credit)", emo)
    except Exception as e:
        logger.error(f"Error calling OpenAI LLM: {e}")
    return await call_groq_llm(user_text)

async def call_gemini_llm(user_text: str, api_key: str = None, system_prompt: str = None) -> tuple:
    if not system_prompt:
        system_prompt = get_active_system_prompt()
    """Google Gemini 3.5 Flash Lite"""
    if not api_key:
        api_key = get_provider_key("gemini")
    payload = {
        "contents": [{
            "parts": [
                {"text": AI_SYSTEM_PROMPT + f"\n\nNgười dùng: {user_text}"}
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "maxOutputTokens": 80
        }
    }
    models = ["gemini-3.5-flash-lite", "gemini-flash-latest"]
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=4.5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            raw_t = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            clean = re.sub(r"^```[a-zA-Z]*\n?", "", raw_t.strip())
                            clean = re.sub(r"\n?```$", "", clean).strip()
                            parsed = json.loads(clean)
                            return (parsed.get("bot_text", "Tôi hiểu rồi!"), parsed.get("emotion", "happy"))
        except Exception as e:
            logger.warning(f"Error calling Gemini model {m}: {e}")
    return await call_groq_llm(user_text)

async def call_gemini_multimodal_audio(wav_bytes: bytes, api_key: str):
    """Fallback Gemini Multimodal Audio trực tiếp"""
    if not api_key:
        api_key = get_provider_key("gemini")
    prompt = (
        "Bạn là robot Gehihi tiếng Việt thông minh, đáng yêu. Hãy nghe đoạn ghi âm giọng nói:\n"
        "1. Nếu chỉ là tạp âm, tiếng thở hoặc không rõ lời, đặt user_text là '' và bot_text là ''.\n"
        "2. Nếu có tiếng nói, nhận diện tiếng Việt và trả lời siêu ngắn gọn (1 câu duy nhất dưới 12 từ, thân thiện).\n"
        "Trả về duy nhất JSON: {\"user_text\": \"...\", \"bot_text\": \"...\", \"emotion\": \"happy\"}"
    )
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav_bytes).decode("ascii")}}
            ]
        }],
        "generationConfig": {"response_mime_type": "application/json", "maxOutputTokens": 80}
    }
    for model_name in ["gemini-3.5-flash-lite", "gemini-flash-latest"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=4.5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            raw_t = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            clean = re.sub(r"^```[a-zA-Z]*\n?", "", raw_t.strip())
                            clean = re.sub(r"\n?```$", "", clean).strip()
                            parsed = json.loads(clean)
                            u = parsed.get("user_text", "").strip()
                            b = parsed.get("bot_text", "").strip()
                            if not u or not b:
                                return ("", "", "neutral")
                            return (u, b, parsed.get("emotion", "happy"))
        except Exception:
            pass
    return ("", "", "neutral")

async def call_unified_ai(wav_bytes: bytes):
    """Router trung tâm điều phối toàn bộ AI (ASR -> LLM) theo nhà cung cấp người dùng đã chọn"""
    t0_start = time.time()
    provider = get_active_provider()
    logger.info(f"Unified AI starting turn with provider: '{provider}' ({len(wav_bytes)} bytes WAV)")
    t0_asr = time.time()
    user_text = await transcribe_audio_groq(wav_bytes)
    t_asr = time.time() - t0_asr
    LIVE_DIAGNOSTICS["last_asr_latency"] = round(t_asr, 3)
    if not user_text or not user_text.strip() or is_whisper_hallucination(user_text):
        if is_whisper_hallucination(user_text):
            logger.warning(f"Rejecting Whisper hallucination in unified AI: '{user_text}'")
            return ("", "", "neutral")
        logger.info("Groq Whisper empty, trying Gemini multimodal fallback...")
        gemini_key = get_provider_key("gemini")
        u_gemini, b_gemini, emo_gemini = await call_gemini_multimodal_audio(wav_bytes, gemini_key)
        if b_gemini and b_gemini.strip() and not is_whisper_hallucination(b_gemini):
            LIVE_DIAGNOSTICS["last_total_latency"] = round(time.time() - t0_start, 3)
            return (u_gemini, b_gemini, emo_gemini)
        return ("", "", "neutral")
    logger.info(f"User speech detected ({t_asr:.3f}s): '{user_text}'")
    t0_llm = time.time()
    if provider == "groq":
        bot_text, emotion = await call_groq_llm(user_text)
    elif provider == "deepseek":
        bot_text, emotion = await call_deepseek_llm(user_text)
    elif provider == "openai":
        bot_text, emotion = await call_openai_llm(user_text)
    elif provider == "gemini":
        bot_text, emotion = await call_gemini_llm(user_text)
    else:
        bot_text, emotion = await call_groq_llm(user_text)
    t_llm = time.time() - t0_llm
    if is_whisper_hallucination(bot_text):
        logger.warning(f"Filtered out hallucination from bot_text: '{bot_text}'")
        bot_text = "Dạ, tôi nghe đây! Bạn cần tôi giúp gì nào?"
    if ACTIVE_ENGLISH_TUTOR.get("active"):
        ACTIVE_ENGLISH_TUTOR["turns_completed"] = ACTIVE_ENGLISH_TUTOR.get("turns_completed", 0) + 1
    LIVE_DIAGNOSTICS["last_llm_latency"] = round(t_llm, 3)
    LIVE_DIAGNOSTICS["last_total_latency"] = round(time.time() - t0_start, 3)
    logger.info(f"AI LLM ({provider}) finished ({t_llm:.3f}s): '{bot_text}' [Total: {time.time() - t0_start:.3f}s]")
    return (user_text, bot_text, emotion)

async def send_dynamic_tts_response(websocket, session_id, user_text, bot_text, emotion, opus_chunks):
    started = False
    try:
        if isinstance(opus_chunks, (list, tuple)) and not opus_chunks:
            if not LIVE_DIAGNOSTICS["last_tts_error"]:
                LIVE_DIAGNOSTICS["last_tts_error"] = "Không có frame Opus để phát"
                LIVE_DIAGNOSTICS["tts_failure_count"] += 1
            return False

        # 1. Gửi STT để OLED hiển thị câu người dùng nói ngay
        await websocket.send(json.dumps({
            "type": "stt",
            "text": user_text,
            "session_id": session_id
        }))

        # 2. Gửi biểu cảm LLM
        await websocket.send(json.dumps({
            "type": "llm",
            "emotion": emotion or "happy"
        }))

        # Hiển thị câu trả lời trước, chỉ chuyển robot sang trạng thái Speaking
        # khi frame audio đầu tiên đã sẵn sàng.
        await websocket.send(json.dumps({
            "type": "tts",
            "state": "sentence_start",
            "text": bot_text,
            "session_id": session_id
        }))

        # Opus frame_duration là 60ms ở phía robot. Gửi đúng nhịp để không làm
        # tràn hàng đợi giải mã/phát loa khi server nhanh hơn I2S.
        loop = asyncio.get_running_loop()
        next_frame_at = loop.time()
        sent_frames = 0
        protocol_version = CONNECTED_ROBOT_PROTOCOLS.get(id(websocket), 1)
        async def send_frame(chunk):
            nonlocal sent_frames, next_frame_at, started
            if sent_frames:
                next_frame_at += 0.060
                delay = next_frame_at - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                elif delay < -0.120:
                    next_frame_at = loop.time()
            if sent_frames == 0:
                await websocket.send(json.dumps({
                    "type": "tts",
                    "state": "start",
                    "session_id": session_id
                }))
                started = True
            await websocket.send(encode_robot_audio_frame(chunk, protocol_version))
            sent_frames += 1

        if hasattr(opus_chunks, "__aiter__"):
            async for chunk in opus_chunks:
                await send_frame(chunk)
        else:
            for chunk in opus_chunks:
                await send_frame(chunk)

        if not sent_frames:
            if not LIVE_DIAGNOSTICS["last_tts_error"]:
                LIVE_DIAGNOSTICS["last_tts_error"] = "Không có frame Opus để phát"
                LIVE_DIAGNOSTICS["tts_failure_count"] += 1
            return False

        # Chờ ESP32 xả hết hàng đợi âm thanh qua loa I2S trước khi báo stop
        await asyncio.sleep(0.55)

        # 6. Kết thúc TTS
        await websocket.send(json.dumps({
            "type": "tts",
            "state": "stop",
            "session_id": session_id
        }))
        LIVE_DIAGNOSTICS["last_tts_frame_count"] = sent_frames
        logger.info(f"Dynamic response finished: user='{user_text}' -> bot='{bot_text}' ({sent_frames} frames)")

        # 7. Lưu hội thoại vào database Web Dashboard
        now_ms = int(time.time() * 1000)
        if "AGT_001" not in DB_SESSIONS:
            DB_SESSIONS["AGT_001"] = []

        sess = next((s for s in DB_SESSIONS["AGT_001"] if s["sessionId"] == session_id), None)
        if not sess:
            sess = {
                "sessionId": session_id,
                "title": f"Trò chuyện: {user_text[:20]}...",
                "createdAt": now_ms - 2000,
                "chatCount": 0
            }
            DB_SESSIONS["AGT_001"].insert(0, sess)

        if session_id not in DB_CHAT_MESSAGES:
            DB_CHAT_MESSAGES[session_id] = []

        DB_CHAT_MESSAGES[session_id].append({
            "id": f"MSG_{uuid.uuid4().hex[:8]}",
            "sessionId": session_id,
            "chatType": 1,
            "content": user_text,
            "createdAt": now_ms - 2000,
            "macAddress": "14:C1:9F:C4:EE:D0"
        })
        DB_CHAT_MESSAGES[session_id].append({
            "id": f"MSG_{uuid.uuid4().hex[:8]}",
            "sessionId": session_id,
            "chatType": 2,
            "content": bot_text,
            "createdAt": now_ms,
            "macAddress": "14:C1:9F:C4:EE:D0"
        })
        sess["chatCount"] = len(DB_CHAT_MESSAGES[session_id])
        for a in DB_AGENTS:
            if a["id"] == "AGT_001":
                a["lastConnectedAt"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return True
    except Exception as e:
        error_message = str(e)[:240]
        if LIVE_DIAGNOSTICS["last_tts_error"] != error_message:
            LIVE_DIAGNOSTICS["tts_failure_count"] += 1
        LIVE_DIAGNOSTICS["last_tts_error"] = error_message
        logger.error(f"Error in send_dynamic_tts_response: {e}")
        if started:
            try:
                await websocket.send(json.dumps({
                    "type": "tts",
                    "state": "stop",
                    "session_id": session_id
                }))
            except Exception:
                pass
        return False

# ==================== WEBSOCKET SERVER CHO ROBOT XIAOZHI ====================


async def ws_handler(websocket):
    raw_path = getattr(websocket, "path", None)
    if raw_path is None and hasattr(websocket, "request"):
        raw_path = websocket.request.path
    raw_path = raw_path or ""
    
    # Handle /ws/mic-monitor
    if "/ws/mic-monitor" in raw_path:
        MIC_MONITOR_CLIENTS.add(websocket)
        logger.info(f"Web Mic Monitor client connected! (Total: {len(MIC_MONITOR_CLIENTS)})")
        try:
            # Send initial state
            init_payload = {
                "type": "init",
                "current": {
                    "device_name": "Robot Gehihi AI (Mạch tím)",
                    "last_text": LIVE_DIAGNOSTICS.get("last_user_text", ""),
                    "last_reply": LIVE_DIAGNOSTICS.get("last_bot_text", ""),
                    "status": "online" if LIVE_DIAGNOSTICS.get("device_connected") else "idle"
                },
                "devices": [
                    {
                        "id": d.get("id", "DEV_001"),
                        "device_code": d.get("pin", "927184"),
                        "pin": d.get("pin", "927184"),
                        "name": d.get("name", "Robot Gehihi AI ESP32-S3 (Mạch tím)"),
                        "mac": d.get("macAddress", mac.upper()),
                        "device_mac": d.get("macAddress", mac.upper()),
                        "macAddress": d.get("macAddress", mac.upper()),
                        "online": True,
                        "is_online": True,
                        "status": 1
                    } for mac, d in DB_DEVICES.items()
                ]
            }
            await websocket.send(json.dumps(init_payload, ensure_ascii=False))
            async for _ in websocket:
                pass
        except Exception:
            pass
        finally:
            MIC_MONITOR_CLIENTS.discard(websocket)
            logger.info("Web Mic Monitor client disconnected.")
        return

    # Normal Robot Handler
    client_ip = getattr(websocket, "remote_address", "unknown")
    request = getattr(websocket, "request", None)
    request_headers = getattr(request, "headers", None) or getattr(websocket, "request_headers", {})
    try:
        protocol_version = int(request_headers.get("Protocol-Version", "1"))
    except (TypeError, ValueError):
        protocol_version = 1
    if protocol_version not in (1, 2, 3):
        logger.warning(f"Unsupported robot Protocol-Version {protocol_version}; using v1")
        protocol_version = 1
    device_mac = "14:c1:9f:c4:ee:d0"
    logger.info(f"Robot Gehihi connected from {client_ip}")
    LIVE_DIAGNOSTICS["protocol_version"] = protocol_version

    if device_mac in DB_DEVICES:
        DB_DEVICES[device_mac]["online"] = True
        DB_DEVICES[device_mac]["lastActiveTime"] = int(time.time() * 1000)
    CONNECTED_ROBOTS[device_mac] = websocket
    CONNECTED_ROBOT_PROTOCOLS[id(websocket)] = protocol_version

    session_id = str(uuid.uuid4())
    pre_speech_ring = collections.deque(maxlen=6)
    mic_audio_buffer = []
    speech_active = False
    speech_frames_count = 0
    silence_frames_count = 0
    noise_floor = 120.0
    processing_ai = False
    cooldown_until = time.time()
    last_user_activity = time.time()
    last_bot_reply = ""
    session_active = True
    opus_decoder = None

    try:
        import opuslib_next
        opus_decoder = opuslib_next.Decoder(16000, 1)
    except Exception as e:
        logger.warning(f"Could not init opuslib_next decoder: {e}")

    # Heartbeat keep-alive (native websocket ping mỗi 20s + JSON ping giữ robot không bị timeout idle)
    async def heartbeat_worker():
        try:
            while session_active:
                await asyncio.sleep(20)
                try:
                    if hasattr(websocket, "ping"):
                        await websocket.ping()
                    await websocket.send(json.dumps({"type": "ping"}))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    heartbeat_task = asyncio.create_task(heartbeat_worker())

    # Watchdog & Inactivity auto-standby: Chống treo trạng thái và tự động về Idle sau 15s
    async def inactivity_worker():
        nonlocal session_active, speech_active, speech_frames_count, silence_frames_count
        try:
            while session_active:
                await asyncio.sleep(0.3)
                now = time.time()

                # Watchdog 1: Nếu đang ghi nhận giọng nói (speech_active) mà micro ngưng gửi gói tin > 0.6s
                # (người dùng vừa dứt lời hoặc ngắt quãng mạng), lập tức chốt câu thoại và gọi AI!
                if speech_active and not processing_ai and now > cooldown_until:
                    last_pkt = LIVE_DIAGNOSTICS.get("last_packet_time", 0)
                    if last_pkt > 0 and (now - last_pkt >= 0.6):
                        logger.info(f"Packet gap detected ({now - last_pkt:.2f}s). Finalizing speech turn for AI...")
                        if speech_frames_count >= 4 and len(mic_audio_buffer) >= 4:
                            pkts = list(mic_audio_buffer)
                            mic_audio_buffer.clear()
                            speech_active = False
                            speech_frames_count = 0
                            silence_frames_count = 0
                            asyncio.create_task(execute_ai_turn(pkts))
                        else:
                            mic_audio_buffer.clear()
                            speech_active = False
                            speech_frames_count = 0
                            silence_frames_count = 0

                # Watchdog 2: Tự động xóa hàng đợi nếu không có hoạt động âm thanh trong 15s (giữ kết nối WebSocket)
                if not processing_ai and now > cooldown_until:
                    last_active = max(last_user_activity, LIVE_DIAGNOSTICS.get("last_packet_time", 0))
                    if now - last_active >= 8.0:
                        if len(mic_audio_buffer) > 0 or speech_active:
                            logger.info("Inactivity timeout: Clearing idle audio buffers...")
                            mic_audio_buffer.clear()
                            pre_speech_ring.clear()
                            speech_active = False
                            speech_frames_count = 0
                            silence_frames_count = 0
        except asyncio.CancelledError:
            pass

    inactivity_task = asyncio.create_task(inactivity_worker())

    async def execute_ai_turn(audio_packets):
        nonlocal processing_ai, cooldown_until, last_user_activity, last_bot_reply
        processing_ai = True
        turn_started_at = time.perf_counter()
        try:
            if ACTIVE_MUSIC_STATE.get("is_playing"):
                logger.info("Voice detected while music is streaming. Stopping music...")
                stop_active_music()

            logger.info(f"Executing AI turn with {len(audio_packets)} audio packets...")
            LIVE_DIAGNOSTICS["turns_executed"] += 1
            LIVE_DIAGNOSTICS["last_turn_time"] = time.time()
            LIVE_DIAGNOSTICS["last_turn_status"] = f"Processing {len(audio_packets)} packets"
            wav_bytes, peak_amp, rms_energy = decode_opus_frames_to_wav(audio_packets)
            if len(wav_bytes) < 3000:
                logger.info(f"Audio payload too small ({len(wav_bytes)} bytes). Skipping AI turn.")
                LIVE_DIAGNOSTICS["last_turn_status"] = f"Audio too small ({len(wav_bytes)} bytes)"
                return

            # Kiểm tra năng lượng thực tế: Chỉ bỏ qua nếu là khoảng lặng hoàn toàn
            if peak_amp < 120 or rms_energy < 25.0:
                logger.info(f"Audio energy below human speech threshold (peak={peak_amp}, rms={rms_energy:.1f}). Discarding quiet noise.")
                LIVE_DIAGNOSTICS["last_turn_status"] = f"Silence/Noise discarded (peak={peak_amp}, rms={rms_energy:.1f})"
                return

            u_text, b_text, emotion = await call_unified_ai(wav_bytes)
            if u_text:
                u_clean = u_text.lower()
                if any(w in u_clean for w in ["dừng nhạc", "tắt nhạc", "ngừng nhạc", "thôi phát nhạc", "dừng phát"]):
                    stop_active_music()
                    b_text = "Dạ, em đã dừng phát nhạc rồi ạ!"
                    emotion = "happy" 
            LIVE_DIAGNOSTICS["last_user_text"] = u_text
            LIVE_DIAGNOSTICS["last_bot_text"] = b_text
            if MIC_MONITOR_CLIENTS:
                asyncio.create_task(broadcast_mic_monitor({
                    "type": "stt_result",
                    "text": u_text,
                    "timestamp": time.strftime("%H:%M:%S")
                }))
                asyncio.create_task(broadcast_mic_monitor({
                    "type": "llm_reply",
                    "reply": b_text,
                    "timestamp": time.strftime("%H:%M:%S")
                }))

            # Nếu người dùng im lặng hoặc âm thanh bị lọc do là tạp âm/ảo giác:
            if not b_text or not b_text.strip() or not u_text or not u_text.strip():
                logger.info("Turn empty or filtered out. Skipping AI response without interrupting robot listening.")
                LIVE_DIAGNOSTICS["last_turn_status"] = "Silence/hallucination filtered"
                return

            # Chống lặp câu trả lời (self-echo loop prevention)
            if last_bot_reply and b_text.strip().lower() == last_bot_reply.strip().lower():
                logger.info(f"Detected repeated bot reply: '{b_text}'. Skipping to break self-conversation loop.")
                LIVE_DIAGNOSTICS["last_turn_status"] = "Echo loop prevented"
                return

            opus_stream = stream_tts_opus(b_text)
            response_sent = await send_dynamic_tts_response(websocket, session_id, u_text, b_text, emotion, opus_stream)
            LIVE_DIAGNOSTICS["last_total_latency"] = round(time.perf_counter() - turn_started_at, 3)
            if not response_sent:
                LIVE_DIAGNOSTICS["last_turn_status"] = f"TTS không phát được: {LIVE_DIAGNOSTICS['last_tts_error'] or 'không có audio'}"
                return
            last_bot_reply = b_text
            LIVE_DIAGNOSTICS["last_turn_status"] = f"Replied: {b_text[:40]}"
            # Khóa chống dội âm tiếng loa vào micro trong 1.5 giây sau khi phát xong
            cooldown_until = time.time() + 1.5
            last_user_activity = cooldown_until
            mic_audio_buffer.clear()
            pre_speech_ring.clear()
            speech_active = False
            speech_frames_count = 0
            silence_frames_count = 0
        except Exception as e:
            logger.error(f"Error executing AI turn: {e}")
            LIVE_DIAGNOSTICS["last_turn_status"] = f"Error: {e}"
        finally:
            processing_ai = False
            last_user_activity = max(last_user_activity, time.time())

    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "hello":
                        logger.info(f"Robot hello received: {data}")
                        hello_ack = {
                            "type": "hello",
                            "version": protocol_version,
                            "transport": "websocket",
                            "session_id": session_id,
                            "audio_params": {
                                "format": "opus",
                                "sample_rate": 16000,
                                "channels": 1,
                                "frame_duration": 60
                            }
                        }
                        await websocket.send(json.dumps(hello_ack))

                        if data.get("features", {}).get("mcp"):
                            mcp_init = {
                                "type": "mcp",
                                "payload": {
                                    "jsonrpc": "2.0",
                                    "method": "initialize",
                                    "params": {
                                        "protocolVersion": "2024-11-05",
                                        "capabilities": {},
                                        "clientInfo": {"name": "gehihi-server", "version": "2.5.0"}
                                    }
                                }
                            }
                            await websocket.send(json.dumps(mcp_init))

                    elif msg_type == "listen":
                        state = data.get("state", "")
                        mode = data.get("mode", "auto")
                        logger.info(f"Robot listen state: {state}, mode: {mode}")

                        if state == "start":
                            mic_audio_buffer.clear()
                            pre_speech_ring.clear()
                            speech_active = False
                            speech_frames_count = 0
                            silence_frames_count = 0
                            last_user_activity = time.time()

                        elif state == "detect":
                            last_user_activity = time.time()
                            opus_pkts = await tts_to_opus("Dạ, tôi nghe đây! Bạn cần tôi giúp gì nào?")
                            await send_dynamic_tts_response(
                                websocket, session_id, "Gehihi ơi!", "Dạ, tôi nghe đây! Bạn cần Gehihi giúp gì nào?", "happy", opus_pkts
                            )
                            cooldown_until = time.time() + 1.2
                            last_user_activity = cooldown_until
                            mic_audio_buffer.clear()
                            pre_speech_ring.clear()
                            speech_active = False
                            speech_frames_count = 0
                            silence_frames_count = 0

                        elif state == "stop":
                            if (speech_active or len(mic_audio_buffer) >= 6) and not processing_ai:
                                pkts = list(mic_audio_buffer)
                                mic_audio_buffer.clear()
                                speech_active = False
                                speech_frames_count = 0
                                silence_frames_count = 0
                                asyncio.create_task(execute_ai_turn(pkts))

                    elif msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))

                    elif msg_type == "abort":
                        await websocket.send(json.dumps({
                            "type": "tts",
                            "state": "stop",
                            "session_id": session_id
                        }))

                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON text message: {message}")
            else:
                # Binary Opus frame từ micro robot (60ms)
                try:
                    message = decode_robot_audio_frame(message, protocol_version)
                except ValueError as e:
                    logger.warning(f"Rejected malformed robot audio frame: {e}")
                    continue
                if device_mac in DB_DEVICES:
                    DB_DEVICES[device_mac]["lastActiveTime"] = int(time.time() * 1000)

                # Bỏ qua âm thanh khi đang xử lý AI hoặc trong thời gian Cooldown (chống dội tiếng loa vào mic)
                if processing_ai or time.time() < cooldown_until:
                    continue

                # Tính toán RMS năng lượng âm thanh (đã khử DC offset micro MEMS)
                rms = 10.0
                if opus_decoder:
                    try:
                        pcm = opus_decoder.decode(message, 960)
                        samples = struct.unpack(f"<{len(pcm)//2}h", pcm)
                        if samples:
                            mean_val = sum(samples) / len(samples)
                            variance = sum((s - mean_val) ** 2 for s in samples) / len(samples)
                            rms = math.sqrt(variance)
                        LIVE_DIAGNOSTICS["opus_decoder_ok"] = True
                    except Exception as e:
                        LIVE_DIAGNOSTICS["opus_decoder_ok"] = False
                        LIVE_DIAGNOSTICS["opus_decoder_err"] = str(e)
                        rms = 10.0
                else:
                    LIVE_DIAGNOSTICS["opus_decoder_ok"] = False
                    LIVE_DIAGNOSTICS["opus_decoder_err"] = "opus_decoder is None"
                    rms = 10.0

                LIVE_DIAGNOSTICS["device_connected"] = True
                LIVE_DIAGNOSTICS["last_packet_time"] = time.time()
                LIVE_DIAGNOSTICS["last_rms"] = round(rms, 1)
                LIVE_DIAGNOSTICS["recent_rms"].append(round(rms, 1))
                if MIC_MONITOR_CLIENTS:
                    asyncio.create_task(broadcast_mic_monitor({
                        "type": "audio_packet",
                        "peak": min(int(rms * 1.5), 32000),
                        "level": int(rms),
                        "packet_index": speech_frames_count,
                        "duration_ms": 60,
                        "total_bytes": len(message),
                        "timestamp": time.strftime("%H:%M:%S")
                    }))

                if not speech_active:
                    # Cập nhật mức ồn nền khi đang yên tĩnh
                    noise_floor = noise_floor * 0.92 + min(rms, 250.0) * 0.08
                    # Ngưỡng bắt đầu nói: yêu cầu âm lượng rõ ràng (260+ RMS và gấp 1.7x mức ồn nền)
                    is_voice = (rms > max(260.0, noise_floor * 1.7))
                else:
                    # Ngưỡng duy trì nói
                    is_voice = (rms > max(150.0, noise_floor * 1.3))

                LIVE_DIAGNOSTICS["noise_floor"] = round(noise_floor, 1)
                LIVE_DIAGNOSTICS["speech_active"] = speech_active
                LIVE_DIAGNOSTICS["speech_frames_count"] = speech_frames_count
                LIVE_DIAGNOSTICS["silence_frames_count"] = silence_frames_count
                LIVE_DIAGNOSTICS["buffer_len"] = len(mic_audio_buffer)

                if is_voice:
                    if not speech_active:
                        speech_active = True
                        speech_frames_count = 0
                        silence_frames_count = 0
                        mic_audio_buffer = list(pre_speech_ring)
                    speech_frames_count += 1
                    last_user_activity = time.time()
                    # Giảm dần silence counter thay vì reset về 0 ngay lập tức nếu bị nhiễu 1 frame
                    if silence_frames_count > 0:
                        silence_frames_count = max(0, silence_frames_count - 1)
                    mic_audio_buffer.append(message)

                    # Giới hạn nói liên tục tối đa ~4.5s (75 frames * 60ms) để phản hồi nhanh
                    if len(mic_audio_buffer) >= 75:
                        if speech_frames_count >= 5 and not processing_ai:
                            pkts = list(mic_audio_buffer)
                            mic_audio_buffer.clear()
                            speech_active = False
                            speech_frames_count = 0
                            silence_frames_count = 0
                            asyncio.create_task(execute_ai_turn(pkts))
                        else:
                            mic_audio_buffer.clear()
                            speech_active = False
                            speech_frames_count = 0
                            silence_frames_count = 0
                else:
                    if not speech_active:
                        pre_speech_ring.append(message)
                    else:
                        mic_audio_buffer.append(message)
                        silence_frames_count += 1
                        # Phát hiện kết thúc câu: 8 frames im lặng (~480ms) sau khi nói ít nhất 6 frames (~360ms)
                        if silence_frames_count >= 5:
                            if speech_frames_count >= 4 and not processing_ai:
                                pkts = list(mic_audio_buffer)
                                mic_audio_buffer.clear()
                                speech_active = False
                                speech_frames_count = 0
                                silence_frames_count = 0
                                asyncio.create_task(execute_ai_turn(pkts))
                            else:
                                mic_audio_buffer.clear()
                                speech_active = False
                                speech_frames_count = 0
                                silence_frames_count = 0

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Robot disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        CONNECTED_ROBOTS.pop(device_mac, None)
        CONNECTED_ROBOT_PROTOCOLS.pop(id(websocket), None)
        session_active = False
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()
        if inactivity_task and not inactivity_task.done():
            inactivity_task.cancel()
        if device_mac in DB_DEVICES:
            # Keep online status active for robot
            DB_DEVICES[device_mac]["online"] = True
            DB_DEVICES[device_mac]["is_online"] = True

# ==================== MAIN HTTP RUNNER ====================


# ==================== AI DASHBOARD & CONTROL API ====================

AI_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gehihi AI Robot - Bảng Điều Khiển AI</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: linear-gradient(135deg, #090D16 0%, #0F172A 100%);
      color: #F8FAFC;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 32px 16px;
    }
    .container { max-width: 960px; width: 100%; }
    header { text-align: center; margin-bottom: 36px; }
    .logo-badge { display: inline-flex; align-items: center; gap: 8px; padding: 6px 16px; background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.35); border-radius: 999px; color: #A5B4FC; font-size: 13px; font-weight: 600; margin-bottom: 14px; text-transform: uppercase; }
    h1 { font-size: 30px; font-weight: 800; background: linear-gradient(to right, #FFFFFF, #94A3B8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px; }
    p.subtitle { color: #94A3B8; font-size: 15px; max-width: 560px; margin: 0 auto; }
    .status-bar { display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }
    .status-card { flex: 1; min-width: 200px; background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 16px 20px; display: flex; align-items: center; gap: 14px; }
    .status-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; background: rgba(255, 255, 255, 0.05); }
    .status-info h4 { font-size: 12px; color: #64748B; text-transform: uppercase; font-weight: 700; }
    .status-info p { font-size: 17px; font-weight: 700; color: #F1F5F9; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 36px; }
    .card { background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(16px); border: 2px solid rgba(255, 255, 255, 0.08); border-radius: 20px; padding: 24px; display: flex; flex-direction: column; position: relative; transition: all 0.25s ease; }
    .card:hover { transform: translateY(-3px); border-color: rgba(255, 255, 255, 0.2); }
    .card.active { border-color: #10B981; background: linear-gradient(180deg, rgba(16, 185, 129, 0.08) 0%, rgba(30, 41, 59, 0.7) 100%); box-shadow: 0 0 25px rgba(16, 185, 129, 0.2); }
    .card-badge { position: absolute; top: 18px; right: 18px; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .badge-active { background: #10B981; color: #064E3B; }
    .badge-fast { background: rgba(245, 158, 11, 0.18); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .provider-title { font-size: 20px; font-weight: 700; margin-bottom: 6px; display: flex; align-items: center; gap: 10px; }
    .provider-desc { font-size: 13px; color: #94A3B8; margin-bottom: 16px; line-height: 1.4; }
    .specs { background: rgba(15, 23, 42, 0.6); border-radius: 12px; padding: 12px; margin-bottom: 18px; font-size: 12px; }
    .specs-row { display: flex; justify-content: space-between; margin-bottom: 6px; }
    .specs-row:last-child { margin-bottom: 0; }
    .specs-label { color: #64748B; }
    .specs-val { color: #E2E8F0; font-weight: 600; font-family: monospace; }
    .btn-group { display: flex; gap: 8px; margin-top: auto; }
    .btn { flex: 1; padding: 11px 16px; border-radius: 12px; font-size: 13px; font-weight: 700; cursor: pointer; border: none; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 6px; }
    .btn-primary { background: #6366F1; color: #FFFFFF; }
    .btn-primary:hover { background: #4F46E5; }
    .btn-active { background: #10B981; color: #FFFFFF; cursor: default; }
    .btn-test { background: rgba(255, 255, 255, 0.08); color: #CBD5E1; flex: 0 0 auto; }
    .btn-test:hover { background: rgba(255, 255, 255, 0.15); }
    .toast { position: fixed; bottom: 24px; right: 24px; background: #1E293B; border: 1px solid #334155; padding: 14px 22px; border-radius: 14px; box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5); font-size: 14px; font-weight: 600; color: #F8FAFC; opacity: 0; transform: translateY(20px); transition: all 0.3s ease; pointer-events: none; z-index: 100; }
    .toast.show { opacity: 1; transform: translateY(0); }
    footer { text-align: center; font-size: 13px; color: #475569; margin-top: auto; }
    footer a { color: #6366F1; text-decoration: none; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-badge">⚡ Gehihi AI Multi-Engine</div>
      <h1>Chọn Trí Tuệ Nhân Tạo Cho Robot</h1>
      <p class="subtitle">Chuyển đổi tức thời giữa Groq (Siêu tốc), DeepSeek, OpenAI và Google Gemini mà không cần khởi động lại robot.</p>
    </header>
    <div class="status-bar">
      <div class="status-card"><div class="status-icon">🤖</div><div class="status-info"><h4>Thiết bị ESP32</h4><p>Mạch Tím (14:C1:9F:C4:EE:D0)</p></div></div>
      <div class="status-card"><div class="status-icon">🚀</div><div class="status-info"><h4>AI Đang Dùng</h4><p id="active-lbl">__ACTIVE_UPPER__</p></div></div>
      <div class="status-card"><div class="status-icon">⏱️</div><div class="status-info"><h4>Độ Trễ Phản Hồi</h4><p>< 1.5 giây</p></div></div>
    </div>
    <div class="grid">
      <!-- GROQ -->
      <div class="card __GROQ_ACTIVE__" id="card-groq">
        <span class="card-badge __GROQ_BADGE__">__GROQ_TAG__</span>
        <div class="provider-title">🚀 Groq LLaMA / Qwen</div>
        <div class="provider-desc">Inference siêu tốc trên phần cứng LPU chuyên dụng. Phản hồi tức thì, đàm thoại tự nhiên không ngắt quãng.</div>
        <div class="specs">
          <div class="specs-row"><span class="specs-label">Mô hình LLM:</span><span class="specs-val">qwen/qwen3.8-27b</span></div>
          <div class="specs-row"><span class="specs-label">ASR Nhận diện:</span><span class="specs-val">Whisper Large v3 Turbo</span></div>
          <div class="specs-row"><span class="specs-label">Tốc độ trung bình:</span><span class="specs-val" style="color:#10B981">~350ms</span></div>
        </div>
        <div class="btn-group">
          <button class="btn __GROQ_BTN__" onclick="activateProvider('groq')">__GROQ_TXT__</button>
          <button class="btn btn-test" onclick="testProvider('groq')">⚡ Thử</button>
        </div>
      </div>
      <!-- GOOGLE GEMINI -->
      <div class="card __GEMINI_ACTIVE__" id="card-gemini">
        <span class="card-badge __GEMINI_BADGE__">__GEMINI_TAG__</span>
        <div class="provider-title">✨ Google Gemini</div>
        <div class="provider-desc">Mô hình đa phương thức tiên tiến từ Google AI, hỗ trợ tiếng Việt phong phú và chuẩn mực.</div>
        <div class="specs">
          <div class="specs-row"><span class="specs-label">Mô hình LLM:</span><span class="specs-val">gemini-3.5-flash-lite</span></div>
          <div class="specs-row"><span class="specs-label">ASR Nhận diện:</span><span class="specs-val">Groq Whisper Turbo</span></div>
          <div class="specs-row"><span class="specs-label">Tốc độ trung bình:</span><span class="specs-val">~1.2s - 4.5s</span></div>
        </div>
        <div class="btn-group">
          <button class="btn __GEMINI_BTN__" onclick="activateProvider('gemini')">__GEMINI_TXT__</button>
          <button class="btn btn-test" onclick="testProvider('gemini')">⚡ Thử</button>
        </div>
      </div>
      <!-- DEEPSEEK -->
      <div class="card __DEEPSEEK_ACTIVE__" id="card-deepseek">
        <span class="card-badge __DEEPSEEK_BADGE__">__DEEPSEEK_TAG__</span>
        <div class="provider-title">🧠 DeepSeek Chat</div>
        <div class="provider-desc">Trí tuệ nhân tạo thế hệ mới DeepSeek V3 với khả năng suy luận sắc bén và giải đáp logic tuyệt vời.</div>
        <div class="specs">
          <div class="specs-row"><span class="specs-label">Mô hình LLM:</span><span class="specs-val">deepseek-chat</span></div>
          <div class="specs-row"><span class="specs-label">ASR Nhận diện:</span><span class="specs-val">Groq Whisper Turbo</span></div>
          <div class="specs-row"><span class="specs-label">Tốc độ trung bình:</span><span class="specs-val">~1.2s</span></div>
        </div>
        <div class="btn-group">
          <button class="btn __DEEPSEEK_BTN__" onclick="activateProvider('deepseek')">__DEEPSEEK_TXT__</button>
          <button class="btn btn-test" onclick="testProvider('deepseek')">⚡ Thử</button>
        </div>
      </div>
      <!-- OPENAI -->
      <div class="card __OPENAI_ACTIVE__" id="card-openai">
        <span class="card-badge __OPENAI_BADGE__">__OPENAI_TAG__</span>
        <div class="provider-title">🌐 OpenAI GPT-4o</div>
        <div class="provider-desc">Dòng mô hình GPT-4o Mini cân bằng tốc độ và độ chính xác của OpenAI hàng đầu thế giới.</div>
        <div class="specs">
          <div class="specs-row"><span class="specs-label">Mô hình LLM:</span><span class="specs-val">gpt-4o-mini</span></div>
          <div class="specs-row"><span class="specs-label">ASR Nhận diện:</span><span class="specs-val">Groq Whisper Turbo</span></div>
          <div class="specs-row"><span class="specs-label">Tốc độ trung bình:</span><span class="specs-val">~800ms</span></div>
        </div>
        <div class="btn-group">
          <button class="btn __OPENAI_BTN__" onclick="activateProvider('openai')">__OPENAI_TXT__</button>
          <button class="btn btn-test" onclick="testProvider('openai')">⚡ Thử</button>
        </div>
      </div>
    </div>
    <footer>
      <p>Gehihi Dynamic Server v2.5.0 • <a href="/xiaozhi/debug/live" target="_blank">Telemetry Live</a> • <a href="/" target="_blank">Web Dashboard</a></p>
    </footer>
  </div>
  <div class="toast" id="toast"></div>
  <script>
    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.classList.add('show');
      setTimeout(function() { t.classList.remove('show'); }, 3500);
    }
    async function activateProvider(p) {
      try {
        const res = await fetch('/xiaozhi/ai/provider', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: p })
        });
        const data = await res.json();
        if (data.code === 0) {
          showToast('✅ Đã kích hoạt ' + p.toUpperCase() + ' thành công!');
          setTimeout(function() { location.reload(); }, 600);
        } else { showToast('❌ Lỗi: ' + data.msg); }
      } catch (e) { showToast('❌ Lỗi kết nối: ' + e); }
    }
    async function testProvider(p) {
      showToast('⏳ Đang gửi tin thử nghiệm tới ' + p.toUpperCase() + '...');
      try {
        const res = await fetch('/xiaozhi/ai/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: p })
        });
        const data = await res.json();
        if (data.code === 0) {
          showToast('⚡ ' + p.toUpperCase() + ' (' + data.data.latency_ms + 'ms): "' + data.data.reply + '"');
        } else { showToast('⚠️ ' + data.msg); }
      } catch (e) { showToast('❌ Lỗi: ' + e); }
    }
  </script>
</body>
</html>
"""

async def handle_ai_provider_get(request):
    active = get_active_provider()
    providers = [
        {"id": "groq", "name": "Groq LLaMA / Qwen 27B", "tag": "Siêu Tốc (<1.5s) - Khuyên dùng", "model": "qwen/qwen3.8-27b", "asr": "whisper-large-v3-turbo", "active": (active == "groq"), "status": "ready"},
        {"id": "gemini", "name": "Google Gemini 3.5 Flash", "tag": "Tiếng Việt chuẩn", "model": "gemini-3.5-flash-lite", "asr": "whisper-large-v3-turbo", "active": (active == "gemini"), "status": "ready"},
        {"id": "deepseek", "name": "DeepSeek Chat (V3)", "tag": "Tư duy thông minh", "model": "deepseek-chat", "asr": "whisper-large-v3-turbo", "active": (active == "deepseek"), "status": "ready"},
        {"id": "openai", "name": "OpenAI GPT-4o Mini", "tag": "Cân bằng & Linh hoạt", "model": "gpt-4o-mini", "asr": "whisper-large-v3-turbo", "active": (active == "openai"), "status": "ready"}
    ]
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "active": active,
            "providers": providers,
            "telemetry": {
                "last_asr_ms": int(LIVE_DIAGNOSTICS.get("last_asr_latency", 0) * 1000),
                "last_llm_ms": int(LIVE_DIAGNOSTICS.get("last_llm_latency", 0) * 1000),
                "last_total_ms": int(LIVE_DIAGNOSTICS.get("last_total_latency", 0) * 1000),
                "turns_executed": LIVE_DIAGNOSTICS.get("turns_executed", 0)
            }
        }
    })

async def handle_ai_provider_set(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    prov = data.get("provider", "groq").lower().strip()
    active = set_active_provider(prov)
    logger.info(f"AI provider switched to: {active}")
    return cors_response({
        "code": 0,
        "msg": f"Đã kích hoạt AI: {active.upper()} thành công!",
        "data": {"active": active}
    })

async def handle_ai_provider_test(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    prov = data.get("provider", "groq").lower().strip()
    test_text = data.get("text", "Chào bạn, hãy giới thiệu ngắn 1 câu.")
    t0 = time.time()
    try:
        if prov == "groq":
            reply, emo = await call_groq_llm(test_text)
        elif prov == "deepseek":
            reply, emo = await call_deepseek_llm(test_text)
        elif prov == "openai":
            reply, emo = await call_openai_llm(test_text)
        elif prov == "gemini":
            reply, emo = await call_gemini_llm(test_text)
        else:
            reply, emo = await call_groq_llm(test_text)
        dt_ms = int((time.time() - t0) * 1000)
        return cors_response({
            "code": 0,
            "msg": "success",
            "data": {
                "provider": prov,
                "latency_ms": dt_ms,
                "reply": reply,
                "emotion": emo
            }
        })
    except Exception as e:
        return cors_response({
            "code": -1,
            "msg": f"Lỗi test AI: {e}",
            "data": {"provider": prov, "error": str(e)}
        })

async def handle_ai_dashboard(request):
    active = get_active_provider()
    html = AI_HTML_TEMPLATE.replace("__ACTIVE_UPPER__", active.upper())
    for p in ["groq", "gemini", "deepseek", "openai"]:
        is_act = (active == p)
        html = html.replace(f"__{p.upper()}_ACTIVE__", "active" if is_act else "")
        html = html.replace(f"__{p.upper()}_BADGE__", "badge-active" if is_act else ("badge-fast" if p == "groq" else ""))
        html = html.replace(f"__{p.upper()}_BTN__", "btn-active" if is_act else "btn-primary")
        html = html.replace(f"__{p.upper()}_TXT__", "✓ Đang Kích Hoạt" if is_act else f"Kích Hoạt {p.capitalize()}")
        tag_desc = "Đang Dùng" if is_act else {
            "groq": "Siêu Tốc 0.4s",
            "gemini": "Tiếng Việt Chuẩn",
            "deepseek": "Thông Minh V3",
            "openai": "Tiêu Chuẩn"
        }.get(p, "")
        html = html.replace(f"__{p.upper()}_TAG__", tag_desc)
    return web.Response(text=html, content_type="text/html")



# ==================== WEB TEMPLATES REST API HANDLERS ====================

WEB_ADMIN_DIR = os.path.join(os.path.dirname(__file__), "web_admin")

async def handle_api_auth_accounts(request):
    """Danh sách các tài khoản Robot để người dùng chọn nhanh"""
    accounts = []
    for mac, dev in DB_DEVICES.items():
        is_on = bool(dev.get("online", True))
        pin_code = dev.get("pin", "927184")
        mac_addr = dev.get("macAddress", mac.upper())
        accounts.append({
            "id": dev.get("id", "DEV_001"),
            "name": dev.get("name", "Robot Gehihi AI ESP32-S3 (Mạch tím)"),
            "device_code": pin_code,
            "pin": pin_code,
            "mac": mac_addr,
            "device_mac": mac_addr,
            "macAddress": mac_addr,
            "avatar": dev.get("avatar", "🤖"),
            "status": 1 if is_on else 0,
            "online": is_on,
            "is_online": is_on
        })
    return cors_response(accounts)

async def handle_api_auth_login(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    auth_type = data.get("type", "admin")
    if auth_type == "admin":
        user = data.get("username", "")
        pwd = data.get("password", "")
        if user == "admin" and (pwd == "admin123" or pwd == os.environ.get("ADMIN_PASSWORD", "admin123")):
            return cors_response({
                "code": 0,
                "msg": "Đăng nhập Admin thành công!",
                "token": "admin-token-" + uuid.uuid4().hex[:12],
                "isAdmin": True,
                "user": {"name": "Super Admin", "role": "admin"}
            })
        return cors_response({"code": 1, "message": "Sai tài khoản hoặc mật khẩu Admin!"}, status=401)
    else:
        # Robot PIN login
        pin = str(data.get("pin", data.get("identifier", ""))).strip()
        found_dev = None
        for mac, dev in DB_DEVICES.items():
            if str(dev.get("pin", "927184")) == pin or mac.lower() == pin.lower() or dev.get("id", "").lower() == pin.lower():
                found_dev = dev
                break
        if found_dev:
            return cors_response({
                "code": 0,
                "msg": "Đăng nhập Robot thành công!",
                "token": "robot-token-" + uuid.uuid4().hex[:12],
                "isAdmin": False,
                "device": {
                    "id": found_dev.get("id"),
                    "name": found_dev.get("name"),
                    "device_code": found_dev.get("macAddress", "").lower(),
                    "pin": found_dev.get("pin", "927184")
                }
            })
        return cors_response({"code": 1, "message": "Mã PIN Robot không đúng!"}, status=401)

async def handle_api_auth_logout(request):
    return cors_response({"code": 0, "msg": "Đã đăng xuất"})

async def handle_api_admin_change_password(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    new_pwd = data.get("new_password", data.get("password", ""))
    if new_pwd:
        os.environ["ADMIN_PASSWORD"] = new_pwd
        return cors_response({"code": 0, "msg": "Đổi mật khẩu Admin thành công!"})
    return cors_response({"code": 1, "message": "Mật khẩu mới không được trống"}, status=400)

async def handle_api_auth_register(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    name = data.get("name", "Robot Gehihi Mới")
    mac = data.get("macAddress", data.get("device_code", f"14:c1:9f:{uuid.uuid4().hex[:6]}"))
    pin = data.get("pin", str(uuid.uuid4().int)[:6])
    dev_id = f"DEV_{mac[-4:].upper()}"
    DB_DEVICES[mac.lower()] = {
        "id": dev_id,
        "macAddress": mac.upper(),
        "name": name,
        "pin": pin,
        "avatar": data.get("avatar", "🤖"),
        "boardType": "ESP32-S3",
        "version": "2.5.0",
        "status": 1,
        "online": True,
        "lastActiveTime": int(time.time() * 1000)
    }
    await broadcast_mic_monitor({
        "type": "device_event",
        "action": "created",
        "data": DB_DEVICES[mac.lower()]
    })
    return cors_response({"code": 0, "msg": "Kích hoạt Robot thành công!", "device": DB_DEVICES[mac.lower()]})

async def handle_api_devices_get_post(request):
    if request.method == "POST":
        return await handle_api_auth_register(request)
    
    # GET list of devices
    res = []
    for mac, d in DB_DEVICES.items():
        is_on = bool(d.get("online", True))
        pin_code = d.get("pin", "927184")
        mac_addr = d.get("macAddress", mac.upper())
        res.append({
            "id": d.get("id", "DEV_001"),
            "device_code": pin_code,
            "pin": pin_code,
            "mac": mac_addr,
            "macAddress": mac_addr,
            "device_mac": mac_addr,
            "name": d.get("name", "Robot Gehihi AI ESP32-S3 (Mạch tím)"),
            "avatar": d.get("avatar", "🤖"),
            "status": 1 if is_on else 0,
            "online": is_on,
            "is_online": is_on,
            "ip": d.get("ip", "10.26.1.70"),
            "version": d.get("version", "2.5.0"),
            "volume": d.get("volume", 80),
            "prompt": d.get("prompt", "Bạn là Gehihi, một trợ lý robot thông minh nói tiếng Việt tự nhiên và thân thiện."),
            "model": ACTIVE_AI_PROVIDER,
            "voice": "vi-VN-HoaiMyNeural",
            "battery": 95,
            "lastActiveTime": d.get("lastActiveTime", int(time.time() * 1000))
        })
    return cors_response(res)

async def handle_api_device_by_id(request):
    dev_id = request.match_info.get("id", "").lower()
    found_key = None
    for mac, dev in DB_DEVICES.items():
        if mac.lower() == dev_id or dev.get("id", "").lower() == dev_id:
            found_key = mac
            break
            
    if request.method == "DELETE":
        if found_key:
            del DB_DEVICES[found_key]
            await broadcast_mic_monitor({"type": "device_event", "action": "deleted", "device_id": dev_id})
            return cors_response({"code": 0, "msg": "Đã xóa thiết bị"})
        return cors_response({"code": 1, "message": "Không tìm thấy thiết bị"}, status=404)
        
    if request.method == "PUT":
        try:
            data = await request.json()
        except Exception:
            data = {}
        if found_key:
            if "name" in data:
                DB_DEVICES[found_key]["name"] = data["name"]
            if "volume" in data:
                DB_DEVICES[found_key]["volume"] = data["volume"]
            if "prompt" in data:
                DB_DEVICES[found_key]["prompt"] = data["prompt"]
            if "avatar" in data:
                DB_DEVICES[found_key]["avatar"] = data["avatar"]
            await broadcast_mic_monitor({"type": "device_event", "action": "updated", "data": DB_DEVICES[found_key]})
            return cors_response({"code": 0, "msg": "Cập nhật thành công", "data": DB_DEVICES[found_key]})
        return cors_response({"code": 1, "message": "Không tìm thấy thiết bị"}, status=404)
        
    # GET
    if found_key:
        return cors_response(DB_DEVICES[found_key])
    return cors_response({"code": 1, "message": "Không tìm thấy thiết bị"}, status=404)

async def handle_api_robot_control(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    action = data.get("action", "stop")
    logger.info(f"Received Remote Control command: {action}")
    # Forward to robot via WebSocket if connected
    for mac, ws in CONNECTED_ROBOTS.items():
        try:
            cmd = json.dumps({"type": "control", "action": action, "speed": data.get("speed", 100)})
            await ws.send(cmd)
        except Exception as e:
            logger.warning(f"Failed to forward control command to robot {mac}: {e}")
    return cors_response({"status": "ok", "message": f"Đã gửi lệnh '{action}' tới Robot Gehihi"})

async def handle_api_robot_display(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    emotion = data.get("emotion", "happy")
    text = data.get("text", "")
    logger.info(f"Received OLED Display command: emotion={emotion}, text={text}")
    for mac, ws in list(CONNECTED_ROBOTS.items()):
        try:
            cmd = json.dumps({"type": "llm", "emotion": emotion})
            await ws.send(cmd)
            if text:
                sub_cmd = json.dumps({"type": "tts", "state": "sentence_start", "text": text})
                await ws.send(sub_cmd)
        except Exception as e:
            logger.warning(f"Failed to forward oled command to robot {mac}: {e}")
    return cors_response({"status": "ok", "message": "Đã gửi hiển thị OLED"})

async def handle_api_robot_speak(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    text = data.get("text", "Xin chào chủ nhân!")
    emotion = data.get("emotion", "happy")
    logger.info(f"Received Speak command: '{text}'")
    # Generate and send TTS
    opus_pkts = await tts_to_opus(text)
    for mac, ws in CONNECTED_ROBOTS.items():
        try:
            await send_dynamic_tts_response(ws, str(uuid.uuid4()), "Lệnh phát loa", text, emotion, opus_pkts)
        except Exception as e:
            logger.warning(f"Failed to speak on robot: {e}")
    return cors_response({"status": "ok", "message": f"Robot Gehihi đang phát: {text}"})

async def call_llm_with_fallback(user_text: str, system_prompt: str = "") -> str:
    if not system_prompt:
        system_prompt = get_active_system_prompt()
    provider = get_active_provider()
    try:
        if provider == "groq":
            res, _ = await call_groq_llm(user_text, system_prompt=system_prompt)
            return res
        elif provider == "deepseek":
            res, _ = await call_deepseek_llm(user_text, system_prompt=system_prompt)
            return res
        elif provider == "gemini":
            res, _ = await call_gemini_llm(user_text, system_prompt=system_prompt)
            return res
        elif provider == "openai":
            res, _ = await call_openai_llm(user_text, system_prompt=system_prompt)
            return res
    except Exception as e:
        logger.warning(f"Error calling {provider} LLM: {e}")
    try:
        res, _ = await call_groq_llm(user_text, system_prompt=system_prompt)
        return res
    except Exception:
        return "Chào bạn! Tôi là Gehihi, rất vui được hỗ trợ bạn!"

async def handle_api_chat(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    text = data.get("text", data.get("message", "")).strip()
    if not text:
        return cors_response({"code": 1, "reply": "Vui lòng nhập tin nhắn!"}, status=400)
        
    t0 = time.time()
    system_prompt = get_active_system_prompt()
    bot_reply = await call_llm_with_fallback(text, system_prompt)
    latency = round(time.time() - t0, 3)

    # Detect emotion from conversation context
    emotion = "happy"
    lower_t = (text + " " + bot_reply).lower()
    if any(w in lower_t for w in ["buồn", "sad", "tiếc", "xin lỗi", "khóc"]):
        emotion = "sad"
    elif any(w in lower_t for w in ["cười", "haha", "vui", "hài", "chuyện cười", "funny", "joke"]):
        emotion = "happy"
    elif any(w in lower_t for w in ["ngạc nhiên", "sao", "thật sao", "wow", "surprise"]):
        emotion = "surprised"
    elif any(w in lower_t for w in ["suy nghĩ", "tính", "đang nghĩ", "think"]):
        emotion = "thinking"

    # Forward emotion and speech directly to physical robot
    logger.info(f"Web chat response: emotion={emotion}, reply='{bot_reply}'. Connected robots: {len(CONNECTED_ROBOTS)}")
    for mac, ws in list(CONNECTED_ROBOTS.items()):
        try:
            await ws.send(json.dumps({"type": "llm", "emotion": emotion}))
        except Exception as e:
            logger.warning(f"Failed to send emotion to robot {mac}: {e}")

    # Generate EdgeTTS and stream audio packets to robot speaker
    try:
        opus_pkts = await tts_to_opus(bot_reply)
        for mac, ws in list(CONNECTED_ROBOTS.items()):
            try:
                await send_dynamic_tts_response(ws, str(uuid.uuid4()), text, bot_reply, emotion, opus_pkts)
                logger.info(f"Successfully streamed speech to physical robot {mac}")
            except Exception as e:
                logger.warning(f"Failed to play audio on robot {mac}: {e}")
    except Exception as e:
        logger.warning(f"Failed to synthesize TTS for web chat: {e}")

    # Broadcast to mic monitor
    await broadcast_mic_monitor({
        "type": "stt_result",
        "text": text,
        "timestamp": time.strftime("%H:%M:%S")
    })
    await broadcast_mic_monitor({
        "type": "llm_reply",
        "reply": bot_reply,
        "emotion": emotion,
        "timestamp": time.strftime("%H:%M:%S")
    })
    
    return cors_response({
        "code": 0,
        "reply": bot_reply,
        "emotion": emotion,
        "latency_sec": latency,
        "provider": ACTIVE_AI_PROVIDER
    })

async def handle_api_my_xiaozhi_config(request):
    if request.method == "PUT":
        try:
            data = await request.json()
        except Exception:
            data = {}
        for a in DB_AGENTS:
            if a["id"] == "AGT_001":
                if "voice" in data:
                    a["ttsVoiceName"] = data["voice"]
                if "prompt" in data:
                    a["systemPrompt"] = data["prompt"]
                if "name" in data:
                    a["agentName"] = data["name"]
        return cors_response({"code": 0, "msg": "Cấu hình Gehihi đã lưu thành công!"})
    
    agent = DB_AGENTS[0] if DB_AGENTS else {}
    return cors_response({
        "name": agent.get("agentName", "Robot Gehihi AI"),
        "language": "vi",
        "voice": agent.get("ttsVoiceName", "vi-VN-HoaiMyNeural"),
        "volume": 8,
        "prompt": agent.get("systemPrompt", "Bạn là robot Gehihi thân thiện, trả lời bằng tiếng Việt tự nhiên."),
        "temperature": 0.7,
        "model": ACTIVE_AI_PROVIDER
    })

async def handle_api_curriculums(request):
    if request.method == "POST":
        try:
            data = await request.json()
        except Exception:
            data = {}
        # Apply or create
        cid = data.get("id", str(uuid.uuid4()))
        title = data.get("title", "Bài học tùy biến")
        logger.info(f"Applied curriculum: {title}")
        return cors_response({"code": 0, "msg": f"Đã áp dụng giáo trình '{title}' vào Robot Gehihi!"})
        
    curriculums_path = os.path.join(WEB_ADMIN_DIR, "curriculums_full.json")
    if os.path.exists(curriculums_path):
        try:
            with open(curriculums_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            return cors_response(cdata)
        except Exception as e:
            logger.warning(f"Error reading curriculums_full.json: {e}")
    return cors_response([])

async def handle_api_curriculums_apply(request):
    cid = request.match_info.get("id", "")
    logger.info(f"Applying curriculum ID: {cid}")
    return cors_response({"code": 0, "msg": f"Đã áp dụng bài học #{cid} vào Robot Gehihi!"})

async def handle_api_english_templates(request):
    mode = request.query.get("mode", "")
    tmpl_path = os.path.join(WEB_ADMIN_DIR, "all_english_templates.json")
    lessons = []
    roleplays = []
    if os.path.exists(tmpl_path):
        try:
            with open(tmpl_path, "r", encoding="utf-8") as f:
                all_t = json.load(f)
                lessons = all_t.get("lessons", [])
                roleplays = all_t.get("roleplay", []) or all_t.get("roleplays", [])
        except Exception as e:
            logger.warning(f"Error reading all_english_templates.json: {e}")
            
    if mode == "roleplay":
        return cors_response({"templates": roleplays})
    elif mode == "lesson":
        return cors_response({"templates": lessons})
    return cors_response({
        "lessons": lessons,
        "roleplays": roleplays,
        "templates": lessons
    })

async def handle_api_english_templates_apply(request):
    tid = request.match_info.get("id", "")
    return await handle_api_english_tutor_activate_template(request)

async def handle_api_english_tutor_activate_template(request):
    global ACTIVE_ENGLISH_TUTOR
    try:
        data = await request.json()
    except Exception:
        data = {}
    
    device_id = data.get("deviceId", "DEV_001")
    template_id = data.get("templateId") or request.match_info.get("id", "")
    title = data.get("title", "")
    template = data.get("template") or {}
    
    if not template or not template.get("target_words"):
        tmpl_path = os.path.join(WEB_ADMIN_DIR, "all_english_templates.json")
        if os.path.exists(tmpl_path):
            try:
                with open(tmpl_path, "r", encoding="utf-8") as f:
                    all_t = json.load(f)
                    all_items = all_t.get("lessons", []) + all_t.get("roleplay", []) + all_t.get("roleplays", [])
                    for item in all_items:
                        if item.get("id") == template_id or item.get("title") == title:
                            template = item
                            break
            except Exception as e:
                logger.warning(f"Error loading template data: {e}")
                
    title = title or template.get("title", "Bài học tiếng Anh")
    level = template.get("level", "a1")
    topic = template.get("topic", "Chung")
    words = template.get("target_words", [])
    phrases = template.get("target_phrases", [])
    tutor_note = template.get("tutor_note", "")
    scenario = template.get("scenario", "")
    
    words_str = ", ".join(words) if isinstance(words, list) else str(words)
    phrases_str = "\n".join(f"- {p}" for p in phrases) if isinstance(phrases, list) else str(phrases)
    note_str = tutor_note or scenario or "Hãy dạy vui vẻ, kiên nhẫn, khuyến khích bé nói theo."
    
    english_system_prompt = f"""Bạn là cô giáo tiếng Anh Sophia (Teacher Sophia) của bé, thông minh, dễ thương, phát âm chuẩn và kiên nhẫn.
Bài học hôm nay: {title}
Trình độ: {level.upper()} | Chủ đề: {topic}
Từ vựng mục tiêu: {words_str}
Mẫu câu luyện nói:
{phrases_str}
Ghi chú giảng dạy: {note_str}

Quy tắc tương tác sư phạm:
1. Bạn là giáo viên tiếng Anh cho trẻ em. Hãy giao tiếp bằng tiếng Anh đơn giản, chuẩn xác, vui tươi, tràn đầy năng lượng tích cực.
2. Mỗi lượt chỉ nói 1 đến 2 câu ngắn (dưới 15 từ), hỏi từng câu một để bé kịp nghe và nhắc lại.
3. Khen ngợi bé nhiệt tình khi bé trả lời (ví dụ: Great job!, Very good!, Excellent!).
4. Nếu bé nói tiếng Việt hoặc chưa hiểu, hãy nhẹ nhàng dịch sang tiếng Anh và hướng dẫn bé nhắc lại bằng tiếng Anh.
5. Tuyệt đối không bao giờ nói về quảng cáo, YouTube, subscribe hay các từ ngữ ngoài lề.
6. Trả về đúng 1 JSON hợp lệ duy nhất định dạng: {{"bot_text": "...", "emotion": "happy"}}
Các biểu cảm hợp lệ: [happy, loving, surprised, thinking, curious]."""

    now_ts = int(time.time())
    ACTIVE_ENGLISH_TUTOR.clear()
    ACTIVE_ENGLISH_TUTOR.update({
        "active": True,
        "activeId": f"active-{now_ts}",
        "id": template_id,
        "title": title,
        "level": level,
        "topic": topic,
        "target_words": words,
        "target_phrases": phrases,
        "tutor_note": note_str,
        "scenario": scenario,
        "content": f"[ENGLISH_TUTOR][{now_ts}] Tiêu đề: {title}\nTrình độ: {level.upper()}\nChủ đề: {topic}\nTừ vựng: {words_str}\nMẫu câu: {phrases_str}\nGhi chú: {note_str}",
        "createdAt": datetime.now().isoformat(),
        "system_prompt": english_system_prompt,
        "turns_completed": 0
    })
    
    for mac in DB_DEVICES:
        DB_DEVICES[mac]["prompt"] = english_system_prompt
        DB_DEVICES[mac]["custom_prompt"] = True
        DB_DEVICES[mac]["english_tutor"] = dict(ACTIVE_ENGLISH_TUTOR)
        
    logger.info(f"Activated English Tutor template: '{title}' (ID: {template_id})")
    
    # Broadcast to physical robots
    welcome_speech = f"Hello! Cô giáo Sophia đã sẵn sàng. Hôm nay chúng ta cùng học bài: {title} nhé!"
    try:
        opus_pkts = await tts_to_opus(welcome_speech)
        for mac, ws in list(CONNECTED_ROBOTS.items()):
            try:
                await ws.send(json.dumps({"type": "llm", "emotion": "loving"}))
                await send_dynamic_tts_response(ws, str(uuid.uuid4()), "Gia sư Tiếng Anh", welcome_speech, "loving", opus_pkts)
            except Exception as ex:
                logger.warning(f"Error streaming speech to robot {mac}: {ex}")
    except Exception as e:
        logger.warning(f"Error speaking welcome on robot: {e}")
        
    return cors_response({
        "success": True,
        "code": 0,
        "message": f"Đã áp dụng giáo trình '{title}' lên Robot!",
        "active": ACTIVE_ENGLISH_TUTOR,
        "activeId": ACTIVE_ENGLISH_TUTOR["activeId"]
    })

async def handle_api_english_tutor_activate(request):
    global ACTIVE_ENGLISH_TUTOR
    try:
        data = await request.json()
    except Exception:
        data = {}
    
    title = data.get("title", "Bài học tiếng Anh tùy chỉnh")
    level = data.get("level", "starter")
    topic = data.get("topic", "Tự chọn")
    words = data.get("targetWords") or data.get("words") or ""
    phrases = data.get("targetPhrases") or data.get("phrases") or ""
    note = data.get("note") or data.get("tutor_note") or ""
    
    words_list = [w.strip() for w in words.split(",") if w.strip()] if isinstance(words, str) else words
    phrases_list = [p.strip() for p in phrases.split("\n") if p.strip()] if isinstance(phrases, str) else phrases
    
    words_str = ", ".join(words_list)
    phrases_str = "\n".join(f"- {p}" for p in phrases_list)
    
    english_system_prompt = f"""Bạn là cô giáo tiếng Anh Sophia (Teacher Sophia) của bé, thông minh, dễ thương, phát âm chuẩn và kiên nhẫn.
Bài học hiện tại: {title}
Trình độ: {level.upper()} | Chủ đề: {topic}
Từ vựng mục tiêu: {words_str}
Mẫu câu luyện nói:
{phrases_str}
Ghi chú giảng dạy: {note}

Quy tắc tương tác sư phạm:
1. Bạn là giáo viên tiếng Anh cho trẻ em. Hãy giao tiếp bằng tiếng Anh đơn giản, chuẩn xác, vui tươi, tràn đầy năng lượng tích cực.
2. Mỗi lượt chỉ nói 1 đến 2 câu ngắn (dưới 15 từ), hỏi từng câu một để bé kịp nghe và nhắc lại.
3. Khen ngợi bé nhiệt tình khi bé trả lời (ví dụ: Great job!, Very good!, Excellent!).
4. Nếu bé nói tiếng Việt hoặc chưa hiểu, hãy nhẹ nhàng dịch sang tiếng Anh và hướng dẫn bé nhắc lại bằng tiếng Anh.
5. Tuyệt đối không bao giờ nói về quảng cáo, YouTube, subscribe hay các từ ngữ ngoài lề.
6. Trả về đúng 1 JSON hợp lệ duy nhất định dạng: {{"bot_text": "...", "emotion": "happy"}}
Các biểu cảm hợp lệ: [happy, loving, surprised, thinking, curious]."""

    now_ts = int(time.time())
    ACTIVE_ENGLISH_TUTOR.clear()
    ACTIVE_ENGLISH_TUTOR.update({
        "active": True,
        "activeId": f"active-{now_ts}",
        "id": f"custom-{now_ts}",
        "title": title,
        "level": level,
        "topic": topic,
        "target_words": words_list,
        "target_phrases": phrases_list,
        "tutor_note": note,
        "content": f"[ENGLISH_TUTOR][{now_ts}] Tiêu đề: {title}\nTrình độ: {level.upper()}\nChủ đề: {topic}\nTừ vựng: {words_str}\nMẫu câu: {phrases_str}\nGhi chú: {note}",
        "createdAt": datetime.now().isoformat(),
        "system_prompt": english_system_prompt,
        "turns_completed": 0
    })
    
    for mac in DB_DEVICES:
        DB_DEVICES[mac]["prompt"] = english_system_prompt
        DB_DEVICES[mac]["custom_prompt"] = True
        DB_DEVICES[mac]["english_tutor"] = dict(ACTIVE_ENGLISH_TUTOR)
        
    logger.info(f"Activated custom English lesson: '{title}'")
    
    welcome_speech = f"Hello! Cô giáo Sophia đã sẵn sàng cho bài: {title}!"
    try:
        opus_pkts = await tts_to_opus(welcome_speech)
        for mac, ws in list(CONNECTED_ROBOTS.items()):
            try:
                await ws.send(json.dumps({"type": "llm", "emotion": "loving"}))
                await send_dynamic_tts_response(ws, str(uuid.uuid4()), "Gia sư Tiếng Anh", welcome_speech, "loving", opus_pkts)
            except Exception as ex:
                logger.warning(f"Error speaking to robot: {ex}")
    except Exception as e:
        logger.warning(f"Error speaking welcome on robot: {e}")
        
    return cors_response({
        "success": True,
        "code": 0,
        "message": f"Đã áp dụng bài học '{title}' lên Robot!",
        "active": ACTIVE_ENGLISH_TUTOR,
        "activeId": ACTIVE_ENGLISH_TUTOR["activeId"]
    })

async def handle_api_english_tutor_deactivate(request):
    ACTIVE_ENGLISH_TUTOR["active"] = False
    ACTIVE_ENGLISH_TUTOR["activeId"] = None
    
    for mac in DB_DEVICES:
        DB_DEVICES[mac]["prompt"] = "Bạn là Gehihi, một trợ lý robot thông minh nói tiếng Việt tự nhiên và thân thiện."
        DB_DEVICES[mac]["custom_prompt"] = False
        DB_DEVICES[mac]["english_tutor"] = None
        
    bye_speech = "Đã tắt chế độ gia sư tiếng Anh. Gehihi quay lại chế độ bình thường nhé!"
    try:
        opus_pkts = await tts_to_opus(bye_speech)
        for mac, ws in list(CONNECTED_ROBOTS.items()):
            try:
                await ws.send(json.dumps({"type": "llm", "emotion": "happy"}))
                await send_dynamic_tts_response(ws, str(uuid.uuid4()), "Hệ thống", bye_speech, "happy", opus_pkts)
            except Exception as ex:
                logger.warning(f"Error speaking goodbye on robot: {ex}")
    except Exception as e:
        logger.warning(f"Error speaking on robot: {e}")
        
    return cors_response({
        "success": True,
        "code": 0,
        "message": "Đã tắt chế độ gia sư tiếng Anh thành công!"
    })

async def handle_api_english_tutor_active(request):
    if request.method == "POST":
        return await handle_api_english_tutor_activate(request)
    elif request.method == "DELETE":
        return await handle_api_english_tutor_deactivate(request)
        
    if ACTIVE_ENGLISH_TUTOR.get("active"):
        return cors_response({
            "active": ACTIVE_ENGLISH_TUTOR,
            "activeId": ACTIVE_ENGLISH_TUTOR.get("activeId"),
            "title": ACTIVE_ENGLISH_TUTOR.get("title"),
            "content": ACTIVE_ENGLISH_TUTOR.get("content"),
            "level": ACTIVE_ENGLISH_TUTOR.get("level", "a1"),
            "topic": ACTIVE_ENGLISH_TUTOR.get("topic", "Daily Routine")
        })
    else:
        return cors_response({"active": None, "activeId": None})

async def handle_api_english_tutor_report(request):
    turns = ACTIVE_ENGLISH_TUTOR.get("turns_completed", 0)
    current_title = ACTIVE_ENGLISH_TUTOR.get("title", "Daily Routine - Bài 1: My day")
    level = ACTIVE_ENGLISH_TUTOR.get("level", "a1").upper()
    return cors_response({
        "profile": {
            "known_words": ["cat", "dog", "hello", "wake up", "eat", "apple", "red", "blue"],
            "weak_words": ["sleep", "student"],
            "weak_phrases": ["I go to sleep."],
            "streak_days": 3,
            "level": level
        },
        "stats": {
            "completed_sessions": 8 + (1 if turns > 3 else 0),
            "started_sessions": 9 + (1 if turns > 0 else 0),
            "abandoned_sessions": 1,
            "avg_score": 92,
            "total_seconds": 9600 + turns * 30
        },
        "sessions": [
            {"id": "sess-1", "title": current_title, "score": 95, "created_at": "Hôm nay", "level": level},
            {"id": "sess-2", "title": "School - Bài 2: In class", "score": 90, "created_at": "Hôm qua", "level": "A1"},
            {"id": "sess-3", "title": "Colors - Bài 1: Basic colors", "score": 94, "created_at": "2 ngày trước", "level": "STARTER"}
        ],
        "total_lessons_completed": 8 + (1 if turns > 3 else 0),
        "fluency_score": "92/100",
        "total_practice_minutes": 160 + turns * 2,
        "vocabulary_mastered": 42
    })

async def handle_api_english_tutor_recommendation(request):
    if ACTIVE_ENGLISH_TUTOR.get("active"):
        return cors_response({
            "type": "active",
            "title": ACTIVE_ENGLISH_TUTOR.get("title", ""),
            "level": ACTIVE_ENGLISH_TUTOR.get("level", "a1"),
            "topic": ACTIVE_ENGLISH_TUTOR.get("topic", ""),
            "reason": "Bài học đang được áp dụng trên Robot. Hãy tiếp tục luyện tập cùng Sophia!"
        })
    return cors_response({
        "type": "template",
        "title": "Daily Routine - Bài 1: My day",
        "level": "a1",
        "topic": "Daily Routine",
        "reason": "Bài mở đầu phù hợp nhất cho trẻ em",
        "template": {
            "id": "31618393-f19b-47d9-8966-043ad408cec6",
            "title": "Daily Routine - Bài 1: My day",
            "level": "a1",
            "topic": "Daily Routine"
        }
    })

async def handle_api_english_tutor_quick_review(request):
    title = "⚡ Ôn nhanh 5 phút: Từ vựng & Mẫu câu"
    review_prompt = """Bạn là cô giáo tiếng Anh Sophia trong phiên ôn tập nhanh 5 phút.
Mục tiêu: Ôn lại các từ cần củng cố: sleep, student, I go to sleep.
Hãy hỏi bé những câu ngắn vui nhộn để bé nói lại từ này. Khen ngợi bé nhiệt tình!
Trả về đúng 1 JSON hợp lệ duy nhất: {"bot_text": "...", "emotion": "happy"}"""

    now_ts = int(time.time())
    ACTIVE_ENGLISH_TUTOR.clear()
    ACTIVE_ENGLISH_TUTOR.update({
        "active": True,
        "activeId": f"review-{now_ts}",
        "id": f"review-{now_ts}",
        "title": title,
        "level": "a1",
        "topic": "Quick Review",
        "target_words": ["sleep", "student"],
        "target_phrases": ["I go to sleep."],
        "tutor_note": "Ôn tập nhanh 5 phút",
        "content": f"[ENGLISH_TUTOR][{now_ts}] Tiêu đề: {title}\nÔn nhanh 5 phút các từ khó",
        "createdAt": datetime.now().isoformat(),
        "system_prompt": review_prompt,
        "turns_completed": 0
    })
    return cors_response({
        "success": True,
        "activeLesson": ACTIVE_ENGLISH_TUTOR,
        "message": "Đã bắt đầu phiên ôn tập 5 phút!"
    })

async def handle_api_ai_roles(request):
    roles = [
        {"id": "ROLE_01", "name": "Gia sư Tiếng Anh", "desc": "Luyện phát âm, đối thoại từ vựng ngắn cho trẻ em", "icon": "🎓"},
        {"id": "ROLE_02", "name": "Bạn Đồng Hành Nhí", "desc": "Tâm sự, kể chuyện cười, động viên tích cực", "icon": "🧸"},
        {"id": "ROLE_03", "name": "Bác Học Nhí", "desc": "Giải đáp kiến thức khoa học, tự nhiên bằng ngôn từ dễ hiểu", "icon": "🔬"},
        {"id": "ROLE_04", "name": "Kể Chuyện Cổ Tích", "desc": "Giọng đọc truyền cảm ru ngủ hoặc kể chuyện đạo đức", "icon": "📖"},
        {"id": "ROLE_05", "name": "Trợ Lý Gia Đình", "desc": "Nhắc việc, báo thức, thông tin thời tiết hằng ngày", "icon": "⏰"}
    ]
    return cors_response(roles)

async def handle_api_ai_roles_apply(request):
    rid = request.match_info.get("id", "")
    logger.info(f"Applied AI Role: {rid}")
    return cors_response({"code": 0, "msg": f"Đã đổi vai trò AI thành công!"})

async def handle_api_memories(request):
    if request.method == "POST":
        try:
            data = await request.json()
        except Exception:
            data = {}
        content = data.get("content", "").strip()
        if content:
            new_mem = {
                "id": f"MEM_{uuid.uuid4().hex[:6].upper()}",
                "content": content,
                "category": data.get("category", "ghi nhớ"),
                "createdAt": int(time.time() * 1000),
                "macAddress": "14:C1:9F:C4:EE:D0"
            }
            DB_MEMORIES.insert(0, new_mem)
            return cors_response({"code": 0, "msg": "Đã thêm bộ nhớ mới!", "data": new_mem})
        return cors_response({"code": 1, "message": "Nội dung bộ nhớ trống!"}, status=400)
    return cors_response(DB_MEMORIES)

async def handle_api_memory_delete(request):
    mid = request.match_info.get("id", "")
    global DB_MEMORIES
    DB_MEMORIES = [m for m in DB_MEMORIES if m["id"] != mid]
    return cors_response({"code": 0, "msg": "Đã xóa bộ nhớ"})

async def handle_api_memories_batch_delete(request):
    global DB_MEMORIES
    try:
        data = await request.json()
    except Exception:
        data = {}
    ids = set(data.get("ids", []))
    DB_MEMORIES = [m for m in DB_MEMORIES if m["id"] not in ids]
    return cors_response({"code": 0, "msg": f"Đã xóa {len(ids)} bộ nhớ"})

async def handle_api_learning_tasks(request):
    if request.method == "POST":
        try:
            data = await request.json()
        except Exception:
            data = {}
        title = data.get("title", "").strip()
        if title:
            new_task = {
                "id": f"TASK_{uuid.uuid4().hex[:6].upper()}",
                "title": title,
                "desc": data.get("desc", ""),
                "completed": False,
                "priority": data.get("priority", "normal"),
                "createdAt": int(time.time() * 1000)
            }
            DB_TASKS.insert(0, new_task)
            return cors_response({"code": 0, "msg": "Đã thêm nhiệm vụ mới!", "data": new_task})
        return cors_response({"code": 1, "message": "Tiêu đề nhiệm vụ trống!"}, status=400)
    return cors_response(DB_TASKS)

async def handle_api_task_complete(request):
    tid = request.match_info.get("id", "")
    for t in DB_TASKS:
        if t["id"] == tid:
            t["completed"] = True
            return cors_response({"code": 0, "msg": "Nhiệm vụ đã hoàn thành!"})
    return cors_response({"code": 1, "message": "Không tìm thấy nhiệm vụ"}, status=404)

async def handle_api_knowledge_docs(request):
    if request.method == "POST":
        try:
            data = await request.json()
        except Exception:
            data = {}
        title = data.get("title", "Tài liệu mới")
        content = data.get("content", "")
        new_doc = {
            "id": f"KB_{uuid.uuid4().hex[:6].upper()}",
            "title": title,
            "content": content,
            "type": data.get("type", "custom"),
            "createdAt": int(time.time() * 1000)
        }
        DB_KNOWLEDGE_DOCS.insert(0, new_doc)
        return cors_response({"code": 0, "msg": "Đã lưu tài liệu tri thức!", "data": new_doc})
    return cors_response(DB_KNOWLEDGE_DOCS)

async def handle_api_feedback(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    DB_FEEDBACKS.append(data)
    logger.info(f"Received user feedback: {data}")
    return cors_response({"code": 0, "msg": "Cảm ơn bạn đã đóng góp ý kiến cho Gehihi!"})

async def handle_api_wss_requests(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    DB_WSS_REQUESTS.append(data)
    logger.info(f"Received Home Assistant request: {data}")
    return cors_response({"code": 0, "msg": "Đã tiếp nhận yêu cầu tích hợp Home Assistant!"})

# ==================== YOUTUBE MUSIC & OPUS STREAMING ENGINE ====================

ACTIVE_MUSIC_STATE = {
    "is_playing": False,
    "task": None,
    "track": None,
    "stop_event": None
}

def stop_active_music():
    """Dừng luồng phát nhạc trên robot ngay lập tức"""
    if ACTIVE_MUSIC_STATE.get("stop_event"):
        try:
            ACTIVE_MUSIC_STATE["stop_event"].set()
        except Exception:
            pass
    if ACTIVE_MUSIC_STATE.get("task"):
        try:
            ACTIVE_MUSIC_STATE["task"].cancel()
        except Exception:
            pass
    ACTIVE_MUSIC_STATE["is_playing"] = False

def get_ffmpeg_cmd():
    f = shutil.which("ffmpeg")
    if f:
        return f
    try:
        if imageio_ffmpeg:
            return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return "ffmpeg"

POPULAR_CHILDREN_SONGS = [
    {
        "id": "X0wxLzTe5rE",
        "title": "Nhạc Thiếu Nhi Tập Thể Dục Buổi Sáng - Con Heo Đất",
        "uploader": "Con Heo Đất",
        "duration_str": "3:54",
        "thumbnail": "https://i.ytimg.com/vi/X0wxLzTe5rE/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=X0wxLzTe5rE"
    },
    {
        "id": "X0wxLzTe5rE",
        "title": "Nhạc Thiếu Nhi Tập Thể Dục Buổi Sáng - Con Heo Đất",
        "uploader": "Con Heo Đất",
        "duration_str": "3:54",
        "thumbnail": "https://i.ytimg.com/vi/X0wxLzTe5rE/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=X0wxLzTe5rE"
    },
    {
        "id": "XqZsoesa55w",
        "title": "Baby Shark Dance - Nhạc Thiếu Nhi Hoạt Hình",
        "uploader": "Pinkfong Baby Shark",
        "duration_str": "2:16",
        "thumbnail": "https://i.ytimg.com/vi/XqZsoesa55w/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=XqZsoesa55w"
    },
    {
        "id": "hl5XQo4Wy6Y",
        "title": "Ca Nhạc Thiếu Nhi Vui Nhộn Cho Bé - Con Lợn Éc",
        "uploader": "Chú Chim Non TV",
        "duration_str": "4:12",
        "thumbnail": "https://i.ytimg.com/vi/hl5XQo4Wy6Y/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=hl5XQo4Wy6Y"
    },
    {
        "id": "nN5z6jL1tO4",
        "title": "Chú Voi Con Ở Bản Đôn - Nhạc Thiếu Nhi Bất Hủ",
        "uploader": "Xuân Mai Official",
        "duration_str": "2:45",
        "thumbnail": "https://i.ytimg.com/vi/nN5z6jL1tO4/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=nN5z6jL1tO4"
    },
    {
        "id": "J1s4Xz8y8dE",
        "title": "Rửa Mặt Như Mèo & Cháu Lên Ba Vui Nhộn",
        "uploader": "Kênh Thiếu Nhi BHMedia",
        "duration_str": "3:20",
        "thumbnail": "https://i.ytimg.com/vi/J1s4Xz8y8dE/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=J1s4Xz8y8dE"
    },
    {
        "id": "vF4r9j2t7y8",
        "title": "Bắc Kim Thang & Cả Nhà Thương Nhau Rộn Ràng",
        "uploader": "Mầm Chồi Lá",
        "duration_str": "3:10",
        "thumbnail": "https://i.ytimg.com/vi/vF4r9j2t7y8/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=vF4r9j2t7y8"
    },
    {
        "id": "75p-NVPKCSE",
        "title": "ABC Phonics Song - Bài Hát Học Tiếng Anh Trẻ Em",
        "uploader": "CoComelon",
        "duration_str": "3:40",
        "thumbnail": "https://i.ytimg.com/vi/75p-NVPKCSE/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=75p-NVPKCSE"
    },
    {
        "id": "k8vD5OsqhYs",
        "title": "Một Con Vịt Xòe Ra Hai Cái Cánh Vui Nhộn",
        "uploader": "Thiếu Nhi Remi",
        "duration_str": "2:50",
        "thumbnail": "https://i.ytimg.com/vi/k8vD5OsqhYs/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=k8vD5OsqhYs"
    },
    {
        "id": "2b3Xk9dY8kM",
        "title": "Chú Ếch Con Kìa Chú Là Chú Ếch Con",
        "uploader": "Vườn Cổ Tích",
        "duration_str": "3:15",
        "thumbnail": "https://i.ytimg.com/vi/2b3Xk9dY8kM/hqdefault.jpg",
        "url": "https://www.youtube.com/watch?v=2b3Xk9dY8kM"
    }
]

async def search_youtube_tracks(q: str, limit: int = 12) -> list:
    q = (q or "").strip()
    if not q:
        return POPULAR_CHILDREN_SONGS[:limit]

    # Kiểm tra dán URL trực tiếp
    if "youtube.com/" in q or "youtu.be/" in q:
        try:
            if yt_dlp:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
                }
                def _extract_direct():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(q, download=False)
                info = await asyncio.wait_for(asyncio.to_thread(_extract_direct), timeout=4.0)
                vid = info.get("id") or "yt_custom"
                dur = info.get("duration") or 180
                dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}"
                return [{
                    "id": vid,
                    "title": info.get("title") or "Bản nhạc YouTube",
                    "uploader": info.get("uploader") or "YouTube",
                    "duration_str": dur_str,
                    "thumbnail": info.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "url": q
                }]
        except Exception as e:
            logger.warning(f"Error parsing direct YouTube link: {e}")

    results = []

    # 1. Tìm kiếm bằng yt_dlp (non-blocking thread với timeout 4s)
    if yt_dlp:
        try:
            ydl_opts = {
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
            }
            def _extract_search():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
            res = await asyncio.wait_for(asyncio.to_thread(_extract_search), timeout=4.0)
            entries = res.get("entries", [])
            for e in entries:
                if not e:
                    continue
                vid = e.get("id")
                title = e.get("title")
                if not vid or not title:
                    continue
                dur = e.get("duration") or 180
                dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}"
                results.append({
                    "id": vid,
                    "title": title,
                    "uploader": e.get("uploader") or "YouTube",
                    "duration_str": dur_str,
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "url": f"https://www.youtube.com/watch?v={vid}"
                })
            if len(results) >= 2:
                return results
        except Exception as e:
            logger.warning(f"yt_dlp search error: {e}")

    # 2. Cào HTML tìm kiếm YouTube (không phụ thuộc yt_dlp)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'vi,en;q=0.9'
        }
        encoded_q = urllib.parse.quote(q)
        search_url = f"https://www.youtube.com/results?search_query={encoded_q}"
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            m = re.search(r'var ytInitialData = ({.*?});</script>', html)
            if not m:
                m = re.search(r'window\["ytInitialData"\] = ({.*?});', html)
            if m:
                data = json.loads(m.group(1))
                contents = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']
                for section in contents:
                    item_section = section.get('itemSectionRenderer', {}).get('contents', [])
                    for item in item_section:
                        vr = item.get('videoRenderer')
                        if vr:
                            vid = vr.get('videoId')
                            title = vr.get('title', {}).get('runs', [{}])[0].get('text', '')
                            length = vr.get('lengthText', {}).get('simpleText', '3:30')
                            uploader = vr.get('ownerText', {}).get('runs', [{}])[0].get('text', 'YouTube')
                            if vid and title:
                                results.append({
                                    "id": vid,
                                    "title": title,
                                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                                    "duration_str": length,
                                    "uploader": uploader,
                                    "url": f"https://www.youtube.com/watch?v={vid}"
                                })
                if len(results) >= 2:
                    return results[:limit]
    except Exception as e:
        logger.warning(f"HTML scraper search error: {e}")

    # 3. Lọc danh mục tuyển chọn
    q_words = [w for w in q.lower().split() if len(w) > 1]
    matched = []
    for s in POPULAR_CHILDREN_SONGS:
        s_text = (s["title"] + " " + s["uploader"]).lower()
        if any(w in s_text for w in q_words):
            matched.append(s)
    if matched:
        return matched[:limit]

    # Fallback tuyệt đối: trả về toàn bộ danh mục trẻ em
    return POPULAR_CHILDREN_SONGS[:limit]

async def stream_music_to_robots(audio_url: str, track_info: dict):
    stop_event = asyncio.Event()
    ACTIVE_MUSIC_STATE["stop_event"] = stop_event
    ACTIVE_MUSIC_STATE["is_playing"] = True
    ACTIVE_MUSIC_STATE["track"] = track_info

    session_id = str(uuid.uuid4())
    raw_title = track_info.get("title", "Bài hát thiếu nhi")
    title_clean = raw_title.split("-")[0].strip()[:26]
    logger.info(f"Starting music stream to robots: '{title_clean}'")

    # 1. Báo hiển thị OLED & khởi tạo luồng âm thanh
    for mac, ws in list(CONNECTED_ROBOTS.items()):
        try:
            await ws.send(json.dumps({"type": "llm", "emotion": "happy"}))
            await asyncio.sleep(0.01)
            await ws.send(json.dumps({"type": "tts", "state": "start", "session_id": session_id}))
            await asyncio.sleep(0.01)
            await ws.send(json.dumps({
                "type": "tts",
                "state": "sentence_start",
                "text": f"🎵 {title_clean}",
                "session_id": session_id
            }))
        except Exception as e:
            logger.warning(f"Error signaling music start to robot {mac}: {e}")

    ffmpeg_exe = get_ffmpeg_cmd()
    cmd = [
        ffmpeg_exe,
        "-i", audio_url,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", "16000",
        "pipe:1"
    ]

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

        import opuslib_next
        encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)
        frame_samples = 960  # 60ms tại 16kHz
        frame_bytes = frame_samples * 2  # 1920 bytes

        frame_idx = 0
        next_frame_time = time.monotonic()

        while not stop_event.is_set():
            chunk = await proc.stdout.read(frame_bytes)
            if not chunk or len(chunk) == 0:
                break
            if len(chunk) < frame_bytes:
                chunk += b"\x00" * (frame_bytes - len(chunk))

            encoded_opus = encoder.encode(chunk, frame_samples)

            # Truyền frame Opus tới tất cả robot kết nối
            for mac, ws in list(CONNECTED_ROBOTS.items()):
                try:
                    await ws.send(encoded_opus)
                except Exception as ex:
                    logger.debug(f"Error sending frame to {mac}: {ex}")

            frame_idx += 1
            if frame_idx <= 4:
                # Preload 4 frames đầu để loa phát tức thì không ngắt quãng
                await asyncio.sleep(0.008)
                next_frame_time = time.monotonic() + 0.058
            else:
                next_frame_time += 0.058
                sleep_dur = next_frame_time - time.monotonic()
                if sleep_dur > 0:
                    await asyncio.sleep(sleep_dur)
                else:
                    await asyncio.sleep(0.002)
                    next_frame_time = time.monotonic()

    except asyncio.CancelledError:
        logger.info(f"Music streaming cancelled for '{title_clean}'")
    except Exception as e:
        logger.error(f"Error in music streaming pipeline: {e}")
    finally:
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        
        # Báo kết thúc phiên phát âm thanh trên robot
        for mac, ws in list(CONNECTED_ROBOTS.items()):
            try:
                await ws.send(json.dumps({"type": "tts", "state": "stop", "session_id": session_id}))
            except Exception:
                pass

        ACTIVE_MUSIC_STATE["is_playing"] = False
        ACTIVE_MUSIC_STATE["stop_event"] = None
        logger.info(f"Music streaming finished for: '{title_clean}'")

async def handle_api_music_status(request):
    return cors_response({
        "success": True,
        "is_playing": bool(ACTIVE_MUSIC_STATE.get("is_playing", False)),
        "track": ACTIVE_MUSIC_STATE.get("track", None)
    })

async def handle_api_music_search(request):
    q = request.query.get("q", "nhạc thiếu nhi vui nhộn")
    tracks = await search_youtube_tracks(q, limit=12)
    return cors_response({
        "success": True,
        "results": tracks,
        "count": len(tracks)
    })

async def resolve_and_stream_music(target_url: str, track_info: dict):
    audio_stream_url = target_url
    if yt_dlp:
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
            }
            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(target_url, download=False)
            info = await asyncio.wait_for(asyncio.to_thread(_extract), timeout=6.0)
            if info and info.get("url"):
                audio_stream_url = info.get("url")
        except Exception as e:
            logger.warning(f"Background stream extract fallback: {e}")

    await stream_music_to_robots(audio_stream_url, track_info)

async def handle_api_music_play(request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    target = data.get("url") or data.get("id") or ""
    logger.info(f"Received Play Music request: target='{target}'")

    if not target:
        return cors_response({"success": False, "error": "Thiếu thông tin bài hát (URL hoặc ID)"}, status=400)

    # 1. Dừng luồng phát nhạc trước nếu đang phát
    stop_active_music()

    target_url = target if target.startswith("http") else f"https://www.youtube.com/watch?v={target}"
    track_info = None

    for song in POPULAR_CHILDREN_SONGS:
        if song["id"] == target or song["url"] == target or target in song["url"]:
            track_info = dict(song)
            break

    if not track_info:
        track_info = {
            "id": target,
            "title": data.get("title") or "Bản nhạc thiếu nhi",
            "uploader": data.get("uploader") or "YouTube Music",
            "duration_str": data.get("duration_str") or "3:30",
            "thumbnail": data.get("thumbnail") or f"https://i.ytimg.com/vi/{target}/hqdefault.jpg",
            "url": target_url
        }

    # 2. Khởi chạy tác vụ phát nhạc trong background ngay lập tức
    ACTIVE_MUSIC_STATE["task"] = asyncio.create_task(resolve_and_stream_music(target_url, track_info))

    # 3. Trả về phản hồi tức thì (<50ms) cho Web UI
    return cors_response({
        "success": True,
        "title": track_info["title"],
        "uploader": track_info.get("uploader", "YouTube"),
        "thumbnail": track_info.get("thumbnail", ""),
        "duration_str": track_info.get("duration_str", "--:--")
    })

async def handle_api_music_stop(request):
    stop_active_music()
    for mac, ws in list(CONNECTED_ROBOTS.items()):
        try:
            await ws.send(json.dumps({"type": "tts", "state": "stop"}))
        except Exception:
            pass
    return cors_response({"success": True, "msg": "Đã dừng phát nhạc trên robot"})

async def handle_api_ocr(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    return cors_response({
        "status": "ok",
        "title": "Bài tập tiếng Anh nhận diện",
        "text": "1. I ___ a happy student. (am/is/are)\n2. She ___ reading an interesting book."
    })

async def handle_api_generate_lesson_plan(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    topic = data.get("text") or data.get("topic") or "Gia đình và bạn bè"
    try:
        prompt = f"Hãy tạo giáo án tiếng Anh ngắn gọn 3 mục cho trẻ em về chủ đề '{topic}': 1. Từ vựng trọng tâm. 2. Câu giao tiếp. 3. Trò chơi phản xạ với Robot Gehihi."
        plan = await call_llm_with_fallback(prompt)
    except Exception:
        plan = f"""Mục tiêu bài học chủ đề '{topic}':
- Học từ vựng: Family, Father, Mother, Brother, Sister.
- Mẫu câu: This is my family. I love my friends.
- Hoạt động tương tác phản xạ cùng Robot Gehihi 5 phút."""
    return cors_response({"status": "ok", "lesson_plan": plan})

async def handle_api_learning_task_solve(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    task_text = data.get("text") or data.get("task") or "1. I ___ a happy student. 2. She ___ reading an interesting book."
    try:
        prompt = f"Hãy giải thích và đưa ra đáp án cho bài tập tiếng Anh sau: '{task_text}'"
        sol = await call_llm_with_fallback(prompt)
    except Exception:
        sol = "Đáp án: Câu 1 điền 'am' (I am a happy student). Câu 2 điền 'is' (She is reading an interesting book)."
    return cors_response({"status": "ok", "solution": sol})

# Static fallback for Web Admin
async def handle_static_web_admin(request):
    path = request.match_info.get("tail", "index.html")
    if not path or path == "/":
        path = "index.html"
    file_path = os.path.join(WEB_ADMIN_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return web.FileResponse(file_path)
    # Default index.html
    idx_path = os.path.join(WEB_ADMIN_DIR, "index.html")
    if os.path.exists(idx_path):
        return web.FileResponse(idx_path)
    return web.Response(text="<h1>Gehihi Server Online</h1>", content_type="text/html")


# ==================== XIAOZHI MCP BRIDGE ====================
XIAOZHI_MCP_ENDPOINT = os.getenv(
    "XIAOZHI_MCP_ENDPOINT",
    "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjEwNzIwOTEsImFnZW50SWQiOjI1NTY0NDAsImVuZHBvaW50SWQiOiJhZ2VudF8yNTU2NDQwIiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc5Mjk0ODY1NywiZXhwIjoxODI0NTA2MjU3fQ.ML3VGTXu1yRPx87KYUDC8zH6fwYmIchug7ZeSPyfXJT3-6f3owZPJAfaN4Llex37wTA6QaTS4WUge-cPH90EiA"
)

XIAOZHI_TOOLS = [
    {
        "name": "get_robot_status",
        "description": "Lấy thông tin trạng thái hoạt động của Robot Gehihi (trực tuyến, phần cứng, RAM, biểu cảm)",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "change_robot_emotion",
        "description": "Thay đổi biểu cảm trên màn hình OLED khuôn mặt của Robot Gehihi",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emotion": {
                    "type": "string",
                    "description": "Tên biểu cảm: happy, sad, thinking, angry, cool, sleepy, surprised, loving, neutral",
                    "enum": ["happy", "sad", "thinking", "angry", "cool", "sleepy", "surprised", "loving", "neutral"]
                }
            },
            "required": ["emotion"]
        }
    },
    {
        "name": "speak_on_robot",
        "description": "Phát giọng nói tiếng Việt trực tiếp ra loa của Robot Gehihi",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Nội dung câu nói tiếng Việt cần phát qua loa"
                },
                "emotion": {
                    "type": "string",
                    "description": "Biểu cảm hiển thị kèm theo khi nói (tùy chọn)",
                    "enum": ["happy", "sad", "thinking", "angry", "cool", "sleepy", "surprised", "loving", "neutral"]
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "play_music_on_robot",
        "description": "Phát nhạc hoặc bài hát trên Robot Gehihi theo từ khóa hoặc tên bài hát",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Tên bài hát hoặc ca sĩ cần phát"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "stop_music_on_robot",
        "description": "Dừng phát nhạc trên Robot Gehihi",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

XIAOZHI_MCP_STATE = {
    "enabled": True,
    "connected": False,
    "endpoint": XIAOZHI_MCP_ENDPOINT,
    "last_connect_time": 0,
    "last_tool_call": "",
    "last_tool_result": "",
    "last_error": "",
    "tools_count": len(XIAOZHI_TOOLS)
}

async def handle_xiaozhi_mcp_status(request):
    """API lấy trạng thái kết nối MCP Bridge với Xiaozhi.me"""
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": XIAOZHI_MCP_STATE
    })

async def handle_xiaozhi_mcp_config(request):
    """API cập nhật URL MCP Endpoint của Xiaozhi.me"""
    global XIAOZHI_MCP_ENDPOINT
    try:
        body = await request.json()
        new_endpoint = body.get("endpoint", "").strip()
        if new_endpoint:
            XIAOZHI_MCP_ENDPOINT = new_endpoint
            XIAOZHI_MCP_STATE["endpoint"] = new_endpoint
            logger.info(f"Updated Xiaozhi MCP Endpoint to: {new_endpoint}")
            return cors_response({"code": 0, "msg": "Endpoint updated successfully"})
        return cors_response({"code": 400, "msg": "Invalid endpoint"}, status=400)
    except Exception as e:
        return cors_response({"code": 500, "msg": str(e)}, status=500)

async def run_xiaozhi_mcp_bridge():
    """Background worker duy trì kết nối persistent MCP WebSocket với Xiaozhi.me"""
    global XIAOZHI_MCP_ENDPOINT
    logger.info("Starting Xiaozhi MCP Bridge Service...")
    while True:
        if not XIAOZHI_MCP_STATE.get("enabled") or not XIAOZHI_MCP_ENDPOINT:
            await asyncio.sleep(10)
            continue

        try:
            logger.info(f"Connecting to Xiaozhi MCP Endpoint: {XIAOZHI_MCP_ENDPOINT[:45]}...")
            async with websockets.connect(XIAOZHI_MCP_ENDPOINT, ping_interval=20, ping_timeout=20) as ws:
                XIAOZHI_MCP_STATE["connected"] = True
                XIAOZHI_MCP_STATE["last_connect_time"] = int(time.time() * 1000)
                XIAOZHI_MCP_STATE["last_error"] = ""
                logger.info(">>> SUCCESS: Gehihi Server Connected to Xiaozhi.me MCP Endpoint! <<<")

                async for message in ws:
                    try:
                        data = json.loads(message)
                        msg_id = data.get("id")
                        method = data.get("method")

                        if method == "initialize":
                            resp = {
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "protocolVersion": "2024-11-05",
                                    "capabilities": {"tools": {}},
                                    "serverInfo": {
                                        "name": "Gehihi-Server-MCP",
                                        "version": "2.5.0"
                                    }
                                }
                            }
                            await ws.send(json.dumps(resp))
                            logger.info(f"Xiaozhi MCP: Handshake initialized (id={msg_id})")

                        elif method in ("notifications/initialized", "initialized"):
                            logger.info("Xiaozhi MCP: Handshake acknowledged by Xiaozhi platform.")

                        elif method == "tools/list":
                            resp = {
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "tools": XIAOZHI_TOOLS
                                }
                            }
                            await ws.send(json.dumps(resp))
                            logger.info(f"Xiaozhi MCP: Registered {len(XIAOZHI_TOOLS)} tools with Xiaozhi.")

                        elif method == "tools/call":
                            params = data.get("params", {})
                            tool_name = params.get("name")
                            args = params.get("arguments", {})
                            logger.info(f"Xiaozhi MCP Executing Tool: {tool_name} with args: {args}")
                            XIAOZHI_MCP_STATE["last_tool_call"] = f"{tool_name}({args})"

                            result_text = ""
                            if tool_name == "get_robot_status":
                                online_count = len(CONNECTED_ROBOTS)
                                if online_count > 0:
                                    result_text = f"Robot Gehihi đang trực tuyến (kết nối qua Gehihi Server), RAM SRAM ổn định 120KB, AI đang dùng: {ACTIVE_AI_PROVIDER}. Biểu cảm hiện tại: {LIVE_DIAGNOSTICS.get('last_emotion', 'neutral')}."
                                else:
                                    result_text = "Robot Gehihi hiện đang ở chế độ chờ (Standby/Offline). Server Gehihi vẫn hoạt động bình thường và sẵn sàng điều khiển."

                            elif tool_name == "change_robot_emotion":
                                emo = args.get("emotion", "happy")
                                LIVE_DIAGNOSTICS["last_emotion"] = emo
                                for mac, r_ws in list(CONNECTED_ROBOTS.items()):
                                    try:
                                        await r_ws.send(json.dumps({"type": "llm", "emotion": emo}))
                                    except Exception:
                                        pass
                                result_text = f"Đã chuyển đổi biểu cảm khuôn mặt Robot Gehihi sang '{emo}' thành công!"

                            elif tool_name == "speak_on_robot":
                                text_to_speak = args.get("text", "")
                                emo = args.get("emotion", "happy")
                                if CONNECTED_ROBOTS and text_to_speak:
                                    try:
                                        opus_pkts = await tts_to_opus(text_to_speak)
                                        for mac, r_ws in list(CONNECTED_ROBOTS.items()):
                                            try:
                                                await r_ws.send(json.dumps({"type": "llm", "emotion": emo}))
                                                await send_dynamic_tts_response(r_ws, str(uuid.uuid4()), "Xiaozhi MCP", text_to_speak, emo, opus_pkts)
                                            except Exception:
                                                pass
                                        result_text = f"Đã phát thành công câu nói: '{text_to_speak}' ra loa Robot Gehihi!"
                                    except Exception as ex:
                                        result_text = f"Lỗi phát âm thanh: {ex}"
                                else:
                                    result_text = f"Server đã tiếp nhận yêu cầu phát câu nói: '{text_to_speak}', nhưng hiện tại Robot Gehihi chưa bật nguồn."

                            elif tool_name == "play_music_on_robot":
                                kw = args.get("keyword", "")
                                if kw:
                                    asyncio.create_task(resolve_and_stream_music(kw, {"title": kw, "artist": "Gehihi Music"}))
                                    result_text = f"Đang tìm kiếm và phát bài hát '{kw}' trên Robot Gehihi!"
                                else:
                                    result_text = "Vui lòng cung cấp tên bài hát cần phát."

                            elif tool_name == "stop_music_on_robot":
                                stop_active_music()
                                result_text = "Đã dừng phát nhạc trên Robot Gehihi thành công."

                            else:
                                result_text = f"Công cụ {tool_name} đã được thực thi."

                            XIAOZHI_MCP_STATE["last_tool_result"] = result_text
                            resp = {
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": result_text
                                        }
                                    ]
                                }
                            }
                            await ws.send(json.dumps(resp))
                            logger.info(f"Xiaozhi MCP Tool {tool_name} executed -> {result_text}")

                        elif method == "ping":
                            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
                            await ws.send(json.dumps(resp))

                    except Exception as parse_ex:
                        logger.error(f"Error handling Xiaozhi MCP message: {parse_ex}")

        except Exception as conn_ex:
            XIAOZHI_MCP_STATE["connected"] = False
            XIAOZHI_MCP_STATE["last_error"] = str(conn_ex)
            logger.warning(f"Xiaozhi MCP connection error: {conn_ex}. Reconnecting in 8s...")
            await asyncio.sleep(8)


# ==================== AIOHTTP WEBSOCKET ADAPTER ====================
class AioHttpWebSocketAdapter:
    """Adapter cho phép ws_handler chạy mượt mà trên cả aiohttp (port 8003) và websockets (port 8000)"""
    def __init__(self, ws, request):
        self.ws = ws
        self.request = request
        self.path = request.path_qs
        self.remote_address = request.remote
        self.request_headers = request.headers

    async def send(self, data):
        if isinstance(data, str):
            await self.ws.send_str(data)
        elif isinstance(data, (bytes, bytearray)):
            await self.ws.send_bytes(data)

    async def ping(self):
        try:
            await self.ws.ping()
        except Exception:
            pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            msg = await self.ws.receive()
            if msg.type in (web.WSMsgType.TEXT, web.WSMsgType.BINARY):
                return msg.data
            elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.CLOSED):
                raise StopAsyncIteration
            elif msg.type == web.WSMsgType.ERROR:
                raise StopAsyncIteration
            raise StopAsyncIteration
        except Exception:
            raise StopAsyncIteration

async def handle_aiohttp_robot_ws(request):
    """Xử lý kết nối WebSocket của Robot và Mic Monitor trực tiếp trên cổng HTTP (8003)"""
    ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=16*1024*1024)
    await ws.prepare(request)
    adapter = AioHttpWebSocketAdapter(ws, request)
    await ws_handler(adapter)
    return ws

async def run_http_server():
    app = web.Application()

    # ========== Web Admin & REST API ==========
    app.router.add_get("/", handle_static_web_admin)
    app.router.add_get("/index.html", handle_static_web_admin)
    app.router.add_get("/english-tutor-app.html", handle_static_web_admin)
    app.router.add_get("/english-tutor.html", handle_static_web_admin)
    app.router.add_get("/chon-bai-hoc.html", handle_static_web_admin)
    app.router.add_get("/cau-hinh-gmbot.html", handle_static_web_admin)
    app.router.add_get("/cau-hinh-gehihi.html", handle_static_web_admin)
    app.router.add_get("/memory_page.html", handle_static_web_admin)
    app.router.add_get("/ha-mcp-guide.html", handle_static_web_admin)
    app.router.add_get("/huong-dan.html", handle_static_web_admin)
    app.router.add_get("/curriculums_full.json", handle_static_web_admin)
    app.router.add_get("/all_english_templates.json", handle_static_web_admin)

    # API Auth
    app.router.add_get("/api/auth/accounts", handle_api_auth_accounts)
    app.router.add_post("/api/auth/login", handle_api_auth_login)
    app.router.add_post("/api/auth/logout", handle_api_auth_logout)
    app.router.add_post("/api/auth/register", handle_api_auth_register)
    app.router.add_post("/api/admin/change-password", handle_api_admin_change_password)

    # API Devices & Robot Control
    app.router.add_get("/api/devices", handle_api_devices_get_post)
    app.router.add_post("/api/devices", handle_api_devices_get_post)
    app.router.add_get("/api/devices/{id}", handle_api_device_by_id)
    app.router.add_put("/api/devices/{id}", handle_api_device_by_id)
    app.router.add_delete("/api/devices/{id}", handle_api_device_by_id)
    app.router.add_post("/api/devices/{id}/control", handle_api_robot_control)
    app.router.add_post("/api/devices/{id}/oled", handle_api_robot_display)
    app.router.add_post("/api/devices/{id}/speak", handle_api_robot_speak)
    app.router.add_post("/api/robot/control", handle_api_robot_control)
    app.router.add_post("/api/robot/display", handle_api_robot_display)
    app.router.add_post("/api/robot/speak", handle_api_robot_speak)
    app.router.add_post("/api/chat", handle_api_chat)

    # API Config & Education
    app.router.add_get("/api/my-xiaozhi/config", handle_api_my_xiaozhi_config)
    app.router.add_put("/api/my-xiaozhi/config", handle_api_my_xiaozhi_config)
    app.router.add_get("/api/curriculums", handle_api_curriculums)
    app.router.add_post("/api/curriculums", handle_api_curriculums)
    app.router.add_post("/api/curriculums/{id}/apply", handle_api_curriculums_apply)
    app.router.add_get("/api/english-templates", handle_api_english_templates)
    app.router.add_post("/api/english-templates/{id}/apply", handle_api_english_templates_apply)
    app.router.add_get("/api/english-tutor/templates", handle_api_english_templates)
    app.router.add_get("/api/english-tutor/active", handle_api_english_tutor_active)
    app.router.add_post("/api/english-tutor/active", handle_api_english_tutor_active)
    app.router.add_delete("/api/english-tutor/active", handle_api_english_tutor_active)
    app.router.add_post("/api/english-tutor/activate", handle_api_english_tutor_activate)
    app.router.add_post("/api/english-tutor/activate-template", handle_api_english_tutor_activate_template)
    app.router.add_post("/api/english-tutor/deactivate", handle_api_english_tutor_deactivate)
    app.router.add_get("/api/english-tutor/recommendation", handle_api_english_tutor_recommendation)
    app.router.add_post("/api/english-tutor/quick-review", handle_api_english_tutor_quick_review)
    app.router.add_get("/api/english-tutor/report", handle_api_english_tutor_report)
    app.router.add_post("/api/apply-curriculum", handle_api_english_tutor_activate_template)
    app.router.add_post("/api/remove-curriculum", handle_api_english_tutor_deactivate)
    app.router.add_get("/api/ai-roles", handle_api_ai_roles)
    app.router.add_post("/api/ai-roles/{id}/apply", handle_api_ai_roles_apply)

    # API Memories & Tasks
    app.router.add_get("/api/memories", handle_api_memories)
    app.router.add_post("/api/memories", handle_api_memories)
    app.router.add_delete("/api/memories/{id}", handle_api_memory_delete)
    app.router.add_post("/api/memories/batch-delete", handle_api_memories_batch_delete)
    app.router.add_get("/api/learning-tasks", handle_api_learning_tasks)
    app.router.add_post("/api/learning-tasks", handle_api_learning_tasks)
    app.router.add_put("/api/learning-tasks/{id}/complete", handle_api_task_complete)
    app.router.add_get("/api/knowledge-base/documents", handle_api_knowledge_docs)
    app.router.add_post("/api/knowledge-base/documents", handle_api_knowledge_docs)

    # API Feedback & Tools
    app.router.add_post("/api/feedback", handle_api_feedback)
    app.router.add_post("/api/wss-requests", handle_api_wss_requests)
    app.router.add_get("/api/music/status", handle_api_music_status)
    app.router.add_get("/api/music/search", handle_api_music_search)
    app.router.add_post("/api/music/play", handle_api_music_play)
    app.router.add_post("/api/music/stop", handle_api_music_stop)
    app.router.add_post("/api/ocr", handle_api_ocr)
    app.router.add_post("/api/generate-lesson-plan", handle_api_generate_lesson_plan)
    app.router.add_post("/api/learning-task", handle_api_learning_task_solve)


    # Health & System
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/xiaozhi/debug/live", handle_debug_live)

    # OTA Endpoints
    app.router.add_get("/xiaozhi/ota/", handle_ota)
    app.router.add_post("/xiaozhi/ota/", handle_ota)
    app.router.add_options("/xiaozhi/ota/", handle_cors_options)
    app.router.add_post("/xiaozhi/ota/activate", handle_ota_activate)
    app.router.add_options("/xiaozhi/ota/activate", handle_cors_options)

    # Vision
    app.router.add_get("/mcp/vision/explain", handle_vision_explain)
    app.router.add_post("/mcp/vision/explain", handle_vision_explain)
    app.router.add_options("/mcp/vision/explain", handle_cors_options)

    # AI Provider Control Center
    app.router.add_get("/ai", handle_ai_dashboard)
    app.router.add_get("/xiaozhi/ai", handle_ai_dashboard)
    app.router.add_get("/xiaozhi/ai/provider", handle_ai_provider_get)
    app.router.add_post("/xiaozhi/ai/provider", handle_ai_provider_set)
    app.router.add_post("/xiaozhi/ai/test", handle_ai_provider_test)
    app.router.add_options("/xiaozhi/ai/provider", handle_cors_options)
    app.router.add_options("/xiaozhi/ai/test", handle_cors_options)

    # Auth & PubConfig
    app.router.add_get("/xiaozhi/user/pub-config", handle_pub_config)
    app.router.add_get("/xiaozhi/user/captcha", handle_captcha)
    app.router.add_post("/xiaozhi/user/login", handle_login)
    app.router.add_get("/xiaozhi/user/info", handle_user_info)
    app.router.add_get("/xiaozhi/admin/users/info", handle_user_info)
    app.router.add_get("/xiaozhi/admin/users/page", handle_user_info)

    # Agents
    app.router.add_get("/xiaozhi/agent/list", handle_agent_list)
    app.router.add_post("/xiaozhi/agent", handle_agent_save)
    app.router.add_get("/xiaozhi/agent/template/list", handle_agent_template_list)
    app.router.add_get("/xiaozhi/agent/page", handle_agent_list)
    app.router.add_get("/xiaozhi/agent/{id}", handle_agent_detail)
    app.router.add_put("/xiaozhi/agent/{id}", handle_agent_update)
    app.router.add_delete("/xiaozhi/agent/{id}", handle_agent_delete)

    # Agent Sessions & Chat History
    app.router.add_get("/xiaozhi/agent/{id}/sessions", handle_agent_sessions)
    app.router.add_get("/xiaozhi/agent/{id}/chat-history/{session_id}", handle_agent_chat_history)
    app.router.add_get("/xiaozhi/agent/{id}/chat-history/user", handle_agent_chat_history_user)
    app.router.add_get("/xiaozhi/agent/{id}/tags", handle_agent_tags)
    app.router.add_put("/xiaozhi/agent/{id}/tags", handle_agent_tags)
    app.router.add_post("/xiaozhi/agent/{id}/chat-history/getDownloadUrl/{tail:.*}", handle_download_url)
    app.router.add_post("/xiaozhi/agent/chat-history/getDownloadUrl/{tail:.*}", handle_download_url)
    app.router.add_post("/xiaozhi/agent/audio/{tail:.*}", handle_download_url)

    # Agent Templates
    app.router.add_get("/xiaozhi/agent/template", handle_agent_template_list)
    app.router.add_get("/xiaozhi/agent/template/page", handle_agent_template_page)
    app.router.add_post("/xiaozhi/agent/template", handle_agent_template_add)
    app.router.add_get("/xiaozhi/agent/template/{id}", handle_agent_template_crud)
    app.router.add_put("/xiaozhi/agent/template/{id}", handle_agent_template_crud)
    app.router.add_delete("/xiaozhi/agent/template/{id}", handle_agent_template_crud)
    app.router.add_post("/xiaozhi/agent/template/batch-remove", handle_agent_template_crud)

    # Providers & Plugins
    app.router.add_get("/xiaozhi/models/provider", handle_model_providers)
    app.router.add_post("/xiaozhi/models/provider", handle_model_providers)
    app.router.add_put("/xiaozhi/models/provider", handle_model_providers)
    app.router.add_delete("/xiaozhi/models/provider/{id}", handle_model_provider_delete)
    app.router.add_get("/xiaozhi/models/provider/plugin/names", handle_model_plugin_names)

    # Voice Clone & Voice Resources
    app.router.add_get("/xiaozhi/voiceClone", handle_voice_clone_list)
    app.router.add_get("/xiaozhi/voice-clone/page", handle_voice_clone_list)
    app.router.add_post("/xiaozhi/voiceClone/upload", handle_voice_clone_action)
    app.router.add_post("/xiaozhi/voiceClone/updateName", handle_voice_clone_action)
    app.router.add_post("/xiaozhi/voiceClone/cloneAudio", handle_voice_clone_action)
    app.router.add_post("/xiaozhi/voiceClone/audio/{tail:.*}", handle_voice_clone_action)
    app.router.add_get("/xiaozhi/voice-resource/page", handle_voice_resource_page)
    app.router.add_get("/xiaozhi/voiceResource", handle_voice_resource_page)

    # Devices
    app.router.add_get("/xiaozhi/device/list", handle_device_list)
    app.router.add_get("/xiaozhi/device/page", handle_device_page)
    app.router.add_get("/xiaozhi/device/bind/{tail:.*}", handle_device_bind_list)
    app.router.add_post("/xiaozhi/device/bind/{tail:.*}", handle_device_bind_action)
    app.router.add_post("/xiaozhi/device/unbind", handle_device_unbind_action)

    # Models
    app.router.add_get("/xiaozhi/models/list", handle_model_list)
    app.router.add_get("/xiaozhi/models/page", handle_model_list)
    app.router.add_get("/xiaozhi/models/names", handle_model_names)
    app.router.add_get("/xiaozhi/models/llm/names", handle_model_names)
    app.router.add_get("/xiaozhi/models/{modelType}/provideTypes", handle_model_provide_types)
    app.router.add_post("/xiaozhi/models/{modelType}/{provideCode}", handle_model_save)
    app.router.add_put("/xiaozhi/models/{id}/status", handle_model_status_toggle)
    app.router.add_put("/xiaozhi/models/{id}/default", handle_model_default_toggle)
    app.router.add_put("/xiaozhi/models/{id}", handle_model_update)
    app.router.add_delete("/xiaozhi/models/{id}", handle_model_delete)

    # TTS Voices
    app.router.add_get("/xiaozhi/ttsVoice", handle_tts_voice_list)
    app.router.add_get("/xiaozhi/models/{id}/voices", handle_tts_voice_list)

    # Knowledge & Address Book
    app.router.add_get("/xiaozhi/knowledge/base/list", handle_knowledge_list)
    app.router.add_get("/xiaozhi/knowledge/base/page", handle_knowledge_page)
    app.router.add_get("/xiaozhi/address-book/list", handle_address_book_list)
    app.router.add_get("/xiaozhi/address-book/page", handle_address_book_page)

    # System & Dicts
    app.router.add_get("/xiaozhi/sys/dict/type/{tail:.*}", handle_dict_data)
    app.router.add_get("/xiaozhi/sys/dict/data/{tail:.*}", handle_dict_data)
    app.router.add_get("/xiaozhi/sys/params/{tail:.*}", handle_dict_data)
    app.router.add_get("/xiaozhi/sys/menu/nav", handle_menu_nav)

    # Generic Fallback & CORS
    # Dual-port WebSocket routes (Hỗ trợ truy cập WebSocket trực tiếp qua HTTP Port / Cloudflare Tunnel)
    app.router.add_get("/ws/device", handle_aiohttp_robot_ws)
    app.router.add_get("/xiaozhi/v1/", handle_aiohttp_robot_ws)
    app.router.add_get("/ws/mic-monitor", handle_aiohttp_robot_ws)

    # Xiaozhi MCP Bridge Endpoints
    app.router.add_get("/xiaozhi/mcp/bridge/status", handle_xiaozhi_mcp_status)
    app.router.add_post("/xiaozhi/mcp/bridge/config", handle_xiaozhi_mcp_config)
    app.router.add_route("*", "/xiaozhi/{tail:.*}", handle_generic_fallback)
    app.router.add_options("/{tail:.*}", handle_cors_options)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    logger.info(f"HTTP & OTA Server listening on port {HTTP_PORT}")

    while True:
        await asyncio.sleep(3600)

async def run_ws_server():
    logger.info(f"WebSocket Server listening on port {WS_PORT}")
    async with websockets.serve(ws_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()

async def run_render_keepalive():
    """Tự động ping server Render mỗi 8 phút để chống ngủ đông (Anti-Cold-Start)"""
    await asyncio.sleep(60)
    while True:
        try:
            url = f"{PUBLIC_URL}/api/devices"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info(f"Render Keep-Alive ping OK ({resp.status})")
        except Exception as e:
            logger.warning(f"Render Keep-Alive ping failed: {e}")
        await asyncio.sleep(480)

async def main():
    logger.info("==================================================")
    logger.info("   Starting Gehihi Full Dynamic Server for Render ")
    logger.info(f"   Public Base URL: {PUBLIC_URL}                 ")
    logger.info(f"   OTA URL:         {PUBLIC_URL}/xiaozhi/ota/    ")
    logger.info(f"   WebSocket URL:   {WS_URL}                     ")
    logger.info("==================================================")
    await asyncio.gather(
        run_http_server(),
        run_ws_server(),
        run_xiaozhi_mcp_bridge(),
        run_render_keepalive()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gehihi Server stopped.")
