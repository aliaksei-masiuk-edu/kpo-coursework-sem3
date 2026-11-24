import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class LoginInput(InputModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class UserInput(InputModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,40}$")
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["admin", "operator"] = "operator"


class OrderInput(InputModel):
    item_name: str = Field(min_length=1, max_length=100)
    brand: str = Field(min_length=1, max_length=100)
    owner_name: str = Field(min_length=2, max_length=150)
    owner_phone: str = Field(min_length=7, max_length=30)
    cost: Decimal = Field(ge=0, le=Decimal("99999999.99"), decimal_places=2)
    received_on: date
    planned_on: date

    @field_validator("owner_phone")
    @classmethod
    def valid_phone(cls, value):
        if (
            not re.fullmatch(r"\+?[0-9 ()-]+", value)
            or not 7 <= len(re.sub(r"\D", "", value)) <= 15
        ):
            raise ValueError("Телефон должен содержать от 7 до 15 цифр")
        return value

    @model_validator(mode="after")
    def valid_dates(self):
        if self.planned_on < self.received_on:
            raise ValueError("Плановая дата выдачи не может быть раньше приёмки")
        return self


class CompletionInput(InputModel):
    completed_on: date | None = None


class ActiveInput(InputModel):
    is_active: bool
