#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

from datetime import datetime
from typing import List, Optional

from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ..models import Sticker


class StickerManager:
    """Sticker management system for saving, searching and retrieving stickers"""

    async def save_sticker(
        self, description: str, raw: bytes, group_id: Optional[str] = None
    ) -> Sticker:
        """
        Save a sticker to the database

        Args:
            description: VLM-generated description of the sticker
            raw: Binary image data
            group_id: Source group ID (optional, for tracking origin)

        Returns:
            The created Sticker object
        """
        current_time = datetime.now()

        sticker = Sticker(
            description=description,
            raw=raw,
            group_id=group_id,
            created_time=current_time.timestamp(),
        )

        async with get_session() as session:
            session.add(sticker)
            await session.commit()
            await session.refresh(sticker)

        return sticker

    async def search_sticker(self, query: str, limit: int = 5) -> List[Sticker]:
        """
        Search stickers by description (fuzzy matching)
        Searches across ALL stickers globally, regardless of group_id

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        async with get_session() as session:
            # Use LIKE for fuzzy matching on description
            # Split query into keywords for better matching
            keywords = query.split()
            
            # Build query - search globally across all stickers
            stmt = select(Sticker)
            
            # Apply keyword filters using LIKE
            for keyword in keywords:
                stmt = stmt.where(Sticker.description.contains(keyword))
            
            # Order by created_time descending (newest first) and limit results
            stmt = stmt.order_by(Sticker.created_time.desc()).limit(limit)
            
            result = await session.scalars(stmt)
            return list(result.all())

    async def search_sticker_any(self, query: str, limit: int = 5) -> List[Sticker]:
        """
        Search stickers matching ANY keyword (OR logic)
        Searches across ALL stickers globally

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching Sticker objects
        """
        from sqlalchemy import or_
        
        async with get_session() as session:
            keywords = query.split()
            
            if not keywords:
                return []
            
            # Build OR conditions for each keyword
            conditions = [Sticker.description.contains(keyword) for keyword in keywords]
            
            stmt = (
                select(Sticker)
                .where(or_(*conditions))
                .order_by(Sticker.created_time.desc())
                .limit(limit)
            )
            
            result = await session.scalars(stmt)
            return list(result.all())

    async def get_sticker(self, sticker_id: int) -> Optional[Sticker]:
        """
        Get a sticker by its ID

        Args:
            sticker_id: The ID of the sticker to retrieve

        Returns:
            The Sticker object if found, None otherwise
        """
        async with get_session() as session:
            return await session.get(Sticker, sticker_id)

    async def delete_sticker(self, sticker_id: int) -> bool:
        """
        Delete a sticker by its ID

        Args:
            sticker_id: The ID of the sticker to delete

        Returns:
            True if deleted, False if not found
        """
        async with get_session() as session:
            sticker = await session.get(Sticker, sticker_id)
            if not sticker:
                return False

            await session.delete(sticker)
            await session.commit()
            return True

    async def get_all_stickers(self, limit: int = 100) -> List[Sticker]:
        """
        Get all stickers (for listing purposes)

        Args:
            limit: Maximum number of stickers to return

        Returns:
            List of Sticker objects
        """
        async with get_session() as session:
            stmt = (
                select(Sticker)
                .order_by(Sticker.created_time.desc())
                .limit(limit)
            )
            result = await session.scalars(stmt)
            return list(result.all())


# Global sticker manager instance
sticker_manager = StickerManager()


async def get_sticker_manager() -> StickerManager:
    """
    Get the global StickerManager instance

    Returns:
        StickerManager instance
    """
    return sticker_manager