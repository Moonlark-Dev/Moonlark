from datetime import datetime

from nonebot_plugin_orm import get_session
from sqlalchemy import select, func

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


async def get_blog_posts(page: int = 1, page_size: int = 10) -> dict:
    """
    Get blog posts with pagination

    Args:
        page: Page number (1-indexed)
        page_size: Number of posts per page

    Returns:
        Dict with items, total, page, page_size
    """
    offset = (page - 1) * page_size

    async with get_session() as session:
        total_result = await session.execute(select(func.count()).select_from(BlogPost))
        total = total_result.scalar() or 0

        stmt = select(BlogPost).order_by(BlogPost.create_at.desc()).offset(offset).limit(page_size)
        result = await session.execute(stmt)
        posts = result.scalars().all()

    return {
        "items": [
            {
                "id": p.id,
                "title": p.title,
                "content": p.content,
                "create_at": p.create_at.isoformat() if p.create_at else None,
            }
            for p in posts
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
