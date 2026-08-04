"""Automatic order audit and manual retry API."""
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.session_auth import require_authenticated_session
from src.services.auto_order_service import auto_order_master_enabled
from src.services.manual_order_retry_service import retry_order_record
from src.services.order_record_service import get_order_record, list_order_records


router = APIRouter(
    prefix="/api/orders",
    tags=["orders"],
    dependencies=[Depends(require_authenticated_session)],
)


@router.get("", response_model=dict)
async def get_orders(
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
):
    try:
        items, total = list_order_records(status=status, page=page, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.post("/{record_id}/retry", response_model=dict)
async def retry_order(record_id: int):
    if not auto_order_master_enabled():
        raise HTTPException(status_code=409, detail="自动锁单全局总开关未开启。")
    record = get_order_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="锁单记录不存在。")
    if record["status"] not in {"blocked", "failed", "skipped"}:
        raise HTTPException(status_code=409, detail="当前锁单状态不允许重试。")
    try:
        return {"order": await retry_order_record(record)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
