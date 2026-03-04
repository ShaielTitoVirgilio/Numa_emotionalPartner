'''
from typing import List
from app.chat_service import ChatService
from app.llm_client import ChatMessage

chat_service = ChatService()

def process_chat(
    conversation: List[ChatMessage],
):
    return chat_service.handle_message(conversation)
'''