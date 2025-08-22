#!/usr/bin/env python
import json
import logging
import os
import asyncio
import threading
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from typing import Any

from src.Agents import AgentClass
from src.Storage import add_user, set_processing_user
from dotenv import load_dotenv as _load_dotenv

_load_dotenv()

# 用户存储通过 Storage.py 模块管理

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("feishu_connection.log")
        ]
    )
    return logging.getLogger("Feishu")


logger = setup_logging()

# 初始化飞书客户端
client = lark.Client.builder() \
    .app_id(os.getenv("FEISHU_APP_ID")) \
    .app_secret(os.getenv("FEISHU_APP_SECRET")) \
    .log_level(lark.LogLevel.DEBUG) \
    .build()


async def process_message_async(message_text: str, user_id: str, message_id: str, chat_id: str):
    """异步处理消息并回复"""
    try:
        logger.info(f"Processing message from {user_id}: {message_text}")
        
        # 记录用户信息
        add_user(user_id, {"user_id": user_id, "chat_id": chat_id})
        
        # 处理消息 - 直接传递用户ID
        response = AgentClass().run_agent(message_text, user_id=user_id)
        reply_text = response['output']
        
        logger.info(f"Generated reply: {reply_text}")
        
        # 构造消息内容 - 修正JSON格式
        content = json.dumps({"text": reply_text}, ensure_ascii=False)
        
        # 构造发送消息请求 - 修正请求参数
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                         .receive_id(chat_id)
                         .msg_type("text")
                         .content(content)
                         .build()) \
            .build()
        
        # 发送回复
        send_response = client.im.v1.message.create(request)
        
        if send_response.success():
            logger.info(f"Successfully sent reply to chat {chat_id}")
        else:
            logger.error(f"Failed to send reply: {send_response.code}: {send_response.msg}")
            
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


def handle_message_receive_v1(event: P2ImMessageReceiveV1) -> None:
    """处理接收消息事件 - 使用正确的事件类型"""

    try:
        logger.info(f"Received message event: {lark.JSON.marshal(event, indent=4)}")
        
        # 获取事件数据
        event_data = event.event
        
        # 检查是否是机器人发送的消息，避免循环
        sender = event_data.sender
        if sender.sender_type == "app":
            logger.info("Ignored bot message")
            return
        
        # 获取消息信息
        message = event_data.message
        message_type = message.message_type
        chat_id = message.chat_id
        message_id = message.message_id
        
        # 获取用户ID - 修正获取方式
        user_id = sender.sender_id.user_id if sender.sender_id and hasattr(sender.sender_id, 'user_id') else \
                  sender.sender_id.open_id if sender.sender_id and hasattr(sender.sender_id, 'open_id') else None
        print("received message ...")
        print(dir(event))
        # 只处理文本消息
        if message_type == "text":
            try:
                content_json = json.loads(message.content)
                message_text = content_json.get("text", "").strip()
                
                
                if message_text and (user_id or chat_id):
                    logger.info(f"Received text message from {user_id} in chat {chat_id}: {message_text}")
                    
                    # 将异步任务添加到当前事件循环
                    asyncio.create_task(
                        process_message_async(message_text, user_id or chat_id, message_id, chat_id)
                    )
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message content as JSON: {e}")
            except Exception as e:
                logger.error(f"Error processing text message: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Error in message event handler: {e}", exc_info=True)


def handle_bot_p2p_chat_entered(event: Any) -> None:
    """处理机器人进入P2P聊天事件"""
    print(event)
    print("entered ...")
    print(dir(event))
   


def handle_message_read_v1(event: Any) -> None:
    """处理消息已读事件"""
    logger.info("Message read event received")
    # 这个事件通常不需要特殊处理，只是用户读取了消息的回执


def handle_customized_event(data: lark.CustomizedEvent) -> None:
    """处理自定义事件"""
    logger.info(f"Received customized event: {lark.JSON.marshal(data, indent=4)}")


def start_ws_client():
    """启动飞书 WebSocket 长连接客户端"""
    try:
        logger.info("Starting Feishu WebSocket Client")
        logger.info(f"App ID: {os.getenv('FEISHU_APP_ID')}")
        # 创建事件处理器 - 使用正确的Builder模式
        event_handler = lark.EventDispatcherHandler.builder(
            verification_token="",  # 如果有验证token，在这里填写
            encrypt_key=""  # 如果有加密key，在这里填写
        ).register_p2_im_message_receive_v1(handle_message_receive_v1) \
         .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(handle_bot_p2p_chat_entered) \
         .register_p2_im_message_message_read_v1(handle_message_read_v1) \
         .build()


        
        logger.info("Event handler registered successfully")
        
        # 创建 WebSocket 客户端并启动
        ws_client = lark.ws.Client(
            app_id=os.getenv("FEISHU_APP_ID"),
            app_secret=os.getenv("FEISHU_APP_SECRET"),
            event_handler=event_handler,
            log_level=lark.LogLevel.DEBUG
        )
        
        logger.info("Starting WebSocket connection...")
        ws_client.start()
        
    except Exception as e:
        logger.error(f"Error in WebSocket client: {e}", exc_info=True)


def main():
    """主函数 - 启动飞书长连接服务"""
    logger.info("Starting Feishu Long Connection Service")
    
    # 检查环境变量
    if not os.getenv("FEISHU_APP_ID") or not os.getenv("FEISHU_APP_SECRET"):
        logger.error("Missing FEISHU_APP_ID or FEISHU_APP_SECRET in environment variables")
        return
    
    try:
        # 直接启动 WebSocket 客户端
        start_ws_client()
        
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Error starting Feishu long connection service: {e}", exc_info=True)
    finally:
        logger.info("Feishu long connection service stopped")


# 如果需要在其他应用中作为线程运行
def start_in_thread():
    """在新线程中启动飞书服务"""
    thread = threading.Thread(target=main, daemon=True)
    thread.start()
    logger.info("Feishu service started in background thread")
    return thread


if __name__ == '__main__':
    main()