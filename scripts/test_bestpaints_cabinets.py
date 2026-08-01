#!/usr/bin/env python3
"""E2E smoke: клиентские кабинеты BestPaints."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

td = tempfile.mkdtemp()
os.environ["BESTPAINTS_DB_PATH"] = str(Path(td) / "t.db")
os.environ["BESTPAINTS_STAFF_PATH"] = str(Path(td) / "staff.json")

from oracle_bot import bestpaints_cabinets as cab
from oracle_bot import bestpaints_crm as crm

failed = 0

def ok(c, m):
    global failed
    print(("OK" if c else "FAIL"), m)
    if not c:
        failed += 1

crm.init_db()
cab.init_db()
obj = crm.create_object({
    "title": "Кабинет QA",
    "address": "Адрес 1",
    "client_name": "Клиент",
    "client_phone": "79001112233",
})
survey = {
    "id": "s_qa",
    "client": {"name": "Клиент", "phone": "79001112233"},
    "buildings": [{
        "id": "b1", "name": "Дом", "houseType": "film", "condition": "good", "material": "beam",
        "colors": "как сейчас", "zones": {"facade": True},
        "tech": {"techId": 4, "paintId": "ADLER::pullex_color"},
        "measure": {"walls": [{"id": "w1", "label": "А", "length": "5", "height": "3", "zone": "facade", "shape": "rect"}], "openings": [], "roundCoef": 1},
        "photos": [],
    }],
    "activeBuildingId": "b1",
    "estimate": {"discountPct": 0},
    "_estimateSnapshot": {"subtotal": 50000, "total": 52500, "discountPct": 0, "area_m2": 15, "areas": {"paintTotal": 15}},
}
res = cab.create_or_refresh_cabinet(object_id=obj["id"], survey=survey)
ok(bool(res.get("link")), "link")
login = cab.client_login(phone="79001112233", access_code=res["access_code"])
ok(bool(login.get("cookie")), "login by code")
pack = cab.verify_client_session(login["cookie"])
s = cab.client_get_bundle(pack["cabinet"])["survey"]
s["buildings"][0]["tech"]["techId"] = 5
saved = cab.client_save_survey(pack["cabinet"], s, phone="79001112233")
ok(any("технология" in c["label"] for c in saved["changes"]), "field diff logged")
logs = cab.list_change_logs(cabinet_id=res["cabinet"]["id"])
ok(any(x["actor_type"] == "client" for x in logs), "client in logs")
ok((ROOT / "oracle_bot/static/bestpaints/cabinet.html").exists(), "cabinet.html")
ok("loadCabinetsPanel" in (ROOT / "oracle_bot/static/bestpaints/js/crm.js").read_text(), "crm tab")
ok("btn-cabinet" in (ROOT / "oracle_bot/static/bestpaints/js/app.js").read_text(), "estimate CTA")
ok("/bestpaints/api/client/login" in (ROOT / "oracle_bot/webapp.py").read_text(), "api routes")
cabjs = (ROOT / "oracle_bot/static/bestpaints/js/cabinet.js").read_text()
ok("cab-pdf" not in cabjs and "openClientReport" not in cabjs, "client no PDF/export")
ok((ROOT / "oracle_bot/static/bestpaints/js/cabinet-guard.js").exists(), "cabinet-guard")
ok("_bp_cabinet_headers" in (ROOT / "oracle_bot/webapp.py").read_text(), "secure headers")
ok("@media print" in (ROOT / "oracle_bot/static/bestpaints/css/cabinet.css").read_text(), "print blocked")
ok("installCabinetGuard" in cabjs, "guard installed")
print("ALL PASSED" if not failed else f"{failed} FAILURES")
sys.exit(1 if failed else 0)
