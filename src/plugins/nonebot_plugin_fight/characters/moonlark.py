import random
from ..base.monomer import Monomer
from ..base.team import ControllableTeam, Team
from ..types import AttackTypes, BuffTypes, CharacterData, SkillInfo
from ..base.character import Character


class Moonlark(Character):

    def __init__(self, team: ControllableTeam, data: CharacterData) -> None:
        super().__init__(team, data)
        self.skills = [
            self.skill_common_attack,
            self.skill_special
        ]
        self.final_skill_power = [0, 100]

    async def skill_common_attack(self, monomer: Monomer, _team: Team) -> None:
        await self.power_final_skill(20)
        h = self.attack
        for buff in self.buff_list:
            if buff["buff_type"] == BuffTypes.moonlark_cold_down:
                h -= h * 0.3
        origin_focus = self.focus
        origin_critical_strike_rate = self.critical_strike[0]
        have_missed = False
        for i in range(3):
            is_cirtical, is_missed = (await self.on_attack(AttackTypes.ME, h, monomer))[1:]
            self.focus *= 0.95
            self.critical_strike = self.critical_strike[0] * 1.01, self.critical_strike[1]
            if is_missed:
                self.focus *= 0.8
                have_missed = True
        if not have_missed:
            await monomer.add_buff({
                "buff_type": BuffTypes.lunar_eclipse_cracks,
                "data": {},
                "remain_rounds": 2 if is_cirtical else 3
            })
        self.focus = origin_focus
        self.critical_strike = origin_critical_strike_rate, self.critical_strike[1]

    async def power_final_skill(self, value: int = 17) -> float:
        percent = await super().power_final_skill(value)
        if self.is_final_skill_powered() and self.skill_final not in self.skills:
            self.skills.append(self.skill_final)
        return percent
    
    def reset_final_skill_power(self) -> None:
        if self.skill_final in self.skills:
            self.skills.pop(self.skills.index(self.skill_final))
        return super().reset_final_skill_power()

    async def skill_special(self, monomer: Monomer, team: Team) -> None:
        await self.power_final_skill(30)
        harm = (await self.on_attack(AttackTypes.ME, self.attack * 1.3, monomer))[0]
        if random.random() <= 0.5:
            for buff_index in range(len(monomer.buff_list)):
                buff = monomer.buff_list[buff_index]
                if buff["buff_type"].value[1] and buff["data"].get("removeable", True):
                    monomer.buff_list.pop(buff_index)
                    break
        for buff_index in range(len(monomer.buff_list)):
            buff = monomer.buff_list[buff_index]
            if buff["buff_type"] == BuffTypes.lunar_eclipse_cracks:
                monomers = team.get_monomers()
                monomer_index = monomers.index(monomer)
                if monomer_index - 1 >= 0:
                    await self.on_attack(AttackTypes.ME, harm * 0.16, monomers[monomer_index - 1])
                if monomer_index + 1 < len(monomers):
                    await self.on_attack(AttackTypes.ME, harm * 0.16, monomers[monomer_index + 1])
                await self.on_attack(AttackTypes.ME, harm * 0.8, monomer)
                await self.add_buff({
                    "buff_type": BuffTypes.moonlark_cold_down,
                    "remain_rounds": 1,
                    "data": {}
                }, True)
                buff["remain_rounds"] -= 1
        monomer.clean_buff()
    
    async def skill_final(self, monomer: Monomer, team: Team) -> None:
        if not self.is_final_skill_powered():
            return
        self.reset_final_skill_power()
        harm = (await self.on_attack(AttackTypes.ME, self.attack * 2.2, monomer))[0]
        for buff_index in range(len(monomer.buff_list)):
            buff = monomer.buff_list[buff_index]
            if buff["buff_type"] == BuffTypes.lunar_eclipse_cracks:
                await self.on_attack(AttackTypes.real, harm * 0.5, monomer)
        for monomer in team.monomers:
            await monomer.add_buff({
                "buff_type": BuffTypes.lunar_eclipse_cracks,
                "data": {},
                "remain_rounds": 1
            })

    @staticmethod
    def get_character_id() -> tuple[int, str]:
        return 1, "moonlark"
    
    async def get_skill_info_list(self) -> list[SkillInfo]:
        l: list[SkillInfo] = [
            {
                "cost": -1,
                "monomer": self,
                "occupy_round": True,
                "instant": False,
                "name": await self.get_text("skills.common"),
                "target_type": "enemy"
            },
            {
                "cost": 1,
                "monomer": self,
                "occupy_round": True,
                "instant": False,
                "name": await self.get_text("skills.skill"),
                "target_type": "enemy"
            }
        ]
        if self.skill_final in self.skills:
            l.append({
                "cost": 0,
                "monomer": self,
                "occupy_round": False,
                "instant": True,
                "name": await self.get_text("skills.final_skill"),
                "target_type": "enemy"
            })
        return l


    

