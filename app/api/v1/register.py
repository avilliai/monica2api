"""Registration endpoints matching the genspark2api surface and dashboard requirements."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import verify_api_key
from app.core.dependencies import get_register_service

router = APIRouter()


class RegisterOneBody(BaseModel):
    signup_url: str | None = None
    backend: str | None = Field(default=None, description="auto, camoufox, playwright or http")
    headless: bool | None = None


class RegisterBatchBody(RegisterOneBody):
    count: int = Field(default=1, ge=1, le=1000)
    concurrency: int | None = Field(default=None, ge=1, le=20)
    rate: float = Field(default=20.0, ge=1.0, le=60.0, description="Target registrations per minute")
    register_all: bool = Field(default=False, description="Whether to register all remaining pool accounts")
    mode: str = Field(default="outlook", description="Registration mode: 'outlook' or 'single'")


class OutlookBatchRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=1000)
    rate_per_minute: float | None = Field(default=None)
    rate: float | None = Field(default=None)
    register_all: bool = Field(default=False)
    concurrency: int | None = Field(default=None)
    mode: str = Field(default="outlook")
    backend: str | None = Field(default=None)
    headless: bool | None = Field(default=None)


class OutlookSingleRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    backend: str | None = None
    headless: bool | None = None


def public_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": account.get("email", ""),
        "password": account.get("password", ""),
        "nickname": account.get("nickname", account.get("name", "")),
        "cookie_names": sorted((account.get("cookies") or {}).keys()),
        "created_at": account.get("created_at"),
    }


@router.get("/register/pool-info", tags=["register"])
@router.get("/admin/register/pool-info", tags=["register"])
async def get_register_pool_info(service=Depends(get_register_service)):
    return service.get_pool_info()


@router.post("/register", dependencies=[Depends(verify_api_key)], tags=["register"])
async def register_one(body: RegisterOneBody, service=Depends(get_register_service)):
    account = await service.register_one(
        body.signup_url,
        backend=body.backend,
        headless=body.headless,
    )
    return {"status": "ok", "account": public_account(account)}


@router.post("/register/start", dependencies=[Depends(verify_api_key)], tags=["register"])
@router.post("/admin/register/start", dependencies=[Depends(verify_api_key)], tags=["register"])
async def start_register_job(body: RegisterBatchBody, service=Depends(get_register_service)):
    job = await service.start_job(
        count=body.count,
        concurrency=body.concurrency,
        rate=body.rate,
        register_all=body.register_all,
        mode=body.mode,
        signup_url=body.signup_url,
        backend=body.backend,
        headless=body.headless,
    )
    return {"status": "ok", "job": job}


# ==================== 前端 Dashboard 对齐兼容路由 ====================

@router.post("/admin/register/outlook/batch", dependencies=[Depends(verify_api_key)], tags=["register"])
async def start_outlook_batch_register(body: OutlookBatchRequest, service=Depends(get_register_service)):
    actual_rate = body.rate_per_minute if body.rate_per_minute is not None else (body.rate if body.rate is not None else 20.0)
    job = await service.start_job(
        count=body.count,
        concurrency=body.concurrency,
        rate=actual_rate,
        register_all=body.register_all,
        mode=body.mode,
        backend=body.backend,
        headless=body.headless,
    )
    return {"status": "ok", "job_id": job["id"], "job": job}


@router.get("/admin/register/outlook/status", tags=["register"])
async def get_outlook_register_status(service=Depends(get_register_service)):
    jobs = await service.list_jobs()
    if not jobs:
        return {
            "status": "IDLE",
            "job_id": None,
            "progress": 0,
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "recent_logs": ["[SYSTEM] 注册服务就绪，暂无正在运行的任务"],
        }
    running_jobs = [j for j in jobs if j.get("status") == "running"]
    current_job = running_jobs[-1] if running_jobs else jobs[-1]

    raw_status = str(current_job.get("status", "idle")).upper()
    if raw_status in ("COMPLETED", "SUCCESS"):
        display_status = "FINISHED"
    elif raw_status in ("RUNNING", "QUEUED"):
        display_status = "RUNNING"
    elif raw_status in ("CANCELLED", "CANCELED"):
        display_status = "CANCELLED"
    elif raw_status == "FAILED":
        display_status = "FAILED"
    else:
        display_status = "IDLE"

    return {
        "status": display_status,
        "job_id": current_job.get("id"),
        "progress": current_job.get("completed", 0),
        "total": current_job.get("requested", 0),
        "success_count": current_job.get("succeeded", 0),
        "failed_count": current_job.get("failed", 0),
        "recent_logs": current_job.get("logs", []),
        "job": current_job,
    }


@router.post("/admin/register/outlook/cancel", dependencies=[Depends(verify_api_key)], tags=["register"])
async def cancel_active_outlook_job(service=Depends(get_register_service)):
    jobs = await service.list_jobs()
    running_jobs = [j for j in jobs if j.get("status") == "running"]
    for j in running_jobs:
        await service.cancel_job(j["id"])
    return {"status": "ok", "cancelled": len(running_jobs)}


@router.post("/admin/register/outlook/single", dependencies=[Depends(verify_api_key)], tags=["register"])
async def register_single_outlook(body: OutlookSingleRequest, service=Depends(get_register_service)):
    try:
        account = await service.register_one(
            backend=body.backend,
            headless=body.headless,
        )
        token = account.get("token") or (account.get("cookies") or {}).get("monica_token") or ""
        return {
            "status": "ok",
            "success": True,
            "email": account.get("email", ""),
            "token": token,
            "account": public_account(account),
        }
    except Exception as exc:
        return {
            "status": "error",
            "success": False,
            "message": str(exc),
            "detail": str(exc),
        }


@router.get("/register/jobs", dependencies=[Depends(verify_api_key)], tags=["register"])
@router.get("/admin/register/jobs", dependencies=[Depends(verify_api_key)], tags=["register"])
async def list_register_jobs(service=Depends(get_register_service)):
    return {"jobs": await service.list_jobs()}


@router.get("/register/jobs/{job_id}", dependencies=[Depends(verify_api_key)], tags=["register"])
@router.get("/admin/register/jobs/{job_id}", dependencies=[Depends(verify_api_key)], tags=["register"])
async def get_register_job(job_id: str, service=Depends(get_register_service)):
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Registration job not found")
    return job


@router.post(
    "/register/jobs/{job_id}/cancel",
    dependencies=[Depends(verify_api_key)],
    tags=["register"],
)
@router.post(
    "/admin/register/jobs/{job_id}/cancel",
    dependencies=[Depends(verify_api_key)],
    tags=["register"],
)
async def cancel_register_job(job_id: str, service=Depends(get_register_service)):
    if not await service.cancel_job(job_id):
        raise HTTPException(status_code=404, detail="Active registration job not found")
    return {"status": "ok"}
