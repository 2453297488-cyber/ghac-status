import json
import os
import ssl
import sys
import tempfile
import urllib.error
import urllib.request

BASE = "https://ghac-api-gateway.hynex.com.cn/honda-facade-mobile-hc-sdk/api/v1"

TOKEN = os.environ.get("GHAC_TOKEN", "").strip()
VIN = os.environ.get("GHAC_VIN", "LHGFE3666S2000980").strip()
CERT_PEM = os.environ.get("GHAC_CERT_PEM", "")
CERT_KEY = os.environ.get("GHAC_CERT_KEY", "")
INCLUDE_LOC = os.environ.get("GHAC_INCLUDE_LOCATION", "") == "1"
OUT = os.environ.get("GHAC_OUT", "status.json")


def make_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    cert_path = os.path.join(tempfile.gettempdir(), "ghac_client.pem")
    key_path = os.path.join(tempfile.gettempdir(), "ghac_client.key")
    with open(cert_path, "w", encoding="utf-8") as f:
        f.write(CERT_PEM)
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(CERT_KEY)
    os.chmod(key_path, 0o600)
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    return ctx


def get(ctx, path, timeout=20):
    url = BASE + path
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "tokenType": "0",
        "gh_android_app_version": "5.0.2",
        "Compatible": "50",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "okhttp/4.11.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, json.loads(r.read(200000).decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read(2000).decode("utf-8", "replace")}
    except Exception as e:
        return None, {"error": str(e)}


def v(d, k):
    x = d.get(k)
    return None if x in (None, "", "--") else x


def _int(x):
    try:
        return int(x)
    except Exception:
        return None


def _float(x):
    try:
        return float(x)
    except Exception:
        return None


def main():
    if not TOKEN or not CERT_PEM or not CERT_KEY:
        print("缺少 GHAC_TOKEN / GHAC_CERT_PEM / GHAC_CERT_KEY", file=sys.stderr)
        sys.exit(1)

    ctx = make_ctx()
    status, body = get(ctx, f"/vehicle/status/vin_code={VIN}")

    if status != 200 or body.get("code") != "000000":
        out = {
            "ok": False,
            "error": body.get("description") or body.get("error") or f"HTTP {status}",
            "code": body.get("code"),
            "updated": None,
        }
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(0)

    b = body.get("responseBody") or {}
    lock_raw = v(b, "leftFrontDoorLockStatus")
    trunk_raw = v(b, "trunklockstatus")

    out = {
        "ok": True,
        "updated": v(b, "sendingtime"),
        "range_km": _int(v(b, "remainderMileage")),
        "oil_pct": _int(v(b, "oil")),
        "mileage_km": _int(v(b, "mileage")),
        "locked": lock_raw == "0" if lock_raw is not None else None,
        "lock_text": "已锁车" if lock_raw == "0" else ("已解锁" if lock_raw else "未知"),
        "trunk_open": trunk_raw == "1" if trunk_raw is not None else None,
        "ac_on": v(b, "airconstatus") == "1",
        "ac_temp": _float(v(b, "airconTemperatureSettingDR")),
        "outdoor_temp": _float(v(b, "outdoorTemperature")),
        "online": v(b, "onlineState") == "1",
        "engine_on": v(b, "enginestatus") == "1",
    }

    if INCLUDE_LOC:
        st2, b2 = get(ctx, f"/vehicle/location_info/vin_code={VIN}")
        if st2 == 200 and b2.get("code") == "000000":
            rb = b2.get("responseBody") or {}
            out["address"] = rb.get("locationAddress")
            out["lat"] = rb.get("latitude")
            out["lng"] = rb.get("longitude")

    st3, b3 = get(ctx, f"/vehicle/vin_code={VIN}")
    if st3 == 200 and b3.get("code") == "000000":
        rb = b3.get("responseBody") or {}
        out["nickname"] = rb.get("carNickName") or "我的车"
        out["model"] = rb.get("modelName") or ""
        out["image"] = rb.get("modelImgUrl") or ""

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
