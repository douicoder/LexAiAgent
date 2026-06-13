from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.services.supabase_db import SupabaseService

security = HTTPBearer()


class AuthHelper:
    @staticmethod
    def _supabase_auth_url(path: str) -> str:
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase auth is not configured",
            )
        return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/{path.lstrip('/')}"

    @staticmethod
    def _supabase_headers(token: str | None = None) -> dict[str, str]:
        if not settings.SUPABASE_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supabase auth is not configured",
            )

        bearer = token or settings.SUPABASE_KEY
        return {
            "apikey": settings.SUPABASE_KEY,
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _supabase_error(response: httpx.Response, fallback: str) -> HTTPException:
        try:
            body = response.json()
        except ValueError:
            body = {}

        message = body.get("msg") or body.get("message") or body.get("error_description") or fallback
        return HTTPException(status_code=response.status_code, detail=message)

    @staticmethod
    async def supabase_sign_up(email: str, password: str, full_name: str, preferred_language: str) -> dict:
        payload = {
            "email": email,
            "password": password,
            "data": {
                "full_name": full_name,
                "preferred_language": preferred_language,
            },
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                AuthHelper._supabase_auth_url("signup"),
                headers=AuthHelper._supabase_headers(),
                json=payload,
            )

        if response.status_code >= 400:
            raise AuthHelper._supabase_error(response, "Unable to register user")
        return response.json()

    @staticmethod
    async def supabase_sign_in(email: str, password: str) -> dict:
        payload = {"email": email, "password": password}

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                AuthHelper._supabase_auth_url("token?grant_type=password"),
                headers=AuthHelper._supabase_headers(),
                json=payload,
            )

        if response.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return response.json()

    @staticmethod
    async def supabase_get_user(access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                AuthHelper._supabase_auth_url("user"),
                headers=AuthHelper._supabase_headers(access_token),
            )

        if response.status_code >= 400:
            raise AuthHelper._supabase_error(response, "Invalid or expired token")
        return response.json()

    @staticmethod
    def supabase_auth_response(payload: dict) -> dict:
        user = payload.get("user") or payload
        metadata = user.get("user_metadata") or {}
        user_id = user.get("id")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supabase did not return a user ID.",
            )

        local_token = AuthHelper.create_jwt(user_id)

        return {
            "email": user.get("email"),
            "full_name": metadata.get("full_name") or "",
            "access_token": local_token,
            "token_type": "bearer",
        }

    @staticmethod
    async def get_current_user_id(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> str:
        payload = AuthHelper.decode_jwt(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id

    @staticmethod
    def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> dict:
        payload = AuthHelper.decode_jwt(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        try:
            parsed_user_id = UUID(user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

        supabase = SupabaseService()
        user = supabase.get_user(str(parsed_user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user

    @staticmethod
    def create_jwt(user_id: str) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
        payload = {"sub": user_id, "exp": expires_at}
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_jwt(token: str) -> dict:
        try:
            return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            ) from exc
