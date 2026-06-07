import secrets
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.db import Repository


SESSION_COOKIE = "x2tg_session"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, repo: Repository, secret_key: str):
        self.repo = repo
        self.serializer = URLSafeSerializer(secret_key, salt="x2tg-session")

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return pwd_context.verify(password, password_hash)

    def create_admin(self, username: str, password: str) -> None:
        self.repo.create_or_update_admin(username, self.hash_password(password))

    def authenticate(self, username: str, password: str) -> bool:
        admin = self.repo.get_admin()
        if not admin:
            return False
        if username != admin["username"]:
            return False
        return self.verify_password(password, admin["password_hash"])

    def login_response(self, redirect_to: str = "/") -> RedirectResponse:
        response = RedirectResponse(redirect_to, status_code=303)
        token = self.serializer.dumps({"admin": True, "nonce": secrets.token_hex(8)})
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
        )
        return response

    def logout_response(self) -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    def is_authenticated(self, request: Request) -> bool:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return False
        try:
            data = self.serializer.loads(token)
        except BadSignature:
            return False
        return bool(data.get("admin"))


def generate_secret_key() -> str:
    return secrets.token_urlsafe(32)

