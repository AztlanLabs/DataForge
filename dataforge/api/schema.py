"""Engine API schemas — Pydantic DTOs for JSON-RPC 2.0 transport."""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ApiRequest(BaseModel):
    def to_jsonrpc(self, request_id: int = 1, method: Optional[str] = None) -> Dict[str, Any]:
        m = method or getattr(self, "__method__", None)
        if m is None:
            name = self.__class__.__name__
            if name.endswith("Request"):
                name = name[: -len("Request")]
            m = name.lower()
        return {"jsonrpc": "2.0", "id": request_id, "method": m, "params": self.model_dump(mode="python", exclude_none=False)}

    def to_payload(self, request_id: int = 1, method: Optional[str] = None) -> Dict[str, Any]:
        return self.to_jsonrpc(request_id=request_id, method=method)

    def to_jsonrpc_payload(self, request_id: int = 1, method: Optional[str] = None) -> Dict[str, Any]:
        return self.to_jsonrpc(request_id=request_id, method=method)


def to_jsonrpc_payload(request: BaseModel, request_id: int = 1, method: Optional[str] = None) -> Dict[str, Any]:
    m = method
    if m is None:
        m = getattr(request, "__method__", None)
        if m is None:
            name = request.__class__.__name__
            if name.endswith("Request"):
                name = name[: -len("Request")]
            m = name.lower()
    params = request.model_dump(mode="python", exclude_none=False) if isinstance(request, BaseModel) else dict(request)
    return {"jsonrpc": "2.0", "id": request_id, "method": m, "params": params}


class ScanRequest(ApiRequest):
    __method__ = "scan"
    root: str = Field(..., min_length=1)
    recursive: bool = Field(default=True)
    max_depth: int = Field(default=-1, ge=-1)
    provider: str = Field(default="local", min_length=1)

    @field_validator("root")
    @classmethod
    def _strip_root(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("root must be a non-empty path")
        return v


class SearchRequest(ApiRequest):
    __method__ = "search"
    root: str = Field(..., min_length=1)
    recursive: bool = Field(default=True)
    max_depth: int = Field(default=-1, ge=-1)
    provider: str = Field(default="local")
    name_pattern: Optional[str] = Field(default=None)
    use_regex: bool = Field(default=False)
    extensions: Optional[List[str]] = Field(default=None)
    content_text: Optional[str] = Field(default=None)
    content_is_regex: bool = Field(default=False)
    case_sensitive: bool = Field(default=False)
    min_size_bytes: Optional[int] = Field(default=None, ge=0)
    max_size_bytes: Optional[int] = Field(default=None, ge=0)
    newer_than_days: Optional[float] = Field(default=None, ge=0)
    older_than_days: Optional[float] = Field(default=None, ge=0)
    sort_key: Optional[str] = Field(default=None)
    reverse: bool = Field(default=False)
    limit: Optional[int] = Field(default=None, ge=1)

    @field_validator("root")
    @classmethod
    def _strip_root(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("root must be a non-empty path")
        return v


class DupesRequest(ApiRequest):
    __method__ = "dupes"
    root: str = Field(..., min_length=1)
    recursive: bool = Field(default=True)
    max_depth: int = Field(default=-1, ge=-1)
    provider: str = Field(default="local")
    hash_algorithm: str = Field(default="sha256")
    verify_content: bool = Field(default=False)

    @field_validator("root")
    @classmethod
    def _strip_root(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("root must be a non-empty path")
        return v

    @field_validator("hash_algorithm")
    @classmethod
    def _validate_algo(cls, v: str) -> str:
        allowed = {"md5", "sha1", "sha256", "sha512", "blake2b"}
        if v.lower() not in allowed:
            raise ValueError(f"hash_algorithm must be one of {sorted(allowed)}")
        return v.lower()


class HashRequest(ApiRequest):
    __method__ = "hash"
    path: Optional[str] = Field(default=None)
    paths: Optional[List[str]] = Field(default=None)
    algo: str = Field(default="sha256")
    algos: Optional[List[str]] = Field(default=None)

    @field_validator("algo")
    @classmethod
    def _validate_algo(cls, v: str) -> str:
        allowed = {"md5", "sha1", "sha256", "sha512", "blake2b"}
        if v.lower() not in allowed:
            raise ValueError(f"algo must be one of {sorted(allowed)}")
        return v.lower()

    @field_validator("algos")
    @classmethod
    def _validate_algos(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        allowed = {"md5", "sha1", "sha256", "sha512", "blake2b"}
        out: List[str] = []
        for a in v:
            if a.lower() not in allowed:
                raise ValueError(f"algos contains unsupported algorithm: {a!r}")
            out.append(a.lower())
        return out

    def model_post_init(self, __context: Any) -> None:
        pass


class IntegrityRequest(ApiRequest):
    __method__ = "integrity"
    path: str = Field(..., min_length=1)
    snapshot: str = Field(..., min_length=1)
    operation: Literal["create", "verify", "check"] = Field(default="create")
    algorithm: str = Field(default="sha256")

    @field_validator("path", "snapshot")
    @classmethod
    def _strip_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be a non-empty path")
        return v

    @field_validator("algorithm")
    @classmethod
    def _validate_algo(cls, v: str) -> str:
        allowed = {"md5", "sha1", "sha256", "sha512", "blake2b"}
        if v.lower() not in allowed:
            raise ValueError(f"algorithm must be one of {sorted(allowed)}")
        return v.lower()


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PENDING = "pending"
    COMPLETED = "completed"


class JobEventType(str, enum.Enum):
    PROGRESS = "progress"
    RESULT = "result"
    ERROR = "error"
    STATUS = "status"


class JobEvent(BaseModel):
    job_id: str = Field(..., min_length=1)
    type: str = Field(...)
    current: Optional[int] = Field(default=None, ge=0)
    total: Optional[int] = Field(default=None, ge=0)
    message: Optional[str] = Field(default=None)
    payload: Optional[Dict[str, Any]] = Field(default=None)
    status: Optional[JobStatus] = Field(default=None)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        return v

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="python", exclude_none=True)


__all__ = [
    "ApiRequest",
    "ScanRequest",
    "SearchRequest",
    "DupesRequest",
    "HashRequest",
    "IntegrityRequest",
    "JobStatus",
    "JobEvent",
    "JobEventType",
    "to_jsonrpc_payload",
]
