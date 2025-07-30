import os
import yaml
import json
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from database.models import Base, Persona
from config import config

PERSONAS_DIR = "persones"

async def migrate_personas():
    # Initialize database engine
    engine = create_async_engine(config.DATABASE_URL)
    
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(engine) as session:
        # Load all existing personas from YAML files
        personas_data = load_personas_from_yaml()
        
        for persona_name, data in personas_data.items():
            # Check if persona already exists in DB
            result = await session.execute(
                select(Persona).where(Persona.name == persona_name)
            )  # Fixed: Added missing closing parenthesis
            existing_persona = result.scalars().first()
            
            if existing_persona:
                print(f"Persona {persona_name} already exists, skipping...")
                continue
            
            # Create new persona record with proper JSON serialization
            try:
                persona = Persona(
                    name=persona_name,
                    age=data["persona"].get("age"),
                    gender=data["persona"].get("gender"),
                    profession=data["persona"].get("profession"),
                    appearance=data["persona"].get("appearance"),
                    short_description=data["persona"].get("short_description"),
                    background=data["background"],
                    trauma_history=json.dumps(data["trauma_history"], ensure_ascii=False),
                    current_symptoms=json.dumps(data["current_symptoms"], ensure_ascii=False),
                    goal_session=data["goal_session"],
                    tone=json.dumps(data["tone"], ensure_ascii=False),
                    behaviour_rules=json.dumps(data["behaviour_rules"], ensure_ascii=False),
                    interaction_guide=json.dumps(data["interaction_guide"], ensure_ascii=False),
                    self_reports=json.dumps(data["self_reports"], ensure_ascii=False),
                    escalation=json.dumps(data["escalation"], ensure_ascii=False),
                    triggers=json.dumps(data["triggers"], ensure_ascii=False),
                )
                
                session.add(persona)
                await session.commit()
                print(f"Successfully added persona: {persona_name}")
            except Exception as e:
                await session.rollback()
                print(f"Error adding persona {persona_name}: {str(e)}")
                continue

def load_personas_from_yaml() -> Dict[str, Dict]:
    personas = {}
    if not os.path.exists(PERSONAS_DIR):
        return personas
    
    for filename in os.listdir(PERSONAS_DIR):
        if filename.endswith((".yml", ".yaml")):  # Combined file extensions check
            path = os.path.join(PERSONAS_DIR, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if validate_persona(data):
                        key = data["persona"]["name"]
                        personas[key] = data
                    else:
                        print(f"Warning! Invalid persona format in {filename}")
            except Exception as e:
                print(f"Error loading {filename}: {str(e)}")
    return personas

def validate_persona(data: Dict[str, Any]) -> bool:
    required_top_keys = {
        "persona", "background", "trauma_history", "current_symptoms",
        "goal_session", "tone", "behaviour_rules", "interaction_guide",
        "self_reports", "escalation", "triggers"
    }
    if not all(k in data for k in required_top_keys):
        return False
    if "name" not in data["persona"]:
        return False
    return True

if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate_personas())