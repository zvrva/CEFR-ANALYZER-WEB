from pydantic import BaseModel
from typing import List, Optional, Literal


class HistoryRequest(BaseModel):
    substring: Optional[str] = None
    levels: Optional[List[str]] = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    sort_by: Literal[
        "analyzed_at_asc",
        "analyzed_at_desc",
        "text_asc",
        "text_desc",
        "level_asc",
        "level_desc",
    ] = "analyzed_at_desc"


class RegisterRequest(BaseModel):
    email: Optional[str] = None
    surname: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None

class LoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None