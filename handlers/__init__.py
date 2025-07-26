from .common import router as common_router
from .feedback import router as feedback_router
from .session import interaction_router
from .session import confirm_router
from .session import random_router
from .profile import router as profile_router
from .referal import router as referal_router
from .help import router as help_router
from .subscription import router as sub_router
from .not_implemented import router as not_implemented_router
from .my_sessions import router as my_sessions_router

routers = [
    not_implemented_router,
    sub_router,
    common_router,
    interaction_router,
    confirm_router,
    random_router,
    feedback_router,
    profile_router,
    my_sessions_router,
    referal_router,
    help_router
]