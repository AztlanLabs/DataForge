"""TICK-003 verification — API schemas and Transport ABC."""

import json
import sys

import pytest
from pydantic import ValidationError


def test_scan_request_validates_and_serializes():
    from dataforge.api.schema import ScanRequest

    req = ScanRequest(root="/tmp", recursive=True)
    payload = req.to_jsonrpc()
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "scan"
    assert payload["params"]["root"] == "/tmp"
    assert payload["params"]["recursive"] is True
    assert payload["id"] == 1
    # JSON serializable
    json.dumps(payload)

    # custom id / method override
    payload2 = req.to_jsonrpc(request_id=42, method="scan")
    assert payload2["id"] == 42

    # alternative helper
    payload3 = req.to_payload()
    assert payload3["jsonrpc"] == "2.0"


def test_scan_request_validation_fails_on_empty_root():
    from dataforge.api.schema import ScanRequest

    with pytest.raises(ValidationError):
        ScanRequest(root="")
    with pytest.raises(ValidationError):
        ScanRequest()  # missing required


def test_all_request_types_importable():
    from dataforge.api.schema import (
        DupesRequest,
        HashRequest,
        IntegrityRequest,
        ScanRequest,
        SearchRequest,
    )

    # smoke construction
    assert ScanRequest(root="/tmp")
    assert SearchRequest(root="/tmp")
    assert DupesRequest(root="/tmp")
    assert HashRequest(path="/tmp/a.txt")
    assert IntegrityRequest(path="/tmp", snapshot="/tmp/snap.json")


def test_search_dupes_hash_integrity_serialize():
    from dataforge.api.schema import DupesRequest, HashRequest, IntegrityRequest, SearchRequest

    for req in [
        SearchRequest(root="/tmp"),
        DupesRequest(root="/tmp"),
        HashRequest(path="/tmp/x"),
        IntegrityRequest(path="/tmp", snapshot="/tmp/s.json"),
    ]:
        p = req.to_jsonrpc()
        assert p["jsonrpc"] == "2.0"
        assert "method" in p
        assert "params" in p


def test_to_jsonrpc_payload_helper():
    from dataforge.api.schema import ScanRequest, to_jsonrpc_payload

    req = ScanRequest(root="/tmp", recursive=False)
    payload = to_jsonrpc_payload(req, request_id=7)
    assert payload["id"] == 7
    assert payload["method"] == "scan"


def test_job_status_and_event():
    from dataforge.api.schema import JobEvent, JobStatus

    assert JobStatus.QUEUED == "queued"
    assert JobStatus.RUNNING == "running"
    assert JobStatus.DONE == "done"
    assert JobStatus.CANCELLED == "cancelled"
    assert JobStatus.FAILED == "failed"

    evt = JobEvent(job_id="01JTEST", type="progress", current=1, total=10, message="hi")
    d = evt.to_dict()
    assert d["job_id"] == "01JTEST"
    assert d["type"] == "progress"

    evt2 = JobEvent(job_id="01JTEST", type="result", payload={"total": 1})
    assert evt2.payload == {"total": 1}


def test_transport_abc_requires_methods():
    from dataforge.api.transport.base import Transport

    assert "send" in Transport.__abstractmethods__
    assert "recv" in Transport.__abstractmethods__
    assert "subscribe" in Transport.__abstractmethods__
    assert "auto_discover" in Transport.__abstractmethods__

    # incomplete subclass must not instantiate
    class Incomplete(Transport):
        async def send(self, payload):  # type: ignore[override]
            return {}

        async def recv(self):  # type: ignore[override]
            return {}

    with pytest.raises(TypeError):
        Incomplete()  # missing subscribe + auto_discover

    # complete subclass succeeds
    class Complete(Transport):
        async def send(self, payload):  # type: ignore[override]
            return {"ok": True}

        async def recv(self):  # type: ignore[override]
            return {}

        def subscribe(self, job_id):  # type: ignore[override]
            async def gen():
                yield {"job_id": job_id, "type": "progress"}

            return gen()

        @classmethod
        def auto_discover(cls):  # type: ignore[override]
            return "http://127.0.0.1:8765"

    c = Complete()
    assert c is not None
    assert Complete.auto_discover() == "http://127.0.0.1:8765"


def test_no_circular_import_with_core():
    # Importing schema must not pull core.scanner via circular dep
    # Do isolated subprocess check
    import subprocess

    code = (
        "import sys; before=set(sys.modules.keys()); "
        "from dataforge.api.schema import ScanRequest; "
        "after=set(sys.modules.keys()); "
        "loaded=after-before; "
        "bad=[m for m in loaded if m.startswith('dataforge.core')]; "
        "assert not bad, f'circular import via {bad}'"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout


def test_api_package_reexports():
    from dataforge.api import ScanRequest as SR1
    from dataforge.api.schema import ScanRequest as SR2

    assert SR1 is SR2

    from dataforge.api.transport import Transport as T1
    from dataforge.api.transport.base import Transport as T2

    assert T1 is T2
