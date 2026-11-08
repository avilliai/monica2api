"""OpenAI-compatible model listing."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.core.auth import verify_bearer_token
from app.models.openai_types import Model, ModelList
from app.services.monica_client import OFFICIAL_MODELS

router = APIRouter()


@router.get("/models", response_model=ModelList)
async def list_models(_: str = Depends(verify_bearer_token)):
    models = [
        Model(id=model_id, object="model", created=int(time.time()), owned_by="monica")
        for model_id in OFFICIAL_MODELS
    ]
    return ModelList(object="list", data=models)
