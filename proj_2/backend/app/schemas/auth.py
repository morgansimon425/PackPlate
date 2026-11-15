"""Request and response models for accounts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Credentials(BaseModel):
    """A username and password, for signing up or logging in. Extra fields are rejected.

    Lengths are checked loosely here and properly in services.auth, so the
    error message can say what's wrong.
    """

    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=100)
    password: str = Field(max_length=1000)


class PasswordConfirm(BaseModel):
    """The current password, to confirm deleting the account."""

    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=1000)


class AccountSettings(BaseModel):
    """Settings the logged-in user can change. Extra fields are rejected."""

    model_config = ConfigDict(extra="forbid")
    open_to_chat: bool


class UserOut(BaseModel):
    """The signed-in account. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    open_to_chat: bool  # shown in chat's list of people to invite; off by default
    created_at: datetime
