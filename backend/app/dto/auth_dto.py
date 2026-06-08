from enum import Enum

from pydantic import BaseModel, EmailStr, field_validator


class LanguageEnum(str, Enum):
    EN = "en"
    HI = "hi"


class RegisterDTO(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    preferred_language: LanguageEnum = LanguageEnum.EN

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class LoginDTO(BaseModel):
    email: EmailStr
    password: str


class AuthResponseDTO(BaseModel):
    email: str
    full_name: str
    access_token: str
    token_type: str = "bearer"


class UserProfileDTO(BaseModel):
    email: str
    full_name: str
    preferred_language: LanguageEnum
    case_count: int
