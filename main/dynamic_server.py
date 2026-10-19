"""
Gehihi Dynamic Server (Lightweight Unified Backend)
- Cung cấp OTA API cho Robot Xiaozhi (https://gehihi.onrender.com/xiaozhi/ota/)
- Cung cấp WebSocket AI Server cho Robot Xiaozhi (wss://gehihi.onrender.com/xiaozhi/v1/)
- Cung cấp API hỗ trợ Web Dashboard quản trị với ngôn ngữ Tiếng Việt
- Tương thích hoàn toàn với Render Environment ($PORT, HTTPS, WSS)
"""

import os
import sys
import json
import time
import uuid
import asyncio
import logging
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

# 1x1 transparent GIF bytes for captcha fallback
TRANSPARENT_GIF = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

# ----------------- HTTP & OTA HANDLERS -----------------
async def handle_health(request):
    return web.json_response({
        "status": "online",
        "service": "Gehihi Robot Server",
        "language": "vi",
        "version": "1.0.0",
        "ota_endpoint": f"{PUBLIC_URL}/xiaozhi/ota/",
        "websocket_endpoint": WS_URL,
        "timestamp": int(time.time())
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_ota(request):
    """
    Xử lý yêu cầu OTA từ robot Xiaozhi (ESP32 firmware)
    Firmware đọc response: { server_time, firmware, websocket, mqtt }
    """
    device_id = request.headers.get("Device-Id", "")
    client_id = request.headers.get("Client-Id", "")
    accept_lang = request.headers.get("Accept-Language", "vi-VN")
    
    body_data = {}
    try:
        if request.can_read_body:
            body_text = await request.text()
            if body_text:
                body_data = json.loads(body_text)
    except Exception as e:
        logger.warning(f"Error parsing OTA request body: {e}")

    logger.info(f"OTA Request received from Device: {device_id}, Client: {client_id}, Lang: {accept_lang}")

    current_app_version = body_data.get("application", {}).get("version", "1.0.0")

    response_data = {
        "server_time": {
            "timestamp": int(time.time() * 1000),
            "timezone_offset": 420  # GMT+7 (Vietnam)
        },
        "firmware": {
            "version": current_app_version,
            "url": ""
        },
        "websocket": {
            "url": WS_URL,
            "token": f"gehihi-token-{uuid.uuid4().hex[:12]}"
        }
    }
    return web.json_response(response_data, headers={'Access-Control-Allow-Origin': '*'})

async def handle_ota_activate(request):
    return web.Response(text="success", status=200, headers={'Access-Control-Allow-Origin': '*'})

async def handle_vision_explain(request):
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": {
            "description": "Hình ảnh nhận dạng từ Robot Xiaozhi Gehihi",
            "text": "Tôi đã nhìn thấy hình ảnh bạn gửi."
        }
    }, headers={'Access-Control-Allow-Origin': '*'})

# ----------------- WEB DASHBOARD API HANDLERS -----------------
async def handle_pub_config(request):
    """Cấu hình dùng chung cho Web Dashboard"""
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": {
            "version": "1.0.0",
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
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_captcha(request):
    """Phục vụ ảnh captcha rỗng nếu có component nào gọi tới"""
    return web.Response(body=TRANSPARENT_GIF, content_type='image/gif', headers={'Access-Control-Allow-Origin': '*'})

async def handle_login(request):
    """Đăng nhập Web Dashboard (hỗ trợ không cần captcha)"""
    return web.json_response({
        "code": 0,
        "msg": "Đăng nhập thành công!",
        "data": {
            "token": "gehihi-jwt-admin-token-2026",
            "expire": 86400
        }
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_user_info(request):
    """Thông tin tài khoản quản trị"""
    return web.json_response({
        "code": 0,
        "data": {
            "id": 1,
            "username": "admin",
            "realName": "Quản trị viên Gehihi",
            "superAdmin": 1,
            "roleIdList": [1]
        }
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_device_page(request):
    return web.json_response({
        "code": 0,
        "data": {
            "total": 1,
            "list": [
                {
                    "id": "1",
                    "macAddress": "E0:5A:1B:A1:B2:C3",
                    "name": "Robot Xiaozhi AI (Gehihi)",
                    "boardType": "ESP32-S3",
                    "version": "1.0.0",
                    "status": 1,
                    "online": True,
                    "lastActiveTime": int(time.time() * 1000)
                }
            ]
        }
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_agent_page(request):
    return web.json_response({
        "code": 0,
        "data": {
            "total": 1,
            "list": [
                {
                    "id": "1",
                    "name": "Xiaozhi Trợ Lý Tiếng Việt",
                    "prompt": "Bạn là robot Xiaozhi thông minh, hỗ trợ người dùng bằng tiếng Việt thân thiện, tự nhiên và hữu ích.",
                    "ttsVoice": "vi-VN-HoaiMyNeural",
                    "llmModel": "gemini-flash",
                    "defaultAgent": True
                }
            ]
        }
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_dict_data(request):
    return web.json_response({
        "code": 0,
        "data": []
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_menu_nav(request):
    return web.json_response({
        "code": 0,
        "data": []
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_agent_list(request):
    """Danh sách Agent / Tác nhân AI cho Web Dashboard (Tiếng Việt)"""
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": [
            {
                "id": "AGT_001",
                "agentName": "Robot AI Xiaozhi (Tiếng Việt)",
                "ttsModelName": "EdgeTTS",
                "ttsVoiceName": "vi-VN-HoaiMyNeural",
                "llmModelName": "Gemini 1.5 Flash",
                "vllmModelName": "Qwen-VL",
                "memModelId": "mem_local_short",
                "systemPrompt": "Bạn là robot Xiaozhi thông minh, hỗ trợ người dùng bằng tiếng Việt thân thiện, tự nhiên và tận tâm.",
                "summaryMemory": "Ghi nhớ ngữ cảnh đối thoại tiếng Việt",
                "lastConnectedAt": "2026-10-19 12:00:00",
                "deviceCount": 1,
                "tags": [
                    {"id": "TAG_01", "tagName": "Tiếng Việt"},
                    {"id": "TAG_02", "tagName": "Mặc định"}
                ]
            }
        ]
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_agent_template_list(request):
    """Danh sách mẫu tác nhân (Agent Templates)"""
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": [
            {
                "id": "TPL_01",
                "templateName": "Trợ lý tiếng Việt thông minh",
                "ttsModelName": "EdgeTTS",
                "ttsVoiceName": "vi-VN-HoaiMyNeural",
                "llmModelName": "Gemini 1.5 Flash",
                "systemPrompt": "Bạn là robot Xiaozhi thông minh, hỗ trợ người dùng bằng tiếng Việt."
            }
        ]
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_device_bind_list(request):
    """Danh sách thiết bị đã gán cho Agent"""
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": [
            {
                "id": "DEV_001",
                "macAddress": "E0:5A:1B:A1:B2:C3",
                "name": "Robot Xiaozhi AI ESP32-S3 (Gehihi)",
                "boardType": "ESP32-S3",
                "version": "1.0.0",
                "status": 1,
                "online": True,
                "lastActiveTime": int(time.time() * 1000)
            }
        ]
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_device_list(request):
    """Danh sách thiết bị kết nối"""
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": [
            {
                "id": "DEV_001",
                "macAddress": "E0:5A:1B:A1:B2:C3",
                "name": "Robot Xiaozhi AI ESP32-S3 (Gehihi)",
                "boardType": "ESP32-S3",
                "version": "1.0.0",
                "status": 1,
                "online": True,
                "lastActiveTime": int(time.time() * 1000)
            }
        ]
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_model_list(request):
    """Danh sách Model AI (LLM, TTS, VLLM)"""
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": 3,
            "list": [
                {
                    "id": "MOD_01",
                    "modelName": "Gemini 1.5 Flash",
                    "modelType": "llm",
                    "provider": "google",
                    "isDefault": True
                },
                {
                    "id": "MOD_02",
                    "modelName": "EdgeTTS (vi-VN-HoaiMy)",
                    "modelType": "tts",
                    "provider": "microsoft",
                    "isDefault": True
                },
                {
                    "id": "MOD_03",
                    "modelName": "Qwen-VL",
                    "modelType": "vllm",
                    "provider": "dashscope",
                    "isDefault": True
                }
            ]
        }
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_tts_voice_list(request):
    """Danh sách giọng đọc TTS Tiếng Việt"""
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": {
            "total": 2,
            "list": [
                {
                    "id": "VOICE_01",
                    "name": "Hoài My (Nữ - Tiếng Việt)",
                    "voiceCode": "vi-VN-HoaiMyNeural",
                    "ttsModelId": "MOD_02",
                    "languages": "vi-VN"
                },
                {
                    "id": "VOICE_02",
                    "name": "Nam Minh (Nam - Tiếng Việt)",
                    "voiceCode": "vi-VN-NamMinhNeural",
                    "ttsModelId": "MOD_02",
                    "languages": "vi-VN"
                }
            ]
        }
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_generic_success(request):
    path = request.path
    if any(k in path for k in ["/list", "/bind", "/tags", "/provideTypes"]):
        return web.json_response({
            "code": 0,
            "msg": "success",
            "data": []
        }, headers={'Access-Control-Allow-Origin': '*'})
    if "/page" in path:
        return web.json_response({
            "code": 0,
            "msg": "success",
            "data": {
                "total": 0,
                "list": []
            }
        }, headers={'Access-Control-Allow-Origin': '*'})
    return web.json_response({
        "code": 0,
        "msg": "success",
        "data": {}
    }, headers={'Access-Control-Allow-Origin': '*'})

async def handle_cors_options(request):
    response = web.Response(status=204)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response

# ----------------- WEBSOCKET SERVER FOR XIAOZHI ROBOT -----------------
async def ws_handler(websocket):
    client_ip = websocket.remote_address
    logger.info(f"Xiaozhi Robot WebSocket connected from {client_ip}")
    session_id = str(uuid.uuid4())
    
    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    
                    if msg_type == "hello":
                        logger.info(f"Robot Xiaozhi hello received: {data}")
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
                        
                    elif msg_type == "listen":
                        state = data.get("state", "")
                        logger.info(f"Robot listen state: {state}")
                        if state == "detect":
                            # Wake word detected
                            await websocket.send(json.dumps({
                                "type": "tts",
                                "state": "start",
                                "session_id": session_id,
                                "text": "Dạ, tôi đây! Bạn cần tôi giúp gì nào?"
                            }))
                            
                    elif msg_type == "abort":
                        logger.info("Robot abort signal received")
                        
                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON text message: {message}")
            else:
                # Binary message: Audio data (Opus packets from Xiaozhi microphone)
                pass

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Robot disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

# ----------------- MAIN RUNNER -----------------
async def run_http_server():
    app = web.Application()
    
    # Health
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/health", handle_health)
    
    # OTA endpoints
    app.router.add_get("/xiaozhi/ota/", handle_ota)
    app.router.add_post("/xiaozhi/ota/", handle_ota)
    app.router.add_options("/xiaozhi/ota/", handle_cors_options)
    app.router.add_post("/xiaozhi/ota/activate", handle_ota_activate)
    app.router.add_options("/xiaozhi/ota/activate", handle_cors_options)
    
    # Vision
    app.router.add_get("/mcp/vision/explain", handle_vision_explain)
    app.router.add_post("/mcp/vision/explain", handle_vision_explain)
    app.router.add_options("/mcp/vision/explain", handle_cors_options)
    
    # Dashboard API
    app.router.add_get("/xiaozhi/user/pub-config", handle_pub_config)
    app.router.add_get("/xiaozhi/user/captcha", handle_captcha)
    app.router.add_post("/xiaozhi/user/login", handle_login)
    app.router.add_get("/xiaozhi/user/info", handle_user_info)
    app.router.add_get("/xiaozhi/admin/users/info", handle_user_info)
    app.router.add_get("/xiaozhi/agent/list", handle_agent_list)
    app.router.add_get("/xiaozhi/agent/template/list", handle_agent_template_list)
    app.router.add_get("/xiaozhi/agent/page", handle_agent_page)
    app.router.add_get("/xiaozhi/device/list", handle_device_list)
    app.router.add_get("/xiaozhi/device/page", handle_device_page)
    app.router.add_get("/xiaozhi/device/bind/{tail:.*}", handle_device_bind_list)
    app.router.add_post("/xiaozhi/device/bind/{tail:.*}", handle_device_bind_list)
    app.router.add_get("/xiaozhi/models/list", handle_model_list)
    app.router.add_get("/xiaozhi/ttsVoice", handle_tts_voice_list)
    app.router.add_get("/xiaozhi/sys/dict/type/{tail:.*}", handle_dict_data)
    app.router.add_get("/xiaozhi/sys/menu/nav", handle_menu_nav)
    
    # Generic fallback for any other GET/POST under /xiaozhi/
    app.router.add_route("*", "/xiaozhi/{tail:.*}", handle_generic_success)
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
    logger.info("   Starting Gehihi Dynamic Server for Render      ")
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
