from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from orderpulse.csv_import import CsvTooLargeError, CsvValidationError, import_orders
from orderpulse.database import get_session
from orderpulse.schemas import ImportResult

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/import")
def upload_orders(
    file: Annotated[UploadFile, File(description="UTF-8 order CSV, up to 5 MiB")],
    session: Annotated[Session, Depends(get_session)],
) -> ImportResult:
    """Validate and import an order CSV in one transaction."""
    try:
        return import_orders(file.file, session)
    except CsvTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except CsvValidationError as exc:
        detail: dict[str, str | int] = {"message": str(exc)}
        if exc.line is not None:
            detail["line"] = exc.line
        if exc.field is not None:
            detail["field"] = exc.field
        raise HTTPException(status_code=422, detail=detail) from exc
