"""FastAPI application: JSON API under /api, built dashboard served at /."""
import asyncio
import base64
import contextlib
import logging
import secrets
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.contacts.registry import build_providers
from app.excel import ATTRIBUTION, clean_filename, write_workbook
from app.jobs import JobManager, is_valid_job_id
from app.models import JobState, JobStatus, ResultRecord, SearchRequest, clean_employee
from app.sheets import SheetStore
from app.refresh import refresh_loop
from app.voa.description_codes import description_codes
from app.voa.repository import DatasetMissingError

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")

MAX_ACTIVE_JOBS = 10  # queued + running, across all users
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
UK_TZ = ZoneInfo("Europe/London")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    manager = JobManager(settings, build_providers(settings))
    app.state.jobs = manager
    app.state.sheets = SheetStore(settings.app_db_path)
    asyncio.get_running_loop().run_in_executor(None, manager.voa.warm_up)  # town/postcode lists for type-ahead
    manager.cleanup_exports()
    manager.resume_interrupted()

    async def periodic_cleanup():
        while True:
            await asyncio.sleep(3600)
            manager.cleanup_exports()

    def places_updated():
        manager.providers = build_providers(settings)

    tasks = [asyncio.create_task(periodic_cleanup()), asyncio.create_task(refresh_loop(settings, places_updated))]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Copilot", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


# ---------- middleware ----------
@app.middleware("http")
async def security(request: Request, call_next):
    if settings.app_password and request.url.path != "/api/health":
        if not _authorised(request.headers.get("authorization", "")):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Copilot"'})
    response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:",
    })
    return response


def _authorised(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        _, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        return False
    return secrets.compare_digest(password.encode(), settings.app_password.encode())


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    messages = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"] if p != "body")
        msg = err["msg"].removeprefix("Value error, ")
        messages.append(f"{field.replace('_', ' ').capitalize()}: {msg}" if field else msg)
    return JSONResponse(status_code=422, content={"detail": messages})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": ["Internal server error."]})


# ---------- API ----------
def _jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def _job_or_404(request: Request, job_id: str) -> JobStatus:
    status = _jobs(request).get(job_id) if is_valid_job_id(job_id) else None
    if status is None:
        raise HTTPException(404, detail=["Search not found (it may have expired)."])
    return status


@app.get("/api/health")
def health(request: Request):
    try:
        meta = _jobs(request).voa.meta()
    except DatasetMissingError:
        meta = None
    return {"status": "ok" if meta else "dataset_missing", "voa_dataset": meta}


@app.get("/api/meta")
def meta(request: Request):
    jobs = _jobs(request)
    try:
        voa = jobs.voa.meta()
    except DatasetMissingError:
        voa = None
    return {
        "voa_dataset": voa,
        "contact_providers": [p.name for p in jobs.providers],
        "max_results_per_search": settings.max_results_per_search,
        "export_retention_hours": settings.export_retention_hours,
        "description_codes": [{"code": c, "label": label} for c, label in description_codes().items()],
    }


def _employee(name: str | None) -> str:
    try:
        return clean_employee(name or "")
    except ValueError as e:
        raise HTTPException(422, detail=[str(e)]) from None


@app.get("/api/suggest/towns")
def suggest_towns(request: Request, q: str = Query("", max_length=60)):
    try:
        return _jobs(request).voa.suggest_towns(q)
    except DatasetMissingError:
        return []


@app.get("/api/suggest/postcodes")
def suggest_postcodes(request: Request, town: str = Query("", max_length=60), q: str = Query("", max_length=10)):
    try:
        return _jobs(request).voa.suggest_postcodes(town, q)
    except DatasetMissingError:
        return []


@app.post("/api/jobs", status_code=202, response_model=JobStatus)
async def create_job(req: SearchRequest, request: Request, employee: str = ""):
    jobs = _jobs(request)
    if sum(j.state in (JobState.QUEUED, JobState.RUNNING) for j in jobs.recent(50)) >= MAX_ACTIVE_JOBS:
        raise HTTPException(429, detail=["Too many searches are running. Please wait for one to finish."])
    return jobs.submit(req, employee=_employee(employee) if employee else "")


@app.get("/api/jobs", response_model=list[JobStatus])
def list_jobs(request: Request, employee: str | None = None):
    return _jobs(request).recent(30, employee=_employee(employee) if employee else None)


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, request: Request):
    _job_or_404(request, job_id)
    if not _jobs(request).delete(job_id):
        raise HTTPException(409, detail=["This search is still running. Delete it once it has finished."])
    return Response(status_code=204)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str, request: Request):
    return _job_or_404(request, job_id)


@app.get("/api/jobs/{job_id}/records")
def get_records(
    job_id: str, request: Request,
    has_phone: bool | None = None,
    offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000),
):
    _job_or_404(request, job_id)
    records: list[ResultRecord] = _jobs(request).records(job_id)
    if has_phone is not None:
        records = [r for r in records if bool(r.phone) == has_phone]
    return {"total": len(records), "items": records[offset: offset + limit]}


@app.post("/api/jobs/{job_id}/retry", response_model=JobStatus)
async def retry_job(job_id: str, request: Request):
    _job_or_404(request, job_id)
    return _jobs(request).retry(job_id)


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str, request: Request, filename: str | None = Query(None, max_length=120)):
    _job_or_404(request, job_id)
    found = _jobs(request).export(job_id)
    if not found:
        raise HTTPException(404, detail=["No spreadsheet is available for this search."])
    path, default_name = found
    return FileResponse(path, filename=clean_filename(filename, default_name), media_type=XLSX)


# ---------- My sheet ----------
def _sheets(request: Request) -> SheetStore:
    return request.app.state.sheets


class _EmployeeBody(BaseModel):
    employee: str = Field(max_length=60)

    @field_validator("employee")
    @classmethod
    def _valid(cls, v: str) -> str:
        return clean_employee(v)


class SheetAdd(_EmployeeBody):
    job_id: str
    only_with_phone: bool = True


class SheetRemove(_EmployeeBody):
    uarns: list[str] = Field(max_length=5000)


class SheetDownload(_EmployeeBody):
    filename: str = Field("", max_length=120)
    uarns: list[str] | None = Field(None, max_length=20000)  # None = whole sheet


@app.get("/api/sheet")
def get_sheet(request: Request, employee: str):
    rows = _sheets(request).rows(_employee(employee))
    return {
        "total": len(rows),
        "items": [r.record.model_dump(mode="json") | {"search": r.search, "added": r.added} for r in rows],
    }


@app.post("/api/sheet/add")
def add_to_sheet(body: SheetAdd, request: Request):
    status = _job_or_404(request, body.job_id)
    if status.state in (JobState.QUEUED, JobState.RUNNING):
        raise HTTPException(409, detail=["Wait for the search to finish before adding it to your sheet."])
    records = _jobs(request).records(body.job_id)
    if body.only_with_phone:
        records = [r for r in records if r.phone]
    added, skipped = _sheets(request).add(body.employee, records, status.label)
    return {"added": added, "already_in_sheet": skipped, "total": len(_sheets(request).rows(body.employee))}


@app.post("/api/sheet/remove")
def remove_from_sheet(body: SheetRemove, request: Request):
    removed = _sheets(request).remove(body.employee, body.uarns)
    return {"removed": removed, "total": len(_sheets(request).rows(body.employee))}


@app.delete("/api/sheet")
def clear_sheet(request: Request, employee: str):
    return {"removed": _sheets(request).clear(_employee(employee)), "total": 0}


@app.post("/api/sheet/download")
def download_sheet(body: SheetDownload, request: Request, background: BackgroundTasks):
    rows = _sheets(request).rows(body.employee)
    if body.uarns is not None:
        wanted = set(body.uarns)
        rows = [r for r in rows if r.record.uarn in wanted]
    if not rows:
        raise HTTPException(404, detail=["There are no rows to download."])
    now = datetime.now(UK_TZ)
    default = f"{body.employee} - My sheet - {now:%d %b %Y}.xlsx"
    about = [
        ("Employee", body.employee),
        ("Generated", now.strftime("%d %b %Y %H:%M %Z")),
        ("Rows", f"{len(rows):,} properties from {len({r.search for r in rows}):,} search(es)"),
        *ATTRIBUTION,
    ]
    tmp = Path(tempfile.mkdtemp(dir=settings.export_dir)) / "sheet.xlsx"
    write_workbook(settings.template_path, tmp, rows, f"RV ({settings.voa_list_year} list)", about)
    background.add_task(lambda: (tmp.unlink(missing_ok=True), tmp.parent.rmdir()))
    return FileResponse(tmp, filename=clean_filename(body.filename, default), media_type=XLSX)


# ---------- dashboard ----------
if settings.frontend_dist.exists():
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="dashboard")
