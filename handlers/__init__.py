from .common import router as common_router
from .feedback import router as feedback_router
from .session import router as session_router
from .profile import router as profile_router
from .referal import router as referal_router
from .help import router as help_router
from .subscription import router as sub_router
from .not_implemented import router as not_implemented_router

routers = [
    not_implemented_router,
    sub_router,
    common_router,
    feedback_router,
    session_router,
    profile_router,
    referal_router,
    help_router
]