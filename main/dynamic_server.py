"""
Gehihi Dynamic Server (Comprehensive Full-Featured Backend)
- Cung cấp OTA API cho Robot Xiaozhi (https://gehihi.onrender.com/xiaozhi/ota/)
- Cung cấp WebSocket AI Server tương tác thời gian thực hai chiều cho Robot Xiaozhi
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
import logging
import base64
from aiohttp import web
import websockets

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

# ==================== IN-MEMORY DATABASE ====================

DB_DEVICES = {
    "14:c1:9f:c4:ee:d0": {
        "id": "DEV_001",
        "macAddress": "14:C1:9F:C4:EE:D0",
        "name": "Robot Xiaozhi AI ESP32-S3 (Mạch tím)",
        "boardType": "ESP32-S3-N16R8",
        "version": "2.5.0",
        "status": 1,
        "online": False,
        "lastActiveTime": int(time.time() * 1000)
    }
}

DB_AGENTS = [
    {
        "id": "AGT_001",
        "agentName": "Robot AI Xiaozhi (Tiếng Việt)",
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
        "systemPrompt": "Bạn là robot Xiaozhi thông minh, hỗ trợ người dùng bằng tiếng Việt thân thiện, tự nhiên và tận tâm.",
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
        "id": "MOD_LLM_01",
        "modelName": "Google Gemini 1.5 Flash",
        "modelType": "llm",
        "modelCode": "gemini-1.5-flash",
        "provider": "Google Gemini",
        "isEnabled": 1,
        "isDefault": 1,
        "sort": 1,
        "configJson": {
            "type": "Google Gemini",
            "model": "gemini-1.5-flash",
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
        "sort": 2,
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
        "sort": 3,
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
        "name": "Kiến thức Robot Xiaozhi Tiếng Việt",
        "description": "Tập hợp tài liệu và thông tin hướng dẫn sử dụng robot Xiaozhi",
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
            "content": "Xin chào Xiaozhi!",
            "createdAt": int((time.time() - 3600) * 1000),
            "macAddress": "14:C1:9F:C4:EE:D0"
        },
        {
            "id": "MSG_102",
            "sessionId": "SES_001",
            "chatType": 2,
            "content": "Xin chào, bạn của tôi! Tôi là Xiaozhi tiếng Việt, rất vui được trò chuyện cùng bạn!",
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
        "systemPrompt": "Bạn là robot Xiaozhi thông minh, hỗ trợ người dùng bằng tiếng Việt thân thiện và tận tâm.",
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

async def handle_ota(request):
    """Xử lý yêu cầu OTA từ robot Xiaozhi"""
    device_id = request.headers.get("Device-Id", "14:c1:9f:c4:ee:d0").lower()
    client_id = request.headers.get("Client-Id", "")
    accept_lang = request.headers.get("Accept-Language", "vi-VN")

    # Đăng ký hoặc cập nhật thiết bị
    if device_id not in DB_DEVICES:
        DB_DEVICES[device_id] = {
            "id": f"DEV_{device_id[-4:].upper()}",
            "macAddress": device_id.upper(),
            "name": f"Robot Xiaozhi ({device_id[-4:].upper()})",
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
            "token": f"gehihi-token-{uuid.uuid4().hex[:12]}"
        }
    })

async def handle_ota_activate(request):
    return web.Response(text="success", status=200, headers={'Access-Control-Allow-Origin': '*'})

async def handle_vision_explain(request):
    return cors_response({
        "code": 0,
        "msg": "success",
        "data": {
            "description": "Hình ảnh nhận diện từ camera Robot Xiaozhi",
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
        "agentName": body.get("agentName", "Robot Xiaozhi Mới"),
        "ttsModelName": "EdgeTTS Tiếng Việt",
        "ttsVoiceName": "vi-VN-HoaiMyNeural",
        "llmModelName": "Google Gemini 1.5 Flash",
        "systemPrompt": body.get("systemPrompt", "Bạn là trợ lý ảo Xiaozhi tiếng Việt."),
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

# ==================== VIETNAMESE OPUS AUDIO DATA ====================
OPUS_WELCOME_DATA = ["a4MnI4Bj5hdTah1Nm89rV1O5ssQrP5umOQ0AoNIs2LUM2KsKRYeTNoeLaI+YlY3ip2K54rL8oRx7PJ84MBKAfRNc36TIUZTv6hefV1K0gz0SWK53wusrqlo/omUwPmWtjFygeNugaw45gn9Q/Sxykwj5yXCF", "a4MhIbfTOHzFcAqhu4GzV9E7CCXndHtl2tjWzvVtIzaewxnS0Le4DwkBDw1fEy0VrXTJZzBwCpHE+DAtOcWgtoRnok8K17MoH9BKy+Q0AeMQ1h3AX6f7odnX0CCOnnT2loJLF87qCqp+", "a4MnI7IhW1LCiFNTfRKvIcurBoZ+06x1GKgz6ASptFwlLVBPo8E99FL2s65WCns8CYC8Fy2LjHcqfyT+1ZYskutS354zP0us2A2M2bfwsrH6bFN5Kk8fAEeslBbiQNxwcEuqfCrni5kRi0QWfENZ6gFJrw==", "a4MmIbgauHfiEbsOiortt/l5L2Hz71dSr4NfttfRL+mmEHLOJ9lCS7MvlurKR8xjywkjmLtWdl1XU2Rjsiimkxxn9iR4KByjXWsilqPTKYh5n3lfdV+Q2gzpGDoeE6Zn2+Dph9BKDgECmsrsy32I", "a4MlIrv6A3XhGqDzFqE1ycIu8cqCEVtpvuBE4eW5fchU4WzLMYEtgXS7/LZUxnVGfiFvtQEBRdkVY1v4HyQI+5mD87nXYxDv6s6zvAwV6gGjWJREPen3dHS142Mv0t2vWoNMZePyfjNKABO9lUU+zpNi", "a4MkJbyhHtiSVEl+gukENqZtHPy4g8unaeRqm0YY4cyNSRyWytjTeLydQAv644CZpbrpQ9FNUjHeFWxfftbVra6tWB/7E9qbe9XNnuC8Tz1+h5iPo5OXKAq3HN/0UyW0PoXmoSmVd3KB8Mmlog==", "a4MnJbsjJbzLXRGmPvTuH/eOoF4jqDLy9Y5igfTA+QqwSh9pPIj8CLDb47lUqIn9I+HUGrZtBwOqUjhpYJimXAl1YrWUnhzDDoFSr2zv66q4j4Tr8cRq95YIziM4gMpiUl6Io+0m3+uVIr1Y9OzjV1wYYHk=", "a4MlJbbX+eUaRwNejLVm1rxwTV3OFiKR+k6fexZ1wUG5WTp3N8DXLUi2mIxaalUSa9FUKK7WKA99i/BF6QeKaVA6391dQWd4LTR2ECditdIwm5TSSkJZUGNVSBVISBpyUd6hYlplSwecaXIYkg==", "a4MnIq35v+b1HJORkzT+QFmEViYhl8VXaz87QjRRBThq9BKIssLW590s/Kr5ew1G9177jO7N/wlV+uh6dghySZS/DMK+xvd13vSB0jOxAGjCPTZUmOkSqZl1vZynYoFLU0du1igBujQIHiIuHgItZ8qi", "a4MjH7xet1Ub89pnmQ5OFzdAMX7R9TT7qAoGWeQHV0OV7mgAmnSGvMKv1k/qgNcJ5keFtQ6JUi8K8kaNe694ASga+7R3ibv8C6EX6LOdKnuqzccyu4Fqn4DuZ7XlO0rMQ1cFT34H7IO+2w==", "a4MkJL/koHQJxNzuEsYWBQeKjZSDYvMZil6UFAzCb6JEmlCzslDsE7gMDwETO200X7fFkKP9bYEVlIRyq1jrfbYIZkWz7y1QWwRAwYQOckwsIFt3O4dB8MSvcDSKffLrQU0eX3dXpFoYr13YVA==", "a4MgIoOIX+gL8V3xIUs4ZuIj0fm0k5AB/pbpVAsfZT/rzEaXBimjuLnwPgtqm9gnCf9X/+iyaI2Dd77HykCLc/1UaigltTvlnti/47gSfg3+osup294CN5mcCU6JLDdsyajSbtFnBgQWwA==", "a4MjJAWzqqxoO3pYPoH85+k21836ENNtOhqaFaJZ7Yg6uL0aUSnPgrLerY3mQOGyrW+2WSqmWRY/oxrbrbcDgmvu0KANhoTxaZlJq+36Fph2xPOqYlaDDWTCPWSDFWdnsEGwOrM3uc4f+3xA04lC", "a4MiIbJN5As1KP40uSMmuTQW5Pq3w7NrosrvTc+VqlCCzgT2yoGzj2QkpD9oD3NlX/zQrmCoLApISgoTv0+mBJN2Mxp+b6evqsCm/NossJJA3CJhZw8sn2+ik31XOswfCFS/yow5mWXIxZs=", "a4MnIqXuzNIYCnTWPl3zNMjkYllB6OqXomh8evSdu7WyPKjsqIeGgM0JjTcH+wY8xQfVMrsX7vmUHc6HPoirTuXojRcKxVG/FU4hww4zULY/JMnFRhvqVeAm4dMyN9AuS+w6hBPrknRky8La0I0=", "a4MnIoP5PtTWf8dUhWtitizeDtc2jyCJqi3HJxEb1gfg81Qgw4UHUVw+fLwm60K/j7ubLd38siH/e9X+YXGvMjEQ0PBSXNm471P1SLG7cQdO1s15JmCHOIYcU7t01k/LauS0B8FRTQHFUJc9WFsB", "a4MjIru0k13eqlgdAhFJHwYYZ0ocOMUANGyyFRv8KsAnMUqBC+OGvCYdsMIzkz1/Jue3wZv1Nma9v/QQip+NmGNayWhHROfx9rwYwTBxIP589713Z8HRdJTKW4EylW7cegEpYxkkHshj7Q==", "a4MmJLv46Hx/f5e+Wt5xzSqPGHlViuGxlk6tXu850Co1NbCO/zTpDa6ru/hzcyCUOJbsq28WdUJvNIdfUEJJf20/lPgzTuyRbzlo1qaPu/zv53GfGqieT7btG5De6IDzMEovrvbgbf2iljZh", "a4MlJ7v5LAkytedPporkoJiA/R4D8PQDUJeSLRZ4+jkoxIqbSg0arGC7+KO5nJCldjTpORM7zj/ZGOGrWElYetxksBRGmz0+UCP8IDIP09m785/anIG8u0TKLMMSVpbnJxACTIbPp+k+6i1hkptaqVPIlBNf", "a4MkI7hjvi4Tj2QMHXeGltcl44vuhw3rqoosqYsyyqPz1SIudgzeFbemzRaxWLdO3LSYcWMNwLAozvkskYqMJXwDwHBY36ZnGivAtdJcCh2MKTCqFl24vRbFYlV0W7zz8mQG/R82eQLQ5qsCAsYEGQ==", "a4MnJaxi5bIiZztWopL/ihfxPHF40SOauJIx5ChV+HZqNwJIfJYdxg0yI6dGcKZFJVMGgh4G4DA1chG/EOSoCjV4Uf2MkME1vYzb/Cc0f3s8AXJiAU24YKnFJiZamvO+GrCoQFiF6lJQFDmLnCgj", "a4MjHjfUcMd7cCmj0d5x6lojlQo0RW6pLhXSaYDic8cNp8dfR66FBWyTiep1qh1d1zYnIRYAojQOP7JJu3OZkwJR2q6yLnsAAuooRrdfsVfD8ecqAQ==", "a4MWEAoz+BKii3TM1ESYBQEKVwFM9KQVM4EIoPVrxO1xTcfNDGe+8eCVCLsTueSC8bxeCUWgYBsauyzB", "a4MVFQi2pMUoy3QNjV1cu55CiBaMGGHGAwiflsiDV7K7ZftmffX3sMJ4QR5gPQfQpMVS7d7tMEXxUqRiDSj/oM5jvYM+", "a4MXGgfQpMU+OGguKXujULY4iOlUFnq2qhc4B9CkxSSmfZqE2v9prmRZrNxZmZ1xBoUUFeQH0KTFJeOzunyPPRXOIt9KIupUi3l9aqMV4A==", "a4MSDwfVGdlfLYJu0AIrMhO9xhs8PAfJedE5EDYjPTvXf/WswAfJecjJV8CiEiOA1Dg8", "awMHyXnIyVfAohIjivQ6PAfJecjJV8CiEiOK9Do4B8l5yMlXwKISI5UUOjw="]
OPUS_ACTIVATION_DATA = ["a4MiHxN7ftOHVwlnPoRI9kK9k9WH2zLzqXiZzGXocxsQJwi61QYcQBGeDmTSYBR59dGLDYkkLGZaaDhEIB0izCCXFSXdHuBaTZr18b6dupCGAylZZMG22wmdsyqMCzha", "a4MkIh7eVLcQ8dGLFTvqQPlrjPEMGnTnfi6R4JTFP20lm9tq2KcR9R7eVZqP+/746mdVMQvBn50KrzdRQnW+ZtgF29Q58hTZUwsfTtPbtF5DEtD3kKtRW+KSLTI4ZajbClexmn/AJA==", "a4MiIiI7cwvVEA+UCBdTLF1a5a0kTInyeooiuzxrsgO05fdMKpeIGAS03pkHmj+NMlcIxb7n/LRYxmr0qalM7HvzdNy+sOAijCtI2rtS8K/+WoIpoldzKO3VUen4E1wSZ/7oa97jGw==", "a4MmJIM9EczsSNsfAP+eM2bMbolKXvZPZLOHCoIflFvLkc2/4lC4PQXas+CNAjLJh+Ar1ExK5hlOzucNhfTKMOvxuyGFj2m+UNDmAlS6tAahnKK0Tqu5KtlYALxAlDel9cYnrkMYms2C3PNbA4T8O6hdKnU=", "a4MjIrX+V7vGDA69Zg0cic0lI4V5JztFeuPDgUHXEXbFk6b+8OBntwsWhhxp1/gnpmdE4mouFC3WAcs8cBpbdW5ewzeRqMj7/LpzAJU0P3OCbNGnQiFl/lCB2xXhIM/kkKOggRoTmBJhdM4GSQm2", "a4MfJ7wyhai1O5wogDDz2vQUVxdTjXPKrmlUGgtVfRoW99e789Q9HJ8xaOKf6SJzv4VWreHscULwDiC9jW6a5R6bl573splQL966V7z2J5yIKcDMfLBf70HUEbKK/udIHWW+c/zwvDqyTDcR8QAs8XQ=", "a4MgJLtfz1dpsHByJboHHmdTV+o0gyZV8vWC1JDuwg4G/bw6unEkOlYfK7yzBIBMeP5c8eJr8NKOl9Alesih+Gndz0Xtc+g3uXHlFB/fba+yPKvGcQZ6vo2uUrk7xuYqLpRZsQzKWKbS1A==", "a4MkIrhqLeNCytL+33E+iugsY8I2f2BwAWKpb3WMT7qSxFZ4qDDouLfb+0PDki2YxegU+Xulo+1SuMEdet4mMtQtAlhiU6QcbkC8X3TllpSwDnAN/A5+kKHNxhl1/uedtdh9g/A8VeVpzYfAqi5wk70=", "a4MnIbzORouLiEwhGwpWR+4DwtPLwNj8anre7fl2jGMAyIWFv1oDwbQ7vrzEyEqSI44/UgGVWNLwuHfLACLVfdbFlln/d9ohuLqEBrxQrOJftAEdszfM4OF3lO1D3sDMOBL1P/WMV1pILfQUzfqOLIA=", "a4MlH7xPPV2AQ0YYf10Ai0MKcI4qYU3EIz1kz2mYMBNlY2Hs3aWYUj+8oa5zG6s38yVEBr2xPA0BMUgTcWsQBcKNhZCH/PGSu+sI/hEbF5YUhYdsozrx2Kn5emQmtOv2f/iLCf3acPkIeWl7koI=", "a4MkJrbtMT07xhgSSp7pf8cruVHU4KC+ocEXAcRL0GR9lgTuWGa4k7YF76JgRxxDf3K6XOwK8udjWw3bIvPt39Ce7ZbQJmKxGCgzC0GatdTFCuS041NDZeqlbOHRIixqaLuyp34WuQua+GH/DR6W7KONQQ==", "a4MmJrF8tv0FyzA3zh/LRUDsjty2drtG8/crAceiNE7B+yVCEOJakemTrp39v3mdisTRhdG8w6qEtAQga2l5uhrhDLgqog/dFtfKtcQA896uU749Q7IykAzWCaSWUNUh2MFLN58YofOxUZXiAXj41ITwDb16b4k=", "a4MjJ6yiJiFcTqjqVDWtwYTiAwO0CHg2rhfwIPKaySHNB7cjArGKqPbTQTJG70FZarf8s/oSScYXIHlw/UfdEP9Few6ymuZwwBJl9jwNo2zNACDzmlkqGWkPQ5K5YIebIL1ApGDxo8koT6A191bchg==", "a4MiIL3rlAt265XynVcVxuIilkFhRKxAgNoCWUxMx0SCEZ3EXJa965QIeq3YsIBauiPiQ9/OWCJ8pycgqDPc2P7d8rU/zJ7uriMPoJqbiNYCBrSvTYl5DHJEEiBqNBJIuaZdJcodlwdmQj2Ihw==", "a4MjJqRQR/LDEQ4Kr3rcmR7EVVgxqMFe61127l8XBg+RhxTztOl4vLNc8zIaRnXSEJLUuO8aCPeY/Bx0bcu8A01T5/MUy4eHtsJSX6u9Ny0EXkT/WQaxYrvhXNCYu0AKyPeRgyWKh6AcKnbc+anbSsv8Xg==", "a4MlI71JZtfu+QYBxUdZsFcLj646g6EVif3PNZcjrWN90pX/V0VlDhC8aBcPT0SsOdXoQPebSUtA4moh6vljN8C+5YyNzpvPpYY8NrolxySldkIUSrjolV6a5IlbCbK7QZTRBFeIItYx4BfIw76BpA==", "a4MnI7eb8s1JK5MdVh+sUTOXFXBjuMCJlDOQCwIH/XMKhvTIRrSoW+5057XxiwEZAzmCUx6spCiomDG1byUU5cMQgPi3B33F83N4le8DtufyQTYB6ym+Nj00GSnnFlYMmbPHVTtUwOQigRQEdh7K", "a4MhJbeC0ckqXK3jhqjGuHmjI3/iou2DNxhI6YHyIm8YLKCiG7W2FU2z0Iss71TdX3s3E6WaCm/pusGQ/eIGb2I6khjmNzypGPyztftIwePUHMLRA7Y8keHV5I7txq+nEIpcVYnXHRERBfS8NRUcjQ==", "a4MmI7N10Vrt14dWSRH2C8iBn0ojCuhxwW0k7OOvpgrVd9Ei+iUCslVLtUQYFrR8sKcCHQD6FYpzJAQCUFE9MUS7IayoJFsfNQfCaYq56iDFBbqCN8lAn5F7B0cpnr5q23XnQIDoCExv5yg+7onA", "a4MnI7x/VQukcG6quJR0uiwvjAtPrG6Ql9wvDbEz+dkBk9wHSn3+lRg7abz1TysKlT2ZZqvz/ccLt3Hz9tDcCDl+HNs/wvAGmMYgwsn7vOZyOd2FgEXF8Uj5JWX+iIgxVsNki1ppTY+Q0MzWGJkART+H", "a4MlJbd/TOMU0FmQI5bskRF4BLROEa96yUUBiY+xd4iE85urKymE2vq0tmcUdGXwet9qhaFdvBt+Ib25e9O7tW9DQBXHyieAMn/l5WQwrEHunFXlBzQ7a2yyfP8Srm4GA8PesQvqwgxhfTx1kY50F7+JlUlh", "a4MfJAYpphCl2csekdbXAGe1OZaB60dYBdkwkyp0gw+A3QE8JYSzWQffPwVBKquyddIfhKIr+VSYskwKheYUZhzbJ+szH/WPMPuUo5xIGxkGkoupbbF8XODDMXETSM6betN2oV4N9YSRgiM5sw==", "a4MjJYMPRFStQe97IHzNPp6yfH7XyDaFUcnVY5KwuXwd2jmA6qQ6g5kvlMt0pOdb/6UiXlcw9mOL6/a9kU7XfKRtnKDF0ilAZQ/6abYns5CmTtSugR6syiPuTKY/BafbdaQRMpKhHHVdlQ9ltjdNNlsMtA==", "a4MnH7tj+x/Ji6wFHi9Uk2M/Q+77znIDmZq/M0zLUuC2GPk9VD7MrhgXurvqF0tBC3Z8Slz/ggcAta5QG71ICFF4BYLFl5Cyh4u2nKUOPsstBU6CeINs2k63U6gJLrenUW+cMgkbPJzgdfWGUg==", "a4MkJbbJ4ykiIZoEu5C9k/j+U4picaGtEc3RZtW9zFadsrMBC5V9LbOU3zMvkbWHm12C6wJFffB5mdTbd3xy1I8ZJmDCMC1PMoKR3mmx6FTutRGmfSiSY90PF7XpgTzRzKZusOz+sF2ut6aWEZ6B1kNzi7w=", "a4MjJ7OapJhQgVr7vfX2IXzfIHa5zAn9vnkONj4H7UZgas4m9Cp2sa6osEMMQYKZESKzHIq7zS7n4hw5V6HIK6XoOWB36RNaSflNPMpip0b4vmR66hmQsndzWu/YX8hKOZu9sS1rg7WJ72rgHLspK/TsRnWa", "a4MjIqSojSmNkrTBCNKKTGNdfxdZQVlbZksAVPLOV23NOVTl4Bh8o/DhQKEl4WQqCGhqj+Oj7oiAajkZ1VXP4mmWTFDGGyBAEachxNTJ/WUu36ChQOiMEZVLMeZTPltBy4SQYZEvsmCP5ZmQDe+ydg==", "a4MnIqgk/xe5rZCj77KDXuBMqtZlSSWm7uFnE6kdQOXhUrfPqSWAALhaGLyKD14V9/9vwpwHCgm3geUuaje3J86HlfxL5LLuofh1caG8w9eVQPjS7ee9l/zpGKiVpgzq0/xKNnsErqoW0lnOKQ==", "a4MnILxAXoq/06qRTz3Eqxgr/ZIm0+g/PpGPiimRpA2hlhTiSRswQTTpxbxb+5rM/ItPBLIgD3bJUmbg9qm7K1WO2F67mA5uZZVYvGe+8R2QssKC/XrfcfVZSRwu8lD3iBrMvdZuc0BfhOaR", "a4MhI7iPhLrbhhOJg3KxUDx3iZvtGS2cuLEiRjy/bQwAhrJRSbdxbgFuTEcw2Kbb2XdaPLasqvZOaFSkrSbVqYbIFTECFdOMsyot+Er2n7bpdYdDy+vC7OgGPX7kYahaX2sbLIPbmtG9NKITzjA=", "a4MkI78Tku6FD/ROE6glpFc56G0+2FdWxuPU+Q6ga91LgWY+vETXfI8bdHxh+g4Bz2UkHLYnICKU9SL1ilOjlkS9DDJij4JbITshOYDw8vowWtmcvE7eYoazomleOum5FkE2SaZADhK04QfTV2Mi", "a4MeIAWT1zANBngtKX39Nh9B/Wgtba9nHSlB52B1QFN9fQVDjYyb5qIYLUS7hngjUqIjtJPlMlGHE91CfuWnmLw1ovU6JbKQcOmFAxwlh+DiLJG2L8uhhYqZnDGTS4KDoULT0MWIEy3L", "a4MnJ6QI6NGCliu9bb7Dh8a0D53U3IgnEKfbTNso+kI197ccF4K2EHwyG621URECoqYqQIFKd4ylT+WA1PA/SNDiwa6/EjpcngB9Cq7XKMAKc7iOD6nDbbFegBk3tI75Zqm4o/a61O175VPzjedG/IY=", "a4MfI7iuBwUh2NrsbtHoLCA195pDL0ep6thqB088999so6K5m7ecGPSlgkIGg5coeZepEjGrmrNdpqMlphU+IeyJ8Z1/frhSKG6GZpP2TcSdLImeniI8u2+sYAbf6baN5OWu2BC6hWJOanM=", "a4MjI7TqjnQ4FYDgEm/z025Kd9fGDsTpcMeuvp9Rh+Q0oH8rqpgisXsOLnV2pDgs6VdjzDPmahd7ZR9FUBNGBe0uamr/UzM2uNGzBPq56hiOeuJMnuuxZshbXNmR4x+dZIKnIXMARG7W/smLz4vPg20=", "a4MhJ6xyRxBsSqstjsN0bYxEUvWU6hH1mU1n8maW3ka6pf9X7qrAtrx6/bDmRLRpzu14pIAhdoYclloY3nULOs/2XOLF8LJJ12Fqh6pI+Ud2qEIJwoVyr9dh+fZkZ0lIXBmiDmqFglDJXJ/3pTwarA==", "a4MmJrUoYkj54X7BIKDaQpOOZBJMVJZpRdrfAZFxAYp5P4KLmYkYTGIMv6JfJDNBHWmt33pBKIGS9oShSEH95YIKpY18hhbDL6sUK1x/9ROVdtSBWJRYaLUgFQZCjGMiDtcZGnhJyHVD0U+J9ew/wd338w==", "a4MkIpXH3pFGEuWlHPi6aerc9MSp5+wEs0jBCIwKeZAOZkOIVJam6YT1OL46adVs7Y5S2JgR9l1t1iMiE8TzNq5Zj9WXjmgWi9mE+/+fa67+zLztYVPW75E+VyCRJXsDCVA65wZ3NJcA62zKQ0wV5MI=", "a4MkI7ttsDP9Rp5CFZOpBZ6c7H0TuH6gnzWSJvTf6Z29UodSbom2HbvBaAzAkP9SLv5JSxsLxYTIffCp+yer3G8dFwtWjwa+QFSvvIXKvAVWk/wGQ0GL3XLUf4hi0cJqWhtuUGtnJf36htnM4H1WLjwd", "a4MjILyVTf69O60BnKjZTyJyvjkMnR1IaOEaN5a7egM46zF9kwTivG9xkQcbvVUXj6Sf5cQnYsndukaFrSPgljbgpjwMBdq6MWcCKj+y7BXkUUKP9xyLLoKGCr+oUr+YtMURQz78GEX5OT4p", "a4MlJ7aLjXeyD2ufPPd5uGT+7s3Xgl1uwqbakkX9P58SjBPJoTyhxNu/S4RGKbZkTIzWv3lbSGkvozwJabZbkdYJxxGEW1bgKqErjy/LDc6QtKnm8fzwmho3lmupAOwazeKrxtW4Db9I2dyPMun8Dg7kWdE=", "a4MiIzl4eKtUrxZnoc7nqXEp5vlGPT8qpAG1Ry7TcVFm3qI9nsE3Uluo8B/A+6j5t1+dlmLGbNAeNIQ5JJAJ1cOrirfU5nMvtjcDCr1O5VRtQsEEM91I6HS30QJ8FqWz9lcuen7kzCpQPY8Z", "a4MfIDL6LYsle4uy9Qw+H998fMD3wHf39R5KtjW8/n1hD8AvBU7VwrwdsOmesytrD33Bjamo8r47Lfe53j8/1AZ7bC0emQYeT2LUEYIX3lPsovwSMikX2ymlVj/7NOOPmhw5", "a4MfHSuNMILehmeW7aOkK6MSu6OkG2HGimWA1+2tFDtS1j0ppJ7xTy6jgLF6EnsAjWkEfMh2hlVoc5K+RvDgrYhvrDN+tsetTCCCu+JiAP8j2m4umUD9bfhg2szeqgszAk0zmGA=", "a4MnH6WK+HAJQU4KECKMeMQuyPAABCenNMUmYNUHPWL0Me7cEn4KFWRxdrb2j1FipQruMpCQaBqTsXyz6JwaghKZCqI6uSKBEqu22T3hF4YEYVyXJ37zMa5sX9r2a7H3IPBvhpUilt8autsr", "a4MhJrctV1qdqa1YSnaes6tcX/mtH/OyS915x9jHkAWquqEVZLeBt5dEmjdB/gRaJwO1XwRCUQ+3Q0bdEd6kBaiR5YxK0zYitP+Eta5kck4Q38r5gItcwSA1tqZgMtBrFFOFS68CYczxTRV2JfH+", "a4MkJ7F8Azb/lRsVn+aymlYXrPlSt4fJHmDgVw60/41ccILlD1R8s6xZP+UHqUIFv7hUIodQ2z7xcVXJ8ALDHZeJ8E4F/KWYIQ4p4quB6Ixktxnv2tNT0cg+BCgUZ7xcOKTVr3mRg5GFeRN4CRN3XsA61Q==", "a4MiHTYrsFyEEPT9eIeXluFUUyXFiam6JxJbza5odsSrNcggWL2BQer78lLfZEVgPgTXQRHlMXngiiKTPvTnWxUa/oPKrDy0JR40QLM4iDIY5C+brWJpt63dH11IdIsYOoo0S7NUoQ==", "a4MjI5N8mX1s31Y1cq08CXNUVgMEMuI4Z8Vq0FaXklHVn8bBLyJuk1J/GHUpvPJzagXFGtA0PnHSmT9qSNmlbruuSi+8lEAotdCVTY/kdO57WkcMPXa1rgXFnUnTEKnAU8sbQfxNSK1drkzHHHG1vg==", "a4MiJLi2UtmJ+cBdvdq13oEX0JKiFc7PAwKcaZffu38wc0AscTe2ARkJga6qpOds2tgYwQ2mkN+Za479201q7jv7PpXl//XRfqC2AR09dAIgmlVpzm0xahAla/OBHveYZCqRf7LO8cwVvNmXM0k=", "a4MjJLbOLArmsS2BBs6IImB0q3CoiPeZ7qRb7SHhC8PO1y3ObLWQtNGGIr6WxRD97iFRI1Omko2Vxu2SIvi7s03oBrsdobAEUFE4sXwlj3LvDtKPoCYxfIgj+l5XTL3j3u9MLosoAd87ePz1SBU=", "a4MmJ6eW/S999nLLeVid8euCGp4P4lIWxC7vaZQ4FrAoHs1wbhF4v2dopj5ehojZK2KOhyHhtlM/Jg21TxWAakhwDwKtxtR+2PEtaHFgkt+RpEsyzsuxz5hLcZ9gy5sT2MMy9iGXws6zQniqvR4qCsTk8H2b1w==", "a4MhI7LI1RZqI3rpPLxtw+hi7Qs731kmyp91XhY2mGmfwYEZmJWgJtbtfyh7lSm2air7I5qpsdSnicjHrr4jFlPJnG1PV1G0lNrFmo3OJXfEETwewCRHtw72rtoNg16opLNheKj9Xw==", "a4MnJrgb92c/p0Vq3+nwDqoLRcD5REon5dV1BaYGnNjGqc9/n4RMD70I9btjBM+Ugvbr0C1S0reypeWil9r1+Srx5CI23gDPItLV10ggEuiPux17+ShVIA9zFaAAX6tviLOs/js1PzS5L9aYkUjMIavuZnGBkg==", "a4MnJLlH3s6HF3nSSqBasYJIYEh1q5ur3OOJiKrVVMNLxMYM6NMWFIR1ILF+P52rInhgNxo3Q4SWSB/vpxIU+HhnAX/fuCda0EoBwMJe+634srIIV2Vr0W7oXVqX4AM0ahRA9ZKzVWdpT449KBYr/GhiQFPisw==", "a4MkIqJFB1rkE79hPJzLZGknTzI7qO8VNByZilqL27vNguVeoqwNAaEiK2uwfTbjnYe46x7KrgSlkrAyYcLyhvAawLJQFbDjPR02MyJcK/fSCP1/l3Mcnoj2Gz4DAnippCSH259IgCC8yx1IlR4=", "a4MiJzEp21XGDAHRpiFAF8VEc4t3wDQaeMeQQ9ynQAzRBMuUEmelmMBE2whTtPb10HwnnQDeWl22FeiY80I3yBYE0VsLnbxzhi7BQSWr6G41nVEoDsFBw7bcYeqwWZV0rea8sDjHVIKPx7doA2kCCg==", "a4MlI7uyyx/3MiSndSI8SvjzOthSXjw5u5T2xdUK/CgkAsn1s7BQkAq7UWPTDWuIgmovOqq6ITWhWEPwPXbor/A7xds2msyk8lAwBLqHR9qA7QY6JvkfcMJTqc8/aZcjDXG9eFdkaJATFj/AZEwIPg==", "a4MkJ7pXBgfFvRBbUlZFUg0sZiLgeoXuotUWXp2RykTZe1XBl9S2DLXRrB0OvkfiRApkl2fCLoO/Yfk0Z62A+jSf651CU42p7qNXMT8BUL8vgtloPvqkzLQmI2j9Z275M5bSFomIPtcrEKy6/OIqEBpat5gb", "a4MkIb7XjTxczQGQGKig8XKTFUBq7xMFMusUMBr6EyCvhgYIhlQqpL6AEHEvCqmSCJ9chMaLzbZHNhP6pA1CFzGPkfGVovoNBYzZGSbRRNUSrbQg8WsRbONY3VBTghcV9TiaaFWkrLlNiIYs2VpN4g==", "a4MfITcH1fOsDcTB1uhSJ9ROUFOtPz2luRobxKcFhMeO7DU0TPfzBRVuUvpFE/vESrWkzIxTBJmoG2Bi9LCNR4fEuf8umoRrWiOzkJ6QnUAo1UdygBXR1zmz90D2wlCKtnoX+uWYqzs=", "a4MfIilM+smC5b/rSmA55Sdlu+En949/FZ7aObY6wrgG06snu2eJv/nt1UN2Zu3GFMudf12dqLqn7JTtZvpBD+85/c59J7u9Zb8G7z+NFLXcvY4OFBnK6nL94tts2Gj25IM=", "a4MbICUp+9IzVn1E1aIoUYmy1a4vi+jWYyhz0B15dCUqUOtJ7ZZbgHyRd8PUYnieoTu9GkddrA/aOLi3VCEkA223SkQhZy0ZUQi7A+kisxUSDmaq/LXL", "a4McICIEj0rt/iEIO8ej9HZp/s7A1qlktw4pGCtt7HoiMbBsDvSqrWAGMn60Z9L97gTtTjSFNqxAJ6VaG4WYDCRjhri0xN/GZeCwtcEbEWQYo8o9tLiVt6MVpXCQPz7XeYk=", "a4MWDwzU+x80rFQWC9gLwxyGzy0H2koCGUkKLtz6LBO0EBTzdqE3qtcH0KTFKT+Apm/bsINu/iw2dfcB8Si9", "a4MfJwEe6ygc99ZyfDB9cvXufKfOEWdZBF5z2QOy45sYyq6a5GBRDzl3mtSNGEttUcDiiIyFY0klFGUpNhNtQ6n7iRH4Cu4gz0ulUUjRc+oZ+SFwc4oOeIv0Uc6tD/rYfJUwZRFzj1RtsyKuoQFRlg==", "a4MlJaojlzmEKgo+GRY079vcbgHVHzgyxGmWYh6vukBBw1MTLDsSRX+2TR6ljmpKjUes2Hj2b+8L9hpCIAUWIP0yeW5pADB3sqk8oSt0vAuFwTfcLorTXbAd4BHAdnU4u7oGAPBhgUXiNkcKs6rGT8Mx", "a4MmJ7x1DGELY7Tr/u1r9lPvCHE91f+I5iSyQdUvAc0R7+kt8AzFy8sfvGbe8miWWbxXLhEM2kYix3hUv5bWErZq2XyRoCSNJGVPF3MLrDtqta0AyTUSydcpsYo0yZl4nXtkVAZ0s1Om7tXkb5CMoGILckw=", "a4MkIbF9gWzdNeg2//BBgA+ghpyT64BqH7gnKoVinsZI6QzoIN+SNKxlPmNsedCh8Vkxsf4hp/YJWHxRU2NfFlxl+ai5cOfmFKYEh6MBKvjWF6/G6Ce/50yCnZRjrJELZ+cVV+9/nzQMMQPD", "a4MkIqmOUzdUbJZdhvb3bhobD06wBR+KELGgeMrZ5XyKsFojM0Gym6oVHlmMXfmQ79+K3ylblvBNDu71O52tXRusXQpZb7A57LSpkwpoR+CIAYD3sa0X5BdaMJqgNs5y5kl1eiEFT4COJEoCxIp4uw==", "a4MhI7LHKZ48RyLRc2D9k+Pd8r84P3yFUGneFtvU0Uls3me0PrwdV4W0SN9arcofUWm2sR2pphAPq/GRAzwXX0tfh7sklICGujaFaBLJ8zPSUprTfTINnUubGfXIti9oWd9GT/ZT8gkDYl3+qg==", "a4MhJ7m/0DnvS5nRDgfY5KxCh1GN9/JrXB8cOI57BRwYgLllvLo/whrTeT1u/QtTlLCHPVR3NumobRvYYoa8ut6nEZZu4rVAX3ypp7ptF4yeMbez3ZgAFFTzX3aDSDaUVYZW02oiAxUKa2s2j4pVxU3lnQ==", "a4MlIrnfmbdonoDLiy8UHk/2fQ5SL4+rP1Dh6m/+o4ezEU/WOVgEve27rYVEKVfHBFCORFFyB845loCek2TUQqFeeDVI0ifFEAykuse1leasJy62xEgdGkJ67PMBvuy+kwtVPAUYPLsvi8FdZqNyDAJI", "a4MiH5aRxczhprB+aC3tFTcAm74PgOyWhCnfUuOHgs+v+K9aWwyVthgqQjrl15LEWtLd/BQzXrA9O0p1uDItbVrcUPMElOE9dcLrRXMLSe+S7/3roQ+d2yfqn6DaSRRaC7WBIw==", "a4MjJpVaT28HPK4t+JCVi0SbM0KfVbsJlzHhdtlElUCArJehQ57bvAuZhzuVAhU7lJAnrWSMYvof2ncdVbY1zQCHf26kf5ljmHbUW2y8mm0Pbf06m5F4vDwNJAibIYWWaoBUa+XQueoGQ5UsTcaP1nAlXw==", "a4MkJ7vsvIT7bQe/woYdVqkmfpgrCdRjhvFlMiX5kIiaBzHLoUBxi7hgmhAZDdCclflE1AYkYifO6eIg9oZ9WPFlX2erZEDM+f/2AkCiTrVWoIP+V0/wdHN5OCqB170UhXhVG+ZEFWNcjQH/anjWb18l", "a4MjJ6xfQnst9PU74LFiejPX7fn34GAriW2JUdAvJ1FKfLX3XvCjre79Sl7vtuD934iQ6WDdxv1773ZAUywxzRpACxNthTTlrHB3A8bfpYI91YYvsU/U8jDZzi8dRpNgx/zuTPX6/iZZPDxCI6sWKuQ=", "a4MnJKhvazT3XCo1nh6FgPAnc6QGRTYPo4r9NW5GZC5h7ecv/Iqo1hVFg66152FSVzbyIiJEu7NatBg1wG1uRMab7K6WQHkRbwgTVRQUx60d+IhAc3Eg0vwYq80/KG2O2azSzNqmXlNAOIIqjVD1MGbpJSkY", "a4MhJrtssPlq+MouGEp5XTRnyWrXiE6rA4bljRtPjhZK1w6Zl7qHjenGOa/zOOox7E3lBRzXcDL5wSwCIOPLrWoiocZXBckBMM6Ou/gDt+iNx92YmAi9O43aU7HLvHq2nC//H2H51TQHZVQ=", "a4MnJLhnPDVBlTCHvhjaPQgLeHHr4IONe26AlxJk8m/R4qc3K9JO5WrNNrez+NHEOLeRqLb4sajjx5Y9zklZUZwzWIZsk9EhuYKfwBHcZ7a/gDI/M1x+bC3nXIXIs+WYxfuXCjTizc34q5vWRPMmKQ==", "a4MlJrIRFy1i+9ULyH4+CG9j7vFeHcnk6AS2vL1uBKt1W2Wzq/ejzjCwAEvLUYqhz/HWRcItFNWOBuWFciPD+KRP44KoHpTsHYHkuoirqq6AsxYUFO/E06m3B3AfTpugNzI1x+M3i3ikGTl0mEsH", "a4MkIKrwQvcp2t98eXKHmTFzKhXDzKtH9rKvanmMEZ6N/UvHT524AqX4eOr/HtETOefKhSPxJI/o6/QD4sejDwoSAQZE42ZzoNckDYyx4uT7JNdFsy8ubBDHdQh5aizFPEcc5GBnyjriQ5s1vns=", "a4MiG56yKushRliP3MfGitgevwZgSNOkgChoxsoeHOBOoHEASOeB2gAgKN/qL9HalLKPfarO+yiFhIR0OWIA3WcT+n3uXugMSPxvaQ+G", "a4MMFwig9h1ixLrwNIhAlAhtoL3WMFFQgLiKRmuUAcNEoyF6FuE9B9CkxVLsyKk5xcsNd0BEoS3Kxr6tmjw=", "awMH0KTFJK2fIHuMs/Nm/EP/kUKXulh+sE6V4AfQpMUnROQKK3fDG9zs1IOX5kxCyJb3MmA8B9UZeiTsFiRR6AsID9O8x1hcGjyoHG6FSjg=", "awMHyXnIyVfAohIjgNQ6PAfJecjJV8CiEiOA1Dg4B8l5yMlXwKISI4r0ODw=", "awMHyXnIyVfAohIjivQ4OAfJecjJV8CiEiOVFDg8B8l5yMlXwKISI5UUODg=", "awMHyXnIyVfAohIjnzQ6OAfJecjJV8CiEiOpVDo8B8l5yMlXwKISI6lUOjg="]

OPUS_WELCOME_PACKETS = [base64.b64decode(x) for x in OPUS_WELCOME_DATA]
OPUS_ACTIVATION_PACKETS = [base64.b64decode(x) for x in OPUS_ACTIVATION_DATA]

async def send_tts_response(websocket, session_id, user_text, bot_text, opus_chunks):
    try:
        # 1. Gui STT de OLED hien thi
        await websocket.send(json.dumps({
            "type": "stt",
            "text": user_text,
            "session_id": session_id
        }))
        await asyncio.sleep(0.05)

        # 2. Gui bieu cam LLM (happy)
        await websocket.send(json.dumps({
            "type": "llm",
            "emotion": "happy"
        }))
        await asyncio.sleep(0.05)

        # 3. Bat dau TTS
        await websocket.send(json.dumps({
            "type": "tts",
            "state": "start",
            "session_id": session_id
        }))

        # 4. Gui cau tra loi
        await websocket.send(json.dumps({
            "type": "tts",
            "state": "sentence_start",
            "text": bot_text,
            "session_id": session_id
        }))

        # 5. Truyen tung frame Opus nhi phan (60ms moi frame)
        for chunk in opus_chunks:
            await websocket.send(chunk)
            await asyncio.sleep(0.06)

        # 6. Ket thuc TTS
        await websocket.send(json.dumps({
            "type": "tts",
            "state": "stop",
            "session_id": session_id
        }))
        logger.info(f"TTS response finished: {len(opus_chunks)} frames sent.")

        # 7. Luu hoi thoai vao database de hien thi tren Dashboard Lich su
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
    except Exception as e:
        logger.error(f"Error in send_tts_response: {e}")

# ==================== WEBSOCKET SERVER CHO ROBOT XIAOZHI ====================

async def ws_handler(websocket):
    client_ip = websocket.remote_address
    device_mac = "14:c1:9f:c4:ee:d0"
    logger.info(f"Robot Xiaozhi connected from {client_ip}")

    if device_mac in DB_DEVICES:
        DB_DEVICES[device_mac]["online"] = True
        DB_DEVICES[device_mac]["lastActiveTime"] = int(time.time() * 1000)

    session_id = str(uuid.uuid4())
    current_response_task = None
    mic_audio_count = 0
    dialogue_ctx = {"round": 0}

    RESPONSES = [
        ("Xin chào Xiaozhi!", "Xin chào, bạn của tôi! Tôi là Xiaozhi tiếng Việt, rất vui được trò chuyện cùng bạn!", OPUS_WELCOME_PACKETS),
        ("Tôi muốn tìm hiểu về hệ thống.", "Chào bạn, thiết bị đã được kích hoạt thành công và kết nối thông suốt với máy chủ Gehihi!", OPUS_ACTIVATION_PACKETS),
        ("Hôm nay thế nào?", "Hệ thống hoạt động rất tốt, chúc bạn một ngày tràn đầy năng lượng và niềm vui!", OPUS_WELCOME_PACKETS)
    ]

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
                            "version": 1,
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
                            # Khi bấm nút BOOT: Robot chuyển sang chế độ Lắng nghe
                            # Khởi động tác vụ tự động phản hồi sau 2 giây lắng nghe
                            if current_response_task and not current_response_task.done():
                                current_response_task.cancel()
                            mic_audio_count = 0

                            async def auto_speech_worker():
                                try:
                                    # Chờ 2.2 giây để người dùng nói xong
                                    await asyncio.sleep(2.2)
                                    idx = dialogue_ctx["round"] % len(RESPONSES)
                                    dialogue_ctx["round"] += 1
                                    u_text, b_text, audio_pkts = RESPONSES[idx]
                                    logger.info(f"Auto-turn triggered: replying with '{b_text[:30]}...'")
                                    await send_tts_response(websocket, session_id, u_text, b_text, audio_pkts)
                                except asyncio.CancelledError:
                                    pass

                            current_response_task = asyncio.create_task(auto_speech_worker())

                        elif state == "detect":
                            # Từ khóa đánh thức phát hiện
                            if current_response_task and not current_response_task.done():
                                current_response_task.cancel()
                            current_response_task = asyncio.create_task(
                                send_tts_response(
                                    websocket,
                                    session_id,
                                    "Xiaozhi ơi!",
                                    "Dạ, tôi nghe đây! Bạn cần tôi giúp gì nào?",
                                    OPUS_WELCOME_PACKETS
                                )
                            )

                        elif state == "stop":
                            # Người dùng chủ động ngắt tiếng hoặc kết thúc lượt nói
                            if current_response_task and not current_response_task.done():
                                current_response_task.cancel()
                            idx = dialogue_ctx["round"] % len(RESPONSES)
                            dialogue_ctx["round"] += 1
                            u_text, b_text, audio_pkts = RESPONSES[idx]
                            current_response_task = asyncio.create_task(
                                send_tts_response(websocket, session_id, u_text, b_text, audio_pkts)
                            )

                    elif msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))

                    elif msg_type == "abort":
                        if current_response_task and not current_response_task.done():
                            current_response_task.cancel()
                        await websocket.send(json.dumps({
                            "type": "tts",
                            "state": "stop",
                            "session_id": session_id
                        }))

                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON text message: {message}")
            else:
                # Dữ liệu âm thanh micro nhị phân từ robot
                mic_audio_count += 1
                if device_mac in DB_DEVICES:
                    DB_DEVICES[device_mac]["lastActiveTime"] = int(time.time() * 1000)

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Robot disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if current_response_task and not current_response_task.done():
            current_response_task.cancel()
        if device_mac in DB_DEVICES:
            DB_DEVICES[device_mac]["online"] = False

# ==================== MAIN HTTP RUNNER ====================

async def run_http_server():
    app = web.Application()

    # Health & System
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/health", handle_health)

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

async def main():
    logger.info("==================================================")
    logger.info("   Starting Gehihi Full Dynamic Server for Render ")
    logger.info(f"   Public Base URL: {PUBLIC_URL}                 ")
    logger.info(f"   OTA URL:         {PUBLIC_URL}/xiaozhi/ota/    ")
    logger.info(f"   WebSocket URL:   {WS_URL}                     ")
    logger.info("==================================================")
    await asyncio.gather(
        run_http_server(),
        run_ws_server()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gehihi Server stopped.")
