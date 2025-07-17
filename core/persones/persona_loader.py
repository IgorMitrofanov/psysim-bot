import os
import yaml
from typing import Dict, Any

PERSONAS_DIR = "persones" 

def validate_persona(data: Dict[str, Any]) -> bool:
    required_top_keys = {
        "persona", "background", "trauma_history", "current_symptoms",
        "goal_session", "tone", "behaviour_rules", "interaction_guide",
        "self_reports", "escalation", "triggers"
    }
    if not all(k in data for k in required_top_keys):
        return False
    if "name" not in data["persona"] or "age" not in data["persona"]:
        return False
    return True

def load_personas() -> Dict[str, Dict]:
    personas = {}
    if not os.path.exists(PERSONAS_DIR):
        return personas
    for filename in os.listdir(PERSONAS_DIR):
        if filename.endswith(".yml") or filename.endswith(".yaml"):
            path = os.path.join(PERSONAS_DIR, filename)
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if validate_persona(data):
                    key = data["persona"]["name"]
                    personas[key] = data
                else:
                    print(f"Warning! Invalid persona format in {filename}")
    return personas
