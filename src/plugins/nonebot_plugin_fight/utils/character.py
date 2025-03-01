

import json
from ..base.team import ControllableTeam
from ..base.character import Character
from ..models import ControllableCharacter
from ..characters import CHARACTERS


async def get_controllable_character(model: ControllableCharacter, team: ControllableTeam) -> Character:
    for chatacter in CHARACTERS:
        if chatacter.get_character_id()[1] == model.character_type:
            return chatacter(team, {
                "buff": json.loads(model.buff),
                "current_hp": model.current_hp,
                "weapon": {
                    "damage_level": model.weapon_damage,
                    "experience": model.weapon_experience,
                    "talent_level": json.loads(model.weapon_talent_level)
                },
                "experience": model.experience,
                "fav": model.fav or 0.0,
                "talent_level": json.loads(model.talent_level),
                "equipment": [
                    # TODO
                ]
            })
    raise ValueError
    

