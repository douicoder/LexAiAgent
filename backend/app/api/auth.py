from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials

from app.dto.auth_dto import AuthResponseDTO, LoginDTO, RegisterDTO, UserProfileDTO
from app.helpers.auth_helper import AuthHelper
from app.helpers.auth_helper import security

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponseDTO, status_code=status.HTTP_201_CREATED)
async def register(dto: RegisterDTO) -> AuthResponseDTO:
    payload = await AuthHelper.supabase_sign_up(
        email=str(dto.email),
        password=dto.password,
        full_name=dto.full_name,
        preferred_language=dto.preferred_language.value,
    )
    return AuthResponseDTO(**AuthHelper.supabase_auth_response(payload))


@router.get("/me", response_model=UserProfileDTO)
async def me(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserProfileDTO:
    user = await AuthHelper.get_current_supabase_user(credentials)
    return UserProfileDTO(**AuthHelper.supabase_profile_response(user))


@router.post("/login", response_model=AuthResponseDTO)
async def login(dto: LoginDTO) -> AuthResponseDTO:
    payload = await AuthHelper.supabase_sign_in(email=str(dto.email), password=dto.password)
    return AuthResponseDTO(**AuthHelper.supabase_auth_response(payload))
