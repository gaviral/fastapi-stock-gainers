import os
import uuid
from fastapi import Depends, Request
from fastapi_users import FastAPIUsers, BaseUserManager, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from sqlalchemy.ext.asyncio import AsyncSession
from .db import User, get_async_session

SECRET = os.getenv("SECRET_KEY", "CHANGEME")

# Dependency to get the user DB adapter
async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)

# User Manager
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Request = None):
        print(f"User {user.email} registered.")

async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)

# Authentication backend: using cookie transport with JWT strategy
cookie_transport = CookieTransport(
    cookie_name="auth", 
    cookie_max_age=3600,
    cookie_secure=False,  # Set to True in production with HTTPS
    cookie_httponly=True
)

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

# Instantiate FastAPIUsers
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend]
)

# Dependency to retrieve the current active user
current_active_user = fastapi_users.current_user(active=True) 