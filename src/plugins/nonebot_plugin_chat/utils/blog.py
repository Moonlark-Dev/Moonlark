from datetime import datetime

from nonebot_plugin_orm import get_session

from ..models import BlogPost


async def create_blog_post(title: str, content: str) -> BlogPost:
    """
    Create a new blog post

    Args:
        title: The title of the blog post
        content: The content of the blog post

    Returns:
        The created BlogPost object
    """
    blog_post = BlogPost(title=title, content=content, create_at=datetime.now())

    async with get_session() as session:
        session.add(blog_post)
        await session.commit()
        await session.refresh(blog_post)

    return blog_post
