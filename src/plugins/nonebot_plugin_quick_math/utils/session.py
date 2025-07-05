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

import random
from datetime import datetime
from typing import NoReturn, Optional, overload

from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic

from nonebot_plugin_achievement.utils.unlock import unlock_achievement
from nonebot_plugin_larkuser import prompt
from nonebot_plugin_larkuser.exceptions import PromptTimeout
from nonebot_plugin_quick_math.__main__ import lang, quick_math
from nonebot_plugin_quick_math.config import config
from nonebot_plugin_quick_math.types import LevelMode, LevelModeString, ReplyType, QuestionData, ExtendReplyType
from nonebot_plugin_quick_math.utils.achievement import get_achievement_location, update_achievements_status
from nonebot_plugin_quick_math.utils.generator import get_difficulty_list, get_max_level
from nonebot_plugin_quick_math.utils.message import wait_answer
from nonebot_plugin_quick_math.utils.point import get_point
from nonebot_plugin_quick_math.utils.question import get_question
from nonebot_plugin_quick_math.utils.user import update_user_data


class QuickMathSession:

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.point = 0
        self.passed = 0
        self.total_answered = 0
        self.skipped_question = 0
        self.available_skip_count = 0
        self.respawned = False
        self.start_time = datetime.now()
        self.end_time = datetime.now()
        self.level: LevelMode = "random", 1

    async def loop(self) -> NoReturn:
        while await self.send_question():
            await self.on_question_finished()
        await self.send_result_image()

    def set_max_level(self, max_level: int) -> LevelMode:
        self.level = self.level[0], min(7, min(max_level, 1))
        return self.level

    def set_level_mode(self, level_mode: LevelModeString) -> LevelMode:
        self.level = level_mode, self.level[1]
        return self.level

    async def send_question(self) -> bool:
        image, question = await self.get_question()
        send_time = datetime.now()
        result = await wait_answer(question, image, self.user_id)
        return await self.process_answer_result(result, send_time, question)

    async def process_answer_result(self, result: ReplyType, send_time: datetime, question: QuestionData) -> bool:
        if result == ReplyType.TIMEOUT or result == ReplyType.WRONG:
            return await self.on_wrong_answer()
        elif result == ReplyType.SKIP and self.available_skip_count > self.skipped_question:
            await self.on_skip(question, send_time)
        elif result == ReplyType.RIGHT:
            await self.on_right_answer(question, send_time)
        return True

    async def on_right_answer(self, question: QuestionData, send_time: datetime) -> None:
        if question["level"] == 7:
            await unlock_achievement(get_achievement_location("calculus"), self.user_id)
        add_point = get_point(question, send_time)
        if self.level[1] > 1:
            add_point = int(add_point * 0.8)
        self.passed += 1
        self.point += add_point
        await lang.send("answer.right", self.user_id, add_point)

    @overload
    async def get_question(
        self, override_time_limitation: Optional[bool] = False
    ) -> tuple[UniMessage, QuestionData]: ...

    async def get_question(self, **kwargs) -> tuple[UniMessage, QuestionData]:
        return await get_question(
            self.get_level(),
            self.user_id,
            self.passed,
            self.point,
            self.available_skip_count,
            self.skipped_question,
            **kwargs,
        )

    def get_level(self) -> int:
        if self.level[0] == "lock":
            return self.level[1]
        return random.choice(get_difficulty_list(self.level[1]))

    async def on_wrong_answer(self) -> bool:
        self.end_time = datetime.now()
        if self.point >= 400 and not self.respawned:
            return await self.ask_respawn()
        return False

    async def ask_respawn(self) -> bool:
        try:
            respawn: str = await prompt(
                await lang.text("main.respawn_prompt", self.user_id, self.point // 2), self.user_id, timeout=20
            )
        except PromptTimeout:
            return False
        if respawn.startswith("y"):
            self.point -= self.point // 2
            self.respawned = True
            return True
        return False

    async def on_skip(self, question: QuestionData, send_time: datetime) -> None:
        self.skipped_question += 1
        self.point += get_point(question, send_time) // 2
        await lang.send("main.skipped", self.user_id)

    async def on_question_finished(self) -> None:
        if (
            self.level[0] != "lock"
            and self.passed % config.qm_change_max_level_count == 0
            and self.level[1] != get_max_level()
        ):
            self.set_max_level(self.level[1] + 1)
        if self.point >= 200 * self.available_skip_count:
            self.available_skip_count += 1

    async def update_achievement(self) -> None:
        await update_achievements_status(
            self.user_id, self.passed, self.point, self.passed / self.total_answered, self.skipped_question
        )

    async def send_result_image(self) -> NoReturn:
        await quick_math.finish(UniMessage().image(raw=await self.get_result_image()))

    async def get_result_image(self) -> Optional[bytes]:
        if self.passed == 0:
            return None
        total_seconds = (self.end_time - self.start_time).total_seconds()
        diff, record = await update_user_data(self.user_id, self.point)
        await self.update_achievement()
        return await md_to_pic(
            await lang.text(
                "main.checkout",
                self.user_id,
                self.passed,
                int(total_seconds // 60),
                total_seconds % 60,
                self.point,
                self.skipped_question,
                total_seconds / self.passed,
                self.point / self.passed,
                self.point / total_seconds,
                self.passed / self.total_answered * 100,
                record,
                self.point,
                diff,
            )
        )


class QuickMathZenSession(QuickMathSession):

    def __init__(self, user_id: str, difficulty: int) -> None:
        super().__init__(user_id)
        self.set_level_mode("lock")
        self.set_max_level(difficulty)

    async def get_question(self) -> tuple[UniMessage, QuestionData]:
        return await super().get_question(override_time_limitation=True)

    async def send_question(self) -> bool:
        image, question = await self.get_question()
        send_time = datetime.now()
        result = await wait_answer(
            question,
            image.text(text=await lang.text("main.zen_mode", self.user_id)),
            self.user_id,
            enable_leave_command=True,
        )
        if result == ExtendReplyType.LEAVE:
            self.point *= 0.75
            return False
        return await self.process_answer_result(result, send_time, question)
