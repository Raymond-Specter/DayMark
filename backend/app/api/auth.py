from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from .. import accounts
from ..runtime import cloud_enabled

router = APIRouter(prefix="/api/auth", tags=["Account"])


class Credentials(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,32}$")
    password: SecretStr = Field(min_length=12, max_length=128)


class Registration(Credentials):
    invite_code: SecretStr = Field(min_length=16, max_length=200)


def require_cloud():
    if not cloud_enabled():
        raise HTTPException(404, "Accounts are only enabled in cloud mode")


def issue_cookie(response, user):
    response.set_cookie(accounts.COOKIE, accounts.create_session(user["id"]),
                        max_age=accounts.SESSION_SECONDS, httponly=True, samesite="lax",
                        secure=True, path="/")
    response.headers["Cache-Control"] = "no-store"


@router.get("/session")
def session(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"mode": "cloud" if cloud_enabled() else "local",
            "user": accounts.session_user(request.cookies.get(accounts.COOKIE)) if cloud_enabled() else None}


@router.post("/register", status_code=201)
def register(data: Registration, request: Request, response: Response):
    require_cloud()
    accounts.rate_limit("register:" + (request.client.host if request.client else "unknown"))
    user = accounts.register(data.username.lower(), data.password.get_secret_value(), data.invite_code.get_secret_value())
    from ..database import tenant_factory
    tenant_factory(user["id"])
    issue_cookie(response, user)
    return user


@router.post("/login")
def login(data: Credentials, request: Request, response: Response):
    require_cloud()
    accounts.rate_limit("login:" + data.username.lower())
    accounts.rate_limit("login-ip:" + (request.client.host if request.client else "unknown"))
    user = accounts.login(data.username.lower(), data.password.get_secret_value())
    issue_cookie(response, user)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    require_cloud()
    accounts.revoke_session(request.cookies.get(accounts.COOKIE))
    response.delete_cookie(accounts.COOKIE, path="/")
