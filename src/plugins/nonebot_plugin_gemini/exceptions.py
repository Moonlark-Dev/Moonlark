class EmptyReplyContent(Exception):
    pass


class GeminiNotConfigured(RuntimeError):
    """没有配置 GEMINI_API_KEY，无法创建客户端"""
