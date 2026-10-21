"""Seed the isolated graph through the same service API as the review UI."""
import json


async def seed(service, graph):
    receipts = []
    for link in graph["links"]:
        body = {k: link[k] for k in ("internal", "external", "kind", "reason", "provenance")}
        body["request_id"] = "adr0956-seed-" + link["id"]
        response = await service({}, {"API_TYPE": "BASIS_LINKS_PROPOSE", "json": body})
        receipts.append({"edge": link["id"], "operation": "propose", "response": response})
        assert response["status"] == 200, json.dumps(response, ensure_ascii=False)
        proposed = response["body"]
        request = {"request_id": "adr0956-activate-" + link["id"], "action": "approve",
                   "reason": "사용자 지시로 격리 시험 DB에서 연결을 활성화함. 운영·법률 승인 아님.",
                   "items": [{"link_id": proposed["link"]["link_id"], "revision": proposed["link"]["revision"],
                              "view_hash": proposed["view_hash"]}]}
        response = await service({}, {"API_TYPE": "BASIS_LINKS_REVIEW", "json": request})
        receipts.append({"edge": link["id"], "operation": "review", "response": response})
        assert response["status"] == 200 and response["body"]["status"] == "completed", json.dumps(response, ensure_ascii=False)
    listed = await service({}, {"API_TYPE": "BASIS_LINKS_LIST"})
    assert listed["status"] == 200
    items = listed["body"]["items"]
    assert len(items) == len(graph["links"]) and all(i["link"]["status"] == "APPROVED" and i["link"]["kind"] == "BASIS" for i in items)
    return {"test_only": True, "legal_relation_certified": False, "receipts": receipts, "listed": listed}
