import asyncio
import httpx


async def test_connecting(url: str) -> bool:
    """测试连接到指定URL
    
    Args:
        url: 要测试的URL
        
    Returns:
        连接是否成功
    """
    try:
        async with httpx.AsyncClient(base_url=url) as client:
            resp = await client.get("/status")
            return resp.status_code == 200
    except Exception:
        return False