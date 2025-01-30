from ...types import CurrentLevel


class LevelCalculator:

    def __init__(self, max_level: int) -> None:
        self.max_level = max_level

    def get_total_exp(self, level: int) -> int:
        """计算达到指定等级所需的总经验值"""
        if level < 0 or level > self.max_level:
            raise ValueError(f"等级必须在0-{self.max_level}之间")
        return 500 * (level**3) + 1000 * (level**2)

    def get_exp_to_next_level(self, current_level: int) -> int:
        """计算升级到下一级需要的经验值"""
        if current_level >= self.max_level:
            return 0
        return self.get_total_exp(current_level + 1) - self.get_total_exp(current_level)

    def get_current_level(self, exp: int) -> CurrentLevel:
        """根据经验值计算当前等级信息"""
        if exp < 0:
            raise ValueError("经验值不能为负数")

        # 快速近似计算
        approx_level = int((exp / 500) ** (1 / 3))
        level = max(0, approx_level - 2)

        # 精确查找
        while level <= self.max_level:
            if exp < self.get_total_exp(level + 1):
                break
            level += 1

        level = min(level, self.max_level)
        current_exp = exp - self.get_total_exp(level)
        exp_to_next = self.get_exp_to_next_level(level) if level < self.max_level else 0
        progress = round((current_exp / exp_to_next * 100), 2) if exp_to_next > 0 else 100.0

        return {"level": level, "current_exp": current_exp, "exp_to_next": exp_to_next, "progress": progress}

    def print_level_table(self, max_level: int = 10) -> str:
        """生成等级经验对照表"""
        table = ["等级 | 总经验        | 升级所需经验"]
        for lv in range(max_level + 1):
            total = self.get_total_exp(lv)
            next_exp = self.get_exp_to_next_level(lv) if lv < self.max_level else 0
            table.append(f"{lv:3} | {total:<12} | {next_exp:<12}")
        return "\n".join(table)
