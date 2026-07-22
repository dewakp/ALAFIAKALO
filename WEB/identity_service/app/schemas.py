"""Identity API request/response schemas."""

from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = None
    biological_sex: str | None = None
    account_role: str = "patient"
    phone: str | None = Field(default=None, max_length=32)  # E.164, an alternate login id


class LoginRequest(BaseModel):
    identifier: str            # email OR username
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ResetRequest(BaseModel):
    identifier: str            # email OR username


class ResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class MigratePasswordRequest(BaseModel):
    """Internal: an app that already verified a legacy (Firebase) password sets
    the credential in the IdP, completing the migration. Guarded by a secret."""
    identifier: str            # email OR username
    new_password: str = Field(min_length=1, max_length=128)
    secret: str


class ProfileUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    biological_sex: str | None = None


class ProfileOut(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    gender: str | None = None
    biological_sex: str | None = None
    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: str
    email: str
    username: str
    account_role: str
    tier: str
    email_verified: bool
    system_id: str | None = None
    created_at: datetime
    profile: ProfileOut | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResult(TokenOut):
    user: UserOut


class LookupOut(BaseModel):
    email_taken: bool
    username_taken: bool


class SidVerifyRequest(BaseModel):
    sid: str


class SidVerifyOut(BaseModel):
    valid: bool
    segments: dict
