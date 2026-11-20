"""Stratix License & Unified Connector Provisioning System."""
import hashlib
import json
import os
import secrets
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from backend import copy_trading as store
from backend.namespaced_store import NamespacedStore

USER_PROFILE_FILE = store.ROOT / "data" / "user_profile.json"


class LicenseCreateRequest(BaseModel):
    holder: str = Field(min_length=1, max_length=100)
    email: str = Field(default="", max_length=120)
    plan: Literal["STARTER", "PRO", "ELITE", "ADMIN"] = "PRO"
    max_accounts: int = Field(default=10, ge=1, le=9999)
    modules: list[str] = Field(default_factory=lambda: ["proppass", "rocketpass", "copy"])
    days_valid: Optional[int] = Field(default=30, ge=1, le=3650)  # None = Lifetime
    notes: str = Field(default="", max_length=300)


class LicenseUpdateRequest(BaseModel):
    active: Optional[bool] = None
    plan: Optional[Literal["STARTER", "PRO", "ELITE", "ADMIN"]] = None
    max_accounts: Optional[int] = Field(default=None, ge=1, le=9999)
    modules: Optional[list[str]] = None
    days_valid: Optional[int] = Field(default=None, ge=0, le=3650)
    holder: Optional[str] = None
    notes: Optional[str] = None


class LicenseValidateRequest(BaseModel):
    license_key: str = Field(min_length=4, max_length=120)
    machine_id: str = Field(default="", max_length=120)
    machine_name: str = Field(default="", max_length=120)


def _load_admin_key() -> str:
    if USER_PROFILE_FILE.exists():
        try:
            prof = json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8"))
            if prof.get("license_key"):
                return str(prof["license_key"]).strip()
        except Exception:
            pass
    return "STX-ADMIN-MASTER-UNLIMITED"


def ensure_master_license():
    """Guarantee the owner's Master Admin license always exists and is active."""
    admin_key = _load_admin_key()
    try:
        existing = store.get("stratix_license", admin_key)
        if not existing.get("active"):
            existing["active"] = True
            store.put("stratix_license", admin_key, existing)
        return existing
    except KeyError:
        rec = {
            "key": admin_key,
            "holder": "Administrador · Founder",
            "email": "admin@stratix.quant",
            "plan": "ADMIN",
            "max_accounts": 999,
            "modules": ["proppass", "rocketpass", "copy"],
            "active": True,
            "is_master": True,
            "created_at": time.time(),
            "expires_at": None,
            "last_seen": None,
            "machine_id": None,
            "machine_name": None,
            "notes": "Licencia Maestra de Administrador (Ilimitada)",
        }
        return store.put("stratix_license", admin_key, rec)


def _provision_connection(namespace: str, label: str):
    """Ensure a valid connection exists in the given namespace and return (id, token)."""
    ns_store = store if namespace == "ninja" else NamespacedStore(namespace)
    conns = ns_store.listing("ninja_connection")
    if conns:
        conn = conns[0]
        cid = conn["id"]
        token = conn.get("token") or secrets.token_urlsafe(32)
        conn["token"] = token
        conn["hash"] = hashlib.sha256(token.encode()).hexdigest()
        ns_store.put("ninja_connection", cid, conn)
        return cid, token
    cid = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    conn = {
        "id": cid,
        "name": label,
        "hash": hashlib.sha256(token.encode()).hexdigest(),
        "token": token,
        "created": time.time(),
    }
    ns_store.put("ninja_connection", cid, conn)
    return cid, token


def _find_nt8_addons_dir() -> Optional[Path]:
    user_home = Path(os.path.expanduser("~"))
    for cdir in [
        user_home / "OneDrive" / "Documentos" / "NinjaTrader 8" / "bin" / "Custom" / "AddOns",
        user_home / "Documentos" / "NinjaTrader 8" / "bin" / "Custom" / "AddOns",
        user_home / "Documents" / "NinjaTrader 8" / "bin" / "Custom" / "AddOns",
    ]:
        if cdir.exists():
            return cdir
    return None


def install_license_routes(app):
    ensure_master_license()

    @app.get("/api/licenses")
    def list_licenses():
        ensure_master_license()
        items = store.listing("stratix_license")
        now = time.time()
        for item in items:
            exp = item.get("expires_at")
            item["expired"] = bool(exp is not None and exp < now)
        items.sort(key=lambda x: (not x.get("is_master", False), -(x.get("created_at") or 0)))
        return {"licenses": items, "master_key": _load_admin_key()}

    @app.post("/api/licenses")
    def create_license(req: LicenseCreateRequest):
        p1 = secrets.token_hex(2).upper()
        p2 = secrets.token_hex(2).upper()
        key = f"STX-{req.plan}-{p1}-{p2}"
        now = time.time()
        expires_at = None if (req.plan == "ADMIN" or req.days_valid is None) else now + req.days_valid * 86400
        rec = {
            "key": key,
            "holder": req.holder.strip(),
            "email": req.email.strip(),
            "plan": req.plan,
            "max_accounts": 999 if req.plan == "ADMIN" else req.max_accounts,
            "modules": req.modules or ["proppass", "rocketpass", "copy"],
            "active": True,
            "is_master": False,
            "created_at": now,
            "expires_at": expires_at,
            "last_seen": None,
            "machine_id": None,
            "machine_name": None,
            "notes": req.notes.strip(),
        }
        store.put("stratix_license", key, rec)
        return {"ok": True, "license": rec}

    @app.patch("/api/licenses/{license_key}")
    def update_license(license_key: str, req: LicenseUpdateRequest):
        try:
            rec = store.get("stratix_license", license_key)
        except KeyError:
            raise HTTPException(404, "Licencia no encontrada")
        if req.active is not None:
            if rec.get("is_master") and not req.active:
                raise HTTPException(400, "No se puede desactivar la licencia maestra de administrador")
            rec["active"] = req.active
        if req.plan is not None:
            rec["plan"] = req.plan
        if req.max_accounts is not None:
            rec["max_accounts"] = req.max_accounts
        if req.modules is not None:
            rec["modules"] = req.modules
        if req.holder is not None:
            rec["holder"] = req.holder.strip()
        if req.notes is not None:
            rec["notes"] = req.notes.strip()
        if req.days_valid is not None:
            rec["expires_at"] = None if req.days_valid == 0 else time.time() + req.days_valid * 86400
        store.put("stratix_license", license_key, rec)
        return {"ok": True, "license": rec}

    @app.delete("/api/licenses/{license_key}")
    def delete_license(license_key: str):
        try:
            rec = store.get("stratix_license", license_key)
        except KeyError:
            raise HTTPException(404, "Licencia no encontrada")
        if rec.get("is_master"):
            raise HTTPException(400, "No se puede eliminar la licencia maestra de administrador")
        with store.connect() as db:
            db.execute("DELETE FROM records WHERE kind='stratix_license' AND id=?", (license_key,))
        return {"deleted": True, "key": license_key}

    @app.post("/api/licenses/validate")
    def validate_license(req: LicenseValidateRequest, request: Request, format: str = "json"):
        ensure_master_license()
        key = req.license_key.strip()
        try:
            rec = store.get("stratix_license", key)
        except KeyError:
            raise HTTPException(401, "Clave de licencia Stratix inválida o inexistente")
        if not rec.get("active"):
            raise HTTPException(403, "Esta licencia está revocada o pausada")
        exp = rec.get("expires_at")
        if exp is not None and exp < time.time():
            raise HTTPException(403, "Esta licencia ha expirado; renueva tu suscripción")

        rec["last_seen"] = time.time()
        if req.machine_id:
            rec["machine_id"] = req.machine_id
        if req.machine_name:
            rec["machine_name"] = req.machine_name
        store.put("stratix_license", key, rec)

        machine_suffix = f" ({req.machine_name})" if req.machine_name else ""
        modules = rec.get("modules", ["proppass", "rocketpass", "copy"])
        pp_id, pp_tok = ("", "")
        rk_id, rk_tok = ("", "")
        if "proppass" in modules or rec.get("plan") == "ADMIN":
            pp_id, pp_tok = _provision_connection("ninja", f"PropPass · NinjaTrader{machine_suffix}")
        if "rocketpass" in modules or rec.get("plan") == "ADMIN":
            rk_id, rk_tok = _provision_connection("rocket", f"RocketPass · NinjaTrader{machine_suffix}")

        payload = {
            "ok": True,
            "license_key": key,
            "plan": rec["plan"],
            "holder": rec.get("holder", ""),
            "modules": modules,
            "max_accounts": rec.get("max_accounts", 10),
            "expires_at": exp,
            "proppass_id": pp_id,
            "proppass_token": pp_tok,
            "rocket_id": rk_id,
            "rocket_token": rk_tok,
        }
        if format == "wire" or "text/plain" in request.headers.get("accept", ""):
            lines = [
                "ok=1",
                f"plan={payload['plan']}",
                f"holder={payload['holder']}",
                f"modules={','.join(modules)}",
                f"max_accounts={payload['max_accounts']}",
                f"proppass_id={pp_id}",
                f"proppass_token={pp_tok}",
                f"rocket_id={rk_id}",
                f"rocket_token={rk_tok}",
            ]
            return PlainTextResponse("\n".join(lines))
        return payload

    @app.get("/api/stratix/download-addon")
    def download_unified_addon():
        path = store.ROOT / "ninjatrader" / "StratixConnector.cs"
        if not path.exists():
            raise HTTPException(404, "AddOn unificado StratixConnector.cs aún no compilado")
        return FileResponse(path, filename="StratixConnector.cs")

    @app.post("/api/stratix/auto-link")
    def unified_auto_link(request: Request):
        localapp = os.environ.get("LOCALAPPDATA")
        if not localapp:
            raise HTTPException(400, "No se encontró LOCALAPPDATA en este equipo")
        master = ensure_master_license()
        lic_key = master["key"]
        pp_id, pp_tok = _provision_connection("ninja", "PropPass · NinjaTrader")
        rk_id, rk_tok = _provision_connection("rocket", "RocketPass · NinjaTrader")

        base_root = Path(localapp) / "Stratix"
        (base_root / "NinjaTrader").mkdir(parents=True, exist_ok=True)
        (base_root / "RocketPass").mkdir(parents=True, exist_ok=True)

        server_url = str(request.base_url).rstrip("/")
        if not server_url.startswith("http"):
            server_url = "http://127.0.0.1:8000"

        cfg_path = base_root / "StratixLicense.cfg"
        cfg_path.write_text(f"url={server_url}\nlicense_key={lic_key}\n", encoding="utf-8")
        (base_root / "NinjaTrader" / "CandleBridge.key").write_text(f"{pp_id}\n{pp_tok}\n", encoding="utf-8")
        (base_root / "RocketPass" / "RocketBridge.key").write_text(f"{rk_id}\n{rk_tok}\n", encoding="utf-8")

        source_addon = store.ROOT / "ninjatrader" / "StratixConnector.cs"
        addon_installed = None
        nt8_dir = _find_nt8_addons_dir()
        if nt8_dir and source_addon.exists():
            # Clean legacy separate files so NT8 doesn't have duplicate class definitions
            for legacy in ("StratixCandleService.cs", "RocketPassService.cs"):
                legacy_path = nt8_dir / legacy
                if legacy_path.exists():
                    try:
                        legacy_path.unlink()
                    except Exception:
                        pass
            dest = nt8_dir / "StratixConnector.cs"
            shutil.copy2(source_addon, dest)
            addon_installed = str(dest)

        return {
            "ok": True,
            "license_key": lic_key,
            "server_url": server_url,
            "proppass_id": pp_id,
            "rocket_id": rk_id,
            "config_file": str(cfg_path),
            "addon_installed": addon_installed,
            "message": "AddOn unificado StratixConnector.cs instalado y vinculado para PropPass + RocketPass.",
        }
