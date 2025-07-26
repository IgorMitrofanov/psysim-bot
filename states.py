from aiogram.fsm.state import State, StatesGroup

class MainMenu(StatesGroup):
    choosing = State()
    feedback = State()
    suggestion = State()
    error_report = State()
    session_resistance = State()
    session_emotion = State()
    session_format = State()
    session_persona = State()
    session_confirm = State()
    in_session = State()
    
    
class ProfileStates(StatesGroup):
    viewing_sessions = State()
    viewing_session_details = State()