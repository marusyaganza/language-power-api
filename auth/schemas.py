from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr

# Counted in characters (code points), like Python's len().
MIN_PASSWORD_LENGTH = 8
# bcrypt only hashes the first 72 bytes and, since bcrypt 5, raises on longer
# input. Bytes, not characters: "é" is two bytes in UTF-8.
MAX_PASSWORD_BYTES = 72


def _long_enough(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return value


def _fits_bcrypt(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return value


def _lowercase(value: str) -> str:
    return value.lower()


# A password being checked at login: only what bcrypt can hash. A too-short
# one just fails to match, so login does not reveal the signup rules.
Password = Annotated[str, AfterValidator(_fits_bcrypt)]
# A password for a new account.
NewPassword = Annotated[str, AfterValidator(_long_enough), AfterValidator(_fits_bcrypt)]
# EmailStr already trims spaces and lowercases the domain; the part before the
# "@" is lowercased too, so "Foo@x.com" and "foo@x.com" are one account. Stored
# emails are lowercase (ck_users_email_lowercase).
Email = Annotated[EmailStr, AfterValidator(_lowercase)]


class UserCreate(BaseModel):
    email: Email
    password: NewPassword


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr


class LoginRequest(BaseModel):
    email: Email
    password: Password
