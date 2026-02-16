from nonebot_plugin_openai.types import Message as OpenAIMessage

def get_role(message: OpenAIMessage) -> str:
    if isinstance(message, dict):
        role = message["role"]
    else:
        role = message.role
    return role