#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

from src.plugins.nonebot_plugin_defuse_tnt.__main__ import lang


def get_result_dict(password: list[int], answer: list[int]) -> dict[str, int]:
    """
    获取结果信息
    :param password: 用户输入的密码
    :param answer: 正确的密码
    """
    result = {
        "right": 0,
        "wrong": 0,
        "pos_wrong": 0,
        "repeated": 0
    }
    for i in range(len(password)):
        if password[i] == answer[i]:
            if password.count(password[i]) <= 1 < answer.count(answer[i]):
                result["repeated"] += 1
            else:
                result["right"] += 1
        elif password[i] in answer:
            result["pos_wrong"] += 1
        else:
            result["wrong"] += 1
    return result


async def get_failed_result_string(password: list[int], answer: list[int], user_id: str) -> str:
    """
    获取尝试结果的字符串（只支持错误的答案，不包含校验）
    :param password: 用户给出密码
    :param answer: 正确答案
    :param user_id: 用户ID
    """
    result_dict = get_result_dict(password, answer)
    result = [(await lang.text(f"result_wrong.{k}", user_id, v)) for k, v in result_dict.items() if v > 0]
    string = (await lang.text("result_wrong.sep", user_id)).join(result)
    return await lang.text("result_wrong.template", user_id, string)




