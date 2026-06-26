import json
import sys
import time
from datetime import datetime

API_BASE = "http://localhost:8011"
CYCLE_DATA = []
PACKAGES_BEFORE_FIX = 0
TIER_NAMES = {0: "NONE", 1: "BRONZE", 2: "SILVER", 3: "GOLD", 4: "PLATINUM"}
LOG_FILE = None


def api_get(path):
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"{API_BASE}{path}", timeout=10)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def bar(val, max_val, width=20):
    if max_val <= 0:
        return " " * width
    filled = int((val / max_val) * width)
    return "#" * filled + "-" * (width - filled)


def sparkline(values, width=20):
    if not values:
        return " " * width
    mx = max(values)
    if mx <= 0:
        return " " * width
    chars = "_-+*=#%@"
    result = ""
    for v in values:
        idx = int((v / mx) * (len(chars) - 1))
        result += chars[min(idx, len(chars) - 1)]
    if len(result) > width:
        result = result[-width:]
    elif len(result) < width:
        result = " " * (width - len(result)) + result
    return result


def log_write(text):
    print(text, flush=True)
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass


def hr(title=""):
    w = 78
    if title:
        side = (w - len(title) - 2) // 2
        return "-" * side + " " + title + " " + "-" * side
    return "-" * w


def format_eta(seconds):
    if seconds is None or seconds < 0 or seconds > 1e12:
        return "inf"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 24:
        d = h // 24
        h = h % 24
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def get_cyber_stats():
    data = api_get("/specialists")
    if not data:
        return None
    for s in data.get("specialists", []):
        if s.get("domain") == "Cybersecurity":
            return s
    return None


def get_logs(limit=5):
    data = api_get(f"/activity-log?limit={limit}")
    return data.get("logs", []) if data else []


def show_dashboard(cyc_data, status, s, now):
    lines = []
    c = status.get("current_cycle", 0)

    lines.append("")
    lines.append(hr(" NURTURE DASHBOARD "))
    lines.append(f"  {now}   Pipeline: {status.get('status','?')}  |  Ciclo {c}")
    lines.append(hr())

    pkgs = [x["packages"] for x in cyc_data if x.get("packages", 0) > 0]
    total_pkgs = sum(pkgs)
    lines.append(f"  PAQUETES NUEVOS (esta ejecucion): {total_pkgs}")
    lines.append("")

    recent = pkgs[-8:]
    avg_pkgs = sum(recent) / len(recent) if recent else 0
    lines.append("  PAQUETES POR CICLO (ultimos 8)")
    if recent:
        lines.append(f"    {sparkline(recent, 25)}  avg={avg_pkgs:.1f}  last={recent[-1]}")
        mx = max(recent)
        for i, (p, cd) in enumerate(zip(cyc_data[-8:], [x.get("duration_min",0) for x in cyc_data[-8:]])):
            if p.get("packages", 0) == 0:
                continue
            bp = p["packages"]
            lines.append(f"    #{i+1:2d}  {bar(bp, mx, 20)}  {bp:3d} pkgs  ({cd:.1f} min)")
    else:
        lines.append("    (esperando datos...)")

    lines.append("")
    lines.append("  VELOCIDAD")
    avg_dur = 0
    dur_list = [x.get("duration_min", 0) for x in cyc_data if x.get("duration_min", 0) > 0]
    if dur_list:
        avg_dur = sum(dur_list) / len(dur_list)
    rate = total_pkgs / sum(dur_list) / 60 if sum(dur_list) > 0 else 0
    lines.append(f"    Duracion media: {avg_dur:.1f} min/ciclo")
    lines.append(f"    Velocidad:      {rate*60:.1f} pkgs/hora")
    lines.append(f"    Paquetes/cycle: {total_pkgs / max(len(cyc_data),1):.1f}")
    lines.append("")

    lines.append("  ESTADISTICAS CYBERSECURITY")
    if s:
        ema = s.get("ema_score", 0)
        tier = s.get("tier", 0)
        racha = s.get("racha_25", 0)
        absorbed = s.get("packages_absorbed", 0)
        is_rel = s.get("is_reliable", 0)
        lines.append(f"    EMA:    {ema:.4f}")
        lines.append(f"    Tier:   {TIER_NAMES.get(tier, f'?{tier}')} ({tier})")
        lines.append(f"    Racha:  {racha*100:.0f}%")
        lines.append(f"    Absorb: {absorbed:,}")
        lines.append(f"    Rel:    {'Yes' if is_rel else 'No'}")

        lines.append("")
        lines.append("  PROYECCION A BRONZE (tier 1)")
        if avg_pkgs > 0 and avg_dur > 0:
            cph = 60 / avg_dur
            qual = min(0.25 * 4 + 0.25 * (avg_pkgs / 60), 0.95)
            tiers_needed = 1 - tier
            if tiers_needed <= 0:
                lines.append(f"    Ya en BRONZE!")
            else:
                cyc_needed = tiers_needed / (qual * 0.01)
                eta_s = (cyc_needed / cph) * 3600
                lines.append(f"    Calidad/cycle: {qual:.3f}")
                lines.append(f"    Ciclos req:    {cyc_needed:.0f}")
                lines.append(f"    ETA:           {format_eta(eta_s)}")
        else:
            lines.append("    (datos insuficientes)")

    lines.append("")
    lines.append("  ACTIVIDAD")
    for log in get_logs(5):
        msg = log.get("message", "")
        if msg:
            lines.append(f"    {msg[:70]}")
    lines.append("")
    lines.append(hr(f" CICLO {c} - FIN "))
    lines.append("")
    return "\n".join(lines)


def main():
    global CYCLE_DATA, PACKAGES_BEFORE_FIX, LOG_FILE

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    LOG_FILE = f"D:/proyectos/expertia/incubator-root/logs/monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_write("Nurture Monitor iniciado")
    log_write(f"Log: {LOG_FILE}")
    log_write("Esperando el primer ciclo...")

    prev_cycle = 0
    cycle_start = None
    prev_pkgs_total = 0

    init_s = get_cyber_stats()
    if init_s:
        PACKAGES_BEFORE_FIX = init_s.get("packages_absorbed", 0)
        prev_pkgs_total = PACKAGES_BEFORE_FIX
        log_write(f"  Baseline packages: {PACKAGES_BEFORE_FIX:,}")

    while True:
        try:
            status = api_get("/status")
            if not status:
                time.sleep(5)
                continue

            cc = status.get("current_cycle", 0)
            pstate = status.get("status", "")
            phase = status.get("phase", "")

            if cc > prev_cycle:
                if prev_cycle > 0:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    s = get_cyber_stats()
                    if s:
                        cur = s.get("packages_absorbed", 0)
                        cycle_pkgs = cur - prev_pkgs_total
                        if CYCLE_DATA:
                            CYCLE_DATA[-1]["packages"] = max(0, cycle_pkgs)
                            dur = time.time() - cycle_start if cycle_start else 0
                            CYCLE_DATA[-1]["duration_min"] = dur / 60
                        prev_pkgs_total = cur

                    display = show_dashboard(CYCLE_DATA, status, s if s else None, now)
                    log_write(display)

                CYCLE_DATA.append({
                    "cycle": cc,
                    "packages": 0,
                    "duration_min": 0,
                    "start_time": time.time(),
                })
                prev_cycle = cc
                cycle_start = time.time()

            elapsed = status.get("elapsed_seconds", 0)
            line = (f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Ciclo {cc}{' > ' + phase[:35] if phase else ''}"
                    f"  |  {int(elapsed//3600)}h {int((elapsed%3600)//60)}m")
            sys.stdout.write(line.ljust(100) + "\n")
            sys.stdout.flush()

            time.sleep(3)

        except KeyboardInterrupt:
            log_write("\nMonitor detenido.")
            return
        except Exception as e:
            log_write(f"\n[Monitor] Error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
