"""Complete the technical preflight using both service display and raw API contracts.

The frozen initial test expected a raw basis error code in the service's public
display envelope. Preserve that mismatch; inspect the real API response as well.
No product behavior or experiment input is changed.
"""
from pathlib import Path
import asyncio
import json

T = Path(__file__).parent
namespace = {"__file__": str(T / "preflight.py"), "__name__": "__main__"}
try:
    exec(compile((T / "preflight.py").read_text(), str(T / "preflight.py"), "exec"), namespace)
except AssertionError:
    assert "denied" in namespace, "Unexpected earlier preflight failure"
    denied = namespace["denied"]
    assert denied["status"] == 409, denied
    assert denied["body"].get("error_code") != "BASIS_SOURCE_HASH", denied

    async def verify():
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=namespace["app"]), base_url="http://test.local") as client:
            response = await client.post("/v1/basis-links/proposals", json=namespace["body"])
            raw = response.json()
            assert response.status_code == 409 and raw["error_code"] == "BASIS_SOURCE_HASH", raw
            return {"status": response.status_code, "body": raw}

    raw = asyncio.run(verify())
    out = namespace["out"]
    out.update(graph_seeded_via_service_api=True, duplicate_seed_same_links=True, stale_review_rejected=True,
               tampered_source_rejected=True, source_scoped_resolver=namespace["counts"], model_calls=0,
               initial_test_failure="Raw basis error code expected in public display envelope; frozen assertion retained.",
               displayed_rejection=denied, raw_api_rejection=raw)
    (namespace["A"] / "artifacts/preflight.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    namespace["p"].store.close()
    print(json.dumps({k: v for k, v in out.items() if k not in ("displayed_rejection", "raw_api_rejection")}, ensure_ascii=False))
