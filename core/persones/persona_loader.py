from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Persona
from typing import Dict, Optional
import json

class PersonaLoader:
    def __init__(self, admin_engine):
        self.admin_engine = admin_engine
        self._cached_personas = None
    
    async def load_all_personas(self) -> Dict[str, Dict]:
        async with AsyncSession(self.admin_engine) as session:
            result = await session.execute(select(Persona))
            personas = result.scalars().all()
            
            personas_dict = {}
            for persona in personas:
                personas_dict[persona.name] = self._convert_to_legacy_format(persona)
            
            self._cached_personas = personas_dict
            return personas_dict
    
    async def get_persona(self, name: str) -> Optional[Dict]:
        if self._cached_personas and name in self._cached_personas:
            return self._cached_personas[name]
            
        async with AsyncSession(self.admin_engine) as session:
            result = await session.execute(
                select(Persona).where(Persona.name == name)
            )
            persona = result.scalars().first()
            if persona:
                return self._convert_to_legacy_format(persona)
            return None
    
    def _convert_to_legacy_format(self, persona: Persona) -> Dict:
        """Convert database Persona object to legacy YAML format"""
        return {
            "persona": {
                "name": persona.name,
                "age": persona.age,
                "gender": persona.gender,
                "profession": persona.profession,
                "appearance": persona.appearance,
                "short_description": persona.short_description,
            },
            "background": persona.background,
            "trauma_history": json.loads(persona.trauma_history) if persona.trauma_history else [],
            "current_symptoms": json.loads(persona.current_symptoms) if persona.current_symptoms else {},
            "goal_session": persona.goal_session,
            "tone": json.loads(persona.tone) if persona.tone else {},
            "behaviour_rules": json.loads(persona.behaviour_rules) if persona.behaviour_rules else [],
            "interaction_guide": json.loads(persona.interaction_guide) if persona.interaction_guide else {},
            "self_reports": json.loads(persona.self_reports) if persona.self_reports else [],
            "escalation": json.loads(persona.escalation) if persona.escalation else [],
            "triggers": json.loads(persona.triggers) if persona.triggers else [],
        }