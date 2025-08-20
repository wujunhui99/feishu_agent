#!/usr/bin/env python
import json
import logging
import os
import asyncio
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi import EventDispatcher

from src.Agents import AgentClass
from src.Storage import add_user
from dotenv import load_dotenv as _load_dotenv

_load_dotenv()

user_storage = {}

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
        add_user("userid", user_id)
        
        # 处理消息
        response = AgentClass().run_agent(message_text)
        reply_text = response['output']
        
        logger.info(f"Generated reply: {reply_text}")
        
        # 发送回复
        request_body = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                         .receive_id(chat_id)
                         .msg_type("text")
                         .content(json.dumps({"text": reply_text}))
                         .reply_in_thread(False)
                         .uuid(f"reply_{message_id}")
                         .build()) \
            .build()
        
        send_response = client.im.v1.message.create(request_body)
        
        if send_response.success():
            logger.info(f"Successfully sent reply to chat {chat_id}")
        else:
            logger.error(f"Failed to send reply: {send_response.code}: {send_response.msg}")
            
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)


class MessageEventHandler:
    """消息事件处理器"""
    
    def __init__(self):
        self.logger = logging.getLogger("MessageEventHandler")
    
    async def do(self, event):
        """处理消息接收事件"""
        try:
            self.logger.info("Received message event")
            
            # 获取事件数据
            event_data = event.event
            
            # 检查是否是机器人发送的消息，避免循环
            sender = event_data.sender
            if sender.sender_type == "app":
                self.logger.info("Ignored bot message")
                return
            
            # 获取消息信息
            message = event_data.message
            message_type = message.message_type
            chat_id = message.chat_id
            message_id = message.message_id
            user_id = sender.sender_id.user_id if sender.sender_id else None
            
            # 只处理文本消息
            if message_type == "text":
                try:
                    content = json.loads(message.content)
                    message_text = content.get("text", "").strip()
                    
                    if message_text and user_id:
                        self.logger.info(f"Received text message from {user_id} in chat {chat_id}: {message_text}")
                        
                        # 异步处理消息
                        asyncio.create_task(
                            process_message_async(message_text, user_id, message_id, chat_id)
                        )
                except json.JSONDecodeError:
                    self.logger.error("Failed to parse message content as JSON")
                    
        except Exception as e:
            self.logger.error(f"Error in message event handler: {e}", exc_info=True)


def main():
    """启动飞书长连接服务"""
    logger.info("Starting Feishu Long Connection Service")
    logger.info(f"App ID: {os.getenv('FEISHU_APP_ID')}")
    
    try:
        # 创建事件分发器
        dispatcher = EventDispatcher()
        
        # 注册消息接收事件处理器
        message_handler = MessageEventHandler()
        dispatcher.register("im.message.receive_v1", message_handler)
        
        logger.info("Event handlers registered successfully")
        
        # 启动长连接
        logger.info("Starting long connection...")
        client.start(dispatcher)
        
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Error starting Feishu long connection service: {e}", exc_info=True)
    finally:
        logger.info("Feishu long connection service stopped")


if __name__ == '__main__':
    main()