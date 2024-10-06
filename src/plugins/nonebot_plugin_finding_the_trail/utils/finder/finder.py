import copy
from src.plugins.nonebot_plugin_finding_the_trail.utils.enums.blocks import Blocks
from src.plugins.nonebot_plugin_finding_the_trail.utils.enums.directions import Directions
from src.plugins.nonebot_plugin_finding_the_trail.utils.finder.utils import (
    get_moveable_directions,
    NodeData,
    MovementExecutor,
    get_back_direction,
)


class Finder:
    def get_start_pos(self) -> list[int]:
        for row in range(len(self.game_map)):
            for col in range(len(self.game_map[row])):
                if self.game_map[row][col] == Blocks.START:
                    return [row, col]
        raise ValueError("No start block found")

    def init_stack(self) -> list[NodeData]:
        start_pos = self.get_start_pos()
        return [
            {"game_map": copy.deepcopy(self.game_map), "pos": start_pos, "answer": [d]}
            for d in get_moveable_directions(start_pos, self.game_map, [])
        ]
