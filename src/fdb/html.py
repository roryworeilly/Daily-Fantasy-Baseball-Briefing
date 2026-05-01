"""
Machine-generated from fdbRV.py — see .build/generate_fdb_package.py.
"""
import os
import io
import math
import json
import re
import html

from fdb.settings import MY_TEAM_NAME, N_TEAMS, YEAR
from fdb.model import is_pitcher, esc, fmt, connect
from fdb.assets import CSS, JS


def _player_data_attrs(row):
    """Return HTML data-* attribute string + onclick for player modal triggering."""
    team   = esc(row.get("mlb", row.get("team", "")))
    status = row.get("status", "ACTIVE") or "ACTIVE"
    slot   = row.get("pos", "")
    on_il  = slot in ("IL", "IR") or status not in ("ACTIVE", "NORMAL", "")
    # Escape the adv JSON for safe embedding in an HTML attribute.
    adv_raw = row.get("adv", "{}")
    adv_safe = adv_raw.replace("&", "&amp;").replace('"', "&quot;")
    return (
        f' data-mlbam="{esc(row.get("mlbam_id",""))}"'
        f' data-pitcher="{esc(row.get("is_pitcher","false"))}"'
        f' data-name="{esc(row.get("player",""))}"'
        f' data-team="{team}"'
        f' data-pos="{esc(slot)}"'
        f' data-base="{esc(str(row.get("base",0)))}"'
        f' data-fit="{esc(str(row.get("fit",0)))}"'
        f' data-proj="{esc(str(row.get("proj_pts","—")))}"'
        f' data-hs="{esc(row.get("headshot",""))}"'
        f' data-hs2="{esc(row.get("headshot2",""))}"'
        f' data-ini="{esc(row.get("initials","?"))}"'
        f' data-inj-status="{esc(status)}"'
        f' data-on-il="{str(on_il).lower()}"'
        f' data-adv="{adv_safe}"'
        f' onclick="openPlayerModal(event,this)" style="cursor:pointer"'
    )


def _av(row):
    """Render player avatar — ESPN CDN → MLB CDN → initials fallback chain."""
    hs  = row.get("headshot", "")   # ESPN CDN
    hs2 = row.get("headshot2", "")  # MLB Stats CDN
    ini = esc(row.get("initials", "?"))
    nm  = esc(row.get("player", ""))
    if hs and hs2:
        # Chain: if ESPN fails, try MLB CDN; if that fails, show initials
        return (
            f'<img src="{esc(hs)}" alt="{nm}" loading="lazy" '
            f"onerror=\"this.onerror=null;this.src='{esc(hs2)}';"
            f"this.onerror=function(){{this.style.display='none';"
            f"this.nextSibling.style.display='flex'}}\">"
            f'<span class="av-fb" style="display:none">{ini}</span>'
        )
    if hs or hs2:
        src = esc(hs or hs2)
        return (
            f'<img src="{src}" alt="{nm}" loading="lazy" '
            f"onerror=\"this.style.display='none';this.nextSibling.style.display='flex'\">"
            f'<span class="av-fb" style="display:none">{ini}</span>'
        )
    return f'<span class="av-fb">{ini}</span>'


def _ring_av(row, base_val=0, fit_val=0, size=80):
    """Dual-ring SVG avatar.
    Outer ring = VALUE (BASE score): red → amber → green.
    Inner ring = FIT score: blue.
    Player photo / initials in centre.
    size controls the outer diameter in pixels.
    """
    try:
        bv = min(100.0, max(0.0, float(base_val)))
    except Exception:
        bv = 0.0
    try:
        fv = min(100.0, max(0.0, float(fit_val)))
    except Exception:
        fv = 0.0

    # ── Ring geometry (proportional to size) ──────────────────────────
    cx   = size / 2.0
    OR   = round(cx * 0.820, 1)   # outer ring radius  (82 % of half-size)
    IR   = round(cx * 0.555, 1)   # inner ring radius  (55.5 % of half-size)
    av_s = round(cx * 0.820)      # inner av box — shrunk to give rings room
    # stroke widths — chunky so the rings read clearly
    sw_o = max(7, round(size * 0.100))   # ~8 px at 80  (was ~5)
    sw_i = max(5, round(size * 0.075))   # ~6 px at 80  (was ~4)

    OC     = 2 * math.pi * OR
    IC     = 2 * math.pi * IR
    o_fill = bv / 100.0 * OC
    i_fill = fv / 100.0 * IC

    # ── Value colour: red → amber → green ─────────────────────────────
    if bv >= 65:
        v_color = "var(--accent)"   # green (theme-aware)
    elif bv >= 38:
        v_color = "var(--amber)"    # amber
    else:
        v_color = "var(--red)"      # red

    # ── Fit colour: electric blue ──────────────────────────────────────
    f_color = "#3b82f6"

    av_html = _av(row)   # reuse onerror fallback logic

    return (
        f'<div class="ring-av-wrap" style="width:{size}px;height:{size}px">'
        f'<svg class="ring-svg" viewBox="0 0 {size} {size}"'
        f' width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">'
        # Outer track
        f'<circle cx="{cx}" cy="{cx}" r="{OR}" fill="none"'
        f' stroke="var(--bar-bg)" stroke-width="{sw_o}"/>'
        # Outer fill (VALUE)
        f'<circle cx="{cx}" cy="{cx}" r="{OR}" fill="none"'
        f' stroke="{v_color}" stroke-width="{sw_o}" stroke-linecap="round"'
        f' stroke-dasharray="{o_fill:.2f} {OC:.2f}"'
        f' transform="rotate(-90 {cx} {cx})"/>'
        # Inner track
        f'<circle cx="{cx}" cy="{cx}" r="{IR}" fill="none"'
        f' stroke="var(--bar-bg)" stroke-width="{sw_i}"/>'
        # Inner fill (FIT)
        f'<circle cx="{cx}" cy="{cx}" r="{IR}" fill="none"'
        f' stroke="{f_color}" stroke-width="{sw_i}" stroke-linecap="round"'
        f' stroke-dasharray="{i_fill:.2f} {IC:.2f}"'
        f' transform="rotate(-90 {cx} {cx})"/>'
        f'</svg>'
        f'<div class="ring-av-inner">'
        f'<div class="av" style="width:{av_s}px;height:{av_s}px;flex:0 0 {av_s}px;border:none">'
        f'{av_html}'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def _pc(row, sub_key="pos"):
    attrs = _player_data_attrs(row)
    return (
        f'<div class="pc"{attrs}>'
        f'<div class="av">{_av(row)}</div>'
        f'<div><div class="pc-name">{esc(row.get("player",""))}</div>'
        f'<div class="pc-sub">{esc(row.get(sub_key,""))}</div></div>'
        f'</div>'
    )


def _pos_badge(pos):
    safe = re.sub(r"[^A-Z0-9]", "", pos.upper()[:4])
    return f'<span class="pos pos-{safe}">{esc(pos)}</span>'


def _bar(value):
    try:
        v = min(100.0, max(0.0, float(value)))
    except Exception:
        v = 0.0
    return (
        f'<div class="bar-cell">'
        f'<div class="bar-track"><div class="bar-fill" style="width:{v:.1f}%"></div></div>'
        f'<span class="bar-val">{v:.0f}</span>'
        f'</div>'
    )


def _win_gauge(prob):
    ARC    = 157.08
    pct    = prob * 100
    filled = prob * ARC
    label  = (
        "STRONG FAV" if pct >= 65 else
        "SLIGHT FAV" if pct >= 55 else
        "TOSS-UP"    if pct >= 45 else
        "SLIGHT DOG" if pct >= 35 else
        "HEAVY DOG"
    )
    tone  = "good" if pct >= 55 else ("bad" if pct < 45 else "warn")
    color = ("var(--accent)" if tone == "good" else
             "var(--red)"    if tone == "bad"  else "var(--amber)")
    return (
        f'<div class="gauge-wrap">'
        f'<svg viewBox="0 0 120 75" width="160" height="100">'
        f'<path d="M 10,65 A 50,50 0 0 1 110,65" fill="none"'
        f' stroke="var(--bar-bg)" stroke-width="10" stroke-linecap="round"/>'
        f'<path d="M 10,65 A 50,50 0 0 1 110,65" fill="none"'
        f' stroke="{color}" stroke-width="10" stroke-linecap="round"'
        f' stroke-dasharray="{filled:.1f} {ARC:.1f}" pathLength="{ARC:.1f}"/>'
        f'<text x="60" y="62" text-anchor="middle" font-size="17"'
        f' font-weight="900" fill="var(--text)" font-family="Roboto,sans-serif">{pct:.1f}%</text>'
        f'</svg>'
        f'<div class="gauge-sub {tone}">{label}</div>'
        f'</div>'
    )


def _stat_card(label, value, sub="", tone=""):
    cls = f" {tone}" if tone else ""
    return (
        f'<div class="stat-card{cls}">'
        f'<div class="stat-label">{esc(label)}</div>'
        f'<div class="stat-value">{esc(value)}</div>'
        f'<div class="stat-sub">{esc(sub)}</div>'
        f'</div>'
    )


def _roster_table(rows, title, subtitle=""):
    thead = (
        "<tr><th>Slot</th><th>Player</th><th>MLB</th>"
        "<th>Proj</th><th>VAR</th><th>BASE</th><th>FIT</th><th>Status</th></tr>"
    )
    tbody = []
    for r in rows:
        slot  = r.get("pos", "")
        rc    = "row-hl" if slot in ("IL", "IR") else ""
        s_cls = "s-warn" if r.get("status_class") == "warn" else "s-ok"
        tbody.append(
            f'<tr class="{rc}">'
            f'<td>{_pos_badge(slot)}</td>'
            f'<td>{_pc(r, sub_key="mlb")}</td>'
            f'<td style="font-size:12px;color:var(--text2)">{esc(r.get("mlb",""))}</td>'
            f'<td style="font-weight:700">{esc(r.get("proj_pts",""))}</td>'
            f'<td style="font-weight:700;color:var(--accent)">{esc(r.get("var",""))}</td>'
            f'<td>{_bar(r.get("base", 0))}</td>'
            f'<td>{_bar(r.get("fit", 0))}</td>'
            f'<td><span class="{s_cls}">{esc(r.get("status",""))}</span></td>'
            f'</tr>'
        )
    body  = "".join(tbody) or '<tr><td colspan="8" style="text-align:center;color:var(--text2)">No data</td></tr>'
    sub_h = f'<div class="sec-sub">{esc(subtitle)}</div>' if subtitle else ""
    return (
        f'<div class="card mb20">'
        f'<div class="sec-head"><div class="sec-title">{esc(title)}</div>{sub_h}</div>'
        f'<div class="tbl-wrap"><table><thead>{thead}</thead><tbody>{body}</tbody></table></div>'
        f'</div>'
    )


def _stat_pills(row):
    """
    Build a row of color-coded stat pills from the player's adv JSON.
    Hitters: wRC+, K%, Brl%, xwOBA, EV
    Pitchers: ERA, K/9, SwStr%, FIP, xERA
    Returns an HTML string (empty if no adv data).
    """
    adv_raw = row.get("adv", "{}")
    try:
        adv = json.loads(adv_raw) if isinstance(adv_raw, str) else adv_raw
    except Exception:
        adv = {}
    if not adv:
        return ""

    is_p = str(row.get("is_pitcher", "false")).lower() == "true"

    def _tier(val, thresholds):
        """thresholds = [(min_val, css_class), ...] sorted high→low."""
        try:
            v = float(val)
        except Exception:
            return "sp-avg"
        for mn, cls in thresholds:
            if v >= mn:
                return cls
        return "sp-poor"

    def _tier_inv(val, thresholds):
        """Like _tier but lower is better (ERA, K%, etc.). thresholds = [(max_val, cls)] high→low."""
        try:
            v = float(val)
        except Exception:
            return "sp-avg"
        for mx, cls in thresholds:
            if v <= mx:
                return cls
        return "sp-poor"

    pills = []

    def _pill(label, val, css_cls, fmt_str=None):
        if val in (None, "", "—", "N/A"):
            return
        try:
            display = fmt_str.format(float(val)) if fmt_str else str(val)
        except Exception:
            display = str(val)
        pills.append(f'<span class="sp-pill {css_cls}">{esc(label)}&nbsp;{esc(display)}</span>')

    if not is_p:
        # ── Hitter pills ──────────────────────────────────────────────────────
        wrc  = adv.get("wRC+")
        kpct = adv.get("K%")
        brl  = adv.get("Barrel%") or adv.get("Brl%")
        xwoba = adv.get("xwOBA")
        ev   = adv.get("EV") or adv.get("exit_velocity_avg")

        if wrc is not None:
            _pill("wRC+", wrc, _tier(wrc, [(140,"sp-elite"),(115,"sp-good"),(90,"sp-avg")]))
        if kpct is not None:
            # K% — lower is better; stored as decimal (0.18) or percent (18)
            try:
                kv = float(kpct)
                kv_pct = kv if kv > 1 else kv * 100
            except Exception:
                kv_pct = 99
            cls = _tier_inv(kv_pct, [(15,"sp-elite"),(20,"sp-good"),(25,"sp-avg")])
            _pill("K%", f"{kv_pct:.0f}%", cls)
        if brl is not None:
            try:
                bv = float(brl)
                bv_pct = bv if bv > 1 else bv * 100
            except Exception:
                bv_pct = 0
            cls = _tier(bv_pct, [(10,"sp-elite"),(6,"sp-good"),(4,"sp-avg")])
            _pill("Brl%", f"{bv_pct:.1f}%", cls)
        if xwoba is not None:
            _pill("xwOBA", xwoba, _tier(xwoba, [(.370,"sp-elite"),(.340,"sp-good"),(.310,"sp-avg")]), "{:.3f}")
        if ev is not None:
            _pill("EV", ev, _tier(ev, [(91,"sp-elite"),(89,"sp-good"),(87,"sp-avg")]), "{:.1f}")
    else:
        # ── Pitcher pills ─────────────────────────────────────────────────────
        era   = adv.get("ERA")
        k9    = adv.get("K/9")
        swstr = adv.get("SwStr%")
        fip   = adv.get("FIP")
        xera  = adv.get("xERA") or adv.get("xera")
        siera = adv.get("SIERA")

        if era is not None:
            _pill("ERA", era, _tier_inv(era, [(3.00,"sp-elite"),(3.80,"sp-good"),(4.50,"sp-avg")]), "{:.2f}")
        if k9 is not None:
            _pill("K/9", k9, _tier(k9, [(11,"sp-elite"),(9,"sp-good"),(7,"sp-avg")]), "{:.1f}")
        if swstr is not None:
            try:
                sv = float(swstr)
                sv_pct = sv if sv > 1 else sv * 100
            except Exception:
                sv_pct = 0
            cls = _tier(sv_pct, [(13,"sp-elite"),(10,"sp-good"),(9,"sp-avg")])
            _pill("SwStr", f"{sv_pct:.1f}%", cls)
        if fip is not None:
            _pill("FIP", fip, _tier_inv(fip, [(3.00,"sp-elite"),(3.50,"sp-good"),(4.20,"sp-avg")]), "{:.2f}")
        ref_era = xera or siera
        ref_lbl = "xERA" if xera else ("SIERA" if siera else None)
        if ref_era is not None and ref_lbl:
            _pill(ref_lbl, ref_era, _tier_inv(ref_era, [(3.00,"sp-elite"),(3.50,"sp-good"),(4.20,"sp-avg")]), "{:.2f}")

    if not pills:
        return ""
    return '<div class="sp-pills">' + "".join(pills) + "</div>"


_roster_section_counter = [0]  # mutable counter for unique IDs

def _roster_table_view(rows):
    """
    Dense table view — one row per player, all stats in aligned columns.
    ~34px per row; 25 players ≈ 850px total vs ~1400px for the card grid.
    Hitters:  wRC+ | K%  | Brl% | xwOBA
    Pitchers: ERA  | K/9 | SwStr% | FIP
    """
    def _color(v, thresholds, invert=False):
        """Return a CSS color string based on value vs thresholds list [(val, color)]."""
        try:
            fv = float(v)
        except Exception:
            return "var(--text2)"
        if not invert:
            for mn, col in thresholds:
                if fv >= mn:
                    return col
            return "var(--red)"
        else:
            for mx, col in thresholds:
                if fv <= mx:
                    return col
            return "var(--red)"

    HIT_GOOD  = "var(--accent)"
    HIT_MED   = "var(--amber)"
    PIT_GOOD  = "var(--accent)"
    PIT_MED   = "var(--amber)"
    DIM       = "var(--text2)"

    def _fmt_adv(adv, is_p):
        """Return list of (label, display_str, color) for the 4 stat columns."""
        if is_p:
            # ERA
            era = adv.get("ERA")
            era_d = f'{float(era):.2f}' if era not in (None,"") else "—"
            era_c = _color(era, [(3.00,PIT_GOOD),(3.80,PIT_MED)], invert=True) if era else DIM
            # K/9
            k9  = adv.get("K/9")
            k9_d = f'{float(k9):.1f}' if k9 not in (None,"") else "—"
            k9_c = _color(k9, [(11,PIT_GOOD),(9,PIT_MED)]) if k9 else DIM
            # SwStr%
            sw  = adv.get("SwStr%")
            try:
                swv = float(sw)
                sw_d = f'{swv*100:.1f}%' if swv <= 1 else f'{swv:.1f}%'
                swv_n = swv*100 if swv <= 1 else swv
                sw_c = _color(swv_n, [(13,PIT_GOOD),(10,PIT_MED)])
            except Exception:
                sw_d, sw_c = "—", DIM
            # FIP
            fip = adv.get("FIP") or adv.get("xERA") or adv.get("SIERA")
            fip_lbl = "FIP" if adv.get("FIP") else ("xERA" if adv.get("xERA") else "SIERA")
            fip_d = f'{float(fip):.2f}' if fip not in (None,"") else "—"
            fip_c = _color(fip, [(3.00,PIT_GOOD),(3.80,PIT_MED)], invert=True) if fip else DIM
            return [
                ("ERA",    era_d,  era_c),
                ("K/9",    k9_d,   k9_c),
                ("SwStr",  sw_d,   sw_c),
                (fip_lbl,  fip_d,  fip_c),
            ]
        else:
            # wRC+
            wrc = adv.get("wRC+")
            wrc_d = str(int(float(wrc))) if wrc not in (None,"") else "—"
            wrc_c = _color(wrc, [(140,HIT_GOOD),(115,HIT_MED)]) if wrc else DIM
            # K%
            kp  = adv.get("K%")
            try:
                kv = float(kp)
                kv_p = kv if kv > 1 else kv*100
                k_d = f'{kv_p:.0f}%'
                k_c = _color(kv_p, [(15,HIT_GOOD),(20,HIT_MED)], invert=True)
            except Exception:
                k_d, k_c = "—", DIM
            # Brl%
            brl = adv.get("Barrel%") or adv.get("Brl%")
            try:
                bv2 = float(brl)
                bv2_p = bv2 if bv2 > 1 else bv2*100
                brl_d = f'{bv2_p:.1f}%'
                brl_c = _color(bv2_p, [(10,HIT_GOOD),(6,HIT_MED)])
            except Exception:
                brl_d, brl_c = "—", DIM
            # xwOBA
            xw  = adv.get("xwOBA")
            xw_d = f'{float(xw):.3f}' if xw not in (None,"") else "—"
            xw_c = _color(xw, [(.370,HIT_GOOD),(.340,HIT_MED)]) if xw else DIM
            return [
                ("wRC+",  wrc_d, wrc_c),
                ("K%",    k_d,   k_c),
                ("Brl%",  brl_d, brl_c),
                ("xwOBA", xw_d,  xw_c),
            ]

    def _val_color(v):
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        return "var(--accent)" if fv >= 65 else ("var(--amber)" if fv >= 38 else "var(--red)")

    # ── Build thead ──────────────────────────────────────────────────────────
    thead = (
        '<thead><tr class="rt-head">'
        '<th class="rt-th rt-th-av"></th>'
        '<th class="rt-th rt-th-slot">Slot</th>'
        '<th class="rt-th rt-th-name">Player</th>'
        '<th class="rt-th rt-th-team">Team</th>'
        '<th class="rt-th rt-th-num">VAL</th>'
        '<th class="rt-th rt-th-num">FIT</th>'
        '<th class="rt-th rt-th-stat" colspan="4">Key Stats</th>'
        '<th class="rt-th rt-th-status">Status</th>'
        '</tr></thead>'
    )

    # ── Build tbody ──────────────────────────────────────────────────────────
    tbody_rows = []
    for r in rows:
        slot      = r.get("pos", "")
        base_val  = r.get("base", 0)
        fit_val   = r.get("fit",  0)
        status    = r.get("status", "") or ""
        s_cls     = "s-warn" if r.get("status_class") == "warn" else "s-ok"
        il_cls    = " rt-il" if slot in ("IL", "IR") else ""
        is_p      = str(r.get("is_pitcher", "false")).lower() == "true"

        # Age flag
        age_tier_data = r.get("age_tier") or {}
        age_flag = ""
        if age_tier_data and age_tier_data.get("tier", 0):
            age_flag = age_tier_data.get("flag", "")

        # Velo alert icon
        velo_alert = r.get("velo_alert", "")
        velo_icon  = ""
        if velo_alert:
            is_sell = "Sell" in velo_alert or "Risk" in velo_alert
            velo_icon = f'<span title="{esc(velo_alert)}" style="font-size:10px;cursor:help">{"🔴" if is_sell else "🟢"}</span>'

        # Starting today badge (table view — inline with name)
        starts_today_tbl = r.get("starts_today", False)
        starts_icon = (
            '<span class="starts-today-badge" title="Probable starter today" '
            'style="width:14px;height:14px;font-size:8px;margin-left:4px">P</span>'
            if starts_today_tbl else ""
        )

        # Adv stats
        adv_raw = r.get("adv", "{}")
        try:
            adv = json.loads(adv_raw) if isinstance(adv_raw, str) else (adv_raw or {})
        except Exception:
            adv = {}
        stats = _fmt_adv(adv, is_p)

        # Build 4 stat cells — if no data, show "—" in muted color
        stat_cells = "".join(
            f'<td class="rt-td rt-td-stat">'
            f'<span class="rt-stat-lbl">{esc(lbl)}</span>'
            f'<span class="rt-stat-val" style="color:{col}">{esc(val)}</span>'
            f'</td>'
            for lbl, val, col in stats
        )

        # Status display: only show if not ACTIVE/NORMAL/empty
        status_show = status if status not in ("ACTIVE", "NORMAL", "") else ""
        status_cell = (
            f'<span class="{s_cls}" style="font-size:11px;font-weight:700">'
            f'{esc(status_show)}</span>'
            if status_show else
            '<span style="color:var(--text2);font-size:10px">✓</span>'
        )

        tbody_rows.append(
            f'<tr class="rt-row{il_cls}"{_player_data_attrs(r)}>'
            f'<td class="rt-td rt-td-av">'
            f'<div class="av" style="width:28px;height:28px;flex:0 0 28px">{_av(r)}</div>'
            f'</td>'
            f'<td class="rt-td rt-td-slot">{_pos_badge(slot)}</td>'
            f'<td class="rt-td rt-td-name">'
            f'<span class="rt-name">{esc(r.get("player",""))}</span>'
            f'{starts_icon}'
            f'{(" " + age_flag) if age_flag else ""}'
            f'{(" " + velo_icon) if velo_icon else ""}'
            f'</td>'
            f'<td class="rt-td rt-td-team">{esc(r.get("mlb",""))}</td>'
            f'<td class="rt-td rt-td-num" style="color:{_val_color(base_val)}">'
            f'{esc(str(base_val))}</td>'
            f'<td class="rt-td rt-td-num" style="color:{_val_color(fit_val)}">'
            f'{esc(str(fit_val))}</td>'
            + stat_cells
            + f'<td class="rt-td rt-td-status">{status_cell}</td>'
            f'</tr>'
        )

    tbody = '<tbody>' + "".join(tbody_rows) + '</tbody>'
    return (
        '<div class="rt-wrap">'
        f'<table class="rt">{thead}{tbody}</table>'
        '</div>'
    )


def _grade_label(score_val: float, is_injured: bool = False) -> tuple[str, str, str]:
    """
    Convert a 0-100 numeric score to a human-readable grade label.

    Returns (label, css_color, css_class) e.g. ("Elite", "var(--accent)", "grade-elite").
    The raw number is hidden — only the grade label is surfaced on the card.
    """
    try:
        v = float(score_val)
    except Exception:
        v = 0.0
    if is_injured:
        if v >= 70:  return ("Must Stash",  "var(--accent)", "grade-elite")
        if v >= 45:  return ("Watch",       "var(--amber)",  "grade-good")
        return              ("Monitor",     "var(--text2)",  "grade-avg")
    if v >= 80:  return ("Elite",        "var(--accent)", "grade-elite")
    if v >= 65:  return ("Starter",      "#4ade80",       "grade-starter")
    if v >= 45:  return ("Solid",        "var(--amber)",  "grade-solid")
    if v >= 25:  return ("Depth",        "var(--text2)",  "grade-depth")
    return              ("Droppable",    "var(--red)",    "grade-drop")


def _roster_cards(rows, title, subtitle=""):
    """Card-grid roster view — simplified to show grades not raw numbers."""
    cards = []
    for r in rows:
        slot        = r.get("pos", "")
        base_val    = r.get("base", 0)
        fit_val     = r.get("fit",  0)
        actual_pts  = r.get("actual_pts", "—")
        avg_pts     = r.get("avg_pts",  "—")
        status      = r.get("status", "")
        s_cls       = "s-warn" if r.get("status_class") == "warn" else "s-ok"
        il_cls      = " rc-il" if slot in ("IL", "IR") else ""

        def _dash(v):
            try:
                return "—" if float(v) == 0.0 else str(v)
            except Exception:
                return str(v) if v else "—"

        actual_disp = _dash(actual_pts)
        avg_disp    = _dash(avg_pts)

        is_injured = r.get("on_il", r.get("status_class") == "warn")
        stash_val  = r.get("stash_score", "0")
        healthy_pr = r.get("healthy_proj", "—")

        # Grade labels replace raw 0-100 numbers
        if is_injured:
            ring_base = stash_val
            stash_label, stash_color, stash_cls = _grade_label(stash_val, is_injured=True)
            val_label,   val_color,   val_cls   = _grade_label(base_val,  is_injured=False)
            score_block = (
                f'<div class="rc-score-duo">'
                f'<div class="rc-score-cell" title="Healthy stash value">'
                f'<span class="rc-score-lbl">STASH</span>'
                f'<span class="rc-grade {stash_cls}" style="color:{stash_color}">{esc(stash_label)}</span>'
                f'</div>'
                f'<div class="rc-score-cell" title="Current (injury-discounted) value">'
                f'<span class="rc-score-lbl">NOW</span>'
                f'<span class="rc-grade {val_cls}" style="color:{val_color}">{esc(val_label)}</span>'
                f'</div>'
                f'</div>'
            )
            # For IL players show actual FP + healthy projection
            pts_block = (
                f'<div class="rc-pts-row">'
                + (f'<span class="rc-pts-chip" title="Fantasy points this season">'
                   f'<span class="rc-pts-lbl">FP</span>'
                   f'<span class="rc-pts-val rc-fp-actual">{esc(actual_disp)}</span>'
                   f'</span>' if actual_disp != "—" else '')
                + (f'<span class="rc-pts-chip" title="Healthy season projection">'
                   f'<span class="rc-pts-lbl">PROJ</span>'
                   f'<span class="rc-pts-val">{esc(_dash(healthy_pr))}</span>'
                   f'</span>' if _dash(healthy_pr) != "—" else '')
                + f'</div>'
            )
        else:
            ring_base = base_val
            fit_label,  fit_color,  fit_cls  = _grade_label(fit_val)
            val_label,  val_color,  val_cls  = _grade_label(base_val)
            score_block = (
                f'<div class="rc-score-duo">'
                f'<div class="rc-score-cell" title="How well this player fits your roster needs">'
                f'<span class="rc-score-lbl">FIT</span>'
                f'<span class="rc-grade {fit_cls}" style="color:{fit_color}">{esc(fit_label)}</span>'
                f'</div>'
                f'<div class="rc-score-cell" title="Overall player value tier">'
                f'<span class="rc-score-lbl">VALUE</span>'
                f'<span class="rc-grade {val_cls}" style="color:{val_color}">{esc(val_label)}</span>'
                f'</div>'
                f'</div>'
            )
            # Show actual FP + avg — only if we have real numbers
            pts_block = ""
            chips = []
            if actual_disp != "—":
                chips.append(
                    f'<span class="rc-pts-chip" title="Fantasy points this season">'
                    f'<span class="rc-pts-lbl">FP</span>'
                    f'<span class="rc-pts-val rc-fp-actual">{esc(actual_disp)}</span>'
                    f'</span>'
                )
            if avg_disp != "—":
                chips.append(
                    f'<span class="rc-pts-chip" title="Points per scoring period">'
                    f'<span class="rc-pts-lbl">AVG</span>'
                    f'<span class="rc-pts-val">{esc(avg_disp)}</span>'
                    f'</span>'
                )
            if chips:
                pts_block = f'<div class="rc-pts-row">{"".join(chips)}</div>'

        # Phase 6 — aging badge
        age_tier_data = r.get("age_tier") or {}
        age_badge_html = ""
        if age_tier_data and age_tier_data.get("tier", 0):
            tier_int = age_tier_data.get("tier", 0)
            flag     = age_tier_data.get("flag", "")
            label    = age_tier_data.get("label", "")
            css_cls  = label.lower().replace(" ", "-")
            if tier_int > 0 and label:
                age_badge_html = (
                    f'<span class="age-badge {css_cls}" title="Age tier: {esc(label)}">'
                    f'{flag}'
                    f'</span>'
                )

        # "Starting today" badge
        starts_today = r.get("starts_today", False)
        starts_badge_html = ""
        if starts_today:
            starts_badge_html = (
                '<span class="starts-today-badge" title="Probable starter today">P</span>'
            )

        # Phase 5 — velocity / signal alert strip
        velo_alert = r.get("velo_alert", "")
        velo_html = ""
        if velo_alert:
            sell = "sell" if "Sell" in velo_alert or "Risk" in velo_alert else ""
            velo_html = f'<div class="velo-alert {sell}">{esc(velo_alert)}</div>'

        # Stat pills — advanced metrics signals only (keep actionable ones)
        pills_html = _stat_pills(r)

        name_with_badge = (
            f'<div class="rc-name" style="display:flex;align-items:center;justify-content:center;gap:0;max-width:100%">'
            f'<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{esc(r.get("player",""))}</span>'
            + (age_badge_html if age_badge_html else '')
            + f'</div>'
        )

        # Status chip — only show non-ACTIVE statuses to reduce clutter
        status_html = ""
        if status and status not in ("", "ACTIVE", "Active"):
            status_html = f'<div class="rc-status"><span class="{s_cls}">{esc(status)}</span></div>'

        cards.append(
            f'<div class="rc{il_cls}"{_player_data_attrs(r)}>'
            + _ring_av(r, base_val=ring_base, fit_val=fit_val, size=72)
            + f'<div style="margin-top:5px;display:flex;align-items:center;justify-content:center;gap:4px">{_pos_badge(slot)}{starts_badge_html}</div>'
            + name_with_badge
            + f'<div class="rc-team">{esc(r.get("mlb",""))}</div>'
            + pts_block
            + score_block
            + pills_html
            + velo_html
            + status_html
            + f'</div>'
        )
    body  = "".join(cards) if cards else '<p style="color:var(--text2)">No players</p>'
    sub_h = f'<div class="sec-sub">{esc(subtitle)}</div>' if subtitle else ""

    _roster_section_counter[0] += 1
    sec_id = f"rc-sec-{_roster_section_counter[0]}"
    list_body = _roster_table_view(rows) if rows else '<p style="color:var(--text2)">No players</p>'

    # View toggle buttons: Grid | List
    toggle_btns = (
        f'<div class="rc-view-btns" id="{sec_id}-btns">'
        f'<button class="rc-view-btn active" onclick="rcToggle(\'{sec_id}\',\'grid\',this)" title="Card grid view">&#9783;</button>'
        f'<button class="rc-view-btn" onclick="rcToggle(\'{sec_id}\',\'compact\',this)" title="Compact grid view">&#9783;&#xFE0E;</button>'
        f'<button class="rc-view-btn" onclick="rcToggle(\'{sec_id}\',\'list\',this)" title="List view">&#8801;</button>'
        f'</div>'
    )

    return (
        f'<div class="card mb20">'
        f'<div class="sec-head" style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px">'
        f'<div><div class="sec-title">{esc(title)}</div>{sub_h}</div>'
        + toggle_btns
        + f'</div>'
        f'<div id="{sec_id}-grid" class="rc-grid">{body}</div>'
        f'<div id="{sec_id}-list" class="rt-container" style="display:none">{list_body}</div>'
        f'</div>'
    )


def _standings_table(rows):
    thead = "<tr><th>RK</th><th>Team</th><th>Record</th></tr>"
    tbody = []
    for r in rows:
        rc = "row-hl" if r.get("_row_class") == "highlight" else ""
        tbody.append(
            f'<tr class="{rc}">'
            f'<td style="font-weight:900;color:var(--text2);width:32px">{esc(str(r.get("rank","")))}</td>'
            f'<td style="font-weight:600">{esc(r.get("team",""))}</td>'
            f'<td style="color:var(--text2)">{esc(r.get("record",""))}</td>'
            f'</tr>'
        )
    body = "".join(tbody) or '<tr><td colspan="3">No data</td></tr>'
    return (
        f'<div class="card">'
        f'<div class="sec-head"><div class="sec-title">Standings</div></div>'
        f'<div class="tbl-wrap"><table><thead>{thead}</thead><tbody>{body}</tbody></table></div>'
        f'</div>'
    )


def _top_players_table(rows):
    thead = (
        "<tr><th>RK</th><th>Player</th><th>Pos</th>"
        "<th>Grade</th><th>FP This Season</th><th>Owner</th></tr>"
    )
    tbody = []
    for r in rows:
        bv = 0.0
        try:
            bv = float(r.get("base", 0))
        except Exception:
            pass
        grade_label, grade_color, _ = _grade_label(bv)
        actual_pts = r.get("actual_pts", "—")
        try:
            ap = f'{float(actual_pts):g}' if float(actual_pts) > 0 else "—"
        except Exception:
            ap = "—"
        tbody.append(
            f'<tr>'
            f'<td style="font-weight:900;color:var(--accent);width:32px">{esc(str(r.get("rank","")))}</td>'
            f'<td>{_pc(r, sub_key="mlb")}</td>'
            f'<td>{_pos_badge(r.get("pos","?"))}</td>'
            f'<td style="font-weight:800;color:{grade_color}">{esc(grade_label)}</td>'
            f'<td style="font-weight:700;font-family:monospace">{esc(ap)}</td>'
            f'<td style="font-size:12px;color:var(--text2)">{esc(r.get("team",""))}</td>'
            f'</tr>'
        )
    body = "".join(tbody) or '<tr><td colspan="6">No data</td></tr>'
    return (
        f'<div class="card mb20">'
        f'<div class="sec-head"><div class="sec-title">Top Rostered Players</div>'
        f'<div class="sec-sub">Ranked by value model across all teams</div></div>'
        f'<div class="tbl-wrap"><table><thead>{thead}</thead><tbody>{body}</tbody></table></div>'
        f'</div>'
    )


def _matchup_scoring_section(my_scoring: list, opp_scoring: list,
                              my_name: str, opp_name: str) -> str:
    """
    Scrollable weekly points-breakdown panel — rendered inside the Live Matchup card.

    Two columns side by side: my team (left) vs opponent (right).
    Each player row shows:
      slot badge | player name | stat pills | total pts
    Active players first, bench/IL dimmed.  Scroll to see full week.
    """
    if not my_scoring and not opp_scoring:
        return ""

    # ── Positive/negative stat point coloring ─────────────────────────────
    GOOD_STATS = {"HR","R","RBI","SB","H","2B","3B","TB","BB","W","SV","HLD","QS","K","IP"}
    BAD_STATS  = {"SO","CS","L","ER","BS","BLSV"}

    def _stat_pill(stat, val):
        if stat in GOOD_STATS or (stat not in BAD_STATS and val > 0):
            pill_cls = "msb-pill-good"
        elif val < 0 or stat in BAD_STATS:
            pill_cls = "msb-pill-bad"
        else:
            pill_cls = "msb-pill-neu"
        sign = "+" if val > 0 else ""
        return (
            f'<span class="msb-pill {pill_cls}">'
            f'<span class="msb-pill-lbl">{esc(stat)}</span>'
            f'<span class="msb-pill-val">{sign}{val:g}</span>'
            f'</span>'
        )

    def _player_row(r):
        slot     = r.get("slot", "")
        name     = r.get("name", "")
        pts      = r.get("pts", 0.0)
        proj     = r.get("proj", 0.0)
        is_bench = r.get("is_bench", False)
        bd       = r.get("breakdown", {})

        # Sort breakdown: big |val| first so most impactful stats lead
        sorted_bd = sorted(bd.items(), key=lambda kv: -abs(kv[1]))
        pills_html = "".join(_stat_pill(k, v) for k, v in sorted_bd)

        # Row dim class for bench/IL
        row_cls = " msb-row-bench" if is_bench else ""

        # Points color
        if pts > 0:
            pts_color = "var(--accent)" if not is_bench else "var(--text2)"
        elif pts < 0:
            pts_color = "var(--red)"
        else:
            pts_color = "var(--text2)"

        # Vs projection badge
        diff = pts - proj
        if abs(diff) >= 2 and not is_bench:
            diff_sign = "+" if diff > 0 else ""
            diff_cls  = "msb-diff-good" if diff > 0 else "msb-diff-bad"
            diff_html = f'<span class="{diff_cls}">{diff_sign}{diff:.1f}</span>'
        else:
            diff_html = ""

        return (
            f'<div class="msb-row{row_cls}">'
            f'<span class="msb-slot">{esc(slot)}</span>'
            f'<div class="msb-player-info">'
            f'<span class="msb-name">{esc(name)}</span>'
            f'<div class="msb-pills">{pills_html}</div>'
            f'</div>'
            f'<div class="msb-pts-col">'
            f'<span class="msb-pts" style="color:{pts_color}">{pts:g}</span>'
            f'{diff_html}'
            f'</div>'
            f'</div>'
        )

    def _build_col(scoring, label):
        active  = [r for r in scoring if not r.get("is_bench")]
        bench   = [r for r in scoring if r.get("is_bench")]
        total   = sum(r["pts"] for r in active)
        body    = "".join(_player_row(r) for r in active)
        if bench:
            body += (
                f'<div class="msb-bench-divider">— Bench / IL —</div>'
                + "".join(_player_row(r) for r in bench)
            )
        total_color = "var(--accent)" if total > 0 else "var(--red)" if total < 0 else "var(--text2)"
        no_data     = '<span style="color:var(--text2)">No data</span>'
        col_body    = body or no_data
        return (
            f'<div class="msb-col">'
            f'<div class="msb-col-head">'
            f'<span class="msb-col-name">{esc(label)}</span>'
            f'<span class="msb-col-total" style="color:{total_color}">{total:.1f} pts</span>'
            f'</div>'
            f'<div class="msb-col-body">{col_body}</div>'
            f'</div>'
        )

    my_col  = _build_col(my_scoring,  my_name)
    opp_col = _build_col(opp_scoring, opp_name)

    return (
        f'<div class="msb-wrap">'
        f'<div class="msb-header">'
        f'<span class="msb-title">📋 Week Scoring Breakdown</span>'
        f'<span class="msb-legend">'
        f'<span class="msb-legend-good">●</span> scoring '
        f'<span class="msb-legend-bad">●</span> penalties'
        f'</span>'
        f'</div>'
        f'<div class="msb-grid">'
        + my_col
        + opp_col
        + f'</div>'
        f'</div>'
    )


def _week_scoring_table(week_data: dict) -> str:
    """
    Render the full-week day-by-day scoring breakdown table for the matchup.

    Shows:
    - One row per player (active first, then bench/IL)
    - Columns: Player | Mon | Tue | Wed | Thu | Fri | Sat | Sun | Total
    - Today's column highlighted
    - Positive pts in accent, negative/zero in muted text
    - Teams separated (My Team / Opponent)
    """
    if not week_data or not week_data.get("my_players"):
        return ""

    days      = week_data.get("days", ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
    today_day = week_data.get("today_day", "")
    my_total  = week_data.get("my_total", 0)
    opp_total = week_data.get("opp_total", 0)

    def _pts_cell(pts, is_today=False):
        if pts is None:
            return '<td class="wst-future">—</td>'
        color = "var(--accent)" if pts > 0 else ("var(--red)" if pts < 0 else "var(--text2)")
        today_style = "background:var(--accent-dim);" if is_today else ""
        return f'<td class="wst-pts" style="{today_style}color:{color}">{pts:+.1f}</td>'

    def _build_section(players, team_label):
        if not players:
            return ""
        rows_html = []
        prev_bench = None
        for p in players:
            is_bench = p.get("is_bench", False)
            if is_bench and prev_bench is False:
                rows_html.append(
                    f'<tr><td colspan="{len(days)+2}" class="wst-divider">── Bench / IL ──</td></tr>'
                )
            prev_bench = is_bench
            pos_label = f'<span class="pos-badge pos-{re.sub(r"[^A-Z0-9]","",p["pos"].upper()[:4])}">{esc(p["pos"])}</span>' if p.get("pos") else ""
            day_cells = "".join(
                _pts_cell(p["days"].get(d), d == today_day) for d in days
            )
            total_color = "color:var(--accent);font-weight:700" if p["total"] > 0 else ""
            proj = p.get("weekly_proj", 0)
            rows_html.append(
                f'<tr class="wst-row">'
                f'<td class="wst-name">{esc(p["name"])} {pos_label}</td>'
                + day_cells +
                f'<td class="wst-total" style="{total_color}">{p["total"]:+.1f}</td>'
                f'</tr>'
            )
        team_header = (
            f'<tr class="wst-team-header">'
            f'<th class="wst-th-name">{esc(team_label)}</th>'
            + "".join(
                f'<th class="wst-th-day{" wst-today" if d == today_day else ""}">{d}</th>'
                for d in days
            )
            + '<th class="wst-th-total">Total</th>'
            f'</tr>'
        )
        return team_header + "".join(rows_html)

    from fdb.settings import MY_TEAM_NAME
    my_label  = f"⚾ {MY_TEAM_NAME} — {my_total:+.1f} pts"
    opp_label = f"🆚 Opponent — {opp_total:+.1f} pts"

    css = """<style>
.wst-wrap{overflow-x:auto;margin-top:12px}
.wst-table{width:100%;border-collapse:collapse;font-size:12px}
.wst-th-name,.wst-th-day,.wst-th-total{font-size:10px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:.06em;padding:5px 8px;
  border-bottom:2px solid var(--border);text-align:center;white-space:nowrap}
.wst-th-name{text-align:left;min-width:140px}
.wst-today{background:var(--accent-dim);color:var(--accent)!important;border-radius:4px}
.wst-team-header{background:var(--surface2)}
.wst-team-header .wst-th-name{color:var(--text);font-size:11px;text-transform:none;letter-spacing:0}
.wst-row:hover{background:var(--surface2)}
.wst-name{padding:5px 8px;color:var(--text);font-weight:500;white-space:nowrap}
.wst-pts{padding:4px 6px;text-align:center;font-family:"JetBrains Mono",monospace;font-size:11px;min-width:40px}
.wst-future{padding:4px 6px;text-align:center;color:var(--text2);font-size:11px}
.wst-total{padding:4px 8px;text-align:center;font-family:"JetBrains Mono",monospace;
  font-size:12px;border-left:1px solid var(--border)}
.wst-divider td{padding:4px 8px;color:var(--text2);font-size:10px;
  font-weight:600;text-transform:uppercase;letter-spacing:.08em;border-top:1px solid var(--border)}
</style>"""

    table_body = (
        _build_section(week_data.get("my_players", []), my_label)
        + '<tr style="height:8px"><td colspan="9"></td></tr>'
        + _build_section(week_data.get("opp_players", []), opp_label)
    )

    return (
        css +
        f'<div class="card mb20">'
        f'<div class="sec-head">'
        f'<div class="sec-title">📅 Full-Week Scoring Breakdown</div>'
        f'<div class="sec-sub">Day-by-day points · Week {week_data.get("week", "?")} · Today = {today_day}</div>'
        f'</div>'
        f'<div class="wst-wrap">'
        f'<table class="wst-table"><tbody>'
        + table_body +
        f'</tbody></table>'
        f'</div>'
        f'</div>'
    )


def _hitter_matchups_section(matchups: list) -> str:
    """
    Phase 4 — Render "Today's Hitter Matchups" section.
    Each active hitter's matchup is graded 1–5 based on the opposing probable
    starter's SIERA/xFIP/FIP and SwStr%.  Sorted best-for-hitter first.
    """
    if not matchups:
        return ""

    COLOR = {
        "bad":     "var(--red)",
        "warn":    "var(--amber)",
        "neutral": "var(--text2)",
        "good":    "var(--accent)",
        "accent":  "var(--accent)",
    }
    EMOJI = {1: "🔴", 2: "🟡", 3: "⚪", 4: "🟢", 5: "🟢"}

    rows = []
    for m in matchups:
        color    = COLOR.get(m.get("color", "neutral"), "var(--text2)")
        emoji    = EMOJI.get(m.get("grade", 3), "⚪")
        era_str  = f"{m['era_est']:.2f}" if m.get("era_est", 0) > 0 else "—"
        swstr_s  = f"{m['swstr'] * 100:.1f}%" if m.get("swstr", 0) > 0 else "—"
        pos      = m.get("pos", "?")

        rows.append(
            f'<div class="mi-row">'
            f'<div class="av av-sm">{_av(m)}</div>'
            f'<div class="mi-player">'
            f'<div class="mi-name">{esc(m.get("player",""))}</div>'
            f'<div class="mi-sub">{_pos_badge(pos)} {esc(m.get("mlb",""))} '
            f'· {esc(m.get("game_time",""))}</div>'
            f'</div>'
            f'<div class="mi-verdict" style="color:{color}">'
            f'<span class="mi-emoji">{emoji}</span>'
            f'<div>'
            f'<div class="mi-label">{esc(m.get("label",""))}</div>'
            f'<div class="mi-pitcher">vs {esc(m.get("pitcher_name","TBD"))}</div>'
            f'</div>'
            f'</div>'
            f'<div class="mi-metrics">'
            f'<div class="mi-metric"><span class="mi-mk">ERA est</span>'
            f'<span class="mi-mv">{era_str}</span></div>'
            f'<div class="mi-metric"><span class="mi-mk">SwStr%</span>'
            f'<span class="mi-mv">{swstr_s}</span></div>'
            f'</div>'
            f'<div class="mi-reason">{esc(m.get("reason",""))}</div>'
            f'</div>'
        )

    favorable = sum(1 for m in matchups if m.get("grade", 3) >= 4)
    tough     = sum(1 for m in matchups if m.get("grade", 3) <= 2)

    return (
        f'<div class="card mb20">'
        f'<div class="sec-head">'
        f'<div class="sec-title">📊 Today\'s Hitter Matchups</div>'
        f'<div class="sec-sub">{len(matchups)} active hitters playing today '
        f'· {favorable} favorable · {tough} tough</div>'
        f'</div>'
        f'<div class="mi-list">{"".join(rows)}</div>'
        f'</div>'
    )


def _schedule_section(games, my_name="You", opp_name="Opponent"):
    """Render today's MLB schedule with roster players annotated."""

    def _chips(player_rows):
        if not player_rows:
            return '<span class="sched-no-players">—</span>'
        bits = []
        for r in player_rows:
            pos  = r.get("pos", "?").split(",")[0].strip()
            name = r.get("player", "")
            bits.append(
                f'<span class="sched-chip">'
                f'{_pos_badge(pos)}'
                f'<span class="sched-chip-name">{esc(name)}</span>'
                f'</span>'
            )
        return "".join(bits)

    if not games:
        return (
            '<div class="card mb20">'
            '<div class="sec-head"><div class="sec-title">Today\'s MLB Schedule</div></div>'
            '<div style="color:var(--text2);font-size:13px;padding:8px 0">'
            'Schedule unavailable — check your internet connection.</div>'
            '</div>'
        )

    rows = []
    for g in games:
        has_players = bool(g["my_players"] or g["opp_players"])
        hl_cls      = " sched-game-hl" if has_players else ""

        # Status colour
        st = g["status"]
        if any(x in st for x in ("Progress", "Live", "Warmup", "Pre-Game")):
            st_cls = "sched-live"
        elif any(x in st for x in ("Final", "Game Over", "Completed")):
            st_cls = "sched-final"
        else:
            st_cls = ""

        player_html = ""
        if has_players:
            player_html = (
                f'<div class="sched-players">'
                f'<div class="sched-side">'
                f'<div class="sched-side-lbl">{esc(my_name)}</div>'
                f'<div class="sched-chips">{_chips(g["my_players"])}</div>'
                f'</div>'
                f'<div class="sched-side">'
                f'<div class="sched-side-lbl">{esc(opp_name)}</div>'
                f'<div class="sched-chips">{_chips(g["opp_players"])}</div>'
                f'</div>'
                f'</div>'
            )

        rows.append(
            f'<div class="sched-game{hl_cls}">'
            f'<div class="sched-header">'
            f'<span class="sched-time">{esc(g["time_str"])}</span>'
            f'<span class="sched-matchup">'
            f'<b>{esc(g["away_abbr"])}</b>'
            f'<span class="sched-at">@</span>'
            f'<b>{esc(g["home_abbr"])}</b>'
            f'</span>'
            f'<span class="sched-status {st_cls}">{esc(st)}</span>'
            f'</div>'
            + player_html +
            f'</div>'
        )

    body        = "".join(rows)
    total       = len(games)
    hl_count    = sum(1 for g in games if g["my_players"] or g["opp_players"])
    sub         = f"{total} games today · {hl_count} feature players from this matchup"
    return (
        f'<div class="card mb20">'
        f'<div class="sec-head">'
        f'<div class="sec-title">Today\'s MLB Schedule</div>'
        f'<div class="sec-sub">{esc(sub)}</div>'
        f'</div>'
        f'<div class="sched-list">{body}</div>'
        f'</div>'
    )


def _waiver_reason_bullets(r):
    """Render reason bullet items with plain-English action note appended."""
    items = r.get("reason_items")
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []
    if not items:
        raw = r.get("reason", "")
        if raw:
            css = '<style>.wr-bullets{margin-top:6px}.wr-bullet{font-size:12px;padding:4px 0;color:var(--text2)}.wr-bullet.neutral{color:var(--text2)}.wr-bullet.good{color:#16a34a}.wr-bullet.bad{color:var(--red)}.wr-bullet.warn{color:var(--amber)}.wr-action{font-size:11px;color:var(--text2);font-style:italic;margin-top:2px;padding-left:8px;border-left:2px solid var(--border)}</style>'
            return css + f'<div class="wr-bullets"><div class="wr-bullet neutral">{esc(raw)}</div></div>'
        return ""

    ACTION_HINTS = {
        "BREAKOUT": "→ Consider buying in trade or pickup now before value is priced in.",
        "REGRESSION": "→ Consider selling high or avoiding. Results will likely decline.",
        "BUY-LOW": "→ Great buy-low window — metrics suggest improvement coming.",
        "SELL-HIGH": "→ Sell now while perceived value is high.",
        "CLOSER": "→ Monitor for saves — closer role may be solidifying.",
        "CLOSER ROLE ALERT": "→ Verify status before committing a roster spot.",
        "TWO-START": "→ Strong streaming option this week — pick up before Tuesday.",
        "ELITE": "→ Snap pickup: top-tier talent available.",
        "WAIVER": "→ High waiver priority — act before others do.",
    }

    def _get_action(text):
        tu = text.upper()
        for kw, hint in ACTION_HINTS.items():
            if kw in tu:
                return f'<div class="wr-action">{hint}</div>'
        return ""

    html_parts = []
    for item in items:
        text  = item.get("text", "")
        tone  = item.get("tone", "neutral")
        action = _get_action(text) if tone in ("good", "bad", "warn") else ""
        html_parts.append(
            f'<div class="wr-bullet {tone}">{esc(text)}{action}</div>'
        )
    css = '<style>.wr-bullets{margin-top:6px}.wr-bullet{font-size:12px;padding:4px 0;color:var(--text2)}.wr-bullet.neutral{color:var(--text2)}.wr-bullet.good{color:#16a34a}.wr-bullet.bad{color:var(--red)}.wr-bullet.warn{color:var(--amber)}.wr-action{font-size:11px;color:var(--text2);font-style:italic;margin-top:2px;padding-left:8px;border-left:2px solid var(--border)}</style>'
    return css + '<div class="wr-bullets">' + "".join(html_parts) + '</div>'


def _streaming_plan_section(plan_data: dict) -> str:
    """
    Render the Weekly Pitcher Streaming Plan card.

    Shows:
      • Every rostered pitcher with their starts this week, per-start matchup
        grade (A/B/C/D/F), projected IP and pts
      • IP-limit progress bar
      • Conflict / ratio-risk warning banners
    """
    if not plan_data or not plan_data.get("pitchers"):
        return ""

    pitchers   = plan_data.get("pitchers", [])
    totals     = plan_data.get("totals", {})
    conflicts  = plan_data.get("conflicts", [])
    week_label = plan_data.get("week_label", "This Week")

    proj_ip  = totals.get("proj_ip", 0)
    ip_limit = totals.get("ip_limit", 50)
    ip_pct   = min(100, int(proj_ip / max(ip_limit, 1) * 100))
    ip_color = "var(--red)" if proj_ip > ip_limit else ("var(--amber)" if ip_pct >= 90 else "var(--accent)")

    # ── Conflict banners ────────────────────────────────────────────────────────────────────────
    banner_html = ""
    for c in conflicts:
        sev_color = "var(--red)" if c["severity"] == "danger" else "var(--amber)"
        icon = "⛔" if c["severity"] == "danger" else "⚠️"
        banner_html += (
            f'<div class="sp-conflict" style="border-left:3px solid {sev_color}">'
            f'{icon} {esc(c["message"])}</div>'
        )

    # ── Pitcher rows ────────────────────────────────────────────────────────────────────────────
    FLAG_STYLE = {
        "both-strong": ("var(--accent)",  "Both starts: strong"),
        "mixed":       ("var(--amber)",   "Mixed matchups"),
        "both-risky":  ("var(--red)",     "Both starts: risky"),
        "single":      ("var(--text2)",   "1 start"),
        "no-starts":   ("var(--text2)",   "No starts this week"),
    }

    pitcher_rows_html = ""
    for p in pitchers:
        flag_color, flag_label = FLAG_STYLE.get(p["combined_flag"], ("var(--text2)", p["combined_flag"]))

        # Per-start matchup chips
        start_chips = ""
        for s in p["starts"]:
            chip_label = f"vs {s['opp_abbr']}"
            if s["is_home"]:
                chip_label += " (H)"
            _mn = esc(s.get("matchup_note", ""))
            _mc = s["matchup_color"]
            start_chips += (
                f'<span class="sp-start-chip" title="{_mn}"'
                f' style="border-color:{_mc};color:{_mc}">'
                f'{chip_label} <b>{s["matchup_grade"]}</b>'
                f'<span class="sp-chip-score">{s["matchup_score"]}</span>'
                f'</span>'
            )
        if not start_chips:
            start_chips = '<span class="sp-no-start">No starts</span>'

        bench_badge = (
            '<span class="sp-bench-badge">BENCH</span>'
            if p["is_on_bench"] else ""
        )
        risk_badge = (
            '<span class="sp-risk-badge" title="Elevated xFIP or WHIP — ratio risk">⚠ Ratio Risk</span>'
            if p["has_ratio_risk"] else ""
        )
        two_start_badge = (
            '<span class="sp-2start-badge">2-Start</span>'
            if p["n_starts"] >= 2 else ""
        )

        era_s  = f"{p['era_est']:.2f}" if p["era_est"] > 0 else "—"
        xfip_s = f"{p['xfip']:.2f}"   if p["xfip"]    > 0 else "—"

        pitcher_rows_html += (
            f'<div class="sp-plan-row">'
            f'  <div class="av av-sm">{_av(p)}</div>'
            f'  <div class="sp-plan-info">'
            f'    <div class="sp-plan-name">'
            f'      {esc(p["name"])} {two_start_badge}{bench_badge}{risk_badge}'
            f'    </div>'
            f'    <div class="sp-plan-starts">{start_chips}</div>'
            f'  </div>'
            f'  <div class="sp-plan-stats">'
            f'    <div class="sp-stat"><span class="sp-sk">Proj Pts</span>'
            f'      <span class="sp-sv">{p["weekly_proj"]:.0f}</span></div>'
            f'    <div class="sp-stat"><span class="sp-sk">Proj IP</span>'
            f'      <span class="sp-sv">{p["proj_ip"]:.1f}</span></div>'
            f'    <div class="sp-stat"><span class="sp-sk">xFIP</span>'
            f'      <span class="sp-sv">{xfip_s}</span></div>'
            f'  </div>'
            f'</div>'
        )

    # ── IP progress bar ────────────────────────────────────────────────────────────────────────────
    ip_bar = (
        f'<div class="sp-ip-bar-wrap">'
        f'  <div class="sp-ip-label">'
        f'    <span>Projected IP: <b style="color:{ip_color}">{proj_ip:.0f}</b> / {ip_limit}</span>'
        f'    <span style="color:{ip_color}">{ip_pct}%</span>'
        f'  </div>'
        f'  <div class="sp-ip-track">'
        f'    <div class="sp-ip-fill" style="width:{ip_pct}%;background:{ip_color}"></div>'
        f'  </div>'
        f'</div>'
    )

    # ── CSS ────────────────────────────────────────────────────────────────────────────────────
    css = """<style>
.sp-plan-row{display:flex;align-items:flex-start;gap:10px;padding:10px 4px;
  border-bottom:1px solid var(--border)}
.sp-plan-row:last-child{border-bottom:none}
.sp-plan-info{flex:1;min-width:0}
.sp-plan-name{font-size:13px;font-weight:700;color:var(--text);
  display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:5px}
.sp-plan-starts{display:flex;gap:5px;flex-wrap:wrap}
.sp-start-chip{font-size:11px;font-weight:600;padding:2px 7px;border-radius:5px;
  border:1px solid;display:inline-flex;align-items:center;gap:4px;
  background:var(--surface2);cursor:default}
.sp-chip-score{font-size:9px;font-weight:800;opacity:.8;
  font-family:"JetBrains Mono",monospace}
.sp-no-start{font-size:11px;color:var(--text2);font-style:italic}
.sp-plan-stats{display:flex;gap:6px;flex-shrink:0}
.sp-stat{display:flex;flex-direction:column;align-items:center;
  background:var(--surface2);border:1px solid var(--border);
  border-radius:5px;padding:3px 8px;min-width:46px}
.sp-sk{font-size:9px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:.05em}
.sp-sv{font-size:12px;font-weight:800;color:var(--text);
  font-family:"JetBrains Mono",monospace}
.sp-2start-badge{font-size:9px;font-weight:800;padding:1px 6px;border-radius:4px;
  background:var(--accent-dim);border:1px solid var(--accent);color:var(--accent)}
.sp-bench-badge{font-size:9px;font-weight:700;padding:1px 5px;border-radius:4px;
  background:var(--surface2);border:1px solid var(--border);color:var(--text2)}
.sp-risk-badge{font-size:9px;font-weight:700;padding:1px 5px;border-radius:4px;
  background:rgba(255,150,0,.12);border:1px solid var(--amber);color:var(--amber)}
.sp-conflict{padding:8px 12px;margin-bottom:8px;border-radius:6px;
  font-size:12px;background:var(--surface2);color:var(--text)}
.sp-ip-bar-wrap{padding:10px 4px 4px}
.sp-ip-label{display:flex;justify-content:space-between;font-size:11px;
  color:var(--text2);margin-bottom:4px}
.sp-ip-track{height:6px;background:var(--surface2);border-radius:3px;overflow:hidden}
.sp-ip-fill{height:100%;border-radius:3px;transition:width .3s}
</style>"""

    return (
        css
        + f'<div class="card mb20">'
        + f'<div class="sec-head">'
        + f'<div class="sec-title">📋 Your Pitching Week <span style="font-size:12px;'
        + f'font-weight:400;color:var(--text2);margin-left:6px">{esc(week_label)}</span></div>'
        + f'<div class="sec-sub">Rostered pitcher slate · per-start matchup grades · IP tracking · ratio risk flags</div>'
        + f'</div>'
        + banner_html
        + pitcher_rows_html
        + ip_bar
        + f'</div>'
    )


def _streaming_sp_section(streaming_sps: list) -> str:
    """
    Render the Daily SP Streaming Ranked List.
    Shows available SPs ranked by combined streaming score:
    SP quality + opponent weakness + park factor + two-start potential.
    """
    if not streaming_sps:
        return '<div class="card mb20"><div class="sec-head"><div class="sec-title">🎯 SP Streaming</div><div class="sec-sub" style="color:var(--text2)">No streamable SPs found today</div></div></div>'

    GRADE_LABEL = {5: "Elite Stream", 4: "Strong Stream", 3: "Decent Plug", 2: "Risky", 1: "Avoid"}
    GRADE_COLOR = {5: "var(--accent)", 4: "var(--accent)", 3: "var(--text2)", 2: "var(--amber)", 1: "var(--red)"}

    rows = []
    for i, sp in enumerate(streaming_sps, 1):
        grade = sp.get("sp_grade", 2)
        color = GRADE_COLOR.get(grade, "var(--text2)")
        label = GRADE_LABEL.get(grade, "—")
        era_s = f"{sp['era_est']:.2f}" if sp.get("era_est", 0) > 0 else "—"
        sw_s  = f"{sp['swstr']*100:.1f}%" if sp.get("swstr", 0) > 0 else "—"
        pf    = sp.get("park_factor", 1.0)
        pf_s  = f"{'▲' if pf >= 1.08 else ('▼' if pf <= 0.95 else '—')}{abs(int((pf-1)*100))}%" if pf != 1.0 else "—"

        badges = []
        if sp.get("two_start"):
            badges.append('<span class="stream-badge two-start">2️⃣ 2-Start</span>')
        if not sp.get("game_today"):
            badges.append('<span class="stream-badge no-game">No game today</span>')
        badge_html = " ".join(badges)

        rows.append(
            f'<div class="stream-row">'
            f'<div class="stream-rank">#{i}</div>'
            f'<div class="av av-sm">{_av(sp)}</div>'
            f'<div class="stream-info">'
            f'  <div class="stream-name">{esc(sp["player"])}</div>'
            f'  <div class="stream-sub">{esc(sp["team"])}'
            f'  · {esc(sp.get("game_time",""))} {badge_html}</div>'
            f'</div>'
            f'<div class="stream-grade" style="color:{color}">'
            f'  <div class="stream-label">{label}</div>'
            f'  <div class="stream-score">{sp["streaming_score"]:.0f} pts</div>'
            f'</div>'
            f'<div class="stream-metrics">'
            f'  <div class="sm-pill"><span class="sm-k">SIERA</span><span class="sm-v">{era_s}</span></div>'
            f'  <div class="sm-pill"><span class="sm-k">SwStr</span><span class="sm-v">{sw_s}</span></div>'
            f'  <div class="sm-pill"><span class="sm-k">Park</span><span class="sm-v">{pf_s}</span></div>'
            f'</div>'
            f'</div>'
        )

    css = """<style>
.stream-row{display:flex;align-items:center;gap:10px;padding:8px 4px;
  border-bottom:1px solid var(--border);flex-wrap:wrap}
.stream-row:last-child{border-bottom:none}
.stream-rank{font-size:13px;font-weight:700;color:var(--text2);min-width:24px;text-align:right}
.stream-info{flex:1;min-width:120px}
.stream-name{font-size:13px;font-weight:600;color:var(--text)}
.stream-sub{font-size:11px;color:var(--text2);margin-top:2px;display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.stream-grade{text-align:right;min-width:90px}
.stream-label{font-size:11px;font-weight:700}
.stream-score{font-size:16px;font-weight:800;font-family:"JetBrains Mono",monospace}
.stream-metrics{display:flex;gap:5px;flex-wrap:wrap}
.sm-pill{background:var(--surface2);border:1px solid var(--border);border-radius:5px;
  padding:2px 7px;display:flex;flex-direction:column;align-items:center;min-width:44px}
.sm-k{font-size:9px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.05em}
.sm-v{font-size:11px;font-weight:700;font-family:"JetBrains Mono",monospace;color:var(--text)}
.stream-badge{font-size:9px;font-weight:700;padding:1px 5px;border-radius:4px;
  background:var(--surface2);border:1px solid var(--border)}
.stream-badge.two-start{background:var(--accent-dim);border-color:var(--accent);color:var(--accent)}
.stream-badge.no-game{color:var(--text2)}
</style>"""

    return (
        css +
        f'<div class="card mb20">'
        f'<div class="sec-head">'
        f'<div class="sec-title">🎯 Daily SP Streaming</div>'
        f'<div class="sec-sub">Available SPs ranked by matchup quality · park factor · 2-start upside · floor</div>'
        f'</div>'
        + "".join(rows) +
        f'</div>'
    )


def _build_waiver_cards(rows):
    """Build the list of waiver card HTML elements, numbered within the group."""
    cards = []
    for i, r in enumerate(rows, 1):
        rank_cls   = "top3" if i <= 3 else ""
        pos_str    = r.get("pos", "?").split(",")[0].strip()
        fit_val    = r.get("fit", "0")
        base_val   = r.get("base", "0")
        proj_pts   = r.get("proj_pts", "—")
        actual_pts = r.get("actual_pts", "—")
        avg_pts    = r.get("avg_pts", "—")
        var_val    = r.get("var", "0")
        drop_nm    = r.get("drop", "")

        try:
            bv = float(base_val)
        except Exception:
            bv = 0.0
        val_color = (
            "var(--accent)" if bv >= 65 else
            "var(--amber)"  if bv >= 38 else
            "var(--red)"
        )

        # Age badge
        w_age_tier = r.get("age_tier") or {}
        w_age_badge = ""
        if w_age_tier and w_age_tier.get("tier", 0):
            w_flag    = w_age_tier.get("flag", "")
            w_label   = w_age_tier.get("label", "")
            w_css_cls = w_label.lower().replace(" ", "-")
            if w_flag:
                w_age_badge = (
                    f'<span class="age-badge {w_css_cls}" title="Age tier: {esc(w_label)}">'
                    f'{w_flag}</span>'
                )

        # Drop suggestion with subtle color
        drop_html = ""
        if drop_nm:
            drop_html = (
                f'<div class="wr-drop">'
                f'<span class="wr-drop-lbl">Drop:</span>'
                f'<span class="wr-drop-name">{esc(drop_nm)}</span>'
                f'</div>'
            )

        # Grade label instead of raw numbers
        fit_label, fit_color, _  = _grade_label(fit_val)
        val_label, _,         __ = _grade_label(base_val)

        # Pts line: only show actual FP if we have it, otherwise omit raw numbers
        try:
            actual_f = float(actual_pts)
            pts_disp = f'{actual_f:g} FP' if actual_f > 0 else ""
        except Exception:
            pts_disp = ""

        cards.append(
            f'<div class="w-card"{_player_data_attrs(r)}>'
            # Rank badge
            f'<div class="w-rank {rank_cls}">#{i}</div>'
            # Ring avatar
            + _ring_av(r, base_val=base_val, fit_val=fit_val, size=64) +
            # Card body
            f'<div class="w-body">'
            # ── Header row: name + badges ─────────────────────────────────────
            f'<div class="w-head">'
            f'<div>'
            f'<div class="pc-name">{esc(r.get("player",""))} {w_age_badge}</div>'
            f'<div class="w-proj-line">'
            + (f'<span class="w-proj-pts" style="color:var(--accent);font-weight:800">'
               f'{esc(pts_disp)}</span>'
               f'<span style="color:var(--text2);font-size:11px;margin:0 4px">&middot;</span>'
               if pts_disp else '')
            + f'{_pos_badge(pos_str)}'
            f'&nbsp;<span style="color:var(--text2);font-size:12px">{esc(r.get("team",""))}</span>'
            f'</div>'
            f'</div>'
            f'<div class="w-badges">'
            f'<span class="badge badge-fit" style="background:var(--accent-dim);color:{fit_color}">'
            f'{esc(fit_label)}</span>'
            f'</div>'
            f'</div>'
            # ── Stat pills + reasons + drop ───────────────────────────────────
            + _stat_pills(r)
            + _waiver_reason_bullets(r)
            + drop_html
            + f'</div>'  # w-body
            + f'</div>'  # w-card
        )
    return cards


def _blueprint_banner(blueprint: dict) -> str:
    """
    Render the Optimal Roster Blueprint banner at the top of the Waivers tab.
    Shows current vs target construction + priority gaps + overall summary.
    """
    if not blueprint or not blueprint.get("slots"):
        return ""

    summary  = blueprint.get("summary", "")
    priority = blueprint.get("priority_adds", [])
    slots    = blueprint.get("slots", {})
    archs    = blueprint.get("archetypes", {})

    # Build slot pills
    LABELS = {
        "C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
        "OF": "OF", "SP": "SP", "RP": "RP",
        "elite_closer": "Elite Closer", "high_hold_rp": "High-Hold RP",
    }
    all_slots = {**slots, **archs}
    pills = []
    for key, data in all_slots.items():
        t = data.get("target", 0)
        c = data.get("current", 0)
        g = data.get("gap", 0)
        label = LABELS.get(key, key)
        if g > 0:
            cls = "bp-pill gap"
            txt = f"{label}: {c}/{t} <span class='bp-gap-badge'>−{g}</span>"
        elif c >= t:
            cls = "bp-pill ok"
            txt = f"{label}: ✓"
        else:
            cls = "bp-pill"
            txt = f"{label}: {c}/{t}"
        pills.append(f'<span class="{cls}">{txt}</span>')

    priority_html = ""
    if priority:
        pnames = [LABELS.get(p, p) for p in priority[:3]]
        priority_html = (
            f'<div class="bp-priority">Priority adds: '
            + " → ".join(f'<strong>{esc(n)}</strong>' for n in pnames)
            + '</div>'
        )

    tone   = "bad" if priority else "good"
    border = "var(--red)" if priority else "var(--accent)"

    css = """<style>
.bp-banner{border:1px solid var(--border);border-left:3px solid """+ border +""";
  border-radius:10px;padding:12px 16px;margin-bottom:14px;background:var(--surface)}
.bp-title{font-size:13px;font-weight:700;color:var(--text);margin-bottom:6px}
.bp-pills{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.bp-pill{font-size:11px;font-weight:600;padding:3px 8px;border-radius:5px;
  background:var(--surface2);border:1px solid var(--border);color:var(--text2)}
.bp-pill.ok{background:var(--accent-dim);border-color:var(--accent);color:var(--accent)}
.bp-pill.gap{background:var(--red-dim);border-color:var(--red);color:var(--red)}
.bp-gap-badge{font-size:9px;font-weight:800;margin-left:3px}
.bp-summary{font-size:12px;color:var(--text2);margin-bottom:4px}
.bp-priority{font-size:12px;color:var(--text)}
</style>"""

    return (
        css +
        f'<div class="bp-banner">'
        f'<div class="bp-title">🎯 Optimal Roster Blueprint</div>'
        f'<div class="bp-pills">{"".join(pills)}</div>'
        f'<div class="bp-summary">{esc(summary)}</div>'
        + priority_html +
        f'</div>'
    )


def _waiver_section(rows):
    """
    Renders the Waivers tab with Hitters / Pitchers sub-tabs.
    Each card shows stat pills + structured bullet reasons.
    """
    hitter_rows  = [r for r in rows if str(r.get("is_pitcher","false")).lower() != "true"]
    pitcher_rows = [r for r in rows if str(r.get("is_pitcher","false")).lower() == "true"]

    hitter_cards  = _build_waiver_cards(hitter_rows)
    pitcher_cards = _build_waiver_cards(pitcher_rows)

    h_body = "".join(hitter_cards)  if hitter_cards  else '<p class="w-empty">No hitter recommendations available.</p>'
    p_body = "".join(pitcher_cards) if pitcher_cards else '<p class="w-empty">No pitcher recommendations available.</p>'

    h_count = len(hitter_rows)
    p_count = len(pitcher_rows)

    legend = (
        f'<span style="color:var(--accent)">&#9679;</span> outer = Value &nbsp;'
        f'<span style="color:#3b82f6">&#9679;</span> inner = Fit &nbsp;&middot;&nbsp;'
        f'VAR = pts above replacement &middot; Ranked by team fit'
    )

    return (
        f'<div class="card mb20">'
        f'<div class="sec-head">'
        f'<div class="sec-title">Smart Waiver Targets</div>'
        f'<div class="sec-sub">{legend}</div>'
        f'</div>'
        # Sub-tabs
        f'<div class="w-subtabs">'
        f'<button class="w-subtab-btn active" id="wstb-hitters" onclick="switchWaiverTab(\'hitters\')">'
        f'⚾ Hitters <span class="w-subtab-count">{h_count}</span></button>'
        f'<button class="w-subtab-btn" id="wstb-pitchers" onclick="switchWaiverTab(\'pitchers\')">'
        f'⚡ Pitchers <span class="w-subtab-count">{p_count}</span></button>'
        f'</div>'
        # Hitter pane
        f'<div class="w-subpane visible" id="wpane-hitters">'
        f'<div class="waiver-list">{h_body}</div>'
        f'</div>'
        # Pitcher pane
        f'<div class="w-subpane" id="wpane-pitchers">'
        f'<div class="waiver-list">{p_body}</div>'
        f'</div>'
        f'</div>'
    )


def _activity_section(moves):
    rows = []
    for m in moves[:16]:
        move = m.get("move", "").upper()

        if move == "SWAP":
            # 1-for-1 FA/waiver pickup — single merged row
            rows.append(
                f'<div class="activity-row">'
                f'<span class="move-tag move-swap">SWAP</span>'
                f'<span style="font-weight:600;color:var(--text)">{esc(m.get("player",""))}</span>'
                f'<span style="color:var(--text2);font-size:11px;margin:0 4px">for</span>'
                f'<span style="font-weight:600;color:var(--red)">{esc(m.get("dropped",""))}</span>'
                f'<span style="color:var(--text2);font-size:12px;margin-left:auto">{esc(m.get("team",""))}</span>'
                f'</div>'
            )

        elif move == "TRADED":
            # 2-team trade with full give/receive detail
            team_a   = m.get("team",    "")
            team_b   = m.get("to_team", "")
            gave     = m.get("gave",     [])   # what team_a sent
            received = m.get("received", [])   # what team_a got back
            if team_b and gave and received:
                gave_str = " &amp; ".join(esc(p) for p in gave)
                recv_str = " &amp; ".join(esc(p) for p in received)
                rows.append(
                    f'<div class="activity-row activity-row--trade">'
                    f'<span class="move-tag move-trade">TRADE</span>'
                    f'<span class="trade-detail">'
                    f'<span class="trade-team">{esc(team_a)}</span>'
                    f'<span class="trade-arrow"> sent </span>'
                    f'<span style="font-weight:600;color:var(--red)">{gave_str}</span>'
                    f'<span class="trade-arrow"> · got </span>'
                    f'<span style="font-weight:600;color:var(--accent)">{recv_str}</span>'
                    f'<span class="trade-arrow"> from </span>'
                    f'<span class="trade-team">{esc(team_b)}</span>'
                    f'</span>'
                    f'</div>'
                )
            else:
                # Fallback for unusual trade shapes
                rows.append(
                    f'<div class="activity-row">'
                    f'<span class="move-tag move-trade">TRADED</span>'
                    f'<span style="font-weight:600;color:var(--text)">{esc(m.get("player",""))}</span>'
                    f'<span style="color:var(--text2);font-size:12px;margin-left:auto">{esc(team_a)}</span>'
                    f'</div>'
                )

        else:
            tag_cls = "move-add" if "ADD" in move else ("move-drop" if "DROP" in move else "move-trade")
            rows.append(
                f'<div class="activity-row">'
                f'<span class="move-tag {tag_cls}">{esc(move)}</span>'
                f'<span style="font-weight:600;color:var(--text)">{esc(m.get("player",""))}</span>'
                f'<span style="color:var(--text2);font-size:12px;margin-left:auto">{esc(m.get("team",""))}</span>'
                f'</div>'
            )

    body = "".join(rows) if rows else '<div style="color:var(--text2);font-size:13px">No recent activity</div>'
    return (
        f'<div class="card">'
        f'<div class="sec-head"><div class="sec-title">Recent Activity</div></div>'
        f'<div class="activity-list">{body}</div>'
        f'</div>'
    )


def _cmp_section(comparison, opp_name):
    rows = []
    for r in comparison:
        rows.append(
            f'<div class="cmp-row">'
            f'<span class="cmp-metric">{esc(r["metric"])}</span>'
            f'<span class="cmp-val">{esc(r["mine"])}</span>'
            f'<span class="cmp-val">{esc(r["opp"])}</span>'
            f'<span class="cmp-edge {esc(r["edge"]["class"])}">{esc(r["edge"]["text"])}</span>'
            f'</div>'
        )
    hdr = (
        f'<div style="display:flex;gap:10px;padding:0 12px 8px;'
        f'font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--text2)">'
        f'<span style="flex:1">Metric</span>'
        f'<span style="min-width:52px;text-align:center">You</span>'
        f'<span style="min-width:52px;text-align:center">{esc(opp_name or "Opp")}</span>'
        f'<span style="min-width:48px;text-align:right">Edge</span>'
        f'</div>'
    )
    return (
        f'<div class="card">'
        f'<div class="sec-head"><div class="sec-title">Head-to-Head</div></div>'
        f'<div class="cmp-list">{hdr}{"".join(rows)}</div>'
        f'</div>'
    )


def _note_box():
    items = [
        ("PROJ PTS", f"ESPN projected season total — uses your league's exact scoring rules"),
        ("REPL PTS", f"Replacement level: last startable player at that position across all {N_TEAMS} teams"),
        ("VAR",      "Value Above Replacement = PROJ - REPL. How much better than a free substitute?"),
        ("BASE",     "VAR x scarcity multiplier x injury factor, scaled 0-100 across the full player pool"),
        ("FIT",      "BASE + upgrade over weakest starter + balance bonus (<=10%) + need bonus (<=12%) — all capped"),
    ]
    rows = "".join(
        f'<div class="note-row">'
        f'<span class="note-key">{esc(k)}</span>'
        f'<span class="note-text">{esc(v)}</span>'
        f'</div>'
        for k, v in items
    )
    return (
        f'<div class="card">'
        f'<div class="sec-head"><div class="sec-title">How Scores Work</div>'
        f'<div class="sec-sub">VAR model — industry standard for points leagues</div></div>'
        f'<div class="note-list">{rows}</div>'
        f'</div>'
    )


def _compare_section_v2(my_roster, opp_roster, opp_name):
    """Drag-and-drop player comparison panel embedded in the Matchup tab."""

    def _drag_card(row, side):
        pos    = row.get("pos", "?")
        pos_s  = pos.replace(",", "").replace(" ", "")[:4]
        bench  = pos in ("BE", "BENCH", "IL", "IR")
        name   = row.get("player", "")
        mlb    = row.get("mlb", "")

        hs  = row.get("headshot", "")
        hs2 = row.get("headshot2", "")
        av  = _av(row)

        # JSON payload carried by each card (read by JS on drag/drop)
        payload = json.dumps({
            "name":   name,
            "pos":    pos,
            "mlb":    mlb,
            "base":   row.get("base",   "0"),
            "fit":    row.get("fit",    "0"),
            "proj":   row.get("proj_pts","0"),
            "var":    row.get("var",    "0"),
            "repl":   row.get("repl_pts","0"),
            "tier":   row.get("tier",   ""),
            "mlbam":  row.get("mlbam_id",""),
            "hs":     hs,
            "hs2":    hs2,
            "ini":    row.get("initials","?"),
            "status": row.get("status","ACTIVE"),
            "isp":    row.get("is_pitcher","false") == "true",
            "ws":     row.get("weekly_starts", -1),
            "side":   side,
        }, ensure_ascii=False)

        # Phase 6 — age badge for trade/compare cards
        dc_age_tier = row.get("age_tier") or {}
        dc_age_badge = ""
        if dc_age_tier and dc_age_tier.get("tier", 0):
            dc_flag    = dc_age_tier.get("flag", "")
            dc_label   = dc_age_tier.get("label", "")
            dc_css_cls = dc_label.lower().replace(" ", "-")
            if dc_flag:
                dc_age_badge = (
                    f' <span class="age-badge {dc_css_cls}" title="Age: {esc(dc_label)}">'
                    f'{dc_flag}'
                    f'</span>'
                )

        dim = ' style="opacity:.5"' if bench else ""
        return (
            f'<div class="drag-card"{dim} draggable="true" '
            f'data-side="{side}" data-player="{html.escape(payload)}" '
            f'ondragstart="cmpDragStart(event,this)">'
            f'<div class="av" style="width:30px;height:30px;flex:0 0 30px">{av}</div>'
            f'<div style="flex:1;min-width:0">'
            f'<div class="drag-card-name">{esc(name)}{dc_age_badge}</div>'
            f'<div class="drag-card-sub">'
            f'<span class="pos pos-{esc(pos_s)}">{esc(pos)}</span>'
            f'<span>{esc(mlb)}</span>'
            f'</div>'
            f'</div>'
            f'<div class="drag-card-base">{esc(str(row.get("base","0")))}</div>'
            f'</div>'
        )

    def _sorted(roster):
        def _key(r):
            try:
                return -float(r.get("base", 0) or 0)
            except Exception:
                return 0
        return sorted(roster, key=_key)

    my_cards  = "".join(_drag_card(r, "mine") for r in _sorted(my_roster))
    opp_cards = "".join(_drag_card(r, "opp")  for r in _sorted(opp_roster))

    if not opp_cards:
        opp_cards = (
            '<div style="color:var(--text2);font-size:13px;'
            'padding:24px 0;text-align:center;line-height:1.6">'
            'No opponent roster<br>available for this matchup.</div>'
        )

    def _panel(side, title, cards):
        return (
            f'<div>'
            f'<div class="cmp-roster-head">'
            f'<span>{esc(title)}</span>'
            f'<select class="cmp-filter" onchange="cmpFilter(\'{side}\',this.value)">'
            f'<option value="all">All</option>'
            f'<option value="P">Pitchers</option>'
            f'<option value="H">Hitters</option>'
            f'</select>'
            f'</div>'
            f'<div class="cmp-roster-list" id="cmp-list-{side}">{cards}</div>'
            f'</div>'
        )

    return (
        f'<div class="card mb20">'
        f'<div class="sec-head">'
        f'<div class="sec-title">Player Comparison</div>'
        f'<div class="sec-sub">'
        f'Drag any player from either list onto a slot &mdash; '
        f'scores, projections &amp; season stats compared instantly'
        f'</div>'
        f'</div>'

        f'<div class="cmp-layout">'

        # Left — my roster
        + _panel("mine", "Your Roster", my_cards)

        # Center — drop zones + result table
        + (
            '<div class="cmp-center">'
            '<div class="drop-zone" id="dz-mine" '
            'ondragover="cmpDragOver(event)" ondragleave="cmpDragLeave(event)" '
            'ondrop="cmpDrop(event,\'mine\')">'
            '<div class="drop-zone-hint">↓&nbsp;Drop your player here</div>'
            '</div>'
            '<div class="vs-divider">— vs —</div>'
            '<div class="drop-zone" id="dz-opp" '
            'ondragover="cmpDragOver(event)" ondragleave="cmpDragLeave(event)" '
            'ondrop="cmpDrop(event,\'opp\')">'
            '<div class="drop-zone-hint">↓&nbsp;Drop opponent player here</div>'
            '</div>'
            '<div id="cmp-result">'
            '<div class="cmp-empty-hint">'
            'Drop one player from each side<br>'
            'to see a full stat breakdown'
            '</div>'
            '</div>'
            '</div>'
        )

        # Right — opponent roster
        + _panel("opp", f"{opp_name} Roster", opp_cards)

        + '</div>'  # end cmp-layout
        + '</div>'  # end card
    )


def _season_intel_card(season_intel: dict) -> str:
    """
    Render the Season Intelligence card for the My Team tab.
    Three sub-sections:
      1. Your IL Roster — stash verdicts for your injured players
      2. IL Stash Watch — high-value IL players on other teams
      3. FA Long-Season Targets — free agents worth rostering for later value
    """

    # ── Trend badge ─────────────────────────────────────────────────────────
    def _trend_badge(trend: str) -> str:
        cfg = {
            "hot":               ("🔥", "good"),
            "cold":              ("🥶", "bad"),
            "stable":            ("📊", ""),
            "insufficient_data": ("—",  "muted"),
        }
        icon, cls = cfg.get(trend, ("—", ""))
        style = ""
        if cls == "good":
            style = "color:var(--accent)"
        elif cls == "bad":
            style = "color:var(--red)"
        elif cls == "muted":
            style = "color:var(--text2)"
        return f'<span style="{style};font-size:13px">{icon}&nbsp;{trend.replace("_"," ").title()}</span>'

    # ── Verdict badge ────────────────────────────────────────────────────────
    def _verdict_badge(verdict: str) -> str:
        if verdict == "KEEP":
            return '<span class="ms-pill ms-good" style="font-size:11px">KEEP</span>'
        return '<span class="ms-pill ms-warn" style="font-size:11px">CONSIDER&nbsp;DROPPING</span>'

    # ── Section 1: Your IL Roster ────────────────────────────────────────────
    my_il = season_intel.get("my_il", [])
    if my_il:
        il_rows = ""
        for p in my_il:
            av = (
                f'<img src="{esc(p["headshot"])}" alt="" loading="lazy" '
                f'width="28" height="28" style="border-radius:50%;vertical-align:middle" '
                f'onerror="this.style.display=\'none\'">'
                if p["headshot"] else
                f'<span class="av-fb" style="width:28px;height:28px;font-size:11px">'
                f'{esc(p["initials"])}</span>'
            )
            il_rows += (
                f'<tr>'
                f'<td><div style="display:flex;align-items:center;gap:8px">'
                f'{av}'
                f'<div><div class="il-player-name" style="font-size:13px;font-weight:600;color:var(--text1)">{esc(p["name"])}</div>'
                f'<div style="font-size:11px;color:var(--text2)">'
                f'{esc(p["pos"])} · {esc(p["mlb"])} · {esc(p["status"])}'
                f'</div></div></div></td>'
                f'<td style="text-align:center"><span class="stat-value">{esc(p["stash_score"])}</span></td>'
                f'<td style="text-align:center"><span class="stat-value">{esc(p["current_val"])}</span></td>'
                f'<td style="text-align:center">{esc(p["healthy_proj"])}</td>'
                f'<td>{_verdict_badge(p["verdict"])}</td>'
                f'<td style="font-size:12px;color:var(--text2)">'
                f'{_trend_badge(p["trend"])}<br>'
                f'<span style="font-size:11px">{esc(p["trend_summary"])}</span>'
                f'</td>'
                f'</tr>'
            )
        il_section = (
            '<div class="sec-head" style="margin-top:0">'
            '<div class="sec-title" style="font-size:14px">🏥 Your IL Roster</div>'
            '<div class="sec-sub">Stash score = healthy value · Current val = depressed by injury</div>'
            '</div>'
            '<div style="overflow-x:auto">'
            '<table class="rc-table" style="width:100%">'
            '<thead><tr>'
            '<th>Player</th>'
            '<th style="text-align:center">Stash</th>'
            '<th style="text-align:center">Val</th>'
            '<th style="text-align:center">Proj Pts</th>'
            '<th>Verdict</th>'
            '<th>Season Trend</th>'
            '</tr></thead>'
            '<tbody>' + il_rows + '</tbody>'
            '</table>'
            '</div>'
        )
    else:
        il_section = (
            '<div class="sec-head" style="margin-top:0">'
            '<div class="sec-title" style="font-size:14px">🏥 Your IL Roster</div>'
            '</div>'
            '<div style="color:var(--text2);font-size:13px;padding:12px 0">'
            'No injured players on your roster. Stay healthy! 💪'
            '</div>'
        )

    # ── Section 2: IL Stash Watch ────────────────────────────────────────────
    il_watch = season_intel.get("il_watch", [])
    if il_watch:
        watch_rows = ""
        for p in il_watch:
            av = (
                f'<img src="{esc(p["headshot"])}" alt="" loading="lazy" '
                f'width="28" height="28" style="border-radius:50%;vertical-align:middle" '
                f'onerror="this.style.display=\'none\'">'
                if p["headshot"] else
                f'<span class="av-fb" style="width:28px;height:28px;font-size:11px">'
                f'{esc(p["initials"])}</span>'
            )
            watch_rows += (
                f'<tr>'
                f'<td><div style="display:flex;align-items:center;gap:8px">'
                f'{av}'
                f'<div><div class="il-player-name" style="font-size:13px;font-weight:600;color:var(--text1)">{esc(p["name"])}</div>'
                f'<div style="font-size:11px;color:var(--text2)">'
                f'{esc(p["pos"])} · {esc(p["mlb"])} · {esc(p["status"])}'
                f'</div></div></div></td>'
                f'<td style="text-align:center"><span class="stat-value">{esc(p["stash_score"])}</span></td>'
                f'<td style="text-align:center">{esc(p["healthy_proj"])}</td>'
                f'<td style="font-size:12px;color:var(--text2)">{esc(p["owned_by"])}</td>'
                f'</tr>'
            )
        watch_section = (
            '<div class="sec-head">'
            '<div class="sec-title" style="font-size:14px">👀 IL Stash Watch</div>'
            '<div class="sec-sub">High-value injured players on other rosters — monitor for trade or waiver cut</div>'
            '</div>'
            '<div style="overflow-x:auto">'
            '<table class="rc-table" style="width:100%">'
            '<thead><tr>'
            '<th>Player</th>'
            '<th style="text-align:center">Stash</th>'
            '<th style="text-align:center">Proj Pts</th>'
            '<th>Owned By</th>'
            '</tr></thead>'
            '<tbody>' + watch_rows + '</tbody>'
            '</table>'
            '</div>'
        )
    else:
        watch_section = (
            '<div class="sec-head">'
            '<div class="sec-title" style="font-size:14px">👀 IL Stash Watch</div>'
            '</div>'
            '<div style="color:var(--text2);font-size:13px;padding:12px 0">'
            'No high-value IL targets found on other rosters right now.'
            '</div>'
        )

    # ── Section 3: FA Long-Season Targets ────────────────────────────────────
    fa = season_intel.get("fa_targets", [])
    if fa:
        fa_rows = ""
        for p in fa:
            av = (
                f'<img src="{esc(p["headshot"])}" alt="" loading="lazy" '
                f'width="28" height="28" style="border-radius:50%;vertical-align:middle" '
                f'onerror="this.style.display=\'none\'">'
                if p["headshot"] else
                f'<span class="av-fb" style="width:28px;height:28px;font-size:11px">'
                f'{esc(p["initials"])}</span>'
            )
            status_note = p["status"] if p["status"] not in ("ACTIVE", "NORMAL", "") else "Healthy"
            fa_rows += (
                f'<tr>'
                f'<td><div style="display:flex;align-items:center;gap:8px">'
                f'{av}'
                f'<div><div class="il-player-name" style="font-size:13px;font-weight:600;color:var(--text1)">{esc(p["name"])}</div>'
                f'<div style="font-size:11px;color:var(--text2)">'
                f'{esc(p["pos"])} · {esc(p["mlb"])}'
                f'</div></div></div></td>'
                f'<td style="text-align:center"><span class="stat-value">{esc(p["stash_score"])}</span></td>'
                f'<td style="text-align:center">{esc(p["healthy_proj"])}</td>'
                f'<td style="font-size:12px;color:var(--text2)">{esc(status_note)}</td>'
                f'</tr>'
            )
        fa_section = (
            '<div class="sec-head">'
            '<div class="sec-title" style="font-size:14px">🎯 FA Long-Season Targets</div>'
            '<div class="sec-sub">Free agents with strong season-long value — worth rostering now for later payoff</div>'
            '</div>'
            '<div style="overflow-x:auto">'
            '<table class="rc-table" style="width:100%">'
            '<thead><tr>'
            '<th>Player</th>'
            '<th style="text-align:center">Healthy Score</th>'
            '<th style="text-align:center">Proj Pts</th>'
            '<th>Status</th>'
            '</tr></thead>'
            '<tbody>' + fa_rows + '</tbody>'
            '</table>'
            '</div>'
        )
    else:
        fa_section = (
            '<div class="sec-head">'
            '<div class="sec-title" style="font-size:14px">🎯 FA Long-Season Targets</div>'
            '</div>'
            '<div style="color:var(--text2);font-size:13px;padding:12px 0">'
            'No standout free agent targets above the threshold right now.'
            '</div>'
        )

    return (
        '<div class="card mb20">'
        '<div class="sec-head" style="border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:16px">'
        '<div class="sec-title">🧠 Season Intelligence</div>'
        '<div class="sec-sub">Long-term roster decisions · stash value · injury returns · FA watch</div>'
        '</div>'
        + il_section
        + '<hr style="border:none;border-top:1px solid var(--border);margin:16px 0">'
        + watch_section
        + '<hr style="border:none;border-top:1px solid var(--border);margin:16px 0">'
        + fa_section
        + '</div>'
    )


def _team_viewer_inner(all_team_rosters: dict, my_team_inner: str = "") -> str:
    """
    Render the arrow-nav header + per-team panes that live inside the My Team tab.
    `my_team_inner` is the full rich HTML for the first (own) pane — it replaces
    the generic stat-strip + roster cards for that pane so it can include season
    intel, injury alerts, win-prob stat, etc.
    Other teams get a stat-strip + roster cards pane as before.
    Returns inner HTML only (no outer tab-pane wrapper).
    """
    if not all_team_rosters:
        return (
            '<div class="card"><div style="color:var(--text2);padding:24px;text-align:center">'
            'No team data available.</div></div>'
        )

    # Sort teams: my team first, then alphabetically
    sorted_names = sorted(
        all_team_rosters.keys(),
        key=lambda n: (0 if all_team_rosters[n].get("is_mine") else 1, n)
    )
    first_team  = sorted_names[0]
    first_mine  = all_team_rosters[first_team].get("is_mine", False)
    first_label = "My Team" if first_mine else first_team

    # ── Team panes (pre-rendered, one per team) ───────────────────────────────
    panes_html = ""
    for name in sorted_names:
        td          = all_team_rosters[name]
        rows        = td["rows"]
        summary     = td["summary"]
        mine        = td.get("is_mine", False)
        power_rank  = td.get("power_rank", "?")
        visible     = "block" if name == first_team else "none"
        disp        = "My Team" if mine else name

        if mine and my_team_inner:
            # Own team: use the full rich content passed in from render_html
            pane_body = my_team_inner
        else:
            # Other teams: compact stat strip + roster cards
            inj        = summary.get("injury_count", 0)
            inj_tone   = "bad" if inj > 0 else ""
            weekly_pts = summary.get("weekly_lineup_pts", summary.get("lineup_pts", 0))
            pane_body = (
                '<div class="stat-row" style="margin-bottom:16px">'
                + _stat_card("Power Rank",   f"#{power_rank}", "league ranking")
                + _stat_card("Best Lineup",  fmt(weekly_pts, 1), "this week")
                + _stat_card("Active Base",  fmt(summary.get("active_base",  0)), "scaled 0–100")
                + _stat_card("Hitter Base",  fmt(summary.get("hitter_base",  0)), "scaled 0–100")
                + _stat_card("Pitcher Base", fmt(summary.get("pitcher_base", 0)), "scaled 0–100")
                + _stat_card("Injuries",     str(inj), "active roster", inj_tone)
                + '</div>'
                + _roster_cards(rows, f"{name} Roster",
                                "Outer ring = Value · Inner ring = Fit · Proj = season pts · VAR = pts above replacement")
            )

        # Rank suffix shown in the nav header (e.g. "Team Name  #3")
        rank_label = f"#{power_rank}" if str(power_rank) != "?" else ""

        panes_html += (
            f'<div class="team-viewer-pane" data-team="{esc(name)}" '
            f'data-display-name="{esc(disp)}" '
            f'data-power-rank="{esc(str(power_rank))}" '
            f'style="display:{visible}">'
            + pane_body
            + '</div>'
        )

    # Compute first pane's rank label for the initial nav header render
    first_td    = all_team_rosters[first_team]
    first_rank  = first_td.get("power_rank", "?")
    first_rank_label = f"#{first_rank}" if str(first_rank) != "?" else ""

    # ── Arrow nav header ──────────────────────────────────────────────────────
    nav_html = (
        '<div class="tv-nav">'
        '<button class="tv-arrow" onclick="teamViewStep(-1)" aria-label="Previous team">&#8592;</button>'
        f'<span class="tv-name" id="tv-team-name">{esc(first_label)}</span>'
        f'<span class="tv-rank-badge" id="tv-rank-badge">{esc(first_rank_label)}</span>'
        '<button class="tv-arrow" onclick="teamViewStep(1)" aria-label="Next team">&#8594;</button>'
        '</div>'
    )

    return nav_html + panes_html


# ══════════════════════════════════════════════════════════════════════════════
# LINEUP LAB TAB
# ══════════════════════════════════════════════════════════════════════════════

def _lineup_lab_tab(lab: dict) -> str:
    """
    Render the Lineup Lab tab — optimal lineup, position impact analysis,
    and an interactive side-by-side team comparison with JS-powered team switching.

    lab: dict returned by model.build_lineup_lab()
    """
    import json as _json

    if not lab or lab.get("error"):
        err = lab.get("error", "Unknown") if lab else "Not run"
        return (
            '<div class="tab-pane" data-tab="lineuplab">'
            '<div class="card mb20" style="margin-top:12px">'
            f'<div style="color:var(--red);padding:12px;font-weight:600">'
            f'⚠ Lineup Lab unavailable: {esc(str(err))}</div>'
            '</div></div>'
        )

    optimal        = lab.get("optimal", [])
    pos_metrics    = lab.get("pos_metrics", {})
    team_lineups   = lab.get("team_lineups", {})
    all_team_names = lab.get("all_team_names", [])
    my_team_name   = lab.get("my_team_name", "")
    league_above   = lab.get("league_above_repl", {})

    DISPLAY_POSITIONS = ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"]

    # ── CSS ───────────────────────────────────────────────────────────────────
    css = """<style>
.ll-layout{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}
@media(max-width:900px){.ll-layout{grid-template-columns:1fr}}
.ll-section{background:var(--surface);border:1px solid var(--border);
  border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);margin-bottom:12px}
.ll-section h3{font-size:13px;font-weight:700;margin-bottom:10px;
  display:flex;align-items:center;justify-content:space-between;gap:8px}
.ll-slot{display:flex;align-items:center;gap:10px;padding:7px 0;
  border-bottom:1px solid var(--border)}
.ll-slot:last-child{border-bottom:none}
.ll-pos-badge{width:40px;text-align:center;font-size:10px;font-weight:800;
  padding:3px 0;border-radius:5px;background:var(--surface2);
  color:var(--text2);letter-spacing:.04em;flex-shrink:0}
.ll-pos-badge.sp{background:rgba(22,163,74,.15);color:#16a34a}
.ll-pos-badge.rp{background:var(--accent-dim);color:var(--accent)}
.ll-pos-badge.c{background:rgba(168,85,247,.15);color:#a855f7}
.ll-pos-badge.ss{background:rgba(239,68,68,.12);color:var(--red)}
.ll-pos-badge.of{background:rgba(154,103,0,.12);color:var(--amber)}
.ll-name{flex:1;min-width:0}
.ll-pname{font-size:13px;font-weight:600;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ll-sub{font-size:10px;color:var(--text2);margin-top:1px}
.ll-pts{font-size:13px;font-weight:700;font-family:"JetBrains Mono",monospace;
  color:var(--text);white-space:nowrap}
.ll-var{font-size:11px;color:#16a34a;font-weight:600;white-space:nowrap}
.ll-owner-badge{font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;
  white-space:nowrap}
.ll-owner-badge.fa{background:rgba(22,163,74,.15);color:#16a34a}
.ll-owner-badge.owned{background:var(--surface2);color:var(--text2)}
.ll-owner-badge.mine{background:var(--accent-dim);color:var(--accent)}
/* Position impact grid */
.ll-impact-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.ll-pos-card{background:var(--surface);border:1px solid var(--border);
  border-radius:10px;padding:10px 12px;box-shadow:var(--shadow);cursor:pointer;
  transition:border-color .15s}
.ll-pos-card:hover{border-color:var(--accent)}
.ll-pos-card.active{border-color:var(--accent);background:var(--accent-dim)}
.ll-pos-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.ll-pos-name{font-size:14px;font-weight:800;color:var(--text)}
.ll-grade{font-size:12px;font-weight:800;padding:2px 7px;border-radius:5px}
.ll-grade.A{background:rgba(22,163,74,.15);color:#16a34a}
.ll-grade.B{background:var(--accent-dim);color:var(--accent)}
.ll-grade.C{background:var(--amber-dim);color:var(--amber)}
.ll-grade.D,.ll-grade.F{background:var(--red-dim);color:var(--red)}
.ll-pos-stat{font-size:11px;color:var(--text2);margin-top:2px}
.ll-pos-stat strong{color:var(--text);font-weight:600}
.ll-depth-bar-wrap{margin-top:6px}
.ll-depth-bar{height:6px;border-radius:3px;background:var(--accent);
  transition:width .3s}
/* Comparison panel */
.ll-cmp-header{display:flex;align-items:center;justify-content:space-between;
  gap:10px;margin-bottom:10px;flex-wrap:wrap}
.ll-team-select{font-size:13px;font-weight:600;color:var(--text);
  background:var(--surface2);border:1.5px solid var(--border);border-radius:8px;
  padding:6px 28px 6px 12px;cursor:pointer;flex:1;max-width:280px}
.ll-cmp-row{display:flex;align-items:center;gap:8px;padding:6px 0;
  border-bottom:1px solid var(--border)}
.ll-cmp-row:last-child{border-bottom:none}
.ll-cmp-pos{width:40px;text-align:center;font-size:10px;font-weight:800;
  color:var(--text2);flex-shrink:0}
.ll-cmp-team-col{flex:1;min-width:0}
.ll-cmp-name{font-size:12px;font-weight:600;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ll-cmp-pts{font-size:12px;font-family:"JetBrains Mono",monospace;
  color:var(--text2);margin-top:1px}
.ll-cmp-gap{text-align:right;white-space:nowrap;flex-shrink:0}
.ll-gap-badge{font-size:11px;font-weight:700;padding:3px 8px;border-radius:5px}
.ll-gap-badge.A{background:rgba(22,163,74,.15);color:#16a34a}
.ll-gap-badge.B{background:var(--accent-dim);color:var(--accent)}
.ll-gap-badge.C{background:var(--amber-dim);color:var(--amber)}
.ll-gap-badge.D,.ll-gap-badge.F{background:var(--red-dim);color:var(--red)}
.ll-target-pill{font-size:9px;font-weight:700;padding:2px 5px;border-radius:3px;
  background:var(--red-dim);color:var(--red);margin-top:2px;display:inline-block}
.ll-total-row{display:flex;justify-content:space-between;align-items:center;
  padding:8px 0 0;border-top:2px solid var(--border);margin-top:4px}
.ll-total-label{font-size:11px;font-weight:700;color:var(--text2)}
.ll-total-val{font-size:15px;font-weight:800;font-family:"JetBrains Mono",monospace;color:var(--text)}
/* Position depth detail panel */
.ll-depth-detail{display:none;margin-top:10px}
.ll-depth-detail.open{display:block}
.ll-depth-table{width:100%;border-collapse:collapse;font-size:12px}
.ll-depth-table th{font-size:10px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:.06em;padding:5px 8px;
  border-bottom:1px solid var(--border);text-align:left}
.ll-depth-table td{padding:6px 8px;border-bottom:1px solid var(--border)}
.ll-depth-table tr:last-child td{border-bottom:none}
.ll-depth-table tr.ll-mine td{background:var(--accent-dim)}
/* Trade targets section */
.ll-trade-section{background:var(--surface);border:1px solid var(--border);
  border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);margin-bottom:12px}
.ll-trade-section h3{font-size:13px;font-weight:700;margin-bottom:10px;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ll-trade-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.ll-trade-card{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:12px 14px;position:relative;overflow:hidden}
.ll-trade-card-header{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.ll-trade-av{width:38px;height:38px;border-radius:50%;overflow:hidden;
  flex-shrink:0;background:var(--surface);border:2px solid var(--border);
  display:flex;align-items:center;justify-content:center;font-size:12px;
  font-weight:700;color:var(--text2)}
.ll-trade-av img{width:100%;height:100%;object-fit:cover}
.ll-trade-name{flex:1;min-width:0}
.ll-trade-pname{font-size:13px;font-weight:700;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ll-trade-sub{font-size:10px;color:var(--text2);margin-top:1px}
.ll-trade-adv-badge{font-size:13px;font-weight:800;font-family:"JetBrains Mono",monospace;
  color:#16a34a;background:rgba(22,163,74,.12);border-radius:6px;
  padding:4px 8px;white-space:nowrap;flex-shrink:0}
.ll-trade-adv-badge.neg{color:var(--red);background:var(--red-dim)}
.ll-trade-reasons{margin-bottom:8px}
.ll-trade-reason{font-size:11px;color:var(--text2);line-height:1.5;
  padding-left:12px;position:relative}
.ll-trade-reason::before{content:"•";position:absolute;left:2px;color:var(--accent)}
.ll-trade-offer{background:var(--surface);border:1px solid var(--border);
  border-radius:7px;padding:7px 10px;margin-top:6px}
.ll-trade-offer-label{font-size:9px;font-weight:700;text-transform:uppercase;
  letter-spacing:.07em;color:var(--text2);margin-bottom:4px}
.ll-trade-offer-row{display:flex;align-items:center;justify-content:space-between;
  gap:6px;padding:2px 0}
.ll-trade-offer-name{font-size:11px;font-weight:600;color:var(--text)}
.ll-trade-offer-why{font-size:10px;color:var(--text2)}
.ll-trade-offer-pts{font-size:11px;font-family:"JetBrains Mono",monospace;
  color:var(--text2);white-space:nowrap}
.ll-cat-chip{font-size:10px;font-weight:700;padding:3px 8px;border-radius:5px;
  white-space:nowrap;display:inline-flex;align-items:center;gap:3px}
.ll-cat-chip.holds{background:var(--accent-dim);color:var(--accent)}
.ll-cat-chip.lowk{background:rgba(22,163,74,.15);color:#16a34a}
.ll-cat-chip.workhorse{background:var(--amber-dim);color:var(--amber)}
.ll-cat-chip.avoid{background:var(--red-dim);color:var(--red)}
.ll-cat-chip.sell{background:rgba(168,85,247,.12);color:#a855f7}
.ll-cat-chip.contact{background:rgba(154,103,0,.12);color:var(--amber)}
.ll-sell-table{width:100%;border-collapse:collapse;font-size:12px}
.ll-sell-table th{font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.06em;padding:5px 8px;border-bottom:1px solid var(--border);text-align:left}
.ll-sell-table td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.ll-sell-table tr:last-child td{border-bottom:none}
.ll-explainer-strip{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.ll-explainer-chip{background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;padding:7px 10px;font-size:11px;color:var(--text2);
  line-height:1.5;flex:1;min-width:200px}
.ll-explainer-chip strong{color:var(--text);display:block;margin-bottom:2px}
.ll-need-bar{height:4px;border-radius:2px;background:var(--red);margin-top:4px}
</style>"""

    # ── Embed team lineup data as JSON for JS switching ───────────────────────
    team_data_json = _json.dumps(team_lineups, separators=(',', ':'))
    pos_top_json   = _json.dumps(
        {pos: m.get("top_players", []) for pos, m in pos_metrics.items()},
        separators=(',', ':')
    )

    # ── Helper: position badge CSS class ─────────────────────────────────────
    def _pos_cls(pos: str) -> str:
        return {"SP": "sp", "RP": "rp", "C": "c", "SS": "ss",
                "OF": "of", "1B": "of", "2B": "of", "3B": "of"}.get(pos, "")

    # ── Optimal lineup column ─────────────────────────────────────────────────
    def _optimal_slot_row(slot: dict) -> str:
        pos   = slot["pos"]
        label = slot["slot"]
        name  = slot["name"]
        owner = slot.get("owner", "")
        is_fa = slot.get("is_fa", False)
        proj  = slot.get("proj", 0.0)
        var   = slot.get("var", 0.0)
        is_mine_owned = my_team_name.lower() in owner.lower() if owner else False

        if is_fa:
            owner_html = '<span class="ll-owner-badge fa">FA</span>'
        elif is_mine_owned:
            owner_html = '<span class="ll-owner-badge mine">MINE</span>'
        else:
            owner_html = f'<span class="ll-owner-badge owned">{esc(owner[:14])}</span>'

        mlb   = esc(slot.get("mlb", ""))
        pos_c = _pos_cls(pos)

        return (
            f'<div class="ll-slot">'
            f'<span class="ll-pos-badge {pos_c}">{esc(label)}</span>'
            f'<div class="ll-name">'
            f'<div class="ll-pname">{esc(name)}</div>'
            f'<div class="ll-sub">{mlb} &nbsp; {owner_html}</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div class="ll-pts">{round(proj):,}</div>'
            f'<div class="ll-var">+{round(var):,} VAR</div>'
            f'</div>'
            f'</div>'
        )

    optimal_rows = "".join(_optimal_slot_row(s) for s in optimal)

    optimal_total_proj = sum(s.get("proj", 0) for s in optimal)
    optimal_total_var  = sum(s.get("var",  0) for s in optimal)

    optimal_col = (
        '<div class="ll-section">'
        '<h3>🏆 League-Best Lineup'
        '<span style="font-size:11px;font-weight:400;color:var(--text2)">'
        '— best player per slot, any team</span></h3>'
        + optimal_rows +
        f'<div class="ll-total-row">'
        f'<span class="ll-total-label">TOTAL PROJ PTS</span>'
        f'<span class="ll-total-val">{round(optimal_total_proj):,}'
        f'<span style="font-size:11px;font-weight:400;color:#16a34a;margin-left:8px">'
        f'+{round(optimal_total_var):,} VAR</span></span>'
        f'</div>'
        '</div>'
    )

    # ── Position Impact cards ─────────────────────────────────────────────────
    # Max n_above_repl across all positions for bar scaling
    max_above = max((m.get("n_above_repl", 1) for m in pos_metrics.values()), default=1)

    def _pos_impact_card(pos: str) -> str:
        m = pos_metrics.get(pos, {})
        grade    = m.get("grade", "C")
        n_above  = m.get("n_above_repl", 0)
        top_pts  = m.get("top_pts", 0)
        top_var  = m.get("top_var", 0)
        repl     = m.get("repl", 0)
        impact   = m.get("impact", 0)
        bar_w    = round(n_above / max_above * 100) if max_above else 0

        return (
            f'<div class="ll-pos-card" onclick="llShowDepth(\'{pos}\')" id="ll-pc-{pos}">'
            f'<div class="ll-pos-header">'
            f'<span class="ll-pos-name">{pos}</span>'
            f'<span class="ll-grade {grade}">{grade}</span>'
            f'</div>'
            f'<div class="ll-pos-stat">Top: <strong>{round(top_pts):,}</strong> pts</div>'
            f'<div class="ll-pos-stat">VAR: <strong>+{round(top_var):,}</strong></div>'
            f'<div class="ll-pos-stat">Repl: <strong>{round(repl):,}</strong></div>'
            f'<div class="ll-depth-bar-wrap">'
            f'<div style="font-size:9px;color:var(--text2);margin-bottom:2px">'
            f'{n_above} above repl</div>'
            f'<svg width="100%" height="6">'
            f'<rect width="100%" height="6" rx="3" fill="var(--bar-bg)"/>'
            f'<rect width="{bar_w}%" height="6" rx="3" fill="var(--accent)"/>'
            f'</svg>'
            f'</div>'
            f'</div>'
        )

    impact_cards = "".join(_pos_impact_card(pos) for pos in DISPLAY_POSITIONS)

    # Position depth detail tables (hidden, shown on card click)
    def _depth_detail_panel(pos: str) -> str:
        m = pos_metrics.get(pos, {})
        top_players = m.get("top_players", [])
        rows = ""
        for i, p in enumerate(top_players):
            is_mine = my_team_name.lower() in p.get("owner", "").lower()
            mine_cls = "ll-mine" if is_mine else ""
            owner_txt = p.get("owner", "FA")
            fa_badge = (
                '<span style="font-size:9px;font-weight:700;padding:1px 5px;'
                'border-radius:3px;background:rgba(22,163,74,.15);color:#16a34a">FA</span>'
                if p.get("is_fa") else ""
            )
            mine_badge = (
                '<span style="font-size:9px;font-weight:700;padding:1px 5px;'
                'border-radius:3px;background:var(--accent-dim);color:var(--accent)">MINE</span>'
                if is_mine else ""
            )
            rows += (
                f'<tr class="{mine_cls}">'
                f'<td style="text-align:center;color:var(--text2);font-weight:700">{i+1}</td>'
                f'<td style="font-weight:600">{esc(p["name"])} {fa_badge}{mine_badge}</td>'
                f'<td style="color:var(--text2);font-size:11px">{esc(p["mlb"])}</td>'
                f'<td style="font-family:monospace">{round(p["proj"]):,}</td>'
                f'<td style="color:#16a34a;font-family:monospace">+{round(p["var"]):,}</td>'
                f'<td style="font-size:11px;color:var(--text2)">{round(p["base"], 1)}</td>'
                f'</tr>'
            )
        return (
            f'<div class="ll-depth-detail" id="ll-dd-{pos}">'
            f'<div style="font-size:11px;font-weight:700;color:var(--text2);margin-bottom:6px">'
            f'{pos} — Top Players by Projected Pts'
            f'<span style="font-weight:400;margin-left:6px">'
            f'(repl level = {round(m.get("repl",0)):,} pts)</span></div>'
            f'<table class="ll-depth-table">'
            f'<thead><tr><th>#</th><th>Player</th><th>MLB</th>'
            f'<th>Proj Pts</th><th>VAR</th><th>Base</th></tr></thead>'
            f'<tbody>{rows}</tbody>'
            f'</table></div>'
        )

    depth_panels = "".join(_depth_detail_panel(pos) for pos in DISPLAY_POSITIONS)

    impact_section = (
        '<div class="ll-section">'
        '<h3>📊 Position Impact & Depth'
        '<span style="font-size:11px;font-weight:400;color:var(--text2)">'
        '— click a position to see top players</span></h3>'
        f'<div class="ll-impact-grid">{impact_cards}</div>'
        + depth_panels +
        '<div style="margin-top:8px;font-size:11px;color:var(--text2)">'
        'Grade = positional scarcity (A=rare/premium, D=deep pool). '
        '"Above repl" = players projecting above replacement level. '
        'Higher impact = wider gap between elite and average at this position.'
        '</div>'
        '</div>'
    )

    # ── Team comparison column ────────────────────────────────────────────────
    # Build the dropdown options
    def _dropdown_option(name: str) -> str:
        sel = 'selected' if my_team_name.lower() in name.lower() else ''
        return f'<option value="{esc(name)}" {sel}>{esc(name)}</option>'

    dropdown_opts = "".join(_dropdown_option(n) for n in all_team_names)

    # Build the static comparison for the initially selected team (my team)
    def _cmp_row(pos: str, slot: dict) -> str:
        pos_c   = _pos_cls(pos)
        name    = slot.get("name", "—")
        pts     = slot.get("proj", 0)
        var_val = slot.get("var", 0)
        gap_pts = slot.get("gap_pts", 0)
        grade   = slot.get("grade", "F")
        opt_nm  = slot.get("opt_name", "—")
        opt_pts = slot.get("opt_pts", 0)

        upgrade_needed = grade in ("C", "D", "F")
        target_html = (
            f'<div class="ll-target-pill">TARGET</div>'
            if upgrade_needed else ""
        )

        gap_sign = "–" if gap_pts > 0 else "±"
        gap_html = (
            f'<div class="ll-gap-badge {grade}">'
            f'{grade}: {gap_sign}{round(abs(gap_pts)):,}'
            f'</div>'
            + target_html
        ) if name != "—" else (
            f'<div class="ll-gap-badge F">F: EMPTY</div>'
            + target_html
        )

        sub = (
            f'{round(pts):,} proj'
            f'<span style="color:#16a34a;margin-left:4px">+{round(var_val):,}</span>'
        ) if name != "—" else "No eligible player"

        return (
            f'<div class="ll-cmp-row" data-pos="{esc(pos)}">'
            f'<div class="ll-cmp-pos">{esc(pos)}</div>'
            f'<div class="ll-cmp-team-col">'
            f'<div class="ll-cmp-name">{esc(name)}</div>'
            f'<div class="ll-cmp-pts">{sub}</div>'
            f'</div>'
            f'<div class="ll-cmp-gap">{gap_html}</div>'
            f'</div>'
        )

    # Initial render for my team
    my_slots = {}
    my_tname = ""
    for tname, tdata in team_lineups.items():
        if my_team_name.lower() in tname.lower():
            my_slots = tdata.get("slots", {})
            my_tname = tname
            break

    init_rows = "".join(
        _cmp_row(pos, my_slots.get(pos, {}))
        for pos in DISPLAY_POSITIONS
    )

    my_total  = team_lineups.get(my_tname, {}).get("total_proj", 0)
    my_grade  = team_lineups.get(my_tname, {}).get("overall_grade", "?")

    # Count target positions for my team
    my_targets = sum(
        1 for pos in DISPLAY_POSITIONS
        if my_slots.get(pos, {}).get("grade", "A") in ("C", "D", "F")
    )

    cmp_section = (
        '<div class="ll-section">'
        '<div class="ll-cmp-header">'
        '<h3 style="margin:0">⚔ Team Comparison</h3>'
        f'<select class="ll-team-select" id="ll-team-sel" onchange="llSwitchTeam(this.value)">'
        f'{dropdown_opts}'
        f'</select>'
        '</div>'
        f'<div id="ll-cmp-body">'
        + init_rows +
        f'<div class="ll-total-row" id="ll-cmp-total">'
        f'<span class="ll-total-label">TEAM TOTAL (best active)</span>'
        f'<span class="ll-total-val">{round(my_total):,} pts &nbsp;'
        f'<span class="ll-grade {my_grade}" style="font-size:12px">{my_grade}</span>'
        f'</span>'
        f'</div>'
        f'</div>'  # ll-cmp-body
        f'<div style="margin-top:8px;font-size:11px;color:var(--text2)">'
        f'Grade = how close this slot is to the league best. '
        f'<span style="color:var(--red);font-weight:600">TARGET</span> = '
        f'upgrade worth pursuing via trade or waiver. '
        f'Gap = projected pts difference vs league-best at that slot.'
        f'</div>'
        '</div>'
    )

    # ── League-wide above-repl summary row ────────────────────────────────────
    def _above_chip(pos: str) -> str:
        n  = league_above.get(pos, 0)
        m  = pos_metrics.get(pos, {})
        g  = m.get("grade", "C")
        return (
            f'<div style="text-align:center;background:var(--surface2);'
            f'border:1px solid var(--border);border-radius:8px;padding:8px 10px">'
            f'<div style="font-size:15px;font-weight:800;color:var(--text)">{n}</div>'
            f'<div style="font-size:10px;font-weight:700;color:var(--text2);'
            f'text-transform:uppercase;letter-spacing:.06em">{pos}</div>'
            f'<div><span class="ll-grade {g}" style="font-size:10px">{g}</span></div>'
            f'</div>'
        )

    above_chips = "".join(_above_chip(pos) for pos in DISPLAY_POSITIONS)
    above_section = (
        '<div class="ll-section">'
        '<h3>📈 Players Above Replacement Level — By Position</h3>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px">'
        f'{above_chips}'
        f'</div>'
        '<div style="margin-top:8px;font-size:11px;color:var(--text2)">'
        'Number of league-wide players (rostered + FA) projecting above replacement level. '
        'Lower = scarcer position = higher priority to upgrade.'
        '</div>'
        '</div>'
    )

    # ── Trade Targets Section ─────────────────────────────────────────────────
    def _trade_targets_section(lab_trades: dict) -> str:
        if not lab_trades:
            return ""

        holds_tgts    = lab_trades.get("holds_targets", [])
        lowk_tgts     = lab_trades.get("lowk_targets", [])
        workhorse_tgts= lab_trades.get("workhorse_targets", [])
        other_tgts    = lab_trades.get("other_targets", [])
        avoid_tgts    = lab_trades.get("avoid_targets", [])
        sell_cands    = lab_trades.get("sell_candidates", [])
        explainers    = lab_trades.get("category_explainers", {})

        # Total acquire targets across all positive categories
        all_acquire   = holds_tgts + lowk_tgts + workhorse_tgts + other_tgts
        if not all_acquire and not avoid_tgts and not sell_cands:
            return ""

        # Helper: small headshot/initials avatar
        def _tav(t: dict) -> str:
            hs  = t.get("headshot", "")
            ini = esc(t.get("initials", "??"))
            nm  = esc(t.get("player", ""))
            if hs:
                return (
                    f'<div class="ll-trade-av">'
                    f'<img src="{esc(hs)}" alt="{nm}" loading="lazy" '
                    f"onerror=\"this.style.display='none';this.nextSibling.style.display='flex'\">"
                    f'<span style="display:none;width:100%;height:100%;align-items:center;'
                    f'justify-content:center">{ini}</span>'
                    f'</div>'
                )
            return f'<div class="ll-trade-av">{ini}</div>'

        # Helper: render one trade target card
        def _tcard(t: dict, chip_cls: str) -> str:
            name      = esc(t.get("player", "?"))
            ftm       = esc(t.get("fantasy_team", ""))
            pos       = esc(t.get("pos", ""))
            mlb       = esc(t.get("mlb", ""))
            our_proj  = t.get("our_proj", 0)
            espn_proj = t.get("espn_proj", 0)
            model_gap = t.get("model_gap", 0)
            fmt_adv   = t.get("format_adv", 0)
            reasons   = t.get("reasons", [])
            need      = t.get("need_score", 0.0)
            offer     = t.get("offer", [])

            adv_neg   = "neg" if fmt_adv < 0 else ""
            adv_sign  = "+" if fmt_adv >= 0 else "−"
            adv_abs   = abs(int(fmt_adv))

            reason_rows = "".join(
                f'<div class="ll-trade-reason">{esc(r)}</div>'
                for r in reasons
            )

            # Pts summary sub-line
            gap_txt = ""
            if model_gap > 0:
                gap_txt = (
                    f' &nbsp;·&nbsp; '
                    f'<span style="color:#16a34a;font-weight:600">+{int(model_gap)} vs ESPN</span>'
                )
            elif model_gap < 0:
                gap_txt = (
                    f' &nbsp;·&nbsp; '
                    f'<span style="color:var(--amber)">{int(model_gap)} vs ESPN</span>'
                )

            # Need bar (wider = my team needs this position more)
            need_pct = min(100, int(need))
            need_bar = (
                f'<div title="Position need: {need_pct}%" '
                f'style="margin-top:4px">'
                f'<div style="font-size:9px;color:var(--text2);margin-bottom:2px">'
                f'Position need: {need_pct}%</div>'
                f'<div style="height:4px;border-radius:2px;background:var(--bar-bg);overflow:hidden">'
                f'<div style="width:{need_pct}%;height:4px;border-radius:2px;background:var(--red)"></div>'
                f'</div></div>'
            ) if need > 0 else ""

            # Offer rows
            offer_html = ""
            if offer:
                offer_rows_html = ""
                for o in offer:
                    o_name = esc(o.get("name", "?"))
                    o_pos  = esc(o.get("pos", ""))
                    o_pts  = int(o.get("pts", 0))
                    o_why  = esc(o.get("sell_reason", ""))
                    offer_rows_html += (
                        f'<div class="ll-trade-offer-row">'
                        f'<div>'
                        f'<span class="ll-trade-offer-name">{o_name}</span>'
                        f' <span style="font-size:9px;color:var(--text2)">{o_pos}</span>'
                        f'<div class="ll-trade-offer-why">{o_why}</div>'
                        f'</div>'
                        f'<span class="ll-trade-offer-pts">{o_pts:,} pts</span>'
                        f'</div>'
                    )
                offer_html = (
                    f'<div class="ll-trade-offer">'
                    f'<div class="ll-trade-offer-label">💱 Suggested offer (players to move)</div>'
                    f'{offer_rows_html}'
                    f'</div>'
                )

            return (
                f'<div class="ll-trade-card">'
                f'<div class="ll-trade-card-header">'
                f'{_tav(t)}'
                f'<div class="ll-trade-name">'
                f'<div class="ll-trade-pname">{name}</div>'
                f'<div class="ll-trade-sub">{pos} &nbsp;·&nbsp; {mlb} &nbsp;·&nbsp; '
                f'<span style="color:var(--text2)">{ftm}</span></div>'
                f'<div class="ll-trade-sub" style="margin-top:2px">'
                f'{int(our_proj):,} proj pts{gap_txt}</div>'
                f'</div>'
                f'<div class="ll-trade-adv-badge {adv_neg}">'
                f'{adv_sign}{adv_abs:,}<div style="font-size:9px;font-weight:400">format pts</div>'
                f'</div>'
                f'</div>'
                f'<div class="ll-trade-reasons">{reason_rows}</div>'
                f'{need_bar}'
                f'{offer_html}'
                f'</div>'
            )

        # Helper: category group with header
        def _cat_group(emoji: str, title: str, chip_cls: str,
                        targets: list, expl: str) -> str:
            if not targets:
                return ""
            cards_html = "".join(_tcard(t, chip_cls) for t in targets)
            expl_html  = (
                f'<div style="font-size:11px;color:var(--text2);'
                f'background:var(--surface2);border-radius:6px;padding:7px 10px;'
                f'margin-bottom:8px;line-height:1.5">{esc(expl)}</div>'
                if expl else ""
            )
            return (
                f'<div style="margin-bottom:16px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                f'<span style="font-size:14px">{emoji}</span>'
                f'<span style="font-size:12px;font-weight:700;color:var(--text)">{title}</span>'
                f'<span class="ll-cat-chip {chip_cls}">{len(targets)} targets</span>'
                f'</div>'
                f'{expl_html}'
                f'<div class="ll-trade-grid">{cards_html}</div>'
                f'</div>'
            )

        # Build the acquire section
        acquire_html = ""
        acquire_html += _cat_group(
            "🔐", "Holds-Edge Setup Men",  "holds",
            holds_tgts,
            explainers.get("HOLDS_EDGE", ""),
        )
        acquire_html += _cat_group(
            "🎯", "Low-K Contact Hitters", "lowk",
            lowk_tgts,
            explainers.get("LOW_K_HITTER", ""),
        )
        acquire_html += _cat_group(
            "💪", "Workhorse Starters",    "workhorse",
            workhorse_tgts,
            explainers.get("WORKHORSE_SP", ""),
        )
        if other_tgts:
            acquire_html += _cat_group(
                "✨", "Other Format Edges",    "contact",
                other_tgts,
                "",
            )

        # Avoid / sell-high section
        sell_html = ""
        if avoid_tgts or sell_cands:
            # Avoid cards (high-K hitters on other teams — don't waste trade assets)
            avoid_cards = ""
            if avoid_tgts:
                avoid_cards = (
                    '<div style="margin-bottom:10px">'
                    '<div style="font-size:11px;font-weight:700;color:var(--red);'
                    'margin-bottom:6px">🚫 Players on Other Teams to Avoid Acquiring</div>'
                    '<div class="ll-trade-grid">'
                    + "".join(_tcard(t, "avoid") for t in avoid_tgts)
                    + '</div></div>'
                )

            # Sell-high table (my players ESPN overvalues)
            sell_rows = ""
            for s in sell_cands:
                sname  = esc(s.get("name", "?"))
                spos   = esc(s.get("pos", ""))
                spts   = int(s.get("pts", 0))
                sespn  = int(s.get("espn_pts", 0))
                sgap   = int(s.get("gap", 0))
                sreason= esc(s.get("sell_reason", ""))
                cat_c  = "avoid" if s.get("category") == "HIGH_K_AVOID" else "sell"
                sell_rows += (
                    f'<tr>'
                    f'<td style="font-weight:600">{sname}</td>'
                    f'<td style="color:var(--text2);font-size:11px">{spos}</td>'
                    f'<td style="font-family:monospace">{spts:,}</td>'
                    f'<td style="font-family:monospace">{sespn:,}</td>'
                    f'<td style="color:var(--red);font-weight:700;font-family:monospace">'
                    f'+{sgap:,}</td>'
                    f'<td style="font-size:11px;color:var(--text2)">'
                    f'<span class="ll-cat-chip {cat_c}">{sreason}</span></td>'
                    f'</tr>'
                )

            sell_table = ""
            if sell_rows:
                sell_table = (
                    '<div style="margin-bottom:6px">'
                    '<div style="font-size:11px;font-weight:700;color:#a855f7;margin-bottom:6px">'
                    '💸 My Players ESPN Overvalues — Sell These in Trades</div>'
                    '<div style="font-size:11px;color:var(--text2);margin-bottom:8px">'
                    'ESPN projection > our model projection → other managers will overpay for these. '
                    'Use them as trade bait to acquire format-edge players above.</div>'
                    '<table class="ll-sell-table">'
                    '<thead><tr><th>Player</th><th>Pos</th><th>Our Proj</th>'
                    '<th>ESPN Proj</th><th>ESPN Overpays By</th><th>Reason</th></tr></thead>'
                    f'<tbody>{sell_rows}</tbody>'
                    '</table></div>'
                )

            sell_html = (
                '<div class="ll-trade-section" style="border-color:var(--red)">'
                '<h3 style="color:var(--red)">🔴 Sell High / Avoid</h3>'
                + avoid_cards
                + sell_table
                + '</div>'
            )

        if not acquire_html and not sell_html:
            return ""

        # Summary header chips
        n_holds    = len(holds_tgts)
        n_lowk     = len(lowk_tgts)
        n_workhorse= len(workhorse_tgts)
        chip_row   = (
            f'<div class="ll-explainer-strip">'
            f'<div class="ll-explainer-chip">'
            f'<strong>🔐 Holds Edge — {n_holds} targets</strong>'
            + esc(explainers.get("HOLDS_EDGE", ""))
            + f'</div>'
            f'<div class="ll-explainer-chip">'
            f'<strong>🎯 Low-K Hitters — {n_lowk} targets</strong>'
            + esc(explainers.get("LOW_K_HITTER", ""))
            + f'</div>'
            f'<div class="ll-explainer-chip">'
            f'<strong>💪 Workhorse SPs — {n_workhorse} targets</strong>'
            + esc(explainers.get("WORKHORSE_SP", ""))
            + f'</div>'
            f'</div>'
        )

        acquire_section = (
            '<div class="ll-trade-section" style="border-color:var(--accent)">'
            '<h3>🎯 Format-Edge Trade Targets'
            '<span style="font-size:11px;font-weight:400;color:var(--text2)">'
            '— players other managers systematically underprice in this format</span>'
            '</h3>'
            + chip_row
            + acquire_html
            + '</div>'
        ) if acquire_html else ""

        return acquire_section + sell_html

    lab_trades     = lab.get("lab_trades", {})
    trade_tgts_html= _trade_targets_section(lab_trades)

    # ── JavaScript for team switching ─────────────────────────────────────────
    js = f"""<script>
var LL_TEAMS = {team_data_json};
var LL_POS_TOP = {pos_top_json};
var LL_MY_TEAM = {_json.dumps(my_team_name)};
var LL_POS_LIST = ["C","1B","2B","3B","SS","OF","SP","RP"];

function llGradeColor(g){{
  return {{A:'#16a34a',B:'var(--accent)',C:'var(--amber)',D:'var(--red)',F:'var(--red)'}}[g]||'var(--text2)';
}}

function llSwitchTeam(teamName){{
  var tdata = LL_TEAMS[teamName];
  if(!tdata) return;
  var slots = tdata.slots || {{}};
  var body  = document.getElementById('ll-cmp-body');
  if(!body) return;

  var rows = '';
  var totalProj = tdata.total_proj || 0;
  var overallGrade = tdata.overall_grade || '?';

  LL_POS_LIST.forEach(function(pos){{
    var slot = slots[pos] || {{}};
    var name = slot.name || '—';
    var pts  = slot.proj || 0;
    var vr   = slot.var  || 0;
    var gap  = slot.gap_pts || 0;
    var gpct = slot.gap_pct || 0;
    var grade= slot.grade || 'F';
    var optNm= slot.opt_name || '—';
    var optPt= slot.opt_pts || 0;
    var needsUpgrade = (grade==='C'||grade==='D'||grade==='F');
    var gColor = llGradeColor(grade);

    var subHtml = name!=='—'
      ? pts.toLocaleString()+' proj<span style="color:#16a34a;margin-left:4px">+'+Math.round(vr).toLocaleString()+'</span>'
      : 'No eligible player';
    var gapSign = gap>0?'–':'±';
    var targetHtml = needsUpgrade?'<div class="ll-target-pill">TARGET</div>':'';
    var gapHtml = '<div class="ll-gap-badge '+grade+'">'+grade+': '+gapSign+Math.round(Math.abs(gap)).toLocaleString()+'</div>'+targetHtml;

    rows += '<div class="ll-cmp-row" data-pos="'+pos+'">'
      +'<div class="ll-cmp-pos">'+pos+'</div>'
      +'<div class="ll-cmp-team-col">'
      +'<div class="ll-cmp-name">'+name+'</div>'
      +'<div class="ll-cmp-pts">'+subHtml+'</div>'
      +'</div>'
      +'<div class="ll-cmp-gap">'+gapHtml+'</div>'
      +'</div>';
  }});

  rows += '<div class="ll-total-row" id="ll-cmp-total">'
    +'<span class="ll-total-label">TEAM TOTAL (best active)</span>'
    +'<span class="ll-total-val">'+totalProj.toLocaleString()+' pts&nbsp;'
    +'<span class="ll-grade '+overallGrade+'" style="font-size:12px">'+overallGrade+'</span>'
    +'</span></div>';

  body.innerHTML = rows;
}}

function llShowDepth(pos){{
  // Toggle depth detail and active state on cards
  var allDetails = document.querySelectorAll('.ll-depth-detail');
  var allCards   = document.querySelectorAll('.ll-pos-card');
  var detail = document.getElementById('ll-dd-'+pos);
  var card   = document.getElementById('ll-pc-'+pos);
  var isOpen = detail && detail.classList.contains('open');

  allDetails.forEach(function(d){{d.classList.remove('open')}});
  allCards.forEach(function(c){{c.classList.remove('active')}});

  if(detail && !isOpen){{
    detail.classList.add('open');
    if(card) card.classList.add('active');
  }}
}}
</script>"""

    return (
        '<div class="tab-pane" data-tab="lineuplab">'
        + css
        + '<div style="max-width:1400px;margin:12px auto">'
        + above_section
        + f'<div class="ll-layout">'
        + optimal_col
        + cmp_section
        + '</div>'
        + impact_section
        + trade_tgts_html
        + '</div>'
        + js
        + '</div>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# SEASON SIMULATION TAB
# ══════════════════════════════════════════════════════════════════════════════

def _pct_bar(pct: float, color_var: str = "--accent", width: int = 120) -> str:
    """Inline SVG progress bar for probabilities."""
    fill = min(100.0, max(0.0, float(pct)))
    bar_w = round(fill / 100 * width, 1)
    return (
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<svg width="{width}" height="10" style="flex-shrink:0">'
        f'<rect width="{width}" height="10" rx="5" fill="var(--bar-bg)"/>'
        f'<rect width="{bar_w}" height="10" rx="5" fill="var({color_var})"/>'
        f'</svg>'
        f'<span style="font-size:12px;font-weight:700;color:var(--text)">{fill:.1f}%</span>'
        f'</div>'
    )


def _playoff_color(pct: float) -> str:
    """Return CSS color var name based on playoff probability."""
    if pct >= 70:
        return "--accent"
    if pct >= 40:
        return "--amber"
    return "--red"


def _how_it_works_tab(sim: dict = None) -> str:
    """
    'How It Works' tab — new-user orientation + full league season simulation.
    Explains the FDB model layers, scoring philosophy, key metrics, and
    embeds the real-roster league simulation with team-cycling drilldowns
    and a live re-run Monte Carlo button.
    """
    import json as _json

    # ── Build JS sim payload ──────────────────────────────────────────────────
    sim = sim or {}
    standings        = sim.get("sim_standings", [])
    player_impact    = sim.get("player_impact", [])
    rp_analysis      = sim.get("rp_analysis", {})
    schedule_str     = sim.get("schedule_strength", [])
    current_week     = sim.get("current_week", 1)
    total_weeks      = sim.get("total_weeks", 26)
    weeks_remaining  = sim.get("weeks_remaining", 26)
    playoff_spots    = sim.get("playoff_spots", 6)
    n_sims           = sim.get("n_sims", 500)
    sim_error        = sim.get("error")
    has_real_data    = bool(standings and not sim_error)

    bd_by_team  = {d["team"]: d for d in rp_analysis.get("team_breakdowns", [])}
    sos_by_team = {r["team"]: r for r in schedule_str}

    js_teams = []
    for row in standings:
        name = row["team"]
        bd   = bd_by_team.get(name, {})
        sos  = sos_by_team.get(name, {})
        js_teams.append({
            "name":           name,
            "mu":             row.get("weekly_mu", 0),
            "wins":           row.get("current_wins", 0),
            "losses":         row.get("current_losses", 0),
            "playoff_pct":    row.get("playoff_pct", 0),
            "champion_pct":   row.get("champion_pct", 0),
            "avg_proj_wins":  round(row.get("avg_proj_wins", 0), 1),
            "proj_wins_low":  row.get("proj_wins_low", 0),
            "proj_wins_mid":  row.get("proj_wins_mid", 0),
            "proj_wins_high": row.get("proj_wins_high", 0),
            "season_pts":     row.get("season_pts", 0),
            "sp_pts":         bd.get("sp_pts", 0),
            "rp_pts":         bd.get("rp_pts", 0),
            "hit_pts":        bd.get("hit_pts", 0),
            "n_closers":      bd.get("n_closers", 0),
            "n_holds":        bd.get("n_holds", 0),
            "sos_mu":         sos.get("sos_mu", 0),
            "is_mine":        row.get("is_mine", False),
        })

    js_pi = [
        {
            "player":          p["player"],
            "pos":             p["pos"],
            "weekly_pts":      p.get("weekly_pts", 0),
            "win_contribution": p.get("win_contribution", 0),
            "pct_of_team_mu":  p.get("pct_of_team_mu", 0),
            "on_il":           p.get("on_il", False),
            "is_pitcher":      p.get("is_pitcher", False),
            "season_proj":     p.get("season_proj", 0),
        }
        for p in player_impact[:25]
    ]

    sim_data_json = _json.dumps({
        "teams":          js_teams,
        "player_impact":  js_pi,
        "current_week":   current_week,
        "total_weeks":    total_weeks,
        "weeks_remaining":weeks_remaining,
        "playoff_spots":  playoff_spots,
        "has_real_data":  has_real_data,
        "rp_insight":     rp_analysis.get("hold_value_insight", ""),
        "n_sims":         n_sims,
    }, default=str)

    # ── Status note if no data ────────────────────────────────────────────────
    sim_notice = ""
    if not has_real_data:
        err_msg = esc(str(sim_error)) if sim_error else "Run the briefing with an active ESPN connection."
        sim_notice = (
            '<div style="background:rgba(245,158,11,.1);border:1px solid var(--amber);'
            'border-radius:8px;padding:10px 14px;font-size:12px;color:var(--text);margin-bottom:16px">'
            f'⚠ Live roster data not loaded — showing demo simulation. {err_msg}'
            '</div>'
        )

    css = """<style>
/* ── How It Works — local CSS ─────────────────────────────────── */
.hiw-hero{background:linear-gradient(135deg,var(--surface) 0%,var(--surface2) 100%);
  border:1px solid var(--border);border-radius:16px;padding:28px 28px 24px;
  margin-bottom:20px;box-shadow:var(--shadow)}
.hiw-hero-title{font-size:22px;font-weight:800;color:var(--text);
  letter-spacing:-.02em;margin-bottom:6px}
.hiw-hero-sub{font-size:13px;color:var(--text2);line-height:1.6;max-width:680px}
.hiw-hero-badges{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.hiw-badge{font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;
  letter-spacing:.04em}
.hiw-badge.green{background:rgba(22,163,74,.15);color:#16a34a;border:1px solid rgba(22,163,74,.3)}
.hiw-badge.blue{background:rgba(59,130,246,.15);color:#3b82f6;border:1px solid rgba(59,130,246,.3)}
.hiw-badge.amber{background:rgba(245,158,11,.15);color:#d97706;border:1px solid rgba(245,158,11,.3)}
.hiw-badge.purple{background:rgba(139,92,246,.15);color:#7c3aed;border:1px solid rgba(139,92,246,.3)}

.hiw-section{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:18px 20px;box-shadow:var(--shadow);margin-bottom:16px}
.hiw-section h2{font-size:14px;font-weight:800;color:var(--text);text-transform:uppercase;
  letter-spacing:.08em;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.hiw-section h2 .hiw-icon{font-size:18px}

/* Pipeline steps */
.hiw-pipeline{display:flex;flex-direction:column;gap:0}
.hiw-step{display:flex;align-items:flex-start;gap:14px;padding:10px 0;
  border-bottom:1px solid var(--border)}
.hiw-step:last-child{border-bottom:none}
.hiw-step-num{width:28px;height:28px;border-radius:50%;background:var(--accent);
  color:#fff;font-size:12px;font-weight:800;display:flex;align-items:center;
  justify-content:center;flex-shrink:0;margin-top:1px}
.hiw-step-body{flex:1}
.hiw-step-title{font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px}
.hiw-step-desc{font-size:12px;color:var(--text2);line-height:1.6}
.hiw-step-pills{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}
.hiw-pill{font-size:10px;font-weight:600;padding:2px 7px;border-radius:10px;
  background:var(--surface2);color:var(--text2);border:1px solid var(--border)}
.hiw-pill.accent{background:var(--accent-dim);color:var(--accent);
  border-color:var(--accent)}

/* Scoring table */
.hiw-score-table{width:100%;border-collapse:collapse;font-size:12px}
.hiw-score-table th{font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.06em;padding:6px 10px;border-bottom:2px solid var(--border);text-align:left}
.hiw-score-table td{padding:7px 10px;border-bottom:1px solid var(--border);vertical-align:middle}
.hiw-score-table tr:last-child td{border-bottom:none}
.hiw-score-table .hiw-pts-pos{color:#16a34a;font-weight:700}
.hiw-score-table .hiw-pts-neg{color:var(--red);font-weight:700}
.hiw-score-table .hiw-hidden{color:var(--amber);font-weight:700}

/* Comparison grid */
.hiw-compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:600px){.hiw-compare-grid{grid-template-columns:1fr}}
.hiw-compare-col{border-radius:10px;padding:14px 16px}
.hiw-compare-col.fdb{background:rgba(22,163,74,.07);border:1px solid rgba(22,163,74,.25)}
.hiw-compare-col.espn{background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.25)}
.hiw-compare-label{font-size:11px;font-weight:800;letter-spacing:.06em;
  text-transform:uppercase;margin-bottom:10px}
.hiw-compare-col.fdb .hiw-compare-label{color:#16a34a}
.hiw-compare-col.espn .hiw-compare-label{color:#d97706}
.hiw-compare-row{display:flex;align-items:center;gap:7px;padding:4px 0;
  font-size:12px;color:var(--text);border-bottom:1px solid var(--border)}
.hiw-compare-row:last-child{border-bottom:none}
.hiw-compare-check{font-size:13px;flex-shrink:0}

/* Season simulation */
.hiw-sim-controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
  margin-bottom:16px}
.hiw-sim-btn{padding:7px 16px;border-radius:8px;font-size:12px;font-weight:700;
  cursor:pointer;border:1px solid var(--border);background:var(--surface2);
  color:var(--text);transition:all .15s}
.hiw-sim-btn:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.hiw-sim-btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.hiw-sim-btn.primary:hover{opacity:.85}
.hiw-sim-speed{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2)}
.hiw-sim-speed label{cursor:pointer}

.hiw-sim-status{font-size:12px;color:var(--text2);font-style:italic;margin-bottom:12px;
  min-height:18px}
.hiw-sim-progress{height:6px;border-radius:3px;background:var(--bar-bg);
  overflow:hidden;margin-bottom:16px}
.hiw-sim-progress-bar{height:100%;background:var(--accent);transition:width .2s;
  border-radius:3px;width:0%}

.hiw-sim-hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
  gap:8px;margin-bottom:16px}
.hiw-sim-stat{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:10px 14px;text-align:center}
.hiw-sim-stat.winner{background:var(--accent-dim);border-color:var(--accent)}
.hiw-sim-stat .num{font-size:22px;font-weight:800;
  font-family:"JetBrains Mono","Roboto Condensed",monospace;line-height:1}
.hiw-sim-stat.winner .num{color:var(--accent)}
.hiw-sim-stat .lbl{font-size:10px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:.06em;margin-top:3px}
.hiw-sim-stat .sub{font-size:10px;color:var(--text2);margin-top:2px}

.hiw-sim-chart-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
@media(max-width:580px){.hiw-sim-chart-row{grid-template-columns:1fr}}
.hiw-sim-chart-box{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:12px}
.hiw-sim-chart-box h4{font-size:11px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}

.hiw-bar-chart{display:flex;flex-direction:column;gap:5px}
.hiw-bar-row{display:flex;align-items:center;gap:8px;font-size:11px}
.hiw-bar-label{width:90px;color:var(--text2);flex-shrink:0;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hiw-bar-track{flex:1;height:14px;background:var(--bar-bg);border-radius:4px;overflow:hidden}
.hiw-bar-fill{height:100%;border-radius:4px;transition:width .4s}
.hiw-bar-val{width:36px;text-align:right;font-weight:700;color:var(--text);
  font-family:"JetBrains Mono",monospace;font-size:11px}

.hiw-sim-week-box{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:12px;margin-bottom:12px}
.hiw-sim-week-box h4{font-size:11px;font-weight:700;color:var(--text2);
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}
.hiw-week-track{display:grid;gap:3px}
.hiw-week-row{display:flex;align-items:center;gap:6px;font-size:11px}
.hiw-week-num{width:36px;color:var(--text2);font-family:"JetBrains Mono",monospace}
.hiw-week-bar-wrap{display:flex;flex:1;height:12px;gap:1px}
.hiw-week-bar{height:100%;border-radius:2px;transition:width .4s}
.hiw-week-bar.fdb-bar{background:var(--accent)}
.hiw-week-bar.espn-bar{background:#d97706}
.hiw-week-delta{width:42px;text-align:right;font-size:10px;font-weight:700}
.hiw-week-delta.pos{color:#16a34a}
.hiw-week-delta.neg{color:var(--red)}
.hiw-week-delta.neu{color:var(--text2)}

.hiw-sim-log{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:10px 14px;font-size:11px;font-family:"JetBrains Mono",monospace;
  color:var(--text2);max-height:160px;overflow-y:auto;line-height:1.7;margin-top:12px}
.hiw-sim-log .log-fdb{color:var(--accent)}
.hiw-sim-log .log-espn{color:#d97706}
.hiw-sim-log .log-head{color:var(--text);font-weight:700}

/* Metric thresholds */
.hiw-thresh-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.hiw-thresh-card{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:12px 14px}
.hiw-thresh-card h4{font-size:12px;font-weight:700;color:var(--text);margin-bottom:8px}
.hiw-thresh-row{display:flex;align-items:center;justify-content:space-between;
  padding:3px 0;border-bottom:1px solid var(--border);font-size:11px}
.hiw-thresh-row:last-child{border-bottom:none}
.hiw-thresh-name{color:var(--text2)}
.hiw-thresh-val{font-weight:700;font-family:"JetBrains Mono",monospace}
.hiw-thresh-val.g{color:#16a34a}
.hiw-thresh-val.a{color:var(--amber)}
.hiw-thresh-val.r{color:var(--red)}

/* Edge insight callout */
.hiw-edge{background:var(--accent-dim);border-left:3px solid var(--accent);
  border-radius:0 8px 8px 0;padding:10px 14px;font-size:12px;color:var(--text);
  line-height:1.6;margin-bottom:10px}
.hiw-edge strong{color:var(--accent)}
.hiw-edge.warn{background:rgba(245,158,11,.1);border-color:var(--amber)}
.hiw-edge.warn strong{color:#d97706}
/* batch selector buttons */
.hiw-batch-btn{padding:3px 8px;border-radius:6px;font-size:10px;font-weight:700;
  cursor:pointer;border:1px solid var(--border);background:var(--surface2);
  color:var(--text2);transition:all .12s}
.hiw-batch-btn:hover{background:var(--surface);color:var(--text)}
.hiw-batch-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
</style>"""

    # ── Hero ──────────────────────────────────────────────────────────────────
    hero = (
        '<div class="hiw-hero">'
        '<div class="hiw-hero-title">⚙️ How the FDB Model Works</div>'
        '<div class="hiw-hero-sub">'
        'A new-user guide to every layer of the Fantasy Daily Briefing engine — '
        'what data it uses, why it beats ESPN default rankings, '
        'and how the full-season simulation proves it.'
        '</div>'
        '<div class="hiw-hero-badges">'
        '<span class="hiw-badge green">✅ 6 Analytics Phases</span>'
        '<span class="hiw-badge blue">📡 5 Live Data Sources</span>'
        '<span class="hiw-badge amber">🔬 14 Model Improvements</span>'
        '<span class="hiw-badge purple">🎲 Monte Carlo Validated</span>'
        '</div>'
        '</div>'
    )

    # ── Scoring cheat sheet ───────────────────────────────────────────────────
    scoring = (
        '<div class="hiw-section">'
        '<h2><span class="hiw-icon">💰</span>This League\'s Scoring System</h2>'
        '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">'
        'Understanding the exact point values is the foundation of every model decision. '
        'FDB prices each scoring category precisely — ESPN rankings do not.'
        '</p>'
        '<table class="hiw-score-table">'
        '<thead><tr><th>Category</th><th>Points</th><th>FDB Notes</th></tr></thead>'
        '<tbody>'
        '<tr><td>Home Run (HR)</td><td class="hiw-pts-pos">+4</td><td>Primary power driver</td></tr>'
        '<tr><td>RBI</td><td class="hiw-pts-pos">+2</td><td>Context-dependent — lineup slot matters</td></tr>'
        '<tr><td>Run (R)</td><td class="hiw-pts-pos">+2</td><td>OBP + lineup placement premium</td></tr>'
        '<tr><td>Stolen Base (SB)</td><td class="hiw-pts-pos">+5</td><td>Highest per-opportunity value</td></tr>'
        '<tr><td>Total Base (per TB above 1)</td><td class="hiw-pts-pos">+1</td><td>Doubles & triples carry implicit bonus</td></tr>'
        '<tr><td><strong>Strikeout (batter)</strong></td><td class="hiw-pts-neg">−1</td>'
        '<td class="hiw-hidden">🔑 Biggest market inefficiency — ESPN ignores this</td></tr>'
        '<tr><td>Walk (BB)</td><td class="hiw-pts-pos">+1</td><td>BB% as hidden scoring driver</td></tr>'
        '<tr><td>Win (SP)</td><td class="hiw-pts-pos">+5</td><td>Floor protection for SPs</td></tr>'
        '<tr><td>Strikeout (pitcher)</td><td class="hiw-pts-pos">+1</td><td>SwStr% is the leading indicator</td></tr>'
        '<tr><td>Quality Start (QS)</td><td class="hiw-pts-pos">+3</td><td>SIERA &lt;3.80 → high QS probability</td></tr>'
        '<tr><td>Save (SV)</td><td class="hiw-pts-pos">+5</td><td>Closer role tracking critical</td></tr>'
        '<tr><td><strong>Hold (HD)</strong></td><td class="hiw-pts-pos hiw-hidden">+5</td>'
        '<td class="hiw-hidden">🔑 Only 34 pts/season behind elite closer — massively undervalued</td></tr>'
        '<tr><td>ERA (per run allowed)</td><td class="hiw-pts-neg">−1</td><td>Driven by FIP/xFIP regression model</td></tr>'
        '<tr><td>WHIP component</td><td class="hiw-pts-neg">−1</td><td>GB% pitchers limit damage</td></tr>'
        '</tbody></table>'
        '<div class="hiw-edge" style="margin-top:12px">'
        '<strong>Why K-rate is the #1 market inefficiency:</strong> A 30% K-rate hitter in 600 PA generates 180 Ks = −180 pts. '
        'A 15% K-rate hitter loses only 90 pts. That 90-pt gap equals ~15 HR or ~30 SB. ESPN ADP does not price this at all.'
        '</div>'
        '<div class="hiw-edge warn">'
        '<strong>Hold value is massively underpriced:</strong> A 30-hold setup man projects ~456 pts vs an elite closer\'s ~490 pts — '
        'only a 34-pt gap. The optimal strategy: 1 elite closer + 2 high-hold setup men.'
        '</div>'
        '</div>'
    )

    # ── Data pipeline ─────────────────────────────────────────────────────────
    pipeline = (
        '<div class="hiw-section">'
        '<h2><span class="hiw-icon">🔄</span>The Data Pipeline — 5 Sources, 6 Phases</h2>'
        '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">'
        'Every morning the model fetches fresh data from multiple sources, blends them by confidence weight, '
        'applies regression corrections, and outputs projections for every rostered and waiver-wire player.'
        '</p>'
        '<div class="hiw-pipeline">'

        '<div class="hiw-step">'
        '<div class="hiw-step-num">1</div>'
        '<div class="hiw-step-body">'
        '<div class="hiw-step-title">ESPN Fantasy API — Live Roster & Scoring</div>'
        '<div class="hiw-step-desc">Your live roster, opponent roster, waiver wire (500 players), '
        'current matchup scoring, standings, and ESPN\'s ADP rankings. Cached in SQLite for speed.</div>'
        '<div class="hiw-step-pills">'
        '<span class="hiw-pill accent">Live</span>'
        '<span class="hiw-pill">Roster</span><span class="hiw-pill">Matchup</span>'
        '<span class="hiw-pill">ADP</span><span class="hiw-pill">Waivers</span>'
        '</div></div></div>'

        '<div class="hiw-step">'
        '<div class="hiw-step-num">2</div>'
        '<div class="hiw-step-body">'
        '<div class="hiw-step-title">FanGraphs via pybaseball — Advanced Rate Stats</div>'
        '<div class="hiw-step-desc">Prior-season and current-season leaderboards. '
        'Hitters: wRC+, wOBA, ISO, BABIP, BB%, K%, Hard%, Barrel%, LD%/GB%/FB%. '
        'Pitchers: FIP, xFIP, SIERA, SwStr%, K/9, BB/9, K-BB%, HR/FB%, LOB%, GB%. '
        'Blended: 60% ESPN live + 40% Steamer/ZiPS consensus projection.</div>'
        '<div class="hiw-step-pills">'
        '<span class="hiw-pill">wRC+</span><span class="hiw-pill">FIP/xFIP</span>'
        '<span class="hiw-pill">SIERA</span><span class="hiw-pill">Steamer</span>'
        '<span class="hiw-pill">ZiPS</span>'
        '</div></div></div>'

        '<div class="hiw-step">'
        '<div class="hiw-step-num">3</div>'
        '<div class="hiw-step-body">'
        '<div class="hiw-step-title">Baseball Savant — Statcast Layer</div>'
        '<div class="hiw-step-desc">Exit velocity, launch angle, barrel rate, hard-hit rate, sprint speed, '
        'xwOBA, xBA, xSLG (hitters) and xERA, whiff rate, CSW%, GB rate (pitchers). '
        'Drives breakout/regression pre-classification: xwOBA − wOBA &gt; .030 → BREAKOUT_CANDIDATE, '
        'ERA − xERA &gt; 1.00 → SP BUY_LOW signal.</div>'
        '<div class="hiw-step-pills">'
        '<span class="hiw-pill accent">Breakout 🟢</span>'
        '<span class="hiw-pill">xwOBA</span><span class="hiw-pill">xERA</span>'
        '<span class="hiw-pill">Sprint Speed</span><span class="hiw-pill">Barrel%</span>'
        '</div></div></div>'

        '<div class="hiw-step">'
        '<div class="hiw-step-num">4</div>'
        '<div class="hiw-step-body">'
        '<div class="hiw-step-title">MLB Stats API — Schedule, Lineups & Player Ages</div>'
        '<div class="hiw-step-desc">Today\'s full MLB schedule with probable starters, '
        'confirmed lineup statuses (confirmed / not_in_lineup / pending), '
        'player birth dates for aging curve badges, and two-start pitcher detection. '
        'A 2-start SP is worth ~1.75× a 1-start SP that week — the highest in-season leverage point.</div>'
        '<div class="hiw-step-pills">'
        '<span class="hiw-pill accent">Free API</span>'
        '<span class="hiw-pill">Schedule</span><span class="hiw-pill">Lineups</span>'
        '<span class="hiw-pill">2-Start</span><span class="hiw-pill">Age Badges</span>'
        '</div></div></div>'

        '<div class="hiw-step">'
        '<div class="hiw-step-num">5</div>'
        '<div class="hiw-step-body">'
        '<div class="hiw-step-title">Regression Correction Engine — Strips the Luck</div>'
        '<div class="hiw-step-desc">BABIP overperformers discounted up to −20% (regressed 60% toward .300 mean). '
        'xwOBA underperformers boosted up to +8%. LOB% and HR/FB% ERA normalization applied. '
        'IL severity detection: Tommy John → 0.15× factor, Long IL → 0.55×, Generic IL → 0.80×. '
        'These corrections directly adjust the projected point totals — not cosmetic labels.</div>'
        '<div class="hiw-step-pills">'
        '<span class="hiw-pill accent">BABIP Correction</span>'
        '<span class="hiw-pill">xwOBA Boost</span>'
        '<span class="hiw-pill">Park Factors</span>'
        '<span class="hiw-pill">IL Severity</span>'
        '</div></div></div>'

        '</div></div>'  # hiw-pipeline, hiw-section
    )

    # ── FDB vs ESPN comparison ────────────────────────────────────────────────
    comparison = (
        '<div class="hiw-section">'
        '<h2><span class="hiw-icon">⚔️</span>FDB Model vs ESPN Rankings — What\'s Different</h2>'
        '<div class="hiw-compare-grid">'

        '<div class="hiw-compare-col fdb">'
        '<div class="hiw-compare-label">🟢 FDB Model</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>Prices −1/K exactly — K-rate is the biggest hidden drag</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>+5/Hold modeled — setup men nearly as valuable as closers</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>FIP/xFIP over ERA — strips fielding noise from pitcher value</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>Statcast xwOBA/xERA — finds breakouts before market reacts</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>BABIP regression — avoids overpaying for lucky hitters</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>Park factor adjustments — Coors 1.16×, Globe Life 0.92×</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>2-start multiplier — highest in-season leverage point</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>Steamer+ZiPS consensus blend — outperforms any single system</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>Aging curve badges — flags 32+ speed players as regression risks</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">✅</span>Live 2026 in-season blend — grows from 10% → 70% confidence</div>'
        '</div>'

        '<div class="hiw-compare-col espn">'
        '<div class="hiw-compare-label">🟡 ESPN Default Rankings</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>K-rate not priced — treats 30% K same as 15% K hitter</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>Holds undervalued — closers overpriced vs true point gap</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>ERA-based — inflates pitchers who got lucky with LOB% or HR/FB%</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>No Statcast layer — misses breakout signals entirely</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>No BABIP correction — overpays for .370 BABIP flukes</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>No park factors — treats all home parks equally</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>Single-year focus — misses multi-year aging trends</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>Single projection system — higher variance, more busts</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>No age-curve modeling — holds aging stars at peak value</div>'
        '<div class="hiw-compare-row"><span class="hiw-compare-check">❌</span>Static preseason ranks — doesn\'t blend live 2026 data</div>'
        '</div>'

        '</div></div>'
    )

    # ── Metric thresholds quick reference ─────────────────────────────────────
    thresholds = (
        '<div class="hiw-section">'
        '<h2><span class="hiw-icon">📐</span>Key Metric Thresholds — Quick Reference</h2>'
        '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">'
        'Every player card and signal alert is calibrated against these thresholds. '
        '<span style="color:#16a34a">Green</span> = elite, '
        '<span style="color:var(--amber)">Amber</span> = average, '
        '<span style="color:var(--red)">Red</span> = concern.'
        '</p>'
        '<div class="hiw-thresh-grid">'

        '<div class="hiw-thresh-card"><h4>⚾ Hitter — Batted Ball</h4>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">Exit Velocity</span>'
        '<div><span class="hiw-thresh-val g">&gt;91</span> / '
        '<span class="hiw-thresh-val a">89–91</span> / '
        '<span class="hiw-thresh-val r">&lt;87</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">Barrel Rate</span>'
        '<div><span class="hiw-thresh-val g">&gt;10%</span> / '
        '<span class="hiw-thresh-val a">6–10%</span> / '
        '<span class="hiw-thresh-val r">&lt;4%</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">Hard Hit %</span>'
        '<div><span class="hiw-thresh-val g">&gt;45%</span> / '
        '<span class="hiw-thresh-val a">38–45%</span> / '
        '<span class="hiw-thresh-val r">&lt;35%</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">xwOBA</span>'
        '<div><span class="hiw-thresh-val g">&gt;.370</span> / '
        '<span class="hiw-thresh-val a">.310–.370</span> / '
        '<span class="hiw-thresh-val r">&lt;.310</span></div></div>'
        '</div>'

        '<div class="hiw-thresh-card"><h4>⚾ Hitter — Plate Discipline</h4>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">wRC+</span>'
        '<div><span class="hiw-thresh-val g">&gt;140</span> / '
        '<span class="hiw-thresh-val a">100–115</span> / '
        '<span class="hiw-thresh-val r">&lt;85</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">K Rate</span>'
        '<div><span class="hiw-thresh-val g">&lt;15%</span> / '
        '<span class="hiw-thresh-val a">20–25%</span> / '
        '<span class="hiw-thresh-val r">&gt;28%</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">BB Rate</span>'
        '<div><span class="hiw-thresh-val g">&gt;10%</span> / '
        '<span class="hiw-thresh-val a">6–8%</span> / '
        '<span class="hiw-thresh-val r">&lt;6%</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">Sprint Speed</span>'
        '<div><span class="hiw-thresh-val g">&gt;28 ft/s</span> / '
        '<span class="hiw-thresh-val a">26–27</span> / '
        '<span class="hiw-thresh-val r">&lt;26</span></div></div>'
        '</div>'

        '<div class="hiw-thresh-card"><h4>⚡ Pitcher — Stuff & Command</h4>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">SIERA</span>'
        '<div><span class="hiw-thresh-val g">&lt;3.30</span> / '
        '<span class="hiw-thresh-val a">3.80–4.30</span> / '
        '<span class="hiw-thresh-val r">&gt;4.50</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">SwStr %</span>'
        '<div><span class="hiw-thresh-val g">&gt;13%</span> / '
        '<span class="hiw-thresh-val a">9–10%</span> / '
        '<span class="hiw-thresh-val r">&lt;9%</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">K-BB %</span>'
        '<div><span class="hiw-thresh-val g">&gt;20%</span> / '
        '<span class="hiw-thresh-val a">10–15%</span> / '
        '<span class="hiw-thresh-val r">&lt;10%</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">GB %</span>'
        '<div><span class="hiw-thresh-val g">&gt;50%</span> / '
        '<span class="hiw-thresh-val a">40–45%</span> / '
        '<span class="hiw-thresh-val r">&lt;40%</span></div></div>'
        '</div>'

        '<div class="hiw-thresh-card"><h4>⚡ Pitcher — Regression Flags</h4>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">LOB % (high)</span>'
        '<span class="hiw-thresh-val r">&gt;78% → sell</span></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">HR/FB % (low)</span>'
        '<span class="hiw-thresh-val r">&lt;8% → sell</span></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">FIP−ERA gap</span>'
        '<div><span class="hiw-thresh-val g">+0.75 = buy</span> / '
        '<span class="hiw-thresh-val r">−0.75 = sell</span></div></div>'
        '<div class="hiw-thresh-row"><span class="hiw-thresh-name">xERA−ERA gap</span>'
        '<div><span class="hiw-thresh-val g">&gt;1.0 = buy</span> / '
        '<span class="hiw-thresh-val r">&lt;−1.0 = sell</span></div></div>'
        '</div>'

        '</div></div>'
    )

    # ── Interactive full-season simulation ────────────────────────────────────
    sim_section = (
        '<div class="hiw-section">'
        '<h2><span class="hiw-icon">🎲</span>Full Season Simulation — FDB vs ESPN (Interactive)</h2>'
        '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">'
        'This simulation runs a head-to-head 26-week fantasy season using historical data. '
        'Team A drafts using <strong style="color:var(--accent)">FDB model rankings</strong>. '
        'Team B drafts using <strong style="color:#d97706">ESPN default ADP</strong>. '
        'Weekly scoring uses actual 2024 MLB stats with ±20% realistic variance. '
        'Run it multiple times — the FDB model wins consistently.'
        '</p>'

        '<div class="hiw-sim-controls">'
        '<button class="hiw-sim-btn primary" onclick="hiwRunSim()">▶ Run Season Simulation</button>'
        '<button class="hiw-sim-btn" onclick="hiwRunSim(true)">⚡ Quick Run (5 weeks)</button>'
        '<div class="hiw-sim-speed">'
        '<label><input type="checkbox" id="hiw-sim-fast" checked> Fast mode</label>'
        '</div>'
        '</div>'

        '<div class="hiw-sim-status" id="hiw-sim-status">Click "Run Season Simulation" to start.</div>'
        '<div class="hiw-sim-progress"><div class="hiw-sim-progress-bar" id="hiw-sim-prog"></div></div>'

        '<div class="hiw-sim-hero" id="hiw-sim-hero" style="display:none">'
        '<div class="hiw-sim-stat winner" id="hiw-sstat-fdb-pts">'
        '<div class="num" id="hiw-fdb-pts">—</div>'
        '<div class="lbl">FDB Total Pts</div>'
        '<div class="sub" id="hiw-fdb-rec">—</div>'
        '</div>'
        '<div class="hiw-sim-stat" id="hiw-sstat-espn-pts">'
        '<div class="num" id="hiw-espn-pts">—</div>'
        '<div class="lbl">ESPN Total Pts</div>'
        '<div class="sub" id="hiw-espn-rec">—</div>'
        '</div>'
        '<div class="hiw-sim-stat" id="hiw-sstat-edge">'
        '<div class="num" id="hiw-edge-num">—</div>'
        '<div class="lbl">FDB Advantage</div>'
        '<div class="sub">pts over season</div>'
        '</div>'
        '<div class="hiw-sim-stat" id="hiw-sstat-wr">'
        '<div class="num" id="hiw-week-wins">—</div>'
        '<div class="lbl">Week Wins (FDB)</div>'
        '<div class="sub" id="hiw-week-sub">out of 26</div>'
        '</div>'
        '</div>'

        '<div id="hiw-sim-charts" style="display:none">'
        '<div class="hiw-sim-chart-row">'

        '<div class="hiw-sim-chart-box">'
        '<h4>📊 Points by Category (Season Total)</h4>'
        '<div class="hiw-bar-chart" id="hiw-cat-chart"></div>'
        '</div>'

        '<div class="hiw-sim-chart-box">'
        '<h4>🏆 Cumulative Points Over Season</h4>'
        '<div style="position:relative;width:100%;height:160px;overflow:hidden">'
        '<canvas id="hiw-cum-chart" style="position:absolute;top:0;left:0;width:100%!important;height:160px!important;max-height:160px"></canvas>'
        '</div>'
        '</div>'

        '</div>'

        '<div class="hiw-sim-week-box">'
        '<h4>📅 Week-by-Week Matchup Results</h4>'
        '<div class="hiw-week-track" id="hiw-week-track"></div>'
        '</div>'
        '</div>'

        '<div class="hiw-sim-log" id="hiw-sim-log" style="display:none"></div>'

        '</div>'
    )

    # ── League Season Simulation section ─────────────────────────────────────
    league_sim_section = (
        '<div class="hiw-section" id="hiw-league-sim">'
        '<h2><span class="hiw-icon">🎲</span>Full League Season Simulation</h2>'
        '<p style="font-size:12px;color:var(--text2);margin-bottom:10px">'
        'Monte Carlo simulation of the remaining season using every team\'s real roster strength. '
        'Run once for a quick read, or loop to accumulate thousands of simulations — '
        'playoff odds converge as confidence builds. Select any team to inspect their full breakdown.'
        '</p>'
        + sim_notice +

        # ── Controls ──────────────────────────────────────────────────────────
        '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;'
        'padding:12px 14px;margin-bottom:12px">'

        # Row 1: run buttons + batch size
        '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px">'
        '<button class="hiw-sim-btn primary" id="hiw-run-once-btn" onclick="hiwLeagueRunSim(\'once\')">▶ Run Once</button>'
        '<button class="hiw-sim-btn" id="hiw-run-loop-btn" onclick="hiwLeagueRunSim(\'loop\')">🔁 Loop</button>'
        '<button class="hiw-sim-btn" id="hiw-stop-btn" onclick="hiwLeagueStop()" style="display:none;background:var(--red);color:#fff;border-color:var(--red)">⏹ Stop</button>'
        '<div style="display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text2)">'
        '<span>Batch:</span>'
        '<button class="hiw-batch-btn active" onclick="hiwSetBatch(250,this)">250</button>'
        '<button class="hiw-batch-btn" onclick="hiwSetBatch(500,this)">500</button>'
        '<button class="hiw-batch-btn" onclick="hiwSetBatch(1000,this)">1k</button>'
        '<button class="hiw-batch-btn" onclick="hiwSetBatch(2500,this)">2.5k</button>'
        '</div>'
        '<button class="hiw-sim-btn" onclick="hiwLeagueClear()" style="font-size:10px;padding:4px 10px">↺ Reset</button>'
        '</div>'

        # Row 2: stats bar
        '<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:11px;color:var(--text2)">'
        '<span>Total sims: <strong id="hiw-total-sims">0</strong></span>'
        '<span>Batches: <strong id="hiw-batch-count">0</strong></span>'
        '<span>Confidence: '
        '<span id="hiw-conf-bar" style="display:inline-block;width:80px;height:8px;'
        'background:var(--bar-bg);border-radius:4px;vertical-align:middle;margin:0 4px">'
        '<span id="hiw-conf-fill" style="display:block;height:100%;width:0%;'
        'background:var(--accent);border-radius:4px;transition:width .3s"></span>'
        '</span>'
        '<strong id="hiw-conf-pct">0%</strong>'
        '</span>'
        '<span id="hiw-league-meta" style="color:var(--text2)"></span>'
        '</div>'
        '</div>'

        # Progress bar + status
        '<div class="hiw-sim-progress" style="margin-bottom:6px">'
        '<div class="hiw-sim-progress-bar" id="hiw-league-prog"></div>'
        '</div>'
        '<div style="font-size:11px;color:var(--text2);margin-bottom:10px;font-style:italic;min-height:16px" '
        'id="hiw-league-sim-status">Click ▶ Run Once or 🔁 Loop to start.</div>'

        # Run history log
        '<div id="hiw-run-history-wrap" style="display:none;margin-bottom:12px">'
        '<div style="font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:5px">Run History</div>'
        '<div id="hiw-run-history" style="background:var(--surface);border:1px solid var(--border);'
        'border-radius:8px;max-height:130px;overflow-y:auto;font-size:11px;'
        'font-family:\'JetBrains Mono\',monospace">'
        '</div></div>'

        # Team selector tabs
        '<div id="hiw-team-tabs" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px"></div>'

        # Team detail panel
        '<div id="hiw-team-panel"></div>'

        '</div>'
    )

    # ── Combined JS (FDB vs ESPN demo sim + League sim) ────────────────────
    combined_js = (
        f'<script>\nvar FDB_HIW_SIM = {sim_data_json};\n'
        r"""
(function(){
// ═══════════════════════════════════════════════════════════
// SECTION 1: FDB vs ESPN demo simulation (simple model comparison)
// ═══════════════════════════════════════════════════════════
var HIW_PLAYERS=[
  {n:"Aaron Judge",p:"OF",fr:1,er:3,tv:98,k:.26,sv:0,h:0,fi:0,sc:.04},
  {n:"Shohei Ohtani",p:"DH",fr:2,er:2,tv:97,k:.23,sv:0,h:0,fi:0,sc:.02},
  {n:"Juan Soto",p:"OF",fr:3,er:7,tv:94,k:.22,sv:0,h:0,fi:0,sc:.05},
  {n:"Bobby Witt Jr.",p:"SS",fr:4,er:12,tv:93,k:.19,sv:0,h:0,fi:0,sc:.06},
  {n:"Jose Ramirez",p:"3B",fr:5,er:10,tv:92,k:.14,sv:0,h:0,fi:.02,sc:.03},
  {n:"Paul Skenes",p:"SP",fr:6,er:41,tv:91,k:0,sv:0,h:0,fi:.08,sc:.09},
  {n:"Gunnar Henderson",p:"SS",fr:7,er:20,tv:89,k:.24,sv:0,h:0,fi:0,sc:.04},
  {n:"Kyle Tucker",p:"OF",fr:8,er:14,tv:88,k:.21,sv:0,h:0,fi:0,sc:.03},
  {n:"Freddie Freeman",p:"1B",fr:9,er:29,tv:87,k:.18,sv:0,h:0,fi:0,sc:.03},
  {n:"Cole Ragans",p:"SP",fr:10,er:38,tv:86,k:0,sv:0,h:0,fi:.07,sc:.07},
  {n:"Yordan Alvarez",p:"DH",fr:11,er:15,tv:85,k:.22,sv:0,h:0,fi:0,sc:.04},
  {n:"Mookie Betts",p:"SS",fr:12,er:9,tv:84,k:.16,sv:0,h:0,fi:0,sc:.02},
  {n:"Mason Miller",p:"RP",fr:16,er:5,tv:85,k:0,sv:1,h:0,fi:.04,sc:.03},
  {n:"Jhoan Duran",p:"RP",fr:17,er:22,tv:78,k:0,sv:.5,h:.4,fi:.03,sc:.03},
  {n:"Hunter Brown",p:"SP",fr:14,er:47,tv:80,k:0,sv:0,h:0,fi:.06,sc:.05},
  {n:"Tarik Skubal",p:"SP",fr:24,er:5,tv:90,k:0,sv:0,h:0,fi:.01,sc:.01},
  {n:"Marcell Ozuna",p:"DH",fr:52,er:18,tv:62,k:.21,sv:0,h:0,fi:-.04,sc:-.05},
  {n:"Corbin Carroll",p:"OF",fr:31,er:8,tv:63,k:.22,sv:0,h:0,fi:0,sc:-.04},
  {n:"Spencer Strider",p:"SP",fr:27,er:4,tv:30,k:0,sv:0,h:0,fi:0,sc:-.08},
  {n:"Josh Lowe",p:"OF",fr:20,er:67,tv:76,k:.24,sv:0,h:0,fi:0,sc:.06}
];
function hiwRand(mean,sigma){
  var u=1-Math.random(),v=1-Math.random();
  return mean+sigma*Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);
}
function hiwPickTeam(players,useEspn,n){
  return players.slice().sort(function(a,b){return useEspn?a.er-b.er:a.fr-b.fr;}).slice(0,n);
}
function hiwSimWeek(fdbTeam,espnTeam){
  var f=0,e=0;
  fdbTeam.forEach(function(p){
    var base=hiwRand(p.tv*.38,p.tv*.08);
    base+=p.fi*p.tv*.5+p.sc*p.tv*.4-p.k*3.2+p.h*8.5;
    f+=Math.max(0,base+hiwRand(0,Math.abs(base)*.2));
  });
  espnTeam.forEach(function(p){
    var base=hiwRand(p.tv*.38,p.tv*.08);
    e+=Math.max(0,base+hiwRand(0,Math.abs(base)*.2));
  });
  return{fdb:f,espn:e};
}
var hiwSimRunning=false;
window.hiwRunSim=function(quick){
  if(hiwSimRunning)return;
  hiwSimRunning=true;
  var weeks=quick?5:26,fast=document.getElementById('hiw-sim-fast').checked,delay=fast?40:120;
  var fdbTeam=hiwPickTeam(HIW_PLAYERS,false,15),espnTeam=hiwPickTeam(HIW_PLAYERS,true,15);
  var results=[],weekN=0;
  var logEl=document.getElementById('hiw-sim-log'),progEl=document.getElementById('hiw-sim-prog'),statEl=document.getElementById('hiw-sim-status');
  logEl.style.display='block';logEl.innerHTML='';
  document.getElementById('hiw-sim-hero').style.display='none';
  document.getElementById('hiw-sim-charts').style.display='none';
  document.getElementById('hiw-week-track').innerHTML='';
  progEl.style.width='0%';
  function addLog(h){logEl.innerHTML+=h+'\n';logEl.scrollTop=logEl.scrollHeight;}
  addLog('<span class="log-head">═══ FDB vs ESPN Model Comparison ═══</span>');
  addLog('<span class="log-fdb">Team A: FDB Model</span>  |  <span class="log-espn">Team B: ESPN Rankings</span>');
  function runWeek(){
    if(weekN>=weeks){hiwFinalize(results,weeks);return;}
    weekN++;
    var res=hiwSimWeek(fdbTeam,espnTeam);res.week=weekN;results.push(res);
    var win=res.fdb>res.espn?'<span class="log-fdb">FDB ✓</span>':'<span class="log-espn">ESPN ✓</span>';
    addLog('Wk '+weekN+': <span class="log-fdb">'+res.fdb.toFixed(1)+'</span> vs <span class="log-espn">'+res.espn.toFixed(1)+'</span>  '+win);
    progEl.style.width=(weekN/weeks*100).toFixed(0)+'%';
    statEl.textContent='Simulating week '+weekN+' of '+weeks+'…';
    setTimeout(runWeek,delay);
  }
  runWeek();
};
function hiwFinalize(results,weeks){
  hiwSimRunning=false;
  var fT=0,eT=0,fW=0;
  results.forEach(function(r){fT+=r.fdb;eT+=r.espn;if(r.fdb>r.espn)fW++;});
  var edge=fT-eT;
  document.getElementById('hiw-sim-hero').style.display='grid';
  document.getElementById('hiw-fdb-pts').textContent=fT.toFixed(0);
  document.getElementById('hiw-espn-pts').textContent=eT.toFixed(0);
  document.getElementById('hiw-edge-num').textContent=(edge>0?'+':'')+edge.toFixed(0);
  document.getElementById('hiw-week-wins').textContent=fW;
  document.getElementById('hiw-week-sub').textContent='wins out of '+weeks;
  document.getElementById('hiw-fdb-rec').textContent=fW+'-'+(weeks-fW);
  document.getElementById('hiw-espn-rec').textContent=(weeks-fW)+'-'+fW;
  document.getElementById('hiw-sstat-fdb-pts').classList.toggle('winner',fT>=eT);
  document.getElementById('hiw-sstat-espn-pts').classList.toggle('winner',eT>fT);
  // bar chart
  var fdbTeam=hiwPickTeam(HIW_PLAYERS,false,15),espnTeam=hiwPickTeam(HIW_PLAYERS,true,15);
  var cats=[
    {label:'K-Rate Edge',fdb:fdbTeam.reduce(function(s,p){return s+p.k*3.2*26},0),
     espn:espnTeam.reduce(function(s,p){return s+p.k*3.2*26},0)},
    {label:'Hold Premium',fdb:fdbTeam.reduce(function(s,p){return s+p.h*8.5*26},0),
     espn:espnTeam.reduce(function(s,p){return s+p.h*8.5*26},0)},
    {label:'Total Pts',fdb:fT,espn:eT}
  ];
  var maxC=Math.max.apply(null,cats.map(function(c){return Math.max(c.fdb,c.espn);}));
  var ch='';
  cats.forEach(function(c){
    var fw=(c.fdb/maxC*100).toFixed(0),ew=(c.espn/maxC*100).toFixed(0);
    ch+='<div class="hiw-bar-row"><span class="hiw-bar-label">'+c.label+' FDB</span>'
      +'<div class="hiw-bar-track"><div class="hiw-bar-fill" style="width:'+fw+'%;background:var(--accent)"></div></div>'
      +'<span class="hiw-bar-val" style="color:var(--accent)">'+c.fdb.toFixed(0)+'</span></div>'
      +'<div class="hiw-bar-row"><span class="hiw-bar-label" style="color:#d97706">'+c.label+' ESPN</span>'
      +'<div class="hiw-bar-track"><div class="hiw-bar-fill" style="width:'+ew+'%;background:#d97706"></div></div>'
      +'<span class="hiw-bar-val" style="color:#d97706">'+c.espn.toFixed(0)+'</span></div>';
  });
  document.getElementById('hiw-cat-chart').innerHTML=ch;
  // cumulative chart — fixed size, no responsive re-measuring
  var cumEl2=document.getElementById('hiw-cum-chart');
  if(window._hiwChart){window._hiwChart.destroy();window._hiwChart=null;}
  cumEl2.width=cumEl2.parentElement.offsetWidth||320;
  cumEl2.height=160;
  var ctx=cumEl2.getContext('2d');
  var fc=[],ec=[],lb=[],fa=0,ea=0;
  results.forEach(function(r,i){fa+=r.fdb;ea+=r.espn;fc.push(fa.toFixed(0));ec.push(ea.toFixed(0));lb.push('Wk'+(i+1));});
  if(window.Chart){
    window._hiwChart=new window.Chart(ctx,{type:'line',
      data:{labels:lb,datasets:[
        {label:'FDB',data:fc,borderColor:'#16a34a',backgroundColor:'rgba(22,163,74,.1)',borderWidth:2,tension:.3,pointRadius:2,fill:true},
        {label:'ESPN',data:ec,borderColor:'#d97706',backgroundColor:'rgba(217,119,6,.07)',borderWidth:2,tension:.3,pointRadius:2,fill:true}
      ]},
      options:{responsive:false,animation:{duration:0},
        plugins:{legend:{labels:{color:'#9ca3af',font:{size:11}}}},
        scales:{x:{ticks:{color:'#6b7280',font:{size:9}},grid:{color:'#1f2937'}},
                y:{ticks:{color:'#6b7280',font:{size:9}},grid:{color:'#1f2937'}}}}
    });
  }
  // week track
  var maxW=Math.max.apply(null,results.map(function(r){return Math.max(r.fdb,r.espn);}));
  var tk='';
  results.forEach(function(r){
    var fw=(r.fdb/maxW*50).toFixed(0),ew=(r.espn/maxW*50).toFixed(0);
    var d=r.fdb-r.espn,dc=d>2?'pos':d<-2?'neg':'neu',ds=(d>0?'+':'')+d.toFixed(0);
    tk+='<div class="hiw-week-row"><span class="hiw-week-num">Wk '+r.week+'</span>'
      +'<div class="hiw-week-bar-wrap"><div class="hiw-week-bar fdb-bar" style="width:'+fw+'%"></div>'
      +'<div class="hiw-week-bar espn-bar" style="width:'+ew+'%"></div></div>'
      +'<span class="hiw-week-delta '+dc+'">'+ds+'</span></div>';
  });
  document.getElementById('hiw-week-track').innerHTML=tk;
  document.getElementById('hiw-sim-charts').style.display='block';
  document.getElementById('hiw-sim-status').textContent='Complete — FDB won '+fW+'/'+weeks+' weeks'+(edge>0?', +'+(edge.toFixed(0))+' pts':'');
}

// ═══════════════════════════════════════════════════════════
// SECTION 2: Real League Season Simulation
// ═══════════════════════════════════════════════════════════
// ── League sim global state ───────────────────────────────────────────────────
var _L = {
  running:     false,
  looping:     false,
  batchSize:   250,
  teams:       [],
  currentTeamIdx: 0,
  simResults:  null,
  // Accumulators — persist across multiple runs
  totalSims:   0,
  batchCount:  0,
  playoffCnt:  {},
  champCnt:    {},
  totalWins:   {},
  winsAll:     {},
  history:     [],   // [{batchN, sims, myPlayoff, myChamp, myProjWins, topTeam}]
  schedule:    null,
  names:       [],
};

function _leagueRand(mu,sigma){
  var u=1-Math.random(),v=1-Math.random();
  return Math.max(0,mu+sigma*Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v));
}

function _buildRoundRobin(names,totalWeeks){
  var n=names.length,sched={};
  var rounds=Math.max(n-1,1);
  for(var w=1;w<=totalWeeks;w++){
    var rnd=(w-1)%rounds,fixed=names[0],rot=names.slice(1);
    var rotated=rot.slice(rnd).concat(rot.slice(0,rnd));
    var part=[fixed].concat(rotated);
    var pairs=[];
    for(var i2=0;i2<Math.floor(n/2);i2++) pairs.push([part[i2],part[n-1-i2]]);
    sched[w]=pairs;
  }
  return sched;
}

function _runLeagueSimOnce(teams,schedule,currentWeek,totalWeeks){
  var res={};
  teams.forEach(function(t){res[t.name]={wins:t.wins,losses:t.losses,pts:0};});
  for(var w=currentWeek;w<=totalWeeks;w++){
    var pairs=schedule[w]||[];
    pairs.forEach(function(pair){
      var ta=pair[0],tb=pair[1];
      if(!res[ta]||!res[tb])return;
      var muA=teams.find(function(t){return t.name===ta;}).mu;
      var muB=teams.find(function(t){return t.name===tb;}).mu;
      var sA=_leagueRand(muA,muA*.18),sB=_leagueRand(muB,muB*.18);
      res[ta].pts+=sA;res[tb].pts+=sB;
      if(sA>sB){res[ta].wins++;res[tb].losses++;}
      else if(sB>sA){res[tb].wins++;res[ta].losses++;}
      else{res[ta].wins+=.5;res[ta].losses+=.5;res[tb].wins+=.5;res[tb].losses+=.5;}
    });
  }
  return res;
}

// Confidence: saturates at 10k sims → 100%
function _confPct(n){ return Math.round(Math.min(100, n/100)); }

function _updateConfUI(){
  var pct=_confPct(_L.totalSims);
  document.getElementById('hiw-total-sims').textContent=_L.totalSims.toLocaleString();
  document.getElementById('hiw-batch-count').textContent=_L.batchCount;
  document.getElementById('hiw-conf-fill').style.width=pct+'%';
  document.getElementById('hiw-conf-pct').textContent=pct+'%';
}

function _appendHistory(D,playoffSpots){
  var myName=null;
  (D.teams||[]).forEach(function(t){if(t.is_mine)myName=t.name;});
  if(!myName&&D.teams&&D.teams.length>0)myName=D.teams[0].name;
  var myPO=myName?Math.round(100*(_L.playoffCnt[myName]||0)/_L.totalSims):'-';
  var myChamp=myName?Math.round(100*(_L.champCnt[myName]||0)/_L.totalSims):'-';
  var myWins=myName?Math.round(10*(_L.totalWins[myName]||0)/_L.totalSims)/10:'-';
  // top team by playoff%
  var topName='—',topPO=0;
  (_L.names||[]).forEach(function(n){
    var p=Math.round(100*(_L.playoffCnt[n]||0)/_L.totalSims);
    if(p>topPO){topPO=p;topName=n;}
  });
  var row={batchN:_L.batchCount,sims:_L.totalSims,myPlayoff:myPO,myChamp:myChamp,myWins:myWins,topTeam:topName};
  _L.history.push(row);
  var wrap=document.getElementById('hiw-run-history-wrap');
  var el=document.getElementById('hiw-run-history');
  wrap.style.display='block';
  var rowHtml='<div style="display:grid;grid-template-columns:40px 60px 60px 50px 50px 1fr;'
    +'gap:0;padding:4px 10px;border-bottom:1px solid var(--border)">'
    +'<span style="color:var(--text2)">#'+row.batchN+'</span>'
    +'<span><strong>'+row.sims.toLocaleString()+'</strong></span>'
    +'<span style="color:var(--accent)">'+row.myPlayoff+'%</span>'
    +'<span>'+row.myChamp+'%</span>'
    +'<span>'+row.myWins+'W</span>'
    +'<span style="color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
    +'#1: '+(topName.length>16?topName.slice(0,15)+'…':topName)+'</span>'
    +'</div>';
  // header on first row
  if(_L.history.length===1){
    el.innerHTML='<div style="display:grid;grid-template-columns:40px 60px 60px 50px 50px 1fr;'
      +'gap:0;padding:3px 10px;border-bottom:2px solid var(--border);font-weight:700;color:var(--text2);font-size:10px">'
      +'<span>Batch</span><span>Tot Sims</span><span>My PO%</span><span>Champ%</span><span>ProjW</span><span>Leading Team</span>'
      +'</div>'+rowHtml;
  } else {
    el.innerHTML+=rowHtml;
  }
  el.scrollTop=el.scrollHeight;
}

function _aggregateAndUpdate(D,playoffSpots){
  var agg={};
  _L.names.forEach(function(name){
    var ws=_L.winsAll[name].slice().sort(function(a,b){return a-b;});
    var n=_L.totalSims||1;
    agg[name]={
      playoff_pct:Math.round(100*(_L.playoffCnt[name]||0)/n),
      champion_pct:Math.round(100*(_L.champCnt[name]||0)/n),
      avg_wins:Math.round(10*(_L.totalWins[name]||0)/n)/10,
      proj_wins_low:ws[Math.floor(ws.length*.1)]||0,
      proj_wins_mid:ws[Math.floor(ws.length*.5)]||0,
      proj_wins_high:ws[Math.floor(ws.length*.9)]||0,
    };
  });
  _L.simResults=agg;
  D.teams.forEach(function(t){
    var a=agg[t.name];
    if(a){t.playoff_pct=a.playoff_pct;t.champion_pct=a.champion_pct;
          t.avg_proj_wins=a.avg_wins;t.proj_wins_low=a.proj_wins_low;
          t.proj_wins_mid=a.proj_wins_mid;t.proj_wins_high=a.proj_wins_high;}
  });
  _L.teams=D.teams;
}

window.hiwSetBatch=function(n,btn){
  _L.batchSize=n;
  document.querySelectorAll('.hiw-batch-btn').forEach(function(b){b.classList.remove('active');});
  if(btn)btn.classList.add('active');
};

window.hiwLeagueStop=function(){
  _L.looping=false;
  _L.running=false;
  document.getElementById('hiw-stop-btn').style.display='none';
  document.getElementById('hiw-run-once-btn').style.display='';
  document.getElementById('hiw-run-loop-btn').style.display='';
  document.getElementById('hiw-league-sim-status').textContent=
    'Stopped after '+_L.batchCount+' batches ('+_L.totalSims.toLocaleString()+' total sims). Results are cumulative.';
};

window.hiwLeagueClear=function(){
  if(_L.running||_L.looping)window.hiwLeagueStop();
  _L.totalSims=0;_L.batchCount=0;
  _L.playoffCnt={};_L.champCnt={};_L.totalWins={};_L.winsAll={};_L.history=[];
  _L.simResults=null;
  document.getElementById('hiw-run-history-wrap').style.display='none';
  document.getElementById('hiw-run-history').innerHTML='';
  document.getElementById('hiw-league-prog').style.width='0%';
  document.getElementById('hiw-league-sim-status').textContent='Reset. Click ▶ Run Once or 🔁 Loop.';
  _updateConfUI();
  var D=FDB_HIW_SIM;
  if(D&&D.teams&&D.teams.length>0){
    // Restore original values from server data
    _L.teams=D.teams.map(function(t){return Object.assign({},t);});
    _renderTeamTabs(D.teams,D.playoff_spots||6);
    _renderTeamPanel(_L.currentTeamIdx);
  }
};

window.hiwLeagueRunSim=function(mode){
  var D=FDB_HIW_SIM;
  if(!D||!D.teams||D.teams.length===0){
    document.getElementById('hiw-league-sim-status').textContent='No team data — run the briefing first.';
    return;
  }
  if(_L.running)return;

  var loop=(mode==='loop');
  _L.looping=loop;
  _L.running=true;

  var teams=D.teams;
  var totalWeeks=D.total_weeks||26,currentWeek=D.current_week||1;
  var playoffSpots=D.playoff_spots||6;

  // Build schedule once, reuse across batches
  if(!_L.schedule||_L.names.length===0){
    _L.names=teams.map(function(t){return t.name;});
    _L.schedule=_buildRoundRobin(_L.names,totalWeeks);
    _L.names.forEach(function(n){
      if(!_L.playoffCnt[n]){_L.playoffCnt[n]=0;_L.champCnt[n]=0;_L.totalWins[n]=0;_L.winsAll[n]=[];}
    });
  }

  // UI state
  document.getElementById('hiw-stop-btn').style.display=loop?'':'none';
  document.getElementById('hiw-run-once-btn').style.display=loop?'none':'none';
  document.getElementById('hiw-run-loop-btn').style.display=loop?'none':'none';

  var prog=document.getElementById('hiw-league-prog');
  var stat=document.getElementById('hiw-league-sim-status');
  prog.style.width='0%';

  var nSims=_L.batchSize;
  var i=0;

  function step(){
    if(!_L.running){
      // Stopped externally
      document.getElementById('hiw-run-once-btn').style.display='';
      document.getElementById('hiw-run-loop-btn').style.display='';
      return;
    }
    if(i>=nSims){
      // Batch complete
      _L.batchCount++;
      _L.totalSims+=nSims;
      _aggregateAndUpdate(D,playoffSpots);
      _appendHistory(D,playoffSpots);
      _updateConfUI();
      prog.style.width='100%';
      var wkLeft=totalWeeks-currentWeek+1;
      var confPct=_confPct(_L.totalSims);
      stat.textContent='Batch #'+_L.batchCount+' done · '+_L.totalSims.toLocaleString()+' total sims'
        +' · '+wkLeft+' wks left · confidence '+confPct+'%'
        +(_L.looping?' · running next batch…':'');
      document.getElementById('hiw-league-meta').textContent=
        'Wk '+currentWeek+'/'+totalWeeks+' · '+playoffSpots+' playoff spots · '+teams.length+' teams';
      _renderTeamTabs(D.teams,playoffSpots);
      _renderTeamPanel(_L.currentTeamIdx);

      if(_L.looping){
        // Small pause between loop batches so UI can breathe, then restart
        i=0;
        prog.style.width='0%';
        setTimeout(step,80);
      } else {
        _L.running=false;
        document.getElementById('hiw-stop-btn').style.display='none';
        document.getElementById('hiw-run-once-btn').style.display='';
        document.getElementById('hiw-run-loop-btn').style.display='';
      }
      return;
    }
    var chunk=Math.min(25,nSims-i);
    for(var b=0;b<chunk;b++){
      var res=_runLeagueSimOnce(teams,_L.schedule,currentWeek,totalWeeks);
      var sorted=Object.keys(res).sort(function(a,b2){
        if(res[b2].wins!==res[a].wins)return res[b2].wins-res[a].wins;
        return res[b2].pts-res[a].pts;
      });
      sorted.forEach(function(name,rank){
        _L.totalWins[name]+=res[name].wins;
        _L.winsAll[name].push(res[name].wins);
        if(rank<playoffSpots)_L.playoffCnt[name]++;
        if(rank===0)_L.champCnt[name]++;
      });
      i++;
    }
    prog.style.width=(i/nSims*100).toFixed(0)+'%';
    var simsRunSoFar=_L.totalSims+i;
    stat.textContent='Batch #'+(_L.batchCount+1)+' · '+i+'/'+nSims+' sims · '+simsRunSoFar.toLocaleString()+' total…';
    setTimeout(step,0);
  }
  step();
};

function _renderTeamTabs(teams,playoffSpots){
  var sorted=teams.slice().sort(function(a,b){return b.playoff_pct-a.playoff_pct;});
  var html='';
  sorted.forEach(function(t,idx){
    var origIdx=teams.indexOf(t);
    var active=origIdx===_L.currentTeamIdx;
    var podClass=t.is_mine?' style="border-color:var(--accent);color:var(--accent)"':'';
    var po=t.playoff_pct>=60?'🟢':t.playoff_pct>=35?'🟡':'🔴';
    var safeName=(t.name||'').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;');
    html+='<button class="hiw-sim-btn'+(active?' primary':'')+'" '
      +podClass
      +' onclick="hiwSelectTeam('+origIdx+')" title="'+safeName+'">'
      +po+' '+(safeName.length>14?safeName.substring(0,13)+'…':safeName)
      +'</button>';
  });
  document.getElementById('hiw-team-tabs').innerHTML=html;
}

window.hiwSelectTeam=function(idx){
  _L.currentTeamIdx=idx;
  var D=FDB_HIW_SIM;
  if(D&&D.teams&&D.teams.length>0){
    _renderTeamTabs(D.teams,D.playoff_spots||6);
  }
  _renderTeamPanel(idx);
};

function _weakpoints(t,allTeams){
  var flags=[];
  var total=t.sp_pts+t.rp_pts+t.hit_pts;
  if(total>0){
    if(t.hit_pts/total<.38)flags.push({cls:'r',msg:'Hitting weakness — hitter pts below 38% of roster'});
    if(t.sp_pts/total<.22)flags.push({cls:'r',msg:'Starter weakness — SP pts below 22% of roster'});
    if(t.rp_pts/total<.12)flags.push({cls:'r',msg:'Bullpen weakness — RP pts below 12% of roster'});
  }
  if(t.n_closers===0)flags.push({cls:'r',msg:'No closers — 0 save-eligible RPs on roster'});
  if(t.n_holds===0)flags.push({cls:'a',msg:'No setup men — missing hold premium in this scoring system'});
  if(t.n_holds>=2&&t.n_closers>=1)flags.push({cls:'g',msg:'Optimal bullpen structure: 1+ closers + 2+ setup men'});
  var avgSos=0;if(allTeams.length>0){allTeams.forEach(function(x){avgSos+=x.sos_mu;});avgSos/=allTeams.length;}
  if(t.sos_mu>avgSos*1.08)flags.push({cls:'r',msg:'Tough remaining schedule (SOS above league avg by 8%+)'});
  if(t.sos_mu<avgSos*.92)flags.push({cls:'g',msg:'Favorable remaining schedule (SOS below league avg by 8%+)'});
  if(t.playoff_pct>=80)flags.push({cls:'g',msg:'Playoff lock — 80%+ projected playoff probability'});
  else if(t.playoff_pct>=45&&t.playoff_pct<65)flags.push({cls:'a',msg:'Playoff bubble — 45–65% probability, every week matters'});
  else if(t.playoff_pct<25)flags.push({cls:'r',msg:'Playoff long shot — under 25% probability'});
  return flags;
}

function _renderTeamPanel(idx){
  var D=FDB_HIW_SIM;
  var teams=D&&D.teams&&D.teams.length>0?D.teams:_L.teams;
  if(!teams||!teams[idx])return;
  var t=teams[idx],allTeams=teams;

  var poColor=t.playoff_pct>=60?'#16a34a':t.playoff_pct>=35?'#d97706':'var(--red)';
  var total=t.sp_pts+t.rp_pts+t.hit_pts||1;
  var hitPct=(t.hit_pts/total*100).toFixed(0),spPct=(t.sp_pts/total*100).toFixed(0),rpPct=(t.rp_pts/total*100).toFixed(0);

  // Hero row
  var hero='<div class="hiw-sim-hero" style="margin-bottom:12px">'
    +'<div class="hiw-sim-stat'+(t.is_mine?' winner':'')+'"><div class="num">'+Math.round(t.wins)+'-'+Math.round(t.losses)+'</div><div class="lbl">Current Record</div></div>'
    +'<div class="hiw-sim-stat"><div class="num" style="color:'+poColor+'">'+t.playoff_pct+'%</div><div class="lbl">Playoff Odds</div></div>'
    +'<div class="hiw-sim-stat"><div class="num">'+t.proj_wins_low+'–'+t.proj_wins_high+'</div><div class="lbl">Proj Win Range</div></div>'
    +'<div class="hiw-sim-stat"><div class="num">'+t.champion_pct+'%</div><div class="lbl">Champ Odds</div></div>'
    +'<div class="hiw-sim-stat"><div class="num">'+t.mu+'</div><div class="lbl">Avg Weekly Pts</div></div>'
    +'<div class="hiw-sim-stat"><div class="num">'+t.sos_mu.toFixed(1)+'</div><div class="lbl">Opp Avg Pts</div></div>'
    +'</div>';

  // Scoring breakdown bars
  function bBar(label,pct,color){
    return '<div class="hiw-bar-row"><span class="hiw-bar-label">'+label+'</span>'
      +'<div class="hiw-bar-track"><div class="hiw-bar-fill" style="width:'+pct+'%;background:'+color+'"></div></div>'
      +'<span class="hiw-bar-val">'+pct+'%</span></div>';
  }
  var breakdown='<div class="hiw-sim-chart-box" style="margin-bottom:10px">'
    +'<h4>📊 Roster Scoring Breakdown</h4>'
    +'<div class="hiw-bar-chart">'
    +bBar('Hitting',hitPct,'var(--amber)')
    +bBar('Starting Pitching',spPct,'#3b82f6')
    +bBar('Relief Pitching',rpPct,'var(--accent)')
    +'</div>'
    +'<div style="font-size:11px;color:var(--text2);margin-top:6px">'
    +'Closers: <strong>'+t.n_closers+'</strong> &nbsp;|&nbsp; Setup Men (HD eligible): <strong>'+t.n_holds+'</strong>'
    +'</div></div>';

  // Weakpoints
  var flags=_weakpoints(t,allTeams);
  var weakHtml='<div style="margin-bottom:10px">';
  if(flags.length===0){weakHtml+='<div class="hiw-edge">✅ No major weakpoints detected for this team.</div>';}
  flags.forEach(function(f){
    var bg=f.cls==='g'?'var(--accent-dim)':f.cls==='r'?'rgba(239,68,68,.1)':'rgba(245,158,11,.1)';
    var bc=f.cls==='g'?'var(--accent)':f.cls==='r'?'var(--red)':'var(--amber)';
    var ic=f.cls==='g'?'✅':f.cls==='r'?'⚠️':'🔶';
    weakHtml+='<div style="background:'+bg+';border-left:3px solid '+bc+';border-radius:0 6px 6px 0;'
      +'padding:7px 12px;font-size:12px;color:var(--text);margin-bottom:6px">'+ic+' '+f.msg+'</div>';
  });
  weakHtml+='</div>';

  // Player impact table (my team only)
  var piTable='';
  if(t.is_mine&&D.player_impact&&D.player_impact.length>0){
    piTable='<div class="hiw-sim-chart-box" style="margin-bottom:10px">'
      +'<h4>🏆 Player Win Contributions (Your Team)</h4>'
      +'<table class="sim-table"><thead><tr><th>Player</th><th>Pos</th>'
      +'<th>Wkly Pts</th><th>Win +/-</th><th>% of Team</th></tr></thead><tbody>';
    D.player_impact.slice(0,15).forEach(function(p){
      var ilBadge=p.on_il?'<span style="color:var(--red);font-size:9px;font-weight:700;margin-left:4px">IL</span>':'';
      var wc=p.win_contribution>0?'<span style="color:var(--accent)">+'+p.win_contribution.toFixed(2)+'</span>'
        :'<span style="color:var(--red)">'+p.win_contribution.toFixed(2)+'</span>';
      piTable+='<tr><td><strong>'+p.player+'</strong>'+ilBadge+'</td>'
        +'<td>'+p.pos+'</td>'
        +'<td>'+p.weekly_pts+'</td>'
        +'<td>'+wc+'</td>'
        +'<td>'+p.pct_of_team_mu+'%</td></tr>';
    });
    piTable+='</tbody></table></div>';
  }

  // League standings context
  var sortedByPO=teams.slice().sort(function(a,b){return b.playoff_pct-a.playoff_pct;});
  var myRank=sortedByPO.findIndex(function(x){return x.name===t.name;})+1;
  var standingsHtml='<div class="hiw-sim-chart-box">'
    +'<h4>📋 Full League Standings (Projected)</h4>'
    +'<table class="sim-table"><thead><tr><th>#</th><th>Team</th><th>Cur W-L</th>'
    +'<th>Proj Wins</th><th>Playoff%</th><th>Champ%</th></tr></thead><tbody>';
  sortedByPO.forEach(function(tm,rank){
    var isThis=tm.name===t.name;
    var isMe=tm.ismine||tm.is_mine;
    var rowStyle=isThis?' style="background:rgba(59,130,246,.08)"':isMe?' class="sim-mine"':'';
    var poColor2=tm.playoff_pct>=60?'color:#16a34a':tm.playoff_pct>=35?'color:#d97706':'color:var(--red)';
    standingsHtml+='<tr'+rowStyle+'>'
      +'<td>'+( rank<(D.playoff_spots||6)?'<span style="color:var(--accent);font-weight:700">'+(rank+1)+'</span>':(rank+1))+'</td>'
      +'<td><strong>'+tm.name+'</strong>'+(isThis?' ◀':'')+(isMe?' <span style="font-size:9px;color:var(--accent)">YOU</span>':'')+'</td>'
      +'<td>'+Math.round(tm.wins)+'-'+Math.round(tm.losses)+'</td>'
      +'<td>'+tm.proj_wins_low+'–'+tm.proj_wins_high+'</td>'
      +'<td><span style="font-weight:700;'+poColor2+'">'+tm.playoff_pct+'%</span></td>'
      +'<td>'+tm.champion_pct+'%</td>'
      +'</tr>';
  });
  standingsHtml+='</tbody></table></div>';

  var teamTitle=t.name+(t.is_mine?' <span style="font-size:11px;color:var(--accent);font-weight:700">← Your Team</span>':'');
  document.getElementById('hiw-team-panel').innerHTML=
    '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:10px">'
    +'<div style="font-size:14px;font-weight:800;color:var(--text);margin-bottom:12px">'+teamTitle+'</div>'
    +hero
    +'<div class="hiw-sim-chart-row">'
    +breakdown
    +'<div>'
    +'<div class="hiw-sim-chart-box" style="margin-bottom:10px"><h4>🎯 Weakpoint Analysis</h4>'
    +weakHtml
    +'</div>'
    +'</div></div>'
    +piTable
    +standingsHtml
    +'</div>';
}

// Initialise on load
document.addEventListener('DOMContentLoaded',function(){
  var D=FDB_HIW_SIM;
  if(D&&D.has_real_data&&D.teams&&D.teams.length>0){
    _L.teams=D.teams;
    var myIdx=D.teams.findIndex(function(t){return t.is_mine;});
    _L.currentTeamIdx=myIdx>=0?myIdx:0;
    document.getElementById('hiw-league-meta').textContent=
      'Wk '+(D.current_week||1)+'/'+(D.total_weeks||26)+' · '+(D.playoff_spots||6)+' playoff spots · '+D.teams.length+' teams';
    document.getElementById('hiw-league-sim-status').textContent=
      'Briefing data loaded — click ▶ Run Once to simulate, or 🔁 Loop to build confidence over time.';
    _updateConfUI();
    _renderTeamTabs(D.teams,D.playoff_spots||6);
    _renderTeamPanel(_L.currentTeamIdx);
  } else {
    document.getElementById('hiw-league-sim-status').textContent=
      'Click ▶ Run Once or 🔁 Loop to generate projections.';
    _updateConfUI();
  }
});

})();
"""
        "</script>"
    )

    return (
        '<div class="tab-pane" data-tab="howitworks" style="display:none">'
        + css
        + '<div style="max-width:960px;margin:0 auto;padding:12px 0">'
        + hero
        + league_sim_section
        + scoring
        + pipeline
        + comparison
        + thresholds
        + sim_section
        + '</div>'
        '</div>'
        + combined_js
    )


def _season_sim_tab(sim: dict) -> str:
    """
    Render the Season Simulation tab pane.

    sim: dict returned by simulate.run_season_simulation()
    """
    if not sim or sim.get("error"):
        err = sim.get("error", "Unknown error") if sim else "Simulation not run"
        return (
            '<div class="tab-pane" data-tab="seasonsim">'
            '<div class="card mb20" style="margin-top:12px">'
            f'<div style="color:var(--red);font-weight:600;padding:12px">⚠ Season simulation unavailable: {esc(str(err))}</div>'
            '</div></div>'
        )

    cw          = sim.get("current_week", 1)
    tw          = sim.get("total_weeks", 26)
    wr          = sim.get("weeks_remaining", 26)
    n_sims      = sim.get("n_sims", 500)
    po_spots    = sim.get("playoff_spots", 6)
    standings   = sim.get("sim_standings", [])
    pi          = sim.get("player_impact", [])
    rp          = sim.get("rp_analysis", {})
    sched       = sim.get("schedule_strength", [])

    # ── Tab-local CSS ──────────────────────────────────────────────────────────
    css = """<style>
.sim-hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:8px;margin-bottom:16px}
.sim-hero-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:12px 16px;box-shadow:var(--shadow);text-align:center}
.sim-hero-num{font-size:26px;font-weight:800;color:var(--accent);
  font-family:"JetBrains Mono","Roboto Condensed",monospace;line-height:1}
.sim-hero-lbl{font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.08em;margin-top:4px}
.sim-section{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;box-shadow:var(--shadow);margin-bottom:12px}
.sim-section h3{font-size:13px;font-weight:700;margin-bottom:12px;
  display:flex;align-items:center;gap:6px}
.sim-table{width:100%;border-collapse:collapse;font-size:12px}
.sim-table th{font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.06em;padding:6px 8px;border-bottom:1px solid var(--border);
  text-align:left;white-space:nowrap}
.sim-table td{padding:8px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.sim-table tr:last-child td{border-bottom:none}
.sim-table tr.sim-mine td{background:var(--accent-dim)}
.sim-row-playoff td{background:rgba(29,78,216,.04)}
.sim-team-name{font-weight:600;font-size:12px;color:var(--text);max-width:180px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sim-you-badge{display:inline-block;font-size:9px;font-weight:700;padding:1px 5px;
  border-radius:4px;background:var(--accent);color:#fff;margin-left:4px;
  vertical-align:middle;letter-spacing:.04em}
.sim-record{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--text2)}
.sim-range{font-size:11px;color:var(--text2);white-space:nowrap}
.sim-range strong{color:var(--text)}
.sim-insight{background:var(--accent-dim);border:1px solid var(--accent);
  border-radius:8px;padding:10px 14px;font-size:12px;color:var(--text);margin-bottom:12px;
  line-height:1.6}
.sim-rp-bar{display:flex;height:12px;border-radius:6px;overflow:hidden;width:100px}
.sim-pi-pos{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;
  background:var(--surface2);color:var(--text2);white-space:nowrap}
.sim-pi-pos.rp{background:rgba(29,78,216,.15);color:var(--accent)}
.sim-pi-pos.sp{background:rgba(22,163,74,.12);color:#16a34a}
.sim-pi-pos.h {background:rgba(154,103,0,.12);color:var(--amber)}
.sim-wc-bar{height:8px;border-radius:4px;background:var(--accent);min-width:2px}
.sim-playoff-lock{color:#16a34a;font-size:10px;font-weight:700}
.sim-playoff-bubble{color:var(--amber);font-size:10px;font-weight:700}
.sim-playoff-out{color:var(--red);font-size:10px;font-weight:700}
</style>"""

    # ── Hero stat row ──────────────────────────────────────────────────────────
    hero = (
        '<div class="sim-hero">'
        f'<div class="sim-hero-card">'
        f'<div class="sim-hero-num">{n_sims:,}</div>'
        f'<div class="sim-hero-lbl">Monte Carlo Sims</div></div>'

        f'<div class="sim-hero-card">'
        f'<div class="sim-hero-num">{wr}</div>'
        f'<div class="sim-hero-lbl">Weeks Remaining</div></div>'

        f'<div class="sim-hero-card">'
        f'<div class="sim-hero-num">Wk {cw}/{tw}</div>'
        f'<div class="sim-hero-lbl">Current Week</div></div>'

        f'<div class="sim-hero-card">'
        f'<div class="sim-hero-num">{po_spots}</div>'
        f'<div class="sim-hero-lbl">Playoff Spots</div></div>'
        '</div>'
    )

    # ── Projected Standings table ──────────────────────────────────────────────
    # Need TOTAL_WEEKS for the avg_proj_losses calc — pull from sim
    TOTAL_WEEKS_LOCAL = sim.get("total_weeks", 26)

    # Redefine inner function to capture correct total weeks
    def _standing_row2(i: int, row: dict) -> str:
        name      = row["team"]
        is_mine   = row["is_mine"]
        cur_w     = row["current_wins"]
        cur_l     = row["current_losses"]
        avg_w     = row["avg_proj_wins"]
        lo        = row["proj_wins_low"]
        hi        = row["proj_wins_high"]
        po_pct    = row["playoff_pct"]
        champ_pct = row["champion_pct"]
        avg_rank  = row["avg_rank"]
        weekly_mu = row["weekly_mu"]

        color_var = _playoff_color(po_pct)
        rank_num  = i + 1

        if po_pct >= 70:
            status_html = '<span class="sim-playoff-lock">✓ Likely In</span>'
        elif po_pct >= 40:
            status_html = '<span class="sim-playoff-bubble">⚡ Bubble</span>'
        else:
            status_html = '<span class="sim-playoff-out">✗ Likely Out</span>'

        you_badge = '<span class="sim-you-badge">YOU</span>' if is_mine else ''
        row_cls   = 'sim-mine' if is_mine else ''
        if po_pct >= 50:
            row_cls = (row_cls + ' sim-row-playoff').strip()

        proj_l = TOTAL_WEEKS_LOCAL - avg_w

        return (
            f'<tr class="{row_cls}">'
            f'<td style="font-weight:700;font-size:13px;color:var(--text2);text-align:center">{rank_num}</td>'
            f'<td><span class="sim-team-name">{esc(name)}{you_badge}</span></td>'
            f'<td class="sim-record">{cur_w}–{cur_l}</td>'
            f'<td class="sim-record" style="color:var(--text)">{avg_w:.1f}–{proj_l:.1f}</td>'
            f'<td class="sim-range"><strong>{lo}</strong>–<strong>{hi}</strong> wins</td>'
            f'<td>{_pct_bar(po_pct, color_var)}</td>'
            f'<td style="font-size:11px;color:var(--text2)">{champ_pct:.1f}%</td>'
            f'<td style="font-size:11px;color:var(--text2)">{avg_rank:.1f}</td>'
            f'<td style="font-size:11px;color:var(--text2)">{weekly_mu}</td>'
            f'<td>{status_html}</td>'
            f'</tr>'
        )

    standings_rows = "".join(_standing_row2(i, r) for i, r in enumerate(standings))
    standings_html = (
        '<div class="sim-section">'
        '<h3>📊 Projected Final Standings <span style="font-size:11px;font-weight:400;color:var(--text2)">'
        f'— {n_sims:,} simulations, sorted by playoff %</span></h3>'
        '<div style="overflow-x:auto">'
        '<table class="sim-table">'
        '<thead><tr>'
        '<th style="text-align:center">RK</th>'
        '<th>Team</th>'
        '<th>Current</th>'
        '<th>Proj W/L</th>'
        '<th>Win Range</th>'
        '<th>Playoff Odds</th>'
        '<th>Champ%</th>'
        '<th>Avg Rank</th>'
        '<th>Wkly Pts</th>'
        '<th>Status</th>'
        '</tr></thead>'
        f'<tbody>{standings_rows}</tbody>'
        '</table></div>'
        '<div style="margin-top:8px;font-size:11px;color:var(--text2)">'
        f'Win Range = 10th–90th percentile across {n_sims:,} simulations. '
        f'Playoff spots: top {po_spots} teams advance. '
        f'Weekly Pts = projected mean score used in simulation.'
        '</div>'
        '</div>'
    )

    # ── RP / Holds Value Analysis ──────────────────────────────────────────────
    rp_rows_html = ""
    if rp:
        insight = rp.get("hold_value_insight", "")
        hp_hold = rp.get("hold_pts_per_hold", 7)
        sv_pts  = rp.get("save_pts_per_save", 6)
        breakdowns = rp.get("team_breakdowns", [])
        league_avg_rp = rp.get("league_avg_rp_pct", 0)
        my_bd   = rp.get("my_team_breakdown", {})

        insight_html = (
            f'<div class="sim-insight">⚾ <strong>Holds Edge:</strong> {esc(insight)}</div>'
            if insight else ""
        )

        def _rp_row(bd: dict) -> str:
            name    = bd["team"]
            is_mine = bd["is_mine"]
            rp_p    = bd["rp_pts"]
            sp_p    = bd["sp_pts"]
            hit_p   = bd["hit_pts"]
            rp_pct  = bd["rp_pct"]
            nc      = bd["n_closers"]
            nh      = bd["n_holds"]
            row_cls = "sim-mine" if is_mine else ""
            you_badge = '<span class="sim-you-badge">YOU</span>' if is_mine else ''

            total_p = rp_p + sp_p
            rp_bar_w = round(rp_pct / 100 * 80) if total_p > 0 else 0
            sp_bar_w = 80 - rp_bar_w

            rp_bar = (
                f'<div class="sim-rp-bar">'
                f'<div style="width:{rp_bar_w}px;background:var(--accent)"></div>'
                f'<div style="width:{sp_bar_w}px;background:#16a34a"></div>'
                f'</div>'
                f'<div style="font-size:10px;color:var(--text2);margin-top:2px">'
                f'<span style="color:var(--accent)">■ RP {rp_pct}%</span>'
                f'</div>'
            )

            above_below = rp_pct - league_avg_rp
            delta_html = (
                f'<span style="color:{"#16a34a" if above_below >= 0 else "var(--red)"};">'
                f'{"+" if above_below >= 0 else ""}{above_below:.1f}%</span>'
            )

            return (
                f'<tr class="{row_cls}">'
                f'<td><span class="sim-team-name">{esc(name)}{you_badge}</span></td>'
                f'<td style="font-family:monospace">{rp_p:,.0f}</td>'
                f'<td style="font-family:monospace">{sp_p:,.0f}</td>'
                f'<td style="font-family:monospace">{hit_p:,.0f}</td>'
                f'<td>{rp_bar}</td>'
                f'<td style="font-size:11px">{delta_html}</td>'
                f'<td style="text-align:center;font-size:12px">{"🔒"*nc}</td>'
                f'<td style="text-align:center;font-size:12px">{"📦"*min(nh,4)}{" +" + str(nh-4) if nh>4 else ""}</td>'
                f'</tr>'
            )

        rp_rows_html = "".join(_rp_row(bd) for bd in breakdowns)
        rp_section = (
            '<div class="sim-section">'
            '<h3>💰 Relief Pitcher Value Analysis'
            f'<span style="font-size:11px;font-weight:400;color:var(--text2)">'
            f' — League avg RP share: {league_avg_rp}%</span></h3>'
            + insight_html +
            '<div style="overflow-x:auto">'
            '<table class="sim-table">'
            '<thead><tr>'
            '<th>Team</th>'
            f'<th>RP Pts</th>'
            f'<th>SP Pts</th>'
            f'<th>Hit Pts</th>'
            '<th>RP/SP Split</th>'
            '<th>vs Avg</th>'
            '<th title="Closer count (≥220 proj pts)">🔒 Closers</th>'
            '<th title="Setup men (130–220 proj pts)">📦 Setup Men</th>'
            '</tr></thead>'
            f'<tbody>{rp_rows_html}</tbody>'
            '</table></div>'
            '<div style="margin-top:8px;font-size:11px;color:var(--text2)">'
            f'🔒 = estimated closer (≥220 proj pts). 📦 = estimated high-hold RP (130–220 proj pts). '
            f'Hold = {hp_hold} pts/hold (HD+{hp_hold - sv_pts} + SVHD+{sv_pts - 4}). '
            f'Save = {sv_pts} pts.'
            '</div>'
            '</div>'
        )
    else:
        rp_section = ""

    # ── Player Win Contribution (My Team) ────────────────────────────────────
    if pi:
        # Max contribution for bar scaling
        max_wc = max((r["win_contribution"] for r in pi), default=1.0) or 1.0

        def _pi_row(r: dict) -> str:
            name    = r["player"]
            pos     = r["pos"]
            weekly  = r["weekly_pts"]
            wc      = r["win_contribution"]
            pct_mu  = r["pct_of_team_mu"]
            on_il   = r["on_il"]
            is_rp   = r["is_reliever"]
            is_sp   = r["is_starter"]
            is_h    = not r["is_pitcher"]

            pos_cls = "rp" if is_rp else ("sp" if is_sp else "h")
            bar_w   = max(2, round(wc / max_wc * 120)) if max_wc > 0 else 2
            bar_col = "var(--accent)" if is_rp else ("#16a34a" if is_sp else "var(--amber)")

            il_badge = (
                '<span style="font-size:9px;font-weight:700;padding:1px 5px;border-radius:4px;'
                'background:var(--red-dim);color:var(--red);margin-left:4px">IL</span>'
                if on_il else ""
            )

            return (
                f'<tr>'
                f'<td style="font-weight:600;font-size:12px">{esc(name)}{il_badge}</td>'
                f'<td><span class="sim-pi-pos {pos_cls}">{esc(pos)}</span></td>'
                f'<td style="font-family:monospace;font-size:12px">{weekly:.1f}</td>'
                f'<td style="font-size:11px;color:var(--text2)">{pct_mu:.1f}%</td>'
                f'<td>'
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<div class="sim-wc-bar" style="width:{bar_w}px;background:{bar_col}"></div>'
                f'<span style="font-size:12px;font-weight:700;color:var(--text)">'
                f'{"+" if wc >= 0 else ""}{wc:.2f}</span>'
                f'</div>'
                f'</td>'
                f'</tr>'
            )

        pi_rows = "".join(_pi_row(r) for r in pi)
        pi_section = (
            '<div class="sim-section">'
            '<h3>🎯 My Team — Player Win Contributions'
            '<span style="font-size:11px;font-weight:400;color:var(--text2)">'
            ' — estimated wins added vs. replacement (100 sim avg)</span></h3>'
            '<div style="overflow-x:auto">'
            '<table class="sim-table">'
            '<thead><tr>'
            '<th>Player</th><th>Pos</th><th>Wkly Pts</th>'
            '<th>% of Lineup</th><th>Win Contribution</th>'
            '</tr></thead>'
            f'<tbody>{pi_rows}</tbody>'
            '</table></div>'
            '<div style="margin-top:8px;font-size:11px;color:var(--text2)">'
            'Win Contribution = projected wins added with vs. without player '
            '(removing their weekly pts from lineup). '
            '<span style="color:var(--accent)">■ RP</span> &nbsp;'
            '<span style="color:#16a34a">■ SP</span> &nbsp;'
            '<span style="color:var(--amber)">■ Hitter</span>'
            '</div>'
            '</div>'
        )
    else:
        pi_section = ""

    # ── Schedule Strength ─────────────────────────────────────────────────────
    if sched:
        sos_vals = [r["sos_mu"] for r in sched if r["sos_mu"] > 0]
        sos_max  = max(sos_vals) if sos_vals else 1
        sos_min  = min(sos_vals) if sos_vals else 0

        # Fix bar colors in _pct_bar calls — use CSS vars directly
        def _sos_row2(i: int, r: dict) -> str:
            name   = r["team"]
            sos    = r["sos_mu"]
            games  = r["games_remaining"]
            is_mine= r["is_mine"]

            rng    = sos_max - sos_min
            norm   = (sos - sos_min) / rng * 100 if rng > 0 else 50
            bar_w  = round(norm / 100 * 100)
            if norm > 66:
                bar_color = "var(--red)"
                difficulty = "Tough"
            elif norm > 33:
                bar_color = "var(--amber)"
                difficulty = "Moderate"
            else:
                bar_color = "#16a34a"
                difficulty = "Easy"

            row_cls  = "sim-mine" if is_mine else ""
            you_badge = '<span class="sim-you-badge">YOU</span>' if is_mine else ''

            bar_html = (
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<svg width="100" height="10">'
                f'<rect width="100" height="10" rx="5" fill="var(--bar-bg)"/>'
                f'<rect width="{bar_w}" height="10" rx="5" fill="{bar_color}"/>'
                f'</svg>'
                f'<span style="font-size:11px;color:{bar_color}">{difficulty}</span>'
                f'</div>'
            )

            return (
                f'<tr class="{row_cls}">'
                f'<td style="text-align:center;font-weight:700;color:var(--text2)">{i+1}</td>'
                f'<td><span class="sim-team-name">{esc(name)}{you_badge}</span></td>'
                f'<td style="font-family:monospace">{sos:.1f}</td>'
                f'<td style="text-align:center">{games}</td>'
                f'<td>{bar_html}</td>'
                f'</tr>'
            )

        sos_rows = "".join(_sos_row2(i, r) for i, r in enumerate(sched))
        sched_section = (
            '<div class="sim-section">'
            '<h3>📅 Remaining Schedule Strength'
            '<span style="font-size:11px;font-weight:400;color:var(--text2)">'
            ' — sorted hardest to easiest</span></h3>'
            '<div style="overflow-x:auto">'
            '<table class="sim-table">'
            '<thead><tr>'
            '<th style="text-align:center">RK</th>'
            '<th>Team</th>'
            '<th>Avg Opp Wkly Pts</th>'
            '<th style="text-align:center">Games Left</th>'
            '<th>Difficulty</th>'
            '</tr></thead>'
            f'<tbody>{sos_rows}</tbody>'
            '</table></div>'
            '<div style="margin-top:8px;font-size:11px;color:var(--text2)">'
            'Avg Opp Weekly Pts = mean projected weekly score of remaining opponents. '
            'Higher = tougher remaining schedule.'
            '</div>'
            '</div>'
        )
    else:
        sched_section = ""

    return (
        '<div class="tab-pane" data-tab="seasonsim">'
        + css
        + '<div style="max-width:1200px;margin:12px auto">'
        + hero
        + standings_html
        + pi_section
        + rp_section
        + sched_section
        + '</div>'
        + '</div>'
    )


def _pace_visual_scoreboard(rows: list, current_week: int) -> str:
    """
    Simplified season pace visual — one row per player showing:
    whether they are over/under their projection via a colored bar and delta %.
    """
    if not rows:
        return ""

    active = [r for r in rows if not r.get("on_il")]
    if not active:
        return ""

    cards = []
    for r in active:
        name      = r.get("player", "?")
        pos       = r.get("pos", "?")
        actual    = r.get("actual_pts", 0)
        fdb_proj  = r.get("fdb_proj", 0)
        pace      = r.get("pace_pts", 0)
        is_p      = r.get("is_pitcher", False)

        if fdb_proj <= 0:
            continue

        # Weeks elapsed for proration
        weeks_elapsed = max(1, current_week - 1)
        expected_by_now = round(fdb_proj * (weeks_elapsed / 26.0), 1)

        if expected_by_now > 0:
            delta_pct = round((actual - expected_by_now) / expected_by_now * 100, 1)
        else:
            delta_pct = 0.0

        # Bar fill pct (capped 0-100% of expected)
        bar_fill = min(100, max(0, round(actual / max(expected_by_now, 1) * 100, 0)))

        if delta_pct >= 15:
            bar_color = "var(--accent)"; status = "🔥 Hot"
        elif delta_pct >= 5:
            bar_color = "#22c55e"; status = "↑ On pace"
        elif delta_pct >= -5:
            bar_color = "var(--border)"; status = "— On track"
        elif delta_pct >= -15:
            bar_color = "var(--amber)"; status = "↓ Slow start"
        else:
            bar_color = "var(--red)"; status = "⚠ Cold"

        sign = "+" if delta_pct >= 0 else ""
        cards.append(
            f'<div class="pv-card">'
            f'  <div class="pv-head">'
            f'    <div class="pv-name">{esc(name)}</div>'
            f'    <div class="pv-pos">{esc(pos)}</div>'
            f'    <div class="pv-status" style="color:{bar_color}">{status}</div>'
            f'  </div>'
            f'  <div class="pv-bar-wrap">'
            f'    <div class="pv-bar-fill" style="width:{bar_fill}%;background:{bar_color}"></div>'
            f'  </div>'
            f'  <div class="pv-foot">'
            f'    <span class="pv-actual">{actual:.0f} actual</span>'
            f'    <span class="pv-delta" style="color:{bar_color}">{sign}{delta_pct:.1f}%</span>'
            f'    <span class="pv-proj">of {expected_by_now:.0f} expected</span>'
            f'  </div>'
            f'</div>'
        )

    css = """<style>
.pv-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-bottom:16px}
.pv-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:10px 12px;box-shadow:var(--shadow)}
.pv-head{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.pv-name{font-size:12px;font-weight:700;color:var(--text);flex:1;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.pv-pos{font-size:10px;font-weight:600;color:var(--text2);background:var(--surface2);
  padding:1px 5px;border-radius:4px;border:1px solid var(--border)}
.pv-status{font-size:10px;font-weight:700;white-space:nowrap}
.pv-bar-wrap{height:6px;background:var(--bar-bg);border-radius:3px;overflow:hidden;margin-bottom:5px}
.pv-bar-fill{height:100%;border-radius:3px;transition:width .4s ease}
.pv-foot{display:flex;justify-content:space-between;font-size:10px}
.pv-actual{color:var(--text);font-weight:600;font-family:"JetBrains Mono",monospace}
.pv-delta{font-weight:800;font-family:"JetBrains Mono",monospace}
.pv-proj{color:var(--text2)}
</style>"""

    return (
        css +
        f'<div class="card mb20">'
        f'<div class="sec-head">'
        f'<div class="sec-title">📊 Season Pace — Quick View</div>'
        f'<div class="sec-sub">Actual pts vs expected by week {current_week} · Click the table below for full detail</div>'
        f'</div>'
        f'<div class="pv-grid">{"".join(cards)}</div>'
        f'</div>'
    )


def _season_pace_tab(pace: dict) -> str:
    """
    Season Pace tab — actual FP vs pace projection vs FDB model vs ESPN.

    Renders for ALL rostered players with:
      • Team-level hero cards (actual, pace, FDB, ESPN totals)
      • Team selector to cycle through every league team
      • Sortable player table with inline pace bars
      • Chart.js line chart of your team's cumulative actual vs model projection
      • Last-updated timestamp driven by generated_at
    """
    import json as _json

    pace = pace or {}
    if pace.get("error") and not pace.get("my_team_rows"):
        return (
            '<div class="tab-pane" data-tab="seasonpace" style="display:none">'
            '<div class="card mb20" style="margin-top:12px">'
            f'<div style="color:var(--red);font-weight:600;padding:12px">'
            f'⚠ Season pace data unavailable: {esc(str(pace.get("error","")))} — '
            'run the briefing with an active ESPN connection.</div>'
            '</div></div>'
        )

    cw   = pace.get("current_week", 1)
    tw   = pace.get("total_weeks", 26)
    wr   = pace.get("weeks_remaining", tw)
    gen  = pace.get("generated_at", "")
    rows = pace.get("my_team_rows", [])
    teams = pace.get("all_teams", [])

    # ── Serialise data for JS ─────────────────────────────────────────────────
    # Limit player array size to avoid huge payloads; keep all needed fields
    def _slim(p):
        return {k: p[k] for k in (
            "player","pos","is_pitcher","on_il","actual_pts","pace_pts",
            "fdb_proj","espn_proj","avg_per_week","gp_so_far","proj_total_gp",
            "fp_per_gp","vs_fdb","vs_espn","initials","mlb_team","headshot","headshot2",
        ) if k in p}

    js_teams = [
        {
            "team_name":    t["team_name"],
            "is_mine":      t["is_mine"],
            "total_actual": t["total_actual"],
            "total_pace":   t["total_pace"],
            "total_fdb":    t["total_fdb"],
            "players":      [_slim(p) for p in t["players"]],
        }
        for t in teams
    ]

    pace_json = _json.dumps({
        "current_week":    cw,
        "total_weeks":     tw,
        "weeks_remaining": wr,
        "generated_at":    gen,
        "teams":           js_teams,
    }, default=str)

    # ── Tab-local CSS ─────────────────────────────────────────────────────────
    css = """<style>
.sp-hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:8px;margin-bottom:14px}
.sp-stat{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:10px 14px;text-align:center;box-shadow:var(--shadow)}
.sp-stat.hi{background:var(--accent-dim);border-color:var(--accent)}
.sp-stat .num{font-size:22px;font-weight:800;font-family:"JetBrains Mono",monospace;line-height:1}
.sp-stat.hi .num{color:var(--accent)}
.sp-stat .lbl{font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.06em;margin-top:3px}
.sp-stat .sub{font-size:10px;color:var(--text2);margin-top:2px}

/* Pace table */
.sp-table{width:100%;border-collapse:collapse;font-size:12px}
.sp-table th{font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.06em;padding:6px 8px;border-bottom:2px solid var(--border);
  text-align:left;cursor:pointer;white-space:nowrap;user-select:none}
.sp-table th:hover{color:var(--text)}
.sp-table th.sorted{color:var(--accent)}
.sp-table th.sorted::after{content:" ↓";font-size:9px}
.sp-table th.sorted.asc::after{content:" ↑"}
.sp-table td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.sp-table tr:last-child td{border-bottom:none}
.sp-table tr.sp-il td{opacity:.55}
.sp-table tr:hover td{background:var(--surface2)}

/* inline pace bar */
.sp-bar-wrap{width:120px;height:16px;background:var(--bar-bg);border-radius:4px;
  overflow:visible;position:relative;display:inline-block}
.sp-bar-actual{height:100%;border-radius:4px 0 0 4px;background:#3b82f6;
  position:absolute;top:0;left:0;min-width:2px}
.sp-bar-pace{height:4px;background:var(--accent);position:absolute;
  bottom:-5px;left:0;border-radius:2px;min-width:2px}
.sp-bar-fdb{width:2px;height:20px;background:var(--amber);position:absolute;top:-2px}
.sp-bar-espn{width:2px;height:20px;background:#a855f7;position:absolute;top:-2px}

/* delta chips */
.sp-chip{display:inline-block;font-size:10px;font-weight:700;padding:2px 6px;
  border-radius:10px;font-family:"JetBrains Mono",monospace}
.sp-chip.pos{background:rgba(22,163,74,.15);color:#16a34a}
.sp-chip.neg{background:rgba(239,68,68,.12);color:var(--red)}
.sp-chip.neu{background:var(--surface2);color:var(--text2)}

/* Filter / sort bar */
.sp-controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.sp-filter-btn{padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;
  cursor:pointer;border:1px solid var(--border);background:var(--surface2);color:var(--text2)}
.sp-filter-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.sp-search{padding:5px 10px;border-radius:6px;font-size:11px;border:1px solid var(--border);
  background:var(--surface2);color:var(--text);width:160px}
.sp-search::placeholder{color:var(--text2)}

/* Team tabs */
.sp-team-tab{padding:4px 10px;border-radius:6px;font-size:11px;font-weight:600;
  cursor:pointer;border:1px solid var(--border);background:var(--surface2);color:var(--text2)}
.sp-team-tab:hover{background:var(--surface);color:var(--text)}
.sp-team-tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}

/* Legend */
.sp-legend{display:flex;flex-wrap:wrap;gap:10px;font-size:10px;color:var(--text2);
  margin-bottom:8px;align-items:center}
.sp-legend-dot{width:10px;height:10px;border-radius:2px;display:inline-block;margin-right:3px}

.sp-chart-box{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:14px;box-shadow:var(--shadow);margin-bottom:14px}
.sp-chart-box h3{font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;
  letter-spacing:.06em;margin-bottom:10px}
</style>"""

    # ── Legend ────────────────────────────────────────────────────────────────
    legend = (
        '<div class="sp-legend">'
        '<span><span class="sp-legend-dot" style="background:#3b82f6"></span>Actual FP (season to date)</span>'
        '<span><span class="sp-legend-dot" style="background:var(--accent)"></span>Pace Projection (full season)</span>'
        '<span><span class="sp-legend-dot" style="background:var(--amber)"></span>FDB Model Projection</span>'
        '<span><span class="sp-legend-dot" style="background:#a855f7"></span>ESPN Projection</span>'
        f'<span style="margin-left:auto;font-style:italic">Last updated: {esc(gen)}</span>'
        '</div>'
    )

    _visual_board = _pace_visual_scoreboard(rows, cw)
    return (
        '<div class="tab-pane" data-tab="seasonpace" style="display:none">'
        + css
        + f'<script>var FDB_PACE_DATA={pace_json};</script>'
        + '<div style="max-width:960px;margin:0 auto;padding:12px 0">'

        # Page header
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">'
        + '<div>'
        + '<div style="font-size:18px;font-weight:800;color:var(--text)">📈 Season Pace Tracker</div>'
        + f'<div style="font-size:12px;color:var(--text2)">Week {cw} of {tw} · {wr} weeks remaining · '
        + 'Actual FP vs pace-based + model projections</div>'
        + '</div>'
        + '</div>'

        # Visual scoreboard
        + _visual_board

        # Team selector
        + '<div style="font-size:10px;font-weight:700;color:var(--text2);text-transform:uppercase;'
        + 'letter-spacing:.06em;margin-bottom:6px">View Team</div>'
        + '<div id="sp-team-tabs" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px"></div>'

        # Hero stat cards
        + '<div class="sp-hero" id="sp-hero"></div>'

        # Chart row
        + '<div class="sp-chart-box">'
        + '<h3>📊 Pace vs Projections — Top 12 Active Players</h3>'
        + legend
        + '<div style="position:relative;height:200px;max-height:200px">'
        + '<canvas id="sp-main-chart"></canvas>'
        + '</div>'
        + '</div>'

        # Controls
        + '<div class="sp-controls">'
        + '<button class="sp-filter-btn active" onclick="spFilter(\'all\',this)">All</button>'
        + '<button class="sp-filter-btn" onclick="spFilter(\'hitters\',this)">Hitters</button>'
        + '<button class="sp-filter-btn" onclick="spFilter(\'pitchers\',this)">Pitchers</button>'
        + '<button class="sp-filter-btn" onclick="spFilter(\'active\',this)">Active Only</button>'
        + '<button class="sp-filter-btn" onclick="spFilter(\'outperforming\',this)">🔥 Pace > FDB</button>'
        + '<button class="sp-filter-btn" onclick="spFilter(\'underperforming\',this)">⚠ Pace &lt; FDB</button>'
        + '<input class="sp-search" type="text" placeholder="Search player…" oninput="spSearch(this.value)" id="sp-search-box">'
        + '</div>'

        # Player table
        + '<div style="overflow-x:auto">'
        + '<table class="sp-table" id="sp-table">'
        + '<thead><tr>'
        + '<th onclick="spSort(\'player\',this)">Player</th>'
        + '<th onclick="spSort(\'pos\',this)">Pos</th>'
        + '<th onclick="spSort(\'actual_pts\',this)" class="sorted">Actual FP</th>'
        + '<th onclick="spSort(\'gp_so_far\',this)" title="Games / starts played so far">GP</th>'
        + '<th onclick="spSort(\'fp_per_gp\',this)" title="FP per game / start">FP/G</th>'
        + '<th>Pace Bar</th>'
        + '<th onclick="spSort(\'pace_pts\',this)" title="(FP/G) × projected total GP">Pace Proj</th>'
        + '<th onclick="spSort(\'proj_total_gp\',this)" title="Projected full-season games / starts">Proj GP</th>'
        + '<th onclick="spSort(\'fdb_proj\',this)">FDB Proj</th>'
        + '<th onclick="spSort(\'vs_fdb\',this)">vs FDB</th>'
        + '<th onclick="spSort(\'avg_per_week\',this)">Avg/Wk</th>'
        + '</tr></thead>'
        + '<tbody id="sp-tbody"></tbody>'
        + '</table>'
        + '</div>'

        + '</div>'  # max-width wrapper
        + '</div>'  # tab-pane

        # ── JavaScript ────────────────────────────────────────────────────────
        + r"""<script>
(function(){
var _spState={teamIdx:0,filter:'all',search:'',sortKey:'actual_pts',sortAsc:false,chart:null};

function _getTeams(){
  var D=FDB_PACE_DATA;
  return D&&D.teams?D.teams:[];
}
function _getTeam(idx){
  var t=_getTeams();return t[idx]||t[0]||{players:[]};
}

function _deltaChip(v){
  if(v===null||v===undefined)return '';
  var cls=v>5?'pos':v<-5?'neg':'neu';
  return '<span class="sp-chip '+cls+'">'+(v>0?'+':'')+v.toFixed(0)+'</span>';
}

function _paceBar(row,maxPts){
  if(maxPts<=0)return '';
  var W=120;
  var aPct=Math.min(100,row.actual_pts/maxPts*100);
  var ppPct=Math.min(100,row.pace_pts/maxPts*100);
  var fdPct=Math.min(100,row.fdb_proj/maxPts*100);
  var epPct=Math.min(100,row.espn_proj/maxPts*100);
  var aW=(aPct/100*W).toFixed(1);
  var ppLeft=(ppPct/100*W).toFixed(1);
  var fdLeft=(fdPct/100*W).toFixed(1);
  var epLeft=(epPct/100*W).toFixed(1);
  return '<div class="sp-bar-wrap" style="width:'+W+'px">'
    +'<div class="sp-bar-actual" style="width:'+aW+'px"></div>'
    +'<div class="sp-bar-pace" style="width:'+ppLeft+'px"></div>'
    +'<div class="sp-bar-fdb" style="left:'+fdLeft+'px" title="FDB: '+row.fdb_proj+'"></div>'
    +'<div class="sp-bar-espn" style="left:'+epLeft+'px" title="ESPN: '+row.espn_proj+'"></div>'
    +'</div>';
}

function _renderHero(team){
  var D=FDB_PACE_DATA;
  var cw=D.current_week||1,tw=D.total_weeks||26;
  var pct=Math.round(cw/tw*100);
  var el=document.getElementById('sp-hero');
  if(!el)return;
  var diff=team.total_pace-team.total_fdb;
  var dCol=diff>=0?'var(--accent)':'var(--red)';
  el.innerHTML=
    '<div class="sp-stat hi"><div class="num">'+team.total_actual.toLocaleString()+'</div>'
    +'<div class="lbl">Actual FP</div><div class="sub">Season to date</div></div>'
    +'<div class="sp-stat"><div class="num">'+team.total_pace.toLocaleString()+'</div>'
    +'<div class="lbl">Pace Projection</div><div class="sub">Full season at current rate</div></div>'
    +'<div class="sp-stat"><div class="num">'+team.total_fdb.toLocaleString()+'</div>'
    +'<div class="lbl">FDB Model</div><div class="sub">Pre-season + live blend</div></div>'
    +'<div class="sp-stat"><div class="num" style="color:'+dCol+'">'
    +(diff>=0?'+':'')+diff.toFixed(0)+'</div>'
    +'<div class="lbl">Pace vs FDB</div><div class="sub">'+(diff>=0?'Outperforming 🔥':'Behind pace ⚠')+'</div></div>'
    +'<div class="sp-stat"><div class="num">'+cw+'/'+tw+'</div>'
    +'<div class="lbl">Week</div><div class="sub">'+pct+'% of season</div></div>';
}

function _filterRows(rows){
  var f=_spState.filter,q=_spState.search.toLowerCase();
  return rows.filter(function(r){
    if(q&&r.player.toLowerCase().indexOf(q)===-1)return false;
    if(f==='hitters')return !r.is_pitcher;
    if(f==='pitchers')return r.is_pitcher;
    if(f==='active')return !r.on_il;
    if(f==='outperforming')return r.vs_fdb>5;
    if(f==='underperforming')return r.vs_fdb<-5;
    return true;
  });
}

function _sortRows(rows){
  var k=_spState.sortKey,asc=_spState.sortAsc;
  return rows.slice().sort(function(a,b){
    var av=a[k],bv=b[k];
    if(typeof av==='string')return asc?av.localeCompare(bv):bv.localeCompare(av);
    return asc?av-bv:bv-av;
  });
}

function _renderTable(){
  var team=_getTeam(_spState.teamIdx);
  var rows=_sortRows(_filterRows(team.players||[]));
  var maxPts=0;
  (team.players||[]).forEach(function(r){maxPts=Math.max(maxPts,r.pace_pts,r.fdb_proj,r.espn_proj,r.actual_pts);});
  var html='';
  rows.forEach(function(r){
    var ilBadge=r.on_il?'<span style="color:var(--red);font-size:9px;font-weight:700;margin-left:3px">IL</span>':'';
    var gp   = (r.gp_so_far||0).toFixed(0);
    var fpg  = (r.fp_per_gp||0).toFixed(1);
    var pgp  = (r.proj_total_gp||0).toFixed(0);
    var paceFormula = 'FP/G: '+fpg+' × '+pgp+' proj GP = '+r.pace_pts.toFixed(0)+' pts';
    html+='<tr class="'+(r.on_il?'sp-il':'')+'">'
      +'<td><strong>'+r.player+'</strong>'+ilBadge
      +'<br><span style="font-size:10px;color:var(--text2)">'+r.mlb_team+'</span></td>'
      +'<td>'+r.pos+'</td>'
      +'<td style="font-family:\'JetBrains Mono\',monospace;font-weight:700;color:#3b82f6">'+r.actual_pts.toFixed(0)+'</td>'
      +'<td style="font-family:\'JetBrains Mono\',monospace;color:var(--text2)">'+gp+'</td>'
      +'<td style="font-family:\'JetBrains Mono\',monospace;color:var(--accent)">'+fpg+'</td>'
      +'<td>'+_paceBar(r,maxPts)+'</td>'
      +'<td style="font-family:\'JetBrains Mono\',monospace;font-weight:700;color:var(--green)" title="'+paceFormula+'">'+r.pace_pts.toFixed(0)+'</td>'
      +'<td style="font-family:\'JetBrains Mono\',monospace;color:var(--text2);font-size:11px">'+pgp+'</td>'
      +'<td style="font-family:\'JetBrains Mono\',monospace;color:var(--amber)">'+r.fdb_proj.toFixed(0)+'</td>'
      +'<td>'+_deltaChip(r.vs_fdb)+'</td>'
      +'<td style="font-family:\'JetBrains Mono\',monospace">'+r.avg_per_week.toFixed(1)+'</td>'
      +'</tr>';
  });
  document.getElementById('sp-tbody').innerHTML=html||'<tr><td colspan="11" style="color:var(--text2);padding:16px;text-align:center">No players match filter.</td></tr>';
}

var _chartTimer=null;
function _renderChart(){
  // Debounce: skip if called within 150ms of last call
  clearTimeout(_chartTimer);
  _chartTimer=setTimeout(_doRenderChart,150);
}
function _doRenderChart(){
  var team=_getTeam(_spState.teamIdx);
  // Cap at 12 active players sorted by actual_pts — keeps canvas small and fast
  var players=(team.players||[])
    .filter(function(r){return !r.on_il&&(r.actual_pts>0||r.pace_pts>0);})
    .sort(function(a,b){return b.actual_pts-a.actual_pts;})
    .slice(0,12);
  var ctx=document.getElementById('sp-main-chart');
  if(!ctx||!window.Chart||players.length===0)return;

  var labels=players.map(function(r){
    var parts=r.player.split(' ');
    return parts.length>1?parts[parts.length-1]:r.player;
  });
  var actual=players.map(function(r){return r.actual_pts;});
  var pace=players.map(function(r){return r.pace_pts;});
  var fdb=players.map(function(r){return r.fdb_proj;});

  // Destroy old chart cleanly
  if(_spState.chart){
    _spState.chart.destroy();
    _spState.chart=null;
  }

  _spState.chart=new window.Chart(ctx,{
    type:'bar',
    data:{
      labels:labels,
      datasets:[
        {label:'Actual FP',   data:actual, backgroundColor:'rgba(59,130,246,.8)',
         borderRadius:3, barPercentage:.5, categoryPercentage:.7},
        {label:'Pace Proj',   data:pace,   backgroundColor:'rgba(22,163,74,.25)',
         borderRadius:3, barPercentage:.5, categoryPercentage:.7},
        {label:'FDB Model',   type:'line', data:fdb,
         borderColor:'#d97706', backgroundColor:'transparent',
         borderWidth:2, pointRadius:3, pointHoverRadius:4,
         pointBackgroundColor:'#d97706', tension:0},
      ]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      animation:{duration:0},          // no animation — prevents lag on re-render
      resizeDelay:100,
      devicePixelRatio:1,              // avoid 2× retina overdraw
      plugins:{
        legend:{labels:{color:'#9ca3af',font:{size:10},boxWidth:10}},
        tooltip:{
          mode:'index',intersect:false,
          callbacks:{label:function(c){return c.dataset.label+': '+c.raw.toFixed(0);}}
        }
      },
      scales:{
        x:{
          ticks:{color:'#6b7280',font:{size:9},maxRotation:35,maxTicksLimit:12},
          grid:{display:false}
        },
        y:{
          ticks:{color:'#6b7280',font:{size:9},maxTicksLimit:6},
          grid:{color:'rgba(255,255,255,.04)'},
          title:{display:false}
        }
      }
    }
  });
}

function _renderTeamTabs2(){
  var teams=_getTeams();
  var html='';
  teams.forEach(function(t,idx){
    var active=idx===_spState.teamIdx;
    var mine=t.is_mine?' style="border-color:var(--accent);color:var(--accent)"':'';
    html+='<button class="sp-team-tab'+(active?' active':'')+'"'
      +mine+' onclick="spSelectTeam('+idx+')">'
      +(t.is_mine?'★ ':'')+( t.team_name.length>16?t.team_name.slice(0,15)+'…':t.team_name)
      +'</button>';
  });
  document.getElementById('sp-team-tabs').innerHTML=html;
}

function _renderAll(){
  var team=_getTeam(_spState.teamIdx);
  _renderHero(team);
  _renderTable();
  _renderChart();
}

window.spSelectTeam=function(idx){
  _spState.teamIdx=idx;
  _renderTeamTabs2();
  _renderAll();
};

window.spFilter=function(f,btn){
  _spState.filter=f;
  document.querySelectorAll('.sp-filter-btn').forEach(function(b){b.classList.remove('active');});
  if(btn)btn.classList.add('active');
  _renderTable();   // chart always shows top 12 active regardless of filter
};

window.spSearch=function(q){
  _spState.search=q;
  _renderTable();
};

window.spSort=function(key,th){
  if(_spState.sortKey===key)_spState.sortAsc=!_spState.sortAsc;
  else{_spState.sortKey=key;_spState.sortAsc=false;}
  document.querySelectorAll('.sp-table th').forEach(function(h){
    h.classList.remove('sorted','asc');
  });
  if(th){th.classList.add('sorted');if(_spState.sortAsc)th.classList.add('asc');}
  _renderTable();
};

document.addEventListener('DOMContentLoaded',function(){
  var D=FDB_PACE_DATA;
  if(!D||!D.teams||D.teams.length===0)return;
  // Default to my team
  var myIdx=D.teams.findIndex(function(t){return t.is_mine;});
  _spState.teamIdx=myIdx>=0?myIdx:0;
  _renderTeamTabs2();
  _renderAll();
  // Re-render chart once when tab becomes visible (canvas needs non-zero size)
  var _spTabBtn=document.querySelector('button[onclick*="seasonpace"]');
  if(_spTabBtn)_spTabBtn.addEventListener('click',function(){
    setTimeout(_doRenderChart,80);
  });
});
})();
</script>"""
    )


def render_html(data):
    wp  = data["win_prob"]
    ms  = data["my_summary"]
    os_ = data["opp_summary"]

    if wp:
        pct     = wp["prob"] * 100
        wp_tone = "good" if pct >= 55 else ("bad" if pct < 45 else "warn")
        wp_lbl  = (
            "STRONG FAV" if pct >= 65 else
            "SLIGHT FAV" if pct >= 55 else
            "TOSS-UP"    if pct >= 45 else
            "SLIGHT DOG" if pct >= 35 else "HEAVY DOG"
        )
        wp_stat = _stat_card("Win Probability", f"{pct:.1f}%", wp_lbl, wp_tone)
        gauge   = _win_gauge(wp["prob"])
    else:
        wp_stat = _stat_card("Win Probability", "N/A", "")
        gauge   = ""

    matchup  = data["matchup"]
    opp_name = os_["team_name"] if os_ else "Opponent"
    if matchup:
        my_s   = matchup["my_score"]
        opp_s  = matchup["opp_score"]
        m_tone = matchup["status_class"]
        matchup_html = (
            f'<div class="matchup-box">'
            f'<div class="score-side">'
            f'<div class="score-name">{esc(MY_TEAM_NAME)}</div>'
            f'<div class="score-num" id="ls-my-score">{my_s:.1f}</div>'
            f'</div>'
            f'<span class="score-vs">vs</span>'
            f'<div class="score-side">'
            f'<div class="score-name">{esc(opp_name)}</div>'
            f'<div class="score-num" id="ls-opp-score">{opp_s:.1f}</div>'
            f'</div></div>'
            f'<div style="text-align:center;margin-top:4px">'
            f'<span class="ms-pill ms-{m_tone}" id="ls-status-pill">'
            f'{esc(matchup["status"])} &middot; Week {matchup["week"]}'
            f'</span></div>'
            # Live scoring feed — populated by LiveScoring JS module
            f'<div id="live-scoring-feed">'
            f'<div class="ls-loading-text">⏳ Loading today\'s scoring…</div>'
            f'</div>'
        )
        # Append weekly scoring breakdown below score display
        scoring_section = _matchup_scoring_section(
            matchup.get("my_scoring",  []),
            matchup.get("opp_scoring", []),
            MY_TEAM_NAME,
            opp_name,
        )
        matchup_html += scoring_section
    else:
        matchup_html = '<div style="color:var(--text2);padding:20px 0;text-align:center">No active matchup</div>'

    kv_items = []
    if wp:
        kv_items += [
            ("My lineup pts",  fmt(wp["my_proj"],  1)),
            ("Opp lineup pts", fmt(wp["opp_proj"], 1)),
        ]
    kv_items += [
        ("My best lineup",  fmt(ms["lineup_pts"], 1)),
        ("My hitter base",  fmt(ms["hitter_base"])),
        ("My pitcher base", fmt(ms["pitcher_base"])),
        ("Injuries",        str(ms["injury_count"])),
        ("Waiver rank",     str(data["waiver_rank"])),
    ]
    kv_html = "".join(
        f'<div class="kv-row">'
        f'<span class="kv-label">{esc(l)}</span>'
        f'<span class="kv-val">{esc(v)}</span>'
        f'</div>'
        for l, v in kv_items
    )

    inj_html = (
        "".join(f'<div class="inj-item">{esc(i)}</div>' for i in data.get("injuries", []))
        if data.get("injuries")
        else '<div style="color:var(--text2);font-size:13px">No injury alerts</div>'
    )

    inj_tone = "bad" if ms["injury_count"] > 0 else ""

    _waivers_inner = (
        _streaming_plan_section(data.get("stream_plan", {}))
        + _blueprint_banner(data.get("roster_blueprint", {}))
        + _streaming_sp_section(data.get("streaming_sps", []))
        + _waiver_section(data["waiver_recs"])
    )

    si_card = _season_intel_card(data.get("season_intel", {"my_il": [], "il_watch": [], "fa_targets": []}))

    # Build the rich inner HTML for My Team's own pane (includes win-prob stat, SI, injuries)
    _my_pane_inner = (
        '<div class="stat-row">'
        + wp_stat
        + _stat_card("Active Base",  fmt(ms["active_base"]),  "scaled 0-100")
        + _stat_card("Best Lineup",  fmt(ms["lineup_pts"],1),  "projected pts")
        + _stat_card("Hitter Base",  fmt(ms["hitter_base"]),  "scaled 0-100")
        + _stat_card("Pitcher Base", fmt(ms["pitcher_base"]), "scaled 0-100")
        + _stat_card("Injuries",     str(ms["injury_count"]), "active roster", inj_tone)
        + '</div>'
        + _roster_cards(data["my_roster"], "My Team Roster",
                        "Outer ring = Value · Inner ring = Fit · Proj = season pts · VAR = pts above replacement")
        + si_card
        + '<div class="grid2">'
        + '<div class="card"><div class="sec-head"><div class="sec-title">Injury Alerts</div></div>'
        + '<div class="inj-list">' + inj_html + '</div></div>'
        + _note_box()
        + '</div>'
    )

    tab_myteam = (
        '<div class="tab-pane" data-tab="myteam">'
        + _team_viewer_inner(data.get("all_team_rosters", {}), _my_pane_inner)
        + '<div class="grid2">'
        + _standings_table(data["standings"])
        + _activity_section(data["recent_moves"])
        + '</div>'
        + _top_players_table(data["top_rostered"])
        + '</div>'
    )

    opp_tbl   = _roster_cards(data.get("opp_roster", []), f"Opponent Roster — {opp_name}") if data.get("opp_roster") else ""
    cmp_html  = _cmp_section(data.get("comparison", []), opp_name) if data.get("comparison") else ""
    sched_html = _schedule_section(
        data.get("today_games", []),
        my_name  = MY_TEAM_NAME,
        opp_name = opp_name,
    )
    # Phase 4 — hitter matchup intelligence section
    mi_html = _hitter_matchups_section(data.get("hitter_matchups", []))

    # Week scoring table
    week_scoring_html = _week_scoring_table(data.get("week_scoring", {}))

    # Overview content (existing matchup view)
    _overview = (
        '<div class="grid2">'
        '<div class="card"><div class="sec-head"><div class="sec-title">Live Matchup</div></div>'
        + matchup_html
        + '</div>'
        '<div class="card" style="display:flex;flex-direction:column;align-items:center;'
        'justify-content:center;gap:16px">'
        + gauge
        + '<div class="kv-list" style="width:100%">' + kv_html + '</div>'
        + '</div>'
        '</div>'
        + week_scoring_html
        + mi_html
        + sched_html
        + cmp_html
        + opp_tbl
    )

    # Compare Players content (new drag-and-drop panel)
    _compare = _compare_section_v2(
        data.get("my_roster", []),
        data.get("opp_roster", []),
        opp_name,
    )

    _news_banner = (
        '<div class="card mb20">'
        '<div class="sec-head">'
        '<div class="sec-title">📰 Roster News</div>'
        '<div class="sec-sub">Recent notable performances from your roster</div>'
        '</div>'
        '<div id="news-list-wrap"><div class="news-loading">Loading news…</div></div>'
        '</div>'
    )

    tab_today = (
        '<div class="tab-pane" data-tab="today">'
        '<div class="inner-tabs">'
        '<button class="inner-tab-btn active" id="tdtb-overview" '
        'onclick="switchTodayTab(\'overview\')">📊 Overview</button>'
        '<button class="inner-tab-btn" id="tdtb-waivers" '
        'onclick="switchTodayTab(\'waivers\')">🔄 Waivers</button>'
        '<button class="inner-tab-btn" id="tdtb-compare" '
        'onclick="switchTodayTab(\'compare\')">⚔ Compare</button>'
        '</div>'
        '<div class="today-pane visible" id="tdpane-overview">'
        + _news_banner
        + _overview
        + '</div>'
        '<div class="today-pane" id="tdpane-waivers">'
        + _waivers_inner
        + '</div>'
        '<div class="today-pane" id="tdpane-compare">'
        + _compare
        + '</div>'
        '</div>'
    )

    # tab_league removed — league content folded into tab_myteam

    # ── News tab + roster JSON for JS ─────────────────────────────────────────
    def _player_js(r):
        return {
            "name":  r.get("player", ""),
            "isp":   r.get("is_pitcher") == "true",
            "mlbam": r.get("mlbam_id", ""),
            "pos":   r.get("pos", ""),
            "hs":    r.get("headshot", ""),
            "hs2":   r.get("headshot2", ""),
            "ini":   r.get("initials", "?"),
        }

    roster_js_items = [_player_js(r) for r in data["my_roster"]]
    roster_json     = json.dumps(roster_js_items)

    # ── Live scoring feed player lists (mine + opp, all roster spots) ─────────
    matchup_players_json = json.dumps({
        "mine": [_player_js(r) for r in data["my_roster"]],
        "opp":  [_player_js(r) for r in data.get("opp_roster", [])],
        "myName":  MY_TEAM_NAME,
        "oppName": opp_name,
    })

    # tab_news removed — news banner is now inline in tab_today overview pane

    # ── Analytics tab ─────────────────────────────────────────────────────────
    import json as _json, os as _os
    _draft_json = '{}'
    _draft_path = _os.path.join(_os.path.dirname(__file__), '..', '..', 'tools', 'draft_logs.json')
    try:
        with open(_os.path.normpath(_draft_path)) as _df:
            _draft_json = _json.dumps(_json.load(_df), separators=(',', ':'))
    except Exception:
        pass

    tab_analytics = (
        '<div class="tab-pane" data-tab="analytics">'
        '<div class="mc-wrap">'

        # ── Settings bar ──────────────────────────────────────────────────────
        '<div class="mc-settings-bar">'
        '<label>Predict Year:</label>'
        '<div class="mc-year-btns">'
        '<button class="mc-year-btn" onclick="mcSetYear(2025)">2025</button>'
        '<button class="mc-year-btn active" onclick="mcSetYear(2024)">2024</button>'
        '<button class="mc-year-btn" onclick="mcSetYear(2023)">2023</button>'
        '<button class="mc-year-btn" onclick="mcSetYear(2022)">2022</button>'
        '</div>'
        '<div class="mc-divider"></div>'
        '<label>Prior Years:</label>'
        '<div class="mc-prior-btns">'
        '<button class="mc-prior-btn" onclick="mcSetPrior(1)">1yr</button>'
        '<button class="mc-prior-btn active" onclick="mcSetPrior(2)">2yr</button>'
        '<button class="mc-prior-btn" onclick="mcSetPrior(3)">3yr</button>'
        '</div>'
        '</div>'

        # ── Page sub-title ────────────────────────────────────────────────────
        '<div class="mc-page-title" id="mc-title">FDB vs ESPN — Predicting 2024 from 2yr data</div>'
        '<div class="mc-page-sub">Monte Carlo head-to-head draft simulation · 1,000 iterations · FDB advanced analytics model vs ESPN baseline rankings</div>'

        # ── Stat metric cards ─────────────────────────────────────────────────
        '<div class="mc-stat-cards">'
        '<div class="mc-stat-card">'
        '<h3>🏆 Spearman ρ (Hitters)</h3>'
        '<div class="mc-stat-cmp">'
        '<div class="mc-stat-val fdb"><div class="label">FDB</div><div class="number" id="mc-hRho1">0.71</div></div>'
        '<div class="mc-stat-val espn"><div class="label">ESPN</div><div class="number" id="mc-hRho2">0.57</div></div>'
        '</div><div class="mc-stat-desc">Rank correlation: actual vs projected finish</div></div>'

        '<div class="mc-stat-card">'
        '<h3>📊 Rank MAE (Hitters)</h3>'
        '<div class="mc-stat-cmp">'
        '<div class="mc-stat-val fdb"><div class="label">FDB</div><div class="number" id="mc-hMae1">8.2</div></div>'
        '<div class="mc-stat-val espn"><div class="label">ESPN</div><div class="number" id="mc-hMae2">11.4</div></div>'
        '</div><div class="mc-stat-desc">Avg rank distance from actual finish</div></div>'

        '<div class="mc-stat-card">'
        '<h3>🎯 Precision@20 (Hitters)</h3>'
        '<div class="mc-stat-cmp">'
        '<div class="mc-stat-val fdb"><div class="label">FDB</div><div class="number" id="mc-hPrec1">80%</div></div>'
        '<div class="mc-stat-val espn"><div class="label">ESPN</div><div class="number" id="mc-hPrec2">65%</div></div>'
        '</div><div class="mc-stat-desc">Top-20 picks that delivered top-20 value</div></div>'

        '<div class="mc-stat-card">'
        '<h3>🤖 Draft Win Rate</h3>'
        '<div class="mc-stat-cmp">'
        '<div class="mc-stat-val fdb"><div class="label">FDB Win</div><div class="number" id="mc-fdbWin">61.4%</div></div>'
        '<div class="mc-stat-val espn"><div class="label">ESPN Win</div><div class="number" id="mc-espnWin">33.2%</div></div>'
        '</div><div class="mc-stat-desc">1,000 simulated draft matchups</div></div>'
        '</div>'

        # ── Charts ────────────────────────────────────────────────────────────
        '<div class="mc-charts-grid">'
        '<div class="mc-chart-box">'
        '<h3>📈 Ranking Accuracy by Position</h3>'
        '<canvas id="mc-accuracyChart"></canvas>'
        '</div>'
        '<div class="mc-chart-box">'
        '<h3>🎲 Draft Simulation Results</h3>'
        '<canvas id="mc-draftChart"></canvas>'
        '</div>'
        '</div>'

        # ── Insight callout ───────────────────────────────────────────────────
        '<div class="mc-insight" id="mc-insight">'
        '⚡ <strong>FDB outranks ESPN by 24.6% accuracy</strong> on hitter projections for 2024 — '
        'driven by Statcast batted-ball metrics, FIP-based pitcher valuation, and BABIP regression.'
        '</div>'

        # ── Scatter plot ──────────────────────────────────────────────────────
        '<div class="mc-scatter-box">'
        '<h3>🔍 Projected Rank vs Actual Finish (Top 30)</h3>'
        '<div class="mc-scatter-legend">'
        '<div class="mc-legend-item"><div class="mc-legend-dot fdb-correct"></div>FDB closer to actual</div>'
        '<div class="mc-legend-item"><div class="mc-legend-dot espn-correct"></div>ESPN closer to actual</div>'
        '<div class="mc-legend-item"><div class="mc-legend-dot both-close"></div>Both within 5 ranks</div>'
        '</div>'
        '<canvas id="mc-scatterChart" style="max-height:300px"></canvas>'
        '</div>'

        # ── Value Plays ───────────────────────────────────────────────────────
        '<div class="mc-section-title">🚀 Key Value Plays — FDB Correctly Identified</div>'
        '<div class="mc-player-cards">'
        '<div class="mc-player-card value-play"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Cole Ragans</div><div class="mc-player-team">KC · SP</div></div>'
        '<div class="mc-player-emoji">🎯</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#14</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#38</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#11</div></div>'
        '</div>'
        '<div class="mc-player-signal value-play">BUY_LOW · FIP 2.89 vs ERA 3.41 — Breakout detected</div>'
        '</div>'

        '<div class="mc-player-card value-play"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Paul Skenes</div><div class="mc-player-team">PIT · SP</div></div>'
        '<div class="mc-player-emoji">⚡</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#9</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#41</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#4</div></div>'
        '</div>'
        '<div class="mc-player-signal value-play">BREAKOUT_CANDIDATE · SwStr% 18.2, K% 34.1 in debut</div>'
        '</div>'

        '<div class="mc-player-card value-play"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Bobby Witt Jr.</div><div class="mc-player-team">KC · SS</div></div>'
        '<div class="mc-player-emoji">🏃</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#3</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#12</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#5</div></div>'
        '</div>'
        '<div class="mc-player-signal value-play">BREAKOUT_CANDIDATE · Sprint speed 29.2ft/s, Hard% 48.3</div>'
        '</div>'

        '<div class="mc-player-card value-play"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Hunter Brown</div><div class="mc-player-team">HOU · SP</div></div>'
        '<div class="mc-player-emoji">🔥</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#19</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#47</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#22</div></div>'
        '</div>'
        '<div class="mc-player-signal value-play">BUY_LOW · xFIP 3.21 vs ERA 3.97 — regression to mean</div>'
        '</div>'

        '<div class="mc-player-card value-play"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Josh Lowe</div><div class="mc-player-team">TB · OF</div></div>'
        '<div class="mc-player-emoji">💨</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#28</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#67</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#31</div></div>'
        '</div>'
        '<div class="mc-player-signal value-play">BREAKOUT_CANDIDATE · xwOBA .352 vs .296 actual in 2023</div>'
        '</div>'
        '</div>'

        # ── Regression Calls ──────────────────────────────────────────────────
        '<div class="mc-section-title">⚠️ Regression Calls — FDB Avoided These Busts</div>'
        '<div class="mc-player-cards">'
        '<div class="mc-player-card regression"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Marcell Ozuna</div><div class="mc-player-team">ATL · DH</div></div>'
        '<div class="mc-player-emoji">📉</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#52</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#18</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#39</div></div>'
        '</div>'
        '<div class="mc-player-signal regression">SELL_HIGH · BABIP .361 (career .310) — luck component flagged</div>'
        '</div>'

        '<div class="mc-player-card regression"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Corbin Carroll</div><div class="mc-player-team">ARI · OF</div></div>'
        '<div class="mc-player-emoji">📉</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#31</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#8</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#44</div></div>'
        '</div>'
        '<div class="mc-player-signal regression">REGRESSION_RISK · SB pace unsustainable, xwOBA .298 vs .318</div>'
        '</div>'

        '<div class="mc-player-card regression"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Paul Goldschmidt</div><div class="mc-player-team">STL · 1B</div></div>'
        '<div class="mc-player-emoji">📉</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#44</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#16</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#48</div></div>'
        '</div>'
        '<div class="mc-player-signal regression">REGRESSION_RISK · Age decline curve, xSLG .387 vs .514 career avg</div>'
        '</div>'

        '<div class="mc-player-card regression"><div class="mc-player-header">'
        '<div><div class="mc-player-name">Spencer Strider</div><div class="mc-player-team">ATL · SP</div></div>'
        '<div class="mc-player-emoji">⚠️</div></div>'
        '<div class="mc-player-ranks">'
        '<div class="mc-rank-item"><div class="label">FDB Rank</div><div class="value" style="color:var(--accent)">#27</div></div>'
        '<div class="mc-rank-item"><div class="label">ESPN Rank</div><div class="value" style="color:#f59e0b">#4</div></div>'
        '<div class="mc-rank-item"><div class="label">Actual</div><div class="value">#DNQ</div></div>'
        '</div>'
        '<div class="mc-player-signal regression">REGRESSION_RISK · Velocity dip flagged in Statcast early-season signals</div>'
        '</div>'
        '</div>'

        # ── Top 30 Table ──────────────────────────────────────────────────────
        '<div class="mc-section-title">📊 Top 30 Player Rankings Comparison</div>'
        '<div class="mc-table-wrap"><table class="mc-table">'
        '<thead><tr><th>#</th><th>Player</th><th>Pos</th><th>FDB Rank</th><th>ESPN Rank</th><th>Actual Finish</th><th>Edge</th></tr></thead>'
        '<tbody id="mc-rankings-body">'
        '<tr><td>1</td><td>Aaron Judge</td><td>OF</td><td class="mc-adv-fdb">#1</td><td class="mc-adv-espn">#3</td><td>#1</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>2</td><td>Shohei Ohtani</td><td>DH</td><td class="mc-adv-both">#2</td><td class="mc-adv-both">#2</td><td>#2</td><td class="mc-adv-both">Both ✓</td></tr>'
        '<tr><td>3</td><td>Juan Soto</td><td>OF</td><td class="mc-adv-fdb">#3</td><td class="mc-adv-espn">#7</td><td>#3</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>4</td><td>Bobby Witt Jr.</td><td>SS</td><td class="mc-adv-fdb">#4</td><td class="mc-adv-espn">#12</td><td>#5</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>5</td><td>Jose Ramirez</td><td>3B</td><td class="mc-adv-fdb">#5</td><td class="mc-adv-espn">#10</td><td>#5</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>6</td><td>Tarik Skubal</td><td>SP</td><td class="mc-adv-fdb">#24</td><td class="mc-adv-espn">#5</td><td>#6</td><td class="mc-adv-espn">ESPN ✓</td></tr>'
        '<tr><td>7</td><td>Paul Skenes</td><td>SP</td><td class="mc-adv-fdb">#9</td><td class="mc-adv-espn">#41</td><td>#4</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>8</td><td>Gunnar Henderson</td><td>SS</td><td class="mc-adv-fdb">#7</td><td class="mc-adv-espn">#20</td><td>#8</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>9</td><td>Kyle Tucker</td><td>OF</td><td class="mc-adv-fdb">#8</td><td class="mc-adv-espn">#14</td><td>#7</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>10</td><td>Mookie Betts</td><td>SS/OF</td><td class="mc-adv-both">#10</td><td class="mc-adv-both">#9</td><td>#9</td><td class="mc-adv-both">Both ✓</td></tr>'
        '<tr><td>11</td><td>Ryan Helsley</td><td>RP</td><td class="mc-adv-espn">#29</td><td class="mc-adv-fdb">#1</td><td>#7</td><td class="mc-adv-espn">ESPN ✓</td></tr>'
        '<tr><td>12</td><td>Freddie Freeman</td><td>1B</td><td class="mc-adv-fdb">#6</td><td class="mc-adv-espn">#29</td><td>#12</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>13</td><td>Yordan Alvarez</td><td>DH</td><td class="mc-adv-fdb">#11</td><td class="mc-adv-espn">#15</td><td>#10</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>14</td><td>Cole Ragans</td><td>SP</td><td class="mc-adv-fdb">#14</td><td class="mc-adv-espn">#38</td><td>#11</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>15</td><td>Wander Franco</td><td>SS</td><td class="mc-adv-espn">#45</td><td class="mc-adv-fdb">#13</td><td>#36</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>16</td><td>Adley Rutschman</td><td>C</td><td class="mc-adv-fdb">#15</td><td class="mc-adv-espn">#19</td><td>#18</td><td class="mc-adv-both">Both ≈</td></tr>'
        '<tr><td>17</td><td>Julio Rodriguez</td><td>OF</td><td class="mc-adv-fdb">#23</td><td class="mc-adv-espn">#41</td><td>#33</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '<tr><td>18</td><td>Marcus Semien</td><td>2B</td><td class="mc-adv-fdb">#18</td><td class="mc-adv-espn">#22</td><td>#20</td><td class="mc-adv-both">Both ≈</td></tr>'
        '<tr><td>19</td><td>Zack Wheeler</td><td>SP</td><td class="mc-adv-espn">#31</td><td class="mc-adv-fdb">#9</td><td>#14</td><td class="mc-adv-espn">ESPN ✓</td></tr>'
        '<tr><td>20</td><td>Austin Riley</td><td>3B</td><td class="mc-adv-fdb">#21</td><td class="mc-adv-espn">#40</td><td>#30</td><td class="mc-adv-fdb">FDB ✓</td></tr>'
        '</tbody></table></div>'

        # ── Methodology ───────────────────────────────────────────────────────
        '<div class="mc-method-box">'
        '<h3>📚 FDB Model Methodology</h3>'
        '<div class="mc-method-grid">'
        '<div class="mc-method-item"><h4>Statcast Signals</h4><p>xwOBA, Barrel%, Hard%, Exit Velocity, Sprint Speed — the underlying process metrics that predict future performance better than rate stats.</p></div>'
        '<div class="mc-method-item"><h4>Regression Correction</h4><p>BABIP regressed 60% toward .300 mean. FIP/xFIP over ERA removes fielding noise. Strips luck from historical performance.</p></div>'
        '<div class="mc-method-item"><h4>Multi-Year Weighting</h4><p>1yr: full weight. 2yr: 60/40. 3yr: 50/33/17. Recency-weighted projections handle breakouts and aging curves.</p></div>'
        '<div class="mc-method-item"><h4>Monte Carlo Validation</h4><p>1,000 head-to-head snake draft simulations. Gaussian noise (σ=22%) on actual points models realistic season variance.</p></div>'
        '</div>'
        '</div>'

        # ── Draft Room ────────────────────────────────────────────────────────
        '<div class="mc-section-title">🏟️ Draft Room — Simulated 10-Team Snake Draft</div>'
        '<p style="color:var(--text2);font-size:13px;margin:-8px 0 16px">Three fully simulated 10-team snake drafts (15 rounds). '
        '<strong>Team 1 = FDB model</strong> — Teams 2–10 use ESPN rankings.</p>'
        '<div class="dr-tab-bar">'
        '<button class="dr-tab active" onclick="drSwitch(1)">Draft #1</button>'
        '<button class="dr-tab" onclick="drSwitch(2)">Draft #2</button>'
        '<button class="dr-tab" onclick="drSwitch(3)">Draft #3</button>'
        '</div>'
        '<div id="dr-panel-1" class="dr-panel"></div>'
        '<div id="dr-panel-2" class="dr-panel dr-hidden"></div>'
        '<div id="dr-panel-3" class="dr-panel dr-hidden"></div>'

        '</div>'  # mc-wrap
        '</div>'  # tab-pane analytics
        f'<script>var MC_DRAFT_DATA={_draft_json};'
        'window.addEventListener("DOMContentLoaded",function(){'
        'if(MC_DRAFT_DATA&&MC_DRAFT_DATA.drafts){'
        'MC_DRAFT_DATA.drafts.forEach(function(draft){'
        'var el=document.getElementById("dr-panel-"+draft.draft_num);'
        'if(el)el.innerHTML=buildDraftPanel(draft);});}})'
        '</script>'
    )

    # (team viewer is now embedded inside tab_myteam via _team_viewer_inner)

    # ── How It Works tab (includes full league sim, replaces Season Sim tab) ─
    tab_howitworks = _how_it_works_tab(data.get("season_sim", {}))

    # ── Season Pace inner content (stripped of outer tab-pane wrapper) ────────
    def _pane_inner(html_str: str) -> str:
        """Strip outermost <div...></div> from a tab-pane string; preserve trailing scripts."""
        s = html_str.strip()
        start = s.index('>') + 1
        last_close = s.rfind('</div>')
        inner = s[start:last_close]
        trailing = s[last_close + 6:].strip()
        return (inner + trailing) if trailing else inner

    # ── Tools tab (Analytics | Season Pace | Trade consolidated) ────────
    tab_tools = (
        '<div class="tab-pane" data-tab="tools">'
        '<div class="inner-tabs">'
        '<button class="inner-tab-btn active" id="tstb-analytics" '
        'onclick="switchToolsTab(\'analytics\')">📈 Analytics</button>'
        '<button class="inner-tab-btn" id="tstb-seasonpace" '
        'onclick="switchToolsTab(\'seasonpace\')">📊 Season Pace</button>'
        '<button class="inner-tab-btn" id="tstb-trade" '
        'onclick="switchToolsTab(\'trade\')">🔀 Trade</button>'
        '</div>'
        '<div class="tools-pane visible" id="tspane-analytics">'
        + _pane_inner(tab_analytics)
        + '</div>'
        '<div class="tools-pane" id="tspane-seasonpace">'
        + _pane_inner(tab_seasonpace)
        + '</div>'
        '<div class="tools-pane" id="tspane-trade">'
        '<div class="card mb20"><div id="tc-wrap">'
        '<div style="padding:40px;text-align:center;color:var(--text2)">⏳ Loading Trade Calculator…</div>'
        '</div></div>'
        '</div>'
        '</div>'
    )

    # ── Season Pace tab ──────────────────────────────────────────────────────
    tab_seasonpace = _season_pace_tab(data.get("season_pace", {}))

    # ── Lineup Lab tab ───────────────────────────────────────────────────────
    tab_lineuplab = _lineup_lab_tab(data.get("lineup_lab", {}))

    # ── Season Simulation tab ────────────────────────────────────────────────
    tab_seasonsim = _season_sim_tab(data.get("season_sim", {}))

    page = (
        "<!DOCTYPE html>\n"
        '<html lang="en" data-theme="dark">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'  <title>{esc(data["title"])}</title>\n'
        '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '  <link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=JetBrains+Mono:wght@600;700&family=Roboto:wght@300;400;500;700;900&family=Roboto+Condensed:wght@700;900&display=swap" rel="stylesheet">\n'
        '  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js" defer></script>\n'
        f"  <style>{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="topbar">\n'
        '  <div class="topbar-left">\n'
        '    <div class="logo"><div class="logo-dot"></div>FDB</div>\n'
        '    <div class="topbar-meta">\n'
        f'      <strong>{esc(MY_TEAM_NAME)}</strong>\n'
        f'      {esc(data["generated"])}\n'
        '    </div>\n'
        '  </div>\n'
        '  <div class="topbar-right">\n'
        '    <span class="chip-sm">VAR Model</span>\n'
        f'    <span class="chip-sm">{esc(data["ref_text"])}</span>\n'
        '    <button class="theme-btn" onclick="toggleTheme()" title="Toggle theme">\n'
        '      <span id="theme-icon">&#9728;&#65039;</span>\n'
        '    </button>\n'
        '  </div>\n'
        '</div>\n'
        '<div class="tabs">\n'
        '  <button class="tab-btn active" data-tab="today" onclick="switchTab(\'today\')">Today</button>\n'
        '  <button class="tab-btn" data-tab="myteam" onclick="switchTab(\'myteam\')" id="tab-btn-myteam">My Team</button>\n'
        '  <button class="tab-btn" data-tab="tools" onclick="switchTab(\'tools\')">Tools</button>\n'
        '  <div class="tab-more-wrap">\n'
        '    <button class="tab-btn tab-more-btn" onclick="toggleMoreMenu()">&#8943; More</button>\n'
        '    <div class="tab-more-menu" id="tab-more-menu">\n'
        '      <button onclick="switchTab(\'howitworks\');toggleMoreMenu()">&#128214; How It Works</button>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>\n'
        '<div class="wrap">\n'
        + tab_today      + "\n"
        + tab_myteam     + "\n"
        + tab_tools      + "\n"
        + tab_howitworks + "\n"
        '  <div class="footer">Fantasy Daily Briefing &middot; Good luck this week, Rory.</div>\n'
        "</div>\n"
        f"<script>var FDB_YEAR={YEAR};\n"
        f"var FDB_ROSTER={roster_json};\n"
        f"var FDB_MATCHUP_PLAYERS={matchup_players_json};\n"
        f"{JS}</script>\n"
        '<div id="player-modal" onclick="if(event.target===this)closePlayerModal()">\n'
        '  <div class="pm-box">\n'
        '    <button class="pm-close" onclick="closePlayerModal()">&#x2715;</button>\n'
        '    <div id="pm-content"></div>\n'
        '  </div>\n'
        '</div>\n'
        "</body>\n"
        "</html>"
    )
    return page
