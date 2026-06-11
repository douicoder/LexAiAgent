import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.dto.auth_dto import AuthResponseDTO, LoginDTO, RegisterDTO, UserProfileDTO
from app.helpers.auth_helper import AuthHelper
from app.helpers.auth_helper import security
from app.mapper.auto_mapper import AutoMapper
from app.services.supabase_db import SupabaseService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponseDTO, status_code=status.HTTP_201_CREATED)
async def register(dto: RegisterDTO) -> AuthResponseDTO:
    payload = await AuthHelper.supabase_sign_up(
        email=str(dto.email),
        password=dto.password,
        full_name=dto.full_name,
        preferred_language=dto.preferred_language.value,
    )
    result = AuthHelper.supabase_auth_response(payload)
    user_id = AuthHelper.decode_jwt(result["access_token"]).get("sub")
    if not user_id:
        raise HTTPException(status_code=500, detail="Failed to extract user ID")

    supabase = SupabaseService()
    existing = supabase.get_user(user_id)
    if not existing:
        supabase.create_user(
            user_id=user_id,
            email=str(dto.email),
            hashed_password=hashlib.sha256(dto.password.encode()).hexdigest(),
            full_name=dto.full_name,
            preferred_language=dto.preferred_language.value,
        )

    return AuthResponseDTO(**result)


@router.get("/me", response_model=UserProfileDTO)
async def me(
    current_user_id: str = Depends(AuthHelper.get_current_user_id),
) -> UserProfileDTO:
    supabase = SupabaseService()
    user = supabase.get_user(current_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    case_count = supabase.count_cases(current_user_id)
    return AutoMapper.user_to_profile_dto(user, case_count)


@router.post("/login", response_model=AuthResponseDTO)
async def login(dto: LoginDTO) -> AuthResponseDTO:
    payload = await AuthHelper.supabase_sign_in(email=str(dto.email), password=dto.password)
    result = AuthHelper.supabase_auth_response(payload)
    user_id = AuthHelper.decode_jwt(result["access_token"]).get("sub")
    if not user_id:
        raise HTTPException(status_code=500, detail="Failed to extract user ID")
    full_name = result.get("full_name") or ""

    supabase = SupabaseService()
    existing = supabase.get_user(user_id)
    if not existing:
        user_data = payload.get("user") or payload
        metadata = user_data.get("user_metadata") or {}
        preferred_language = metadata.get("preferred_language", "en")
        supabase.create_user(
            user_id=user_id,
            email=str(dto.email),
            hashed_password=hashlib.sha256(dto.password.encode()).hexdigest(),
            full_name=full_name,
            preferred_language=preferred_language,
        )

    return AuthResponseDTO(**result)
