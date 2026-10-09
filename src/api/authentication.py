from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from services.authentication.interface import VerifiedUser

from .dependencies import current_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.get("/me")
def me(user: Annotated[VerifiedUser, Depends(current_user)]):
    return JSONResponse(
        {"id": str(user.id), "email": user.email, "name": user.name},
        headers={"Cache-Control": "no-store"},
    )
