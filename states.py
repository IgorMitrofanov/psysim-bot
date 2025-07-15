from aiogram.fsm.state import State, StatesGroup

class MainMenu(StatesGroup):
    choosing = State()
    feedback = State()
    suggestion = State()
    error_report = State()
    free_session_resistance = State()
    free_session_emotion = State()
    free_session_format = State()
    free_session_confirm = State()