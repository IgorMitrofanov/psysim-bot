from .common import router as common_router
from .feedback import router as feedback_router
from .session import router as session_router
from .profile import router as profile_router
from .referal import router as referal_router

routers = [
    common_router,
    feedback_router,
    session_router,
    profile_router,
    referal_router
]