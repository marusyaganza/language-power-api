from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, ConfigDict

# bcrypt only hashes the first 72 bytes and, since bcrypt 5, raises on longer
# input. Bytes, not characters: "é" is two bytes in UTF-8.
MAX_PASSWORD_BYTES = 72


def _fits_bcrypt(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return value


Password = Annotated[str, AfterValidator(_fits_bcrypt)]


class UserCreate(BaseModel):
    email: EmailStr
    password: Password

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: Password
