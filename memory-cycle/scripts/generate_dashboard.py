"""Generate Memory Cycle Tracker HTML dashboard.

Produces a self-contained HTML file with 6 panels + header, matching the
lyst-index-dashboard.html dark-theme aesthetic. All charts are inline SVG
computed in Python — no external JS libraries.

Output: ~/Documents/Obsidian Vault/研究/研究笔记/memory-cycle-dashboard.html
"""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

import memory_db as db

# ── Output path ──────────────────────────────────────────────────────
OUTPUT_PATH = (
    Path.home()
    / "Documents"
    / "Obsidian Vault"
    / "研究"
    / "研究笔记"
    / "memory-cycle-dashboard.html"
)

# ── Color constants ──────────────────────────────────────────────────
C_MU = "#4a8ef5"
C_WDC = "#e85d50"
C_SAMSUNG = "#50c878"
C_HYNIX = "#c9a96e"
C_SOXX = "#555555"

C_DDR5 = "#4a8ef5"
C_DDR4 = "#6ab0ff"
C_NAND = "#e85d50"

C_GREEN = "#3ab577"
C_RED = "#e85d50"
C_ORANGE = "#e8a94e"
C_BLUE = "#4a8ef5"
C_GOLD = "#c9a96e"

PHASE_COLORS = {
    "early_recovery": C_GREEN,
    "mid_expansion": C_BLUE,
    "late_cycle": C_ORANGE,
    "contraction": C_RED,
    "unknown": "#555",
}

PHASE_LABELS = {
    "early_recovery": "Early Recovery",
    "mid_expansion": "Mid Expansion",
    "late_cycle": "Late Cycle / Peak",
    "contraction": "Contraction",
    "unknown": "Unknown",
}

PHASE_INVESTMENT = {
    "early_recovery": "Best risk/reward -- get long",
    "mid_expansion": "Hold, add on dips",
    "late_cycle": "Trim, tighten stops",
    "contraction": "Avoid or short",
    "unknown": "Insufficient data",
}


# ── SVG helpers ──────────────────────────────────────────────────────

def _esc(s: str) -> str:
    """Escape HTML special chars."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fmt_num(v, decimals=1):
    """Format a number safely."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.{decimals}f}"
    except (ValueError, TypeError):
        return "N/A"


def _fmt_pct(v, decimals=1):
    """Format as percentage."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v) * 100:.{decimals}f}%"
    except (ValueError, TypeError):
        return "N/A"


def _polyline(points: list[tuple[float, float]]) -> str:
    """Generate SVG polyline points attribute."""
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _line_path(points: list[tuple[float, float]]) -> str:
    """Generate SVG path d attribute for a line."""
    if not points:
        return ""
    parts = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for x, y in points[1:]:
        parts.append(f"L{x:.1f},{y:.1f}")
    return "".join(parts)


def _scale_linear(val, domain_min, domain_max, range_min, range_max):
    """Linear scale mapping."""
    if domain_max == domain_min:
        return (range_min + range_max) / 2
    return range_min + (val - domain_min) / (domain_max - domain_min) * (range_max - range_min)


def _no_data_placeholder(width, height, msg="No data available"):
    """Return SVG placeholder for empty panels."""
    return (
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;display:block;">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>'
        f'<text x="{width/2}" y="{height/2}" text-anchor="middle" '
        f'fill="#5a5650" font-size="14" font-family="\'JetBrains Mono\',monospace">'
        f'{_esc(msg)}</text></svg>'
    )


# ── Data loading ─────────────────────────────────────────────────────

def _load_freshness() -> list[dict]:
    """Query latest date per data source for the header freshness row."""
    conn = db.get_db()
    rows = conn.execute("""
        SELECT source, MAX(date) as latest_date, COUNT(*) as n_rows
        FROM price_signals
        GROUP BY source
        ORDER BY source
    """).fetchall()
    # Friendly labels
    labels = {
        "yfinance": "yfinance",
        "korea_exports": "Korea Exports",
        "sec_xbrl": "SEC XBRL",
        "spot_pricing": "Spot Pricing",
    }
    result = []
    for r in rows:
        src = r[0]
        result.append({
            "source": labels.get(src, src),
            "latest_date": r[1],
            "n_rows": r[2],
        })
    # Also add per-company for SEC XBRL (MU vs WDC have different filing dates)
    xbrl_rows = conn.execute("""
        SELECT
            CASE WHEN metric LIKE 'mu_%' THEN 'SEC: Micron'
                 WHEN metric LIKE 'wdc_%' THEN 'SEC: WDC'
                 ELSE 'SEC: Other' END as company,
            MAX(date) as latest_date
        FROM price_signals
        WHERE source = 'sec_xbrl'
        GROUP BY company
        ORDER BY company
    """).fetchall()
    for r in xbrl_rows:
        result.append({
            "source": r[0],
            "latest_date": r[1],
            "n_rows": None,  # sub-detail, no count needed
        })
    return result


def _load_price_data():
    """Load stock price data for Panel 1."""
    signals = db.get_signals(source="yfinance")
    # Group by metric, each metric is like price_MU, price_WDC, etc.
    series = defaultdict(list)
    for s in signals:
        m = s["metric"]
        if m.startswith("price_"):
            ticker = m.replace("price_", "")
            series[ticker].append((s["date"], s["value"]))
    # Sort each series by date
    for k in series:
        series[k].sort(key=lambda x: x[0])
    return dict(series)


def _load_korea_exports():
    """Load Korean export data for Panel 2."""
    value_signals = db.get_signals(source="korea_exports", metric="korea_memory_export_value")
    ratio_signals = db.get_signals(source="korea_exports", metric="korea_memory_value_volume_ratio")
    value_signals.sort(key=lambda x: x["date"])
    ratio_signals.sort(key=lambda x: x["date"])
    return value_signals, ratio_signals


def _load_spot_pricing():
    """Load spot pricing data for Panel 3."""
    signals = db.get_signals(source="spot_pricing")
    series = defaultdict(list)
    for s in signals:
        series[s["metric"]].append((s["date"], s["value"]))
    for k in series:
        series[k].sort(key=lambda x: x[0])
    return dict(series)


def _load_inventory_margin():
    """Load MU inventory days and gross margin for Panel 4."""
    inv = db.get_signals(metric="mu_inventory_days")
    gm = db.get_signals(metric="mu_gross_margin")
    inv.sort(key=lambda x: x["date"])
    gm.sort(key=lambda x: x["date"])
    return inv, gm


def _load_composites():
    """Load composite scores for Panels 4, 5, 6."""
    comps = db.get_composites()
    comps.sort(key=lambda x: x["date"])
    return comps


def _load_latest_composite():
    """Load latest composite for header."""
    return db.get_latest_composite()


# ── Panel SVG generators ─────────────────────────────────────────────

def _panel1_stock_performance(price_data: dict) -> str:
    """Panel 1: Memory Stock Performance — normalized to 100."""
    W, H = 900, 300
    margin = {"top": 30, "right": 100, "bottom": 40, "left": 55}
    cw = W - margin["left"] - margin["right"]
    ch = H - margin["top"] - margin["bottom"]

    ticker_map = {
        "MU": (C_MU, "MU"),
        "WDC": (C_WDC, "WDC"),
        "005930.KS": (C_SAMSUNG, "Samsung"),
        "000660.KS": (C_HYNIX, "SK Hynix"),
        "SOXX": (C_SOXX, "SOXX"),
    }

    # Normalize each series to 100 from its first value
    normalized = {}
    all_dates = set()
    for ticker, (color, label) in ticker_map.items():
        raw = price_data.get(ticker, [])
        if not raw:
            continue
        base = raw[0][1]
        if base is None or base == 0:
            continue
        norm = [(d, (v / base) * 100) for d, v in raw if v is not None]
        if norm:
            normalized[ticker] = norm
            all_dates.update(d for d, _ in norm)

    if not normalized:
        return _no_data_placeholder(W, H, "No stock price data")

    all_dates = sorted(all_dates)
    date_count = len(all_dates)
    if date_count < 2:
        return _no_data_placeholder(W, H, "Insufficient price data")

    date_idx = {d: i for i, d in enumerate(all_dates)}

    # Find y domain across all normalized series
    all_vals = [v for series in normalized.values() for _, v in series]
    y_min = min(all_vals) * 0.95
    y_max = max(all_vals) * 1.05

    def x_pos(i):
        return margin["left"] + (i / (date_count - 1)) * cw

    def y_pos(v):
        return margin["top"] + (1 - (v - y_min) / (y_max - y_min)) * ch

    svg = f'<svg viewBox="0 0 {W} {H}" style="width:100%;display:block;overflow:visible;">'

    # Y-axis grid
    y_ticks = _nice_ticks(y_min, y_max, 5)
    for t in y_ticks:
        yy = y_pos(t)
        svg += (
            f'<line x1="{margin["left"]}" y1="{yy:.1f}" '
            f'x2="{W - margin["right"]}" y2="{yy:.1f}" '
            f'stroke="rgba(255,255,255,0.04)" stroke-width="1"/>'
            f'<text x="{margin["left"] - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'fill="#5a5650" font-size="10" font-family="\'JetBrains Mono\',monospace">'
            f'{t:.0f}</text>'
        )

    # 100 baseline
    baseline_y = y_pos(100)
    svg += (
        f'<line x1="{margin["left"]}" y1="{baseline_y:.1f}" '
        f'x2="{W - margin["right"]}" y2="{baseline_y:.1f}" '
        f'stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="4,4"/>'
    )

    # X-axis labels — show ~8 evenly spaced dates
    label_step = max(1, date_count // 8)
    for i in range(0, date_count, label_step):
        xx = x_pos(i)
        d = all_dates[i]
        label = d[2:7] if len(d) >= 7 else d  # YY-MM
        svg += (
            f'<text x="{xx:.1f}" y="{H - 5}" text-anchor="middle" '
            f'fill="#5a5650" font-size="9" font-family="\'JetBrains Mono\',monospace">'
            f'{_esc(label)}</text>'
        )

    # Draw lines — SOXX first (behind), then stocks
    draw_order = ["SOXX", "005930.KS", "000660.KS", "WDC", "MU"]
    for ticker in draw_order:
        if ticker not in normalized:
            continue
        color, label = ticker_map[ticker]
        points = [(x_pos(date_idx[d]), y_pos(v)) for d, v in normalized[ticker] if d in date_idx]
        if len(points) < 2:
            continue
        stroke_w = "1.5" if ticker == "SOXX" else "2.2"
        dash = ' stroke-dasharray="6,3"' if ticker == "SOXX" else ""
        opacity = '0.5' if ticker == "SOXX" else "1"
        svg += (
            f'<path d="{_line_path(points)}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke_w}" stroke-linejoin="round" '
            f'stroke-linecap="round" opacity="{opacity}"{dash}/>'
        )
        # End label
        last_x, last_y = points[-1]
        svg += (
            f'<text x="{last_x + 8:.1f}" y="{last_y + 4:.1f}" '
            f'fill="{color}" font-size="10" font-weight="600" '
            f'font-family="\'DM Sans\',sans-serif">{_esc(label)}</text>'
        )

    svg += "</svg>"
    return svg


def _panel2_korea_exports(value_signals, ratio_signals) -> str:
    """Panel 2: Korean Exports — bar chart + overlay line."""
    W, H = 900, 300
    margin = {"top": 30, "right": 70, "bottom": 40, "left": 55}
    cw = W - margin["left"] - margin["right"]
    ch = H - margin["top"] - margin["bottom"]

    if not value_signals:
        return _no_data_placeholder(W, H, "No Korean export data")

    dates = [s["date"] for s in value_signals]
    values = [s["value"] for s in value_signals]
    n = len(dates)

    # Ratio data aligned by date
    ratio_map = {s["date"]: s["value"] for s in ratio_signals}
    ratios = [ratio_map.get(d) for d in dates]

    v_min = 0
    v_max = max(v for v in values if v is not None) * 1.15

    def x_pos(i):
        return margin["left"] + (i + 0.5) / n * cw

    def y_pos(v):
        return margin["top"] + (1 - (v - v_min) / (v_max - v_min)) * ch

    bar_w = max(4, cw / n * 0.7)

    svg = f'<svg viewBox="0 0 {W} {H}" style="width:100%;display:block;overflow:visible;">'

    # Y-axis (values)
    y_ticks = _nice_ticks(v_min, v_max, 5)
    for t in y_ticks:
        yy = y_pos(t)
        svg += (
            f'<line x1="{margin["left"]}" y1="{yy:.1f}" '
            f'x2="{W - margin["right"]}" y2="{yy:.1f}" '
            f'stroke="rgba(255,255,255,0.04)" stroke-width="1"/>'
            f'<text x="{margin["left"] - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'fill="#5a5650" font-size="10" font-family="\'JetBrains Mono\',monospace">'
            f'{_fmt_val_axis(t)}</text>'
        )

    # Bars
    for i, v in enumerate(values):
        if v is None:
            continue
        xx = x_pos(i)
        yy = y_pos(v)
        h = y_pos(v_min) - yy
        svg += (
            f'<rect x="{xx - bar_w / 2:.1f}" y="{yy:.1f}" '
            f'width="{bar_w:.1f}" height="{h:.1f}" '
            f'fill="{C_GOLD}" opacity="0.6" rx="1"/>'
        )

    # X-axis labels
    label_step = max(1, n // 10)
    for i in range(0, n, label_step):
        xx = x_pos(i)
        label = dates[i][2:7] if len(dates[i]) >= 7 else dates[i]
        svg += (
            f'<text x="{xx:.1f}" y="{H - 5}" text-anchor="middle" '
            f'fill="#5a5650" font-size="9" font-family="\'JetBrains Mono\',monospace">'
            f'{_esc(label)}</text>'
        )

    # Overlay: value/volume ratio as line (secondary y-axis)
    valid_ratios = [(i, r) for i, r in enumerate(ratios) if r is not None]
    if valid_ratios:
        r_vals = [r for _, r in valid_ratios]
        r_min = min(r_vals) * 0.9
        r_max = max(r_vals) * 1.1
        if r_min == r_max:
            r_max = r_min + 1

        def r_y(v):
            return margin["top"] + (1 - (v - r_min) / (r_max - r_min)) * ch

        ratio_points = [(x_pos(i), r_y(r)) for i, r in valid_ratios]
        svg += (
            f'<path d="{_line_path(ratio_points)}" fill="none" '
            f'stroke="{C_ORANGE}" stroke-width="2" stroke-linejoin="round" stroke-dasharray="4,3"/>'
        )
        # Secondary y-axis labels (right side)
        r_ticks = _nice_ticks(r_min, r_max, 4)
        for t in r_ticks:
            yy = r_y(t)
            svg += (
                f'<text x="{W - margin["right"] + 8}" y="{yy + 4:.1f}" text-anchor="start" '
                f'fill="{C_ORANGE}" font-size="9" font-family="\'JetBrains Mono\',monospace">'
                f'{t:.2f}</text>'
            )
        # Right axis label
        svg += (
            f'<text x="{W - 5}" y="{margin["top"] - 8}" text-anchor="end" '
            f'fill="{C_ORANGE}" font-size="8" font-family="\'DM Sans\',sans-serif" '
            f'letter-spacing="0.08em">VALUE/VOL RATIO</text>'
        )

    # Left axis label
    svg += (
        f'<text x="{margin["left"]}" y="{margin["top"] - 8}" text-anchor="start" '
        f'fill="{C_GOLD}" font-size="8" font-family="\'DM Sans\',sans-serif" '
        f'letter-spacing="0.08em">EXPORT VALUE</text>'
    )

    svg += "</svg>"
    return svg


def _panel3_spot_pricing(spot_data: dict) -> str:
    """Panel 3: Spot/Retail DRAM + SSD Pricing — multi-line chart."""
    W, H = 900, 300
    margin = {"top": 30, "right": 100, "bottom": 40, "left": 55}
    cw = W - margin["left"] - margin["right"]
    ch = H - margin["top"] - margin["bottom"]

    # Identify series by name pattern
    dram_series = {}
    nand_series = {}
    for metric, data in spot_data.items():
        ml = metric.lower()
        if "ddr5" in ml:
            dram_series[metric] = (data, C_DDR5, "DDR5")
        elif "ddr4" in ml:
            dram_series[metric] = (data, C_DDR4, "DDR4")
        elif "nand" in ml or "ssd" in ml:
            nand_series[metric] = (data, C_NAND, metric.replace("spot_", "").replace("_", " ").title())

    all_series = {**dram_series, **nand_series}
    if not all_series:
        return _no_data_placeholder(W, H, "No spot pricing data")

    # Collect all dates and values
    all_dates = set()
    for metric, (data, _, _) in all_series.items():
        all_dates.update(d for d, _ in data)
    all_dates = sorted(all_dates)
    date_count = len(all_dates)
    if date_count < 2:
        return _no_data_placeholder(W, H, "Insufficient spot pricing data")

    date_idx = {d: i for i, d in enumerate(all_dates)}

    # Normalize each series to 100 from start (different price scales)
    norm_series = {}
    for metric, (data, color, label) in all_series.items():
        if not data or data[0][1] is None or data[0][1] == 0:
            continue
        base = data[0][1]
        norm = [(d, (v / base) * 100) for d, v in data if v is not None]
        norm_series[metric] = (norm, color, label)

    if not norm_series:
        return _no_data_placeholder(W, H, "Spot pricing data incomplete")

    all_vals = [v for _, (data, _, _) in norm_series.items() for _, v in data]
    y_min = min(all_vals) * 0.95
    y_max = max(all_vals) * 1.05

    def x_pos(i):
        return margin["left"] + (i / (date_count - 1)) * cw

    def y_pos(v):
        return margin["top"] + (1 - (v - y_min) / (y_max - y_min)) * ch

    svg = f'<svg viewBox="0 0 {W} {H}" style="width:100%;display:block;overflow:visible;">'

    # Grid
    y_ticks = _nice_ticks(y_min, y_max, 5)
    for t in y_ticks:
        yy = y_pos(t)
        svg += (
            f'<line x1="{margin["left"]}" y1="{yy:.1f}" '
            f'x2="{W - margin["right"]}" y2="{yy:.1f}" '
            f'stroke="rgba(255,255,255,0.04)" stroke-width="1"/>'
            f'<text x="{margin["left"] - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'fill="#5a5650" font-size="10" font-family="\'JetBrains Mono\',monospace">'
            f'{t:.0f}</text>'
        )

    # 100 baseline
    baseline_y = y_pos(100)
    svg += (
        f'<line x1="{margin["left"]}" y1="{baseline_y:.1f}" '
        f'x2="{W - margin["right"]}" y2="{baseline_y:.1f}" '
        f'stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="4,4"/>'
    )

    # X-axis
    label_step = max(1, date_count // 8)
    for i in range(0, date_count, label_step):
        xx = x_pos(i)
        label = all_dates[i][2:7] if len(all_dates[i]) >= 7 else all_dates[i]
        svg += (
            f'<text x="{xx:.1f}" y="{H - 5}" text-anchor="middle" '
            f'fill="#5a5650" font-size="9" font-family="\'JetBrains Mono\',monospace">'
            f'{_esc(label)}</text>'
        )

    # Lines
    for metric, (data, color, label) in norm_series.items():
        points = [(x_pos(date_idx[d]), y_pos(v)) for d, v in data if d in date_idx]
        if len(points) < 2:
            continue
        svg += (
            f'<path d="{_line_path(points)}" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        last_x, last_y = points[-1]
        svg += (
            f'<text x="{last_x + 8:.1f}" y="{last_y + 4:.1f}" '
            f'fill="{color}" font-size="10" font-weight="600" '
            f'font-family="\'DM Sans\',sans-serif">{_esc(label)}</text>'
        )

    svg += "</svg>"
    return svg


def _panel4_cycle_phase_and_inv_gm(composites, inv_signals, gm_signals) -> str:
    """Panel 4: Cycle Phase Timeline + Inventory Days vs Gross Margin."""
    W, H = 900, 300
    mid = W // 2

    svg = f'<svg viewBox="0 0 {W} {H}" style="width:100%;display:block;overflow:visible;">'

    # ── Left side: Traffic light timeline ──
    left_w = mid - 30
    margin_l = {"top": 30, "right": 20, "bottom": 40, "left": 15}
    lcw = left_w - margin_l["left"] - margin_l["right"]
    lch = H - margin_l["top"] - margin_l["bottom"]

    phases_data = [(c["date"], c.get("cycle_phase", "unknown")) for c in composites if c.get("date")]
    if phases_data:
        n = len(phases_data)
        dot_r = max(4, min(10, lcw / n / 2.5))
        spacing = lcw / max(n - 1, 1) if n > 1 else 0

        # Title
        svg += (
            f'<text x="{margin_l["left"]}" y="{margin_l["top"] - 10}" '
            f'fill="#9a9690" font-size="10" font-weight="700" '
            f'font-family="\'DM Sans\',sans-serif" letter-spacing="0.08em">CYCLE PHASE TIMELINE</text>'
        )

        # Phase legend
        legend_x = margin_l["left"]
        for phase, color in PHASE_COLORS.items():
            if phase == "unknown":
                continue
            svg += (
                f'<circle cx="{legend_x + 5}" cy="{margin_l["top"] + 8}" r="3" fill="{color}"/>'
                f'<text x="{legend_x + 12}" y="{margin_l["top"] + 11}" '
                f'fill="#5a5650" font-size="7" font-family="\'DM Sans\',sans-serif">'
                f'{PHASE_LABELS.get(phase, phase)[:10]}</text>'
            )
            legend_x += 85

        # Timeline dots
        timeline_y = margin_l["top"] + lch * 0.55
        for i, (date, phase) in enumerate(phases_data):
            xx = margin_l["left"] + i * spacing
            color = PHASE_COLORS.get(phase, "#555")
            svg += f'<circle cx="{xx:.1f}" cy="{timeline_y:.1f}" r="{dot_r:.1f}" fill="{color}" opacity="0.85"/>'
            # Date label below (show every few)
            if i % max(1, n // 6) == 0 or i == n - 1:
                label = date[2:7] if len(date) >= 7 else date
                svg += (
                    f'<text x="{xx:.1f}" y="{timeline_y + dot_r + 14:.1f}" text-anchor="middle" '
                    f'fill="#5a5650" font-size="8" font-family="\'JetBrains Mono\',monospace">'
                    f'{_esc(label)}</text>'
                )
        # Connecting line behind dots
        if n > 1:
            x_start = margin_l["left"]
            x_end = margin_l["left"] + (n - 1) * spacing
            svg += (
                f'<line x1="{x_start:.1f}" y1="{timeline_y:.1f}" '
                f'x2="{x_end:.1f}" y2="{timeline_y:.1f}" '
                f'stroke="rgba(255,255,255,0.06)" stroke-width="2"/>'
            )
    else:
        svg += (
            f'<text x="{left_w / 2}" y="{H / 2}" text-anchor="middle" '
            f'fill="#5a5650" font-size="12" font-family="\'JetBrains Mono\',monospace">'
            f'No phase data</text>'
        )

    # ── Right side: Inventory Days (bars) vs Gross Margin (line) ──
    r_margin = {"top": 30, "right": 60, "bottom": 40, "left": 55}
    r_offset = mid + 20
    rcw = W - r_offset - r_margin["right"] - r_margin["left"]
    rch = H - r_margin["top"] - r_margin["bottom"]

    if inv_signals or gm_signals:
        # Title
        svg += (
            f'<text x="{r_offset + r_margin["left"]}" y="{r_margin["top"] - 10}" '
            f'fill="#9a9690" font-size="10" font-weight="700" '
            f'font-family="\'DM Sans\',sans-serif" letter-spacing="0.08em">'
            f'INVENTORY DAYS vs GROSS MARGIN (MU)</text>'
        )

        # Inventory bars
        inv_dates = [s["date"] for s in inv_signals]
        inv_vals = [s["value"] for s in inv_signals]
        n_inv = len(inv_dates)

        if n_inv > 0:
            inv_min = 0
            inv_max = max(v for v in inv_vals if v is not None) * 1.2

            bar_area_w = rcw
            bar_w = max(4, bar_area_w / n_inv * 0.7)

            def inv_x(i):
                return r_offset + r_margin["left"] + (i + 0.5) / n_inv * bar_area_w

            def inv_y(v):
                return r_margin["top"] + (1 - (v - inv_min) / (inv_max - inv_min)) * rch

            # Y grid for inventory
            inv_ticks = _nice_ticks(inv_min, inv_max, 4)
            for t in inv_ticks:
                yy = inv_y(t)
                svg += (
                    f'<line x1="{r_offset + r_margin["left"]}" y1="{yy:.1f}" '
                    f'x2="{W - r_margin["right"]}" y2="{yy:.1f}" '
                    f'stroke="rgba(255,255,255,0.04)" stroke-width="1"/>'
                    f'<text x="{r_offset + r_margin["left"] - 8}" y="{yy + 4:.1f}" text-anchor="end" '
                    f'fill="#5a5650" font-size="9" font-family="\'JetBrains Mono\',monospace">'
                    f'{t:.0f}d</text>'
                )

            for i, v in enumerate(inv_vals):
                if v is None:
                    continue
                xx = inv_x(i)
                yy = inv_y(v)
                h = inv_y(inv_min) - yy
                svg += (
                    f'<rect x="{xx - bar_w / 2:.1f}" y="{yy:.1f}" '
                    f'width="{bar_w:.1f}" height="{h:.1f}" '
                    f'fill="{C_BLUE}" opacity="0.45" rx="1"/>'
                )

            # X-axis labels
            label_step = max(1, n_inv // 6)
            for i in range(0, n_inv, label_step):
                xx = inv_x(i)
                label = inv_dates[i][2:7] if len(inv_dates[i]) >= 7 else inv_dates[i]
                svg += (
                    f'<text x="{xx:.1f}" y="{H - 5}" text-anchor="middle" '
                    f'fill="#5a5650" font-size="8" font-family="\'JetBrains Mono\',monospace">'
                    f'{_esc(label)}</text>'
                )

        # Gross margin line (secondary y-axis)
        if gm_signals:
            gm_dates = [s["date"] for s in gm_signals]
            gm_vals = [s["value"] for s in gm_signals]
            n_gm = len(gm_dates)

            valid_gm = [v for v in gm_vals if v is not None]
            if valid_gm:
                gm_min = min(valid_gm) * 0.9
                gm_max = max(valid_gm) * 1.1

                # Map GM dates to the inv x-axis if possible, or use own axis
                # Use a shared date set for alignment
                all_r_dates = sorted(set(inv_dates) | set(gm_dates))
                n_all = len(all_r_dates)
                r_date_idx = {d: i for i, d in enumerate(all_r_dates)}

                def gm_x(i):
                    return r_offset + r_margin["left"] + (i + 0.5) / n_all * bar_area_w if n_inv > 0 else r_offset + r_margin["left"] + (i + 0.5) / n_gm * rcw

                def gm_y(v):
                    return r_margin["top"] + (1 - (v - gm_min) / (gm_max - gm_min)) * rch

                gm_points = []
                for d, v in zip(gm_dates, gm_vals):
                    if v is not None and d in r_date_idx:
                        gm_points.append((gm_x(r_date_idx[d]), gm_y(v)))

                if len(gm_points) >= 2:
                    svg += (
                        f'<path d="{_line_path(gm_points)}" fill="none" '
                        f'stroke="{C_GREEN}" stroke-width="2.2" stroke-linejoin="round"/>'
                    )
                    # Dots
                    for px, py in gm_points:
                        svg += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" fill="{C_GREEN}" stroke="#12121a" stroke-width="1.5"/>'

                # Secondary y-axis labels (right)
                gm_ticks = _nice_ticks(gm_min, gm_max, 4)
                for t in gm_ticks:
                    yy = gm_y(t)
                    svg += (
                        f'<text x="{W - r_margin["right"] + 8}" y="{yy + 4:.1f}" text-anchor="start" '
                        f'fill="{C_GREEN}" font-size="9" font-family="\'JetBrains Mono\',monospace">'
                        f'{t * 100:.0f}%</text>'
                    )
                svg += (
                    f'<text x="{W - 5}" y="{r_margin["top"] - 10}" text-anchor="end" '
                    f'fill="{C_GREEN}" font-size="8" letter-spacing="0.08em" '
                    f'font-family="\'DM Sans\',sans-serif">GROSS MARGIN</text>'
                )
    else:
        svg += (
            f'<text x="{(r_offset + W) / 2}" y="{H / 2}" text-anchor="middle" '
            f'fill="#5a5650" font-size="12" font-family="\'JetBrains Mono\',monospace">'
            f'No inventory/margin data</text>'
        )

    # Divider line
    svg += f'<line x1="{mid}" y1="{20}" x2="{mid}" y2="{H - 10}" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>'

    svg += "</svg>"
    return svg


def _panel5_divergence(composites) -> str:
    """Panel 5: Group A vs Group B Divergence."""
    W, H = 900, 280
    margin = {"top": 30, "right": 80, "bottom": 40, "left": 55}
    cw = W - margin["left"] - margin["right"]
    ch = H - margin["top"] - margin["bottom"]

    # Extract z-scores
    data = [(c["date"], c.get("group_a_zscore"), c.get("group_b_zscore"), c.get("divergence"))
            for c in composites if c.get("group_a_zscore") is not None or c.get("group_b_zscore") is not None]

    if not data:
        return _no_data_placeholder(W, H, "No composite z-score data")

    dates = [d for d, _, _, _ in data]
    a_vals = [a for _, a, _, _ in data]
    b_vals = [b for _, _, b, _ in data]
    div_vals = [dv for _, _, _, dv in data]
    n = len(dates)

    all_z = [v for v in a_vals + b_vals if v is not None]
    if not all_z:
        return _no_data_placeholder(W, H, "Z-scores are empty")

    z_min = min(all_z) - 0.3
    z_max = max(all_z) + 0.3

    def x_pos(i):
        return margin["left"] + (i / max(n - 1, 1)) * cw

    def y_pos(v):
        return margin["top"] + (1 - (v - z_min) / (z_max - z_min)) * ch

    svg = f'<svg viewBox="0 0 {W} {H}" style="width:100%;display:block;overflow:visible;">'

    # Grid
    z_ticks = _nice_ticks(z_min, z_max, 5)
    for t in z_ticks:
        yy = y_pos(t)
        svg += (
            f'<line x1="{margin["left"]}" y1="{yy:.1f}" '
            f'x2="{W - margin["right"]}" y2="{yy:.1f}" '
            f'stroke="rgba(255,255,255,0.04)" stroke-width="1"/>'
            f'<text x="{margin["left"] - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'fill="#5a5650" font-size="10" font-family="\'JetBrains Mono\',monospace">'
            f'{t:+.1f}</text>'
        )

    # Zero line
    zero_y = y_pos(0)
    svg += (
        f'<line x1="{margin["left"]}" y1="{zero_y:.1f}" '
        f'x2="{W - margin["right"]}" y2="{zero_y:.1f}" '
        f'stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="4,4"/>'
    )

    # Shaded area where divergence > 1.0
    for i in range(n - 1):
        dv = div_vals[i]
        if dv is not None and abs(dv) > 1.0:
            x1 = x_pos(i)
            x2 = x_pos(i + 1)
            svg += (
                f'<rect x="{x1:.1f}" y="{margin["top"]}" '
                f'width="{x2 - x1:.1f}" height="{ch}" '
                f'fill="{C_ORANGE}" opacity="0.08"/>'
            )

    # Lines: Group A
    a_points = [(x_pos(i), y_pos(v)) for i, v in enumerate(a_vals) if v is not None]
    if len(a_points) >= 2:
        svg += (
            f'<path d="{_line_path(a_points)}" fill="none" '
            f'stroke="{C_BLUE}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        last_x, last_y = a_points[-1]
        svg += (
            f'<text x="{last_x + 8:.1f}" y="{last_y + 4:.1f}" '
            f'fill="{C_BLUE}" font-size="10" font-weight="600" '
            f'font-family="\'DM Sans\',sans-serif">Group A</text>'
        )

    # Lines: Group B
    b_points = [(x_pos(i), y_pos(v)) for i, v in enumerate(b_vals) if v is not None]
    if len(b_points) >= 2:
        svg += (
            f'<path d="{_line_path(b_points)}" fill="none" '
            f'stroke="{C_GREEN}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        last_x, last_y = b_points[-1]
        svg += (
            f'<text x="{last_x + 8:.1f}" y="{last_y + 4:.1f}" '
            f'fill="{C_GREEN}" font-size="10" font-weight="600" '
            f'font-family="\'DM Sans\',sans-serif">Group B</text>'
        )

    # X-axis labels
    label_step = max(1, n // 8)
    for i in range(0, n, label_step):
        xx = x_pos(i)
        label = dates[i][2:7] if len(dates[i]) >= 7 else dates[i]
        svg += (
            f'<text x="{xx:.1f}" y="{H - 5}" text-anchor="middle" '
            f'fill="#5a5650" font-size="9" font-family="\'JetBrains Mono\',monospace">'
            f'{_esc(label)}</text>'
        )

    svg += "</svg>"
    return svg


def _panel6_health_cards(composites) -> str:
    """Panel 6: 3 Sub-Cycle Health Cards (HBM, DRAM, NAND)."""
    latest = composites[-1] if composites else {}
    prev = composites[-2] if len(composites) >= 2 else {}

    cards_config = [
        ("HBM", "hbm_score", "#9b6dff"),
        ("Commodity DRAM", "dram_score", C_BLUE),
        ("NAND", "nand_score", C_RED),
    ]

    html_parts = []
    for label, field, accent in cards_config:
        score = latest.get(field)
        prev_score = prev.get(field)

        # Determine trend
        if score is not None and prev_score is not None:
            diff = score - prev_score
            if diff > 0.1:
                arrow = "&#9650;"  # up triangle
                arrow_color = C_GREEN
            elif diff < -0.1:
                arrow = "&#9660;"  # down triangle
                arrow_color = C_RED
            else:
                arrow = "&#9654;"  # right triangle (flat)
                arrow_color = "#9a9690"
        else:
            arrow = "&#8212;"  # em dash
            arrow_color = "#5a5650"

        # Background color coding
        if score is not None:
            if score > 0.5:
                bg = "rgba(58, 181, 119, 0.08)"
                border_color = "rgba(58, 181, 119, 0.2)"
                val_color = C_GREEN
            elif score < -0.5:
                bg = "rgba(232, 93, 80, 0.08)"
                border_color = "rgba(232, 93, 80, 0.2)"
                val_color = C_RED
            else:
                bg = "rgba(255, 255, 255, 0.02)"
                border_color = "rgba(255, 255, 255, 0.06)"
                val_color = "#9a9690"
            score_display = f"{score:+.2f}"
        else:
            bg = "rgba(255, 255, 255, 0.02)"
            border_color = "rgba(255, 255, 255, 0.06)"
            val_color = "#5a5650"
            score_display = "N/A"

        html_parts.append(f"""
        <div style="flex:1;min-width:200px;background:{bg};border:1px solid {border_color};
                    border-radius:3px;padding:1.2rem;position:relative;overflow:hidden;">
          <div style="position:absolute;left:0;top:0;bottom:0;width:3px;background:{accent};"></div>
          <div style="font-size:0.6rem;text-transform:uppercase;letter-spacing:0.15em;
                      color:#5a5650;font-weight:700;margin-bottom:0.5rem;">{_esc(label)}</div>
          <div style="display:flex;align-items:baseline;gap:0.6rem;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:1.8rem;font-weight:500;
                        color:{val_color};">{score_display}</div>
            <div style="font-size:1.2rem;color:{arrow_color};">{arrow}</div>
          </div>
          <div style="font-size:0.65rem;color:#9a9690;margin-top:0.4rem;">z-score</div>
        </div>""")

    return "\n".join(html_parts)


# ── Utility ──────────────────────────────────────────────────────────

def _nice_ticks(lo, hi, n_ticks=5):
    """Generate nice tick values for an axis."""
    if lo == hi:
        return [lo]
    raw_step = (hi - lo) / max(n_ticks - 1, 1)
    # Round to a nice number
    import math
    magnitude = 10 ** math.floor(math.log10(max(abs(raw_step), 1e-10)))
    residual = raw_step / magnitude
    if residual <= 1.5:
        nice = 1
    elif residual <= 3:
        nice = 2
    elif residual <= 7:
        nice = 5
    else:
        nice = 10
    step = nice * magnitude
    if step == 0:
        return [lo]

    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.01:
        if v >= lo - step * 0.5:
            ticks.append(round(v, 10))
        v += step
    return ticks if ticks else [lo, hi]


def _fmt_val_axis(v):
    """Format value for axis labels (auto-scale to M/B/K)."""
    av = abs(v)
    if av >= 1e9:
        return f"{v / 1e9:.1f}B"
    if av >= 1e6:
        return f"{v / 1e6:.1f}M"
    if av >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:.1f}"


# ── HTML Assembly ────────────────────────────────────────────────────

def _generate_descriptions(
    price_data: dict,
    value_signals: list,
    ratio_signals: list,
    spot_data: dict,
    composites: list,
    inv_signals: list,
    gm_signals: list,
    header_data: dict,
) -> dict:
    """Generate dynamic description text for each panel using actual data."""
    descs = {}

    # ── Panel 1 ──
    p1_parts = []
    for ticker, label in [
        ("MU", "MU"), ("WDC", "WDC"), ("005930_KS", "Samsung"),
        ("000660_KS", "SK Hynix"), ("SOXX", "SOXX"),
    ]:
        # price_data keys are ticker names (no "price_" prefix), values are tuples (date, value)
        series = price_data.get(ticker, [])
        if series:
            latest = series[-1][1]
            first = series[0][1]
            chg = (latest / first - 1) * 100 if first else 0
            arrow = "signal-up" if chg > 0 else "signal-dn"
            p1_parts.append(f'<strong>{label}</strong> <span class="{arrow}">{chg:+.0f}%</span>')
    n_months = len(price_data.get("MU", []))
    descs["p1"] = (
        f'{n_months}-month returns (start to latest): {" &middot; ".join(p1_parts)}. '
        f'<em>MU vs SOXX relative performance</em> tracks the 2nd derivative — '
        f'when MU underperforms SOXX, it signals peak positioning is fading. '
        f'SK Hynix divergence from MU in 2024-25 reflects HBM leadership premium.'
    )

    # ── Panel 2 ──
    if value_signals:
        latest_val = value_signals[-1]["value"]
        trough_val = min(s["value"] for s in value_signals)
        trough_date = min(value_signals, key=lambda s: s["value"])["date"][:7]
        yoy = ""
        if len(value_signals) >= 13:
            curr = value_signals[-1]["value"]
            prev = value_signals[-13]["value"]
            if prev > 0:
                yoy_pct = (curr / prev - 1) * 100
                arrow = "signal-up" if yoy_pct > 0 else "signal-dn"
                yoy = f' YoY: <span class="{arrow}">{yoy_pct:+.0f}%</span>.'
        ratio_note = ""
        if ratio_signals and len(ratio_signals) >= 2:
            r_latest = ratio_signals[-1]["value"]
            r_prev = ratio_signals[-6]["value"] if len(ratio_signals) >= 6 else ratio_signals[0]["value"]
            if r_prev > 0:
                r_chg = (r_latest / r_prev - 1) * 100
                if r_chg > 10:
                    ratio_note = (
                        f' <em>Value/volume ratio rising {r_chg:+.0f}%</em> — '
                        f'export value up but volume flat/down = HBM/premium mix improving, not volume expansion.'
                    )
                elif r_chg < -10:
                    ratio_note = (
                        f' Value/volume ratio falling {r_chg:+.0f}% — '
                        f'volume-driven growth, commodity mix.'
                    )
        descs["p2"] = (
            f'Korean memory exports (HS 854232) are the <em>leading indicator</em> — they move 1 quarter ahead of Micron revenue. '
            f'Latest: <strong>${latest_val / 1e6:.1f}M</strong>. '
            f'Trough was ${trough_val / 1e6:.1f}M ({trough_date}).{yoy}{ratio_note}'
        )
    else:
        descs["p2"] = "Korean memory exports (HS 854232) — leading indicator, tracks 1 quarter ahead of Micron revenue. No data loaded."

    # ── Panel 3 ──
    p3_parts = []
    for metric, label in [("ddr4_spot_price", "DDR4"), ("ddr5_spot_price", "DDR5"), ("nand_spot_price", "NAND")]:
        series = spot_data.get(metric, [])
        if series:
            # spot_data series are tuples (date, value)
            latest = series[-1][1]
            trough = min(s[1] for s in series if s[1])
            mult = latest / trough if trough > 0 else 0
            p3_parts.append(f'<strong>{label}</strong> ${latest:.2f} ({mult:.1f}x from trough)')
    descs["p3"] = (
        f'Spot/retail prices normalized to 100. Current levels: {" &middot; ".join(p3_parts)}. '
        f'The 2025 parabolic spike was driven by Samsung/SK Hynix reallocating legacy DDR4 capacity to HBM + CXMT sanctions. '
        f'<em>NAND typically lags DRAM by 1-2 quarters</em> — watch for NAND to catch up or diverge.'
    ) if p3_parts else "Spot/retail DRAM + SSD pricing — DDR4, DDR5, NAND normalized to 100. No data loaded."

    # ── Panel 4 ──
    phase_counts = {}
    for c in composites:
        p = c.get("cycle_phase")
        if p:
            phase_counts[p] = phase_counts.get(p, 0) + 1
    phase_summary = ", ".join(f'{PHASE_LABELS.get(k, k)}: {v}' for k, v in sorted(phase_counts.items(), key=lambda x: -x[1]))
    inv_note = ""
    if inv_signals:
        inv_latest = inv_signals[-1]["value"]
        inv_peak = max(s["value"] for s in inv_signals)
        inv_peak_date = max(inv_signals, key=lambda s: s["value"])["date"][:7]
        inv_note = (
            f' MU inventory days: <strong>{inv_latest:.0f}</strong> (peaked at {inv_peak:.0f} in {inv_peak_date}). '
            f'Declining inventory = demand absorbing supply — classic recovery/expansion signal.'
        )
    gm_note = ""
    if gm_signals:
        gm_latest = gm_signals[-1]["value"]
        gm_low = min(s["value"] for s in gm_signals)
        gm_note = (
            f' Gross margin: <strong>{gm_latest * 100:.0f}%</strong> (cycle low was {gm_low * 100:.0f}%). '
        )
        if gm_latest > 0.40:
            gm_note += '<em>Above 40% historically signals late cycle</em> — capex response builds here.'
        elif gm_latest < 0.20:
            gm_note += 'Below 20% = trough territory, early recovery ahead.'
    descs["p4"] = (
        f'<strong>Left:</strong> Cycle phase timeline — {phase_summary}. '
        f'Phase is classified using Korean export YoY trajectory + MU gross margin + capex/revenue ratio + inventory days. '
        f'<strong>Right:</strong> Inventory-margin inverse relationship is the core cycle mechanism.{inv_note}{gm_note}'
    )

    # ── Panel 5 ──
    if composites:
        latest_c = composites[-1]
        ga = latest_c.get("group_a_zscore", 0)
        gb = latest_c.get("group_b_zscore", 0)
        div = latest_c.get("divergence", 0)
        div_count = sum(1 for c in composites if abs(c.get("divergence", 0) or 0) >= 1.0)
        div_direction = ""
        if div and abs(div) >= 0.5:
            if div > 0:
                div_direction = ' Prices leading fundamentals — could signal speculative excess or early anticipation.'
            else:
                div_direction = ' Fundamentals leading prices — potential catch-up opportunity in stocks.'
        descs["p5"] = (
            f'<strong>Group A</strong> (price momentum: stocks + spot prices) z-score: <span class="{"signal-up" if ga > 0 else "signal-dn"}">{ga:+.2f}</span>. '
            f'<strong>Group B</strong> (fundamentals: Korean exports 1.5x weight + MU financials) z-score: <span class="{"signal-up" if gb > 0 else "signal-dn"}">{gb:+.2f}</span>. '
            f'Divergence: <strong>{div:+.2f}</strong>. '
            f'Orange shading marks {div_count} months where divergence exceeded &plusmn;1.0.{div_direction} '
            f'<em>Primary signal = divergence between the two groups, not a blended composite.</em>'
        )
    else:
        descs["p5"] = "Group A (price momentum) vs Group B (fundamentals) z-score divergence. No composite data."

    # ── Panel 6 ──
    if composites:
        latest_c = composites[-1]
        hbm = latest_c.get("hbm_score", 0) or 0
        dram = latest_c.get("dram_score", 0) or 0
        nand = latest_c.get("nand_score", 0) or 0
        descs["p6"] = (
            f'Three distinct sub-cycles with different drivers — the headline phase can mask divergent dynamics underneath. '
            f'<strong>HBM</strong> (<span class="{"signal-up" if hbm > 0 else "signal-dn"}">{hbm:+.2f}</span>): AI/hyperscaler capex driven. '
            f'<strong>Commodity DRAM</strong> (<span class="{"signal-up" if dram > 0 else "signal-dn"}">{dram:+.2f}</span>): traditional inventory cycle, DDR4/DDR5 spot. '
            f'<strong>NAND</strong> (<span class="{"signal-up" if nand > 0 else "signal-dn"}">{nand:+.2f}</span>): often lags DRAM, WDC is the cleaner pure-play. '
            f'<em>Critical false signal risk: HBM margins can mask commodity DRAM weakness in blended financials.</em>'
        )
    else:
        descs["p6"] = "Three sub-cycles: HBM (AI demand), Commodity DRAM (inventory cycle), NAND (lags DRAM). No data."

    return descs


def _build_html(
    header_data: dict,
    panel1_svg: str,
    panel2_svg: str,
    panel3_svg: str,
    panel4_svg: str,
    panel5_svg: str,
    panel6_html: str,
    descs: dict = None,
    freshness: list = None,
) -> str:
    """Assemble final HTML document."""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")

    # Header data
    phase = header_data.get("cycle_phase", "unknown") if header_data else "unknown"
    confidence = header_data.get("phase_confidence") if header_data else None
    phase_label = PHASE_LABELS.get(phase, "Unknown")
    phase_color = PHASE_COLORS.get(phase, "#555")
    implication = PHASE_INVESTMENT.get(phase, "Insufficient data")
    conf_display = f"{confidence * 100:.0f}%" if confidence is not None else "N/A"
    last_date = header_data.get("date", "N/A") if header_data else "N/A"

    # Build freshness chips HTML
    freshness_html = ""
    if freshness:
        chips = []
        for f in freshness:
            d = f["latest_date"]
            src = _esc(f["source"])
            # Color: green if within 35 days, orange if within 90, red if older
            from datetime import datetime as _dt
            try:
                days_old = (_dt.strptime(today, "%Y-%m-%d") - _dt.strptime(d, "%Y-%m-%d")).days
            except Exception:
                days_old = 999
            if days_old <= 35:
                dot_color = "var(--green)"
            elif days_old <= 90:
                dot_color = "var(--orange)"
            else:
                dot_color = "var(--red)"
            count_str = f" ({f['n_rows']})" if f.get("n_rows") else ""
            chips.append(
                f'<span class="fresh-chip">'
                f'<span class="fresh-dot" style="background:{dot_color}"></span>'
                f'{src}{count_str}: <strong>{d}</strong>'
                f'</span>'
            )
        freshness_html = '<div class="freshness-row">' + "".join(chips) + '</div>'

    # Unpack panel descriptions
    desc_p1 = descs.get("p1", "") if descs else ""
    desc_p2 = descs.get("p2", "") if descs else ""
    desc_p3 = descs.get("p3", "") if descs else ""
    desc_p4 = descs.get("p4", "") if descs else ""
    desc_p5 = descs.get("p5", "") if descs else ""
    desc_p6 = descs.get("p6", "") if descs else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memory Cycle Tracker — Dashboard</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0a0a0f;--bg2:#12121a;--bg3:#1a1a25;
  --text:#e8e4dc;--text2:#9a9690;--text3:#5a5650;
  --gold:#c9a96e;--gold2:#a08040;
  --green:#3ab577;--red:#e85d50;--blue:#4a8ef5;--orange:#e8a94e;
}}
html{{font-size:14px}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI','SF Mono',Consolas,'Liberation Mono',Menlo,monospace;min-height:100vh;overflow-x:hidden}}
body::before{{content:'';position:fixed;inset:0;background:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.025'/%3E%3C/svg%3E");pointer-events:none;z-index:0}}

.container{{max-width:1400px;margin:0 auto;padding:2rem;position:relative;z-index:1}}

header{{margin-bottom:2rem;border-bottom:1px solid rgba(201,169,110,0.15);padding-bottom:1.5rem}}
header h1{{font-size:2rem;font-weight:700;letter-spacing:-0.02em;color:var(--text);margin-bottom:0.3rem}}
header h1 span{{color:var(--gold);font-style:italic}}
header .subtitle{{font-size:0.85rem;color:var(--text2);letter-spacing:0.08em;text-transform:uppercase;font-weight:500}}
header .meta{{margin-top:0.5rem;font-size:0.7rem;color:var(--text3)}}

.phase-banner{{
  display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap;
  background:var(--bg2);border:1px solid rgba(255,255,255,0.04);border-radius:3px;
  padding:1.2rem 1.5rem;margin-bottom:2rem;
}}
.phase-dot{{width:28px;height:28px;border-radius:50%;flex-shrink:0;box-shadow:0 0 12px var(--dot-glow,transparent)}}
.phase-info{{flex:1;min-width:200px}}
.phase-label{{font-size:1.1rem;font-weight:700;letter-spacing:0.03em}}
.phase-conf{{font-size:0.75rem;color:var(--text2);margin-top:0.15rem}}
.phase-implication{{
  font-size:0.8rem;color:var(--gold);padding:0.4rem 0.8rem;
  border:1px solid rgba(201,169,110,0.2);border-radius:2px;
  background:rgba(201,169,110,0.05);white-space:nowrap;
}}
.phase-updated{{font-size:0.65rem;color:var(--text3);margin-left:auto;text-align:right}}

.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:1.5rem}}
@media(max-width:900px){{.grid-2{{grid-template-columns:1fr}}}}

.panel{{
  background:var(--bg2);border:1px solid rgba(255,255,255,0.04);border-radius:3px;
  padding:1.2rem;overflow:hidden;
}}
.panel-full{{margin-bottom:1.5rem}}
.panel-title{{
  font-size:0.7rem;font-weight:700;color:var(--text2);letter-spacing:0.1em;
  text-transform:uppercase;margin-bottom:0.8rem;padding-bottom:0.4rem;
  border-bottom:1px solid rgba(255,255,255,0.04);
}}
.panel-title span{{color:var(--gold)}}
.panel-desc{{
  font-size:0.72rem;line-height:1.6;color:var(--text3);
  margin-top:0.8rem;padding-top:0.6rem;
  border-top:1px solid rgba(255,255,255,0.03);
}}
.panel-desc strong{{color:var(--text2);font-weight:600}}
.panel-desc em{{color:var(--gold2);font-style:normal}}
.panel-desc .signal-up{{color:var(--green)}}
.panel-desc .signal-dn{{color:var(--red)}}

.health-cards{{display:flex;gap:1rem;flex-wrap:wrap}}

.freshness-row{{
  display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;
  margin-bottom:1.5rem;padding:0.7rem 1rem;
  background:var(--bg2);border:1px solid rgba(255,255,255,0.04);border-radius:3px;
}}
.fresh-chip{{
  display:inline-flex;align-items:center;gap:0.3rem;
  font-size:0.65rem;color:var(--text2);
  padding:0.2rem 0.5rem;background:var(--bg3);border-radius:2px;
  white-space:nowrap;
}}
.fresh-chip strong{{color:var(--text);font-weight:600}}
.fresh-dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0}}

.footer{{margin-top:2rem;text-align:center;font-size:0.65rem;color:var(--text3);letter-spacing:0.05em}}
.footer span{{color:var(--gold2)}}
</style>
</head>
<body>

<div class="container">
  <header>
    <h1>Memory Cycle <span>Tracker</span></h1>
    <div class="subtitle">Semiconductor Memory — Cycle Phase &amp; Signal Dashboard</div>
    <div class="meta">MU &middot; WDC &middot; Samsung &middot; SK Hynix &middot; Korean Exports &middot; Spot Pricing &middot; Fundamentals</div>
  </header>

  <!-- Phase Banner -->
  <div class="phase-banner">
    <div class="phase-dot" style="background:{phase_color};--dot-glow:{phase_color};"></div>
    <div class="phase-info">
      <div class="phase-label" style="color:{phase_color};">{_esc(phase_label)}</div>
      <div class="phase-conf">Confidence: {conf_display}</div>
    </div>
    <div class="phase-implication">{_esc(implication)}</div>
    <div class="phase-updated">
      Data: {_esc(last_date)}<br>
      Generated: {now}
    </div>
  </div>

  <!-- Data Freshness -->
  {freshness_html}

  <!-- Panel 1: Stock Performance (full width) -->
  <div class="panel panel-full">
    <div class="panel-title">Panel 1 &mdash; <span>Memory Stock Performance</span> (normalized to 100)</div>
    {panel1_svg}
    <div class="panel-desc">{desc_p1}</div>
  </div>

  <!-- Panel 2 & 3: side by side -->
  <div class="grid-2">
    <div class="panel">
      <div class="panel-title">Panel 2 &mdash; <span>Korean Memory Exports</span></div>
      {panel2_svg}
      <div class="panel-desc">{desc_p2}</div>
    </div>
    <div class="panel">
      <div class="panel-title">Panel 3 &mdash; <span>Spot / Retail Pricing</span> (DRAM + NAND, normalized)</div>
      {panel3_svg}
      <div class="panel-desc">{desc_p3}</div>
    </div>
  </div>

  <!-- Panel 4: Cycle Phase + Inv/GM (full width) -->
  <div class="panel panel-full">
    <div class="panel-title">Panel 4 &mdash; <span>Cycle Phase Timeline</span> + Inventory Days vs Gross Margin</div>
    {panel4_svg}
    <div class="panel-desc">{desc_p4}</div>
  </div>

  <!-- Panel 5: Divergence (full width) -->
  <div class="panel panel-full">
    <div class="panel-title">Panel 5 &mdash; <span>Group A vs Group B</span> Z-Score Divergence
      <span style="font-weight:400;font-size:0.6rem;color:var(--text3);margin-left:0.5rem;">
        Orange shading = divergence &gt; 1.0
      </span>
    </div>
    {panel5_svg}
    <div class="panel-desc">{desc_p5}</div>
  </div>

  <!-- Panel 6: Health Cards -->
  <div class="panel panel-full">
    <div class="panel-title">Panel 6 &mdash; <span>Sub-Cycle Health</span></div>
    <div class="health-cards">
      {panel6_html}
    </div>
    <div class="panel-desc">{desc_p6}</div>
  </div>

  <div class="footer">
    Source: <span>Memory Cycle Tracker</span> &middot; yfinance &middot; Korea Customs &middot; SEC XBRL &middot; Spot Markets &middot; Updated {now}
  </div>
</div>

</body>
</html>"""


# ── Main entry point ─────────────────────────────────────────────────

def run():
    """Generate the Memory Cycle dashboard HTML."""
    print("  [Dashboard] Loading data from SQLite...")

    # Load all data
    print("  [Dashboard] Generating panel 1: Stock Performance...")
    price_data = _load_price_data()
    panel1 = _panel1_stock_performance(price_data)

    print("  [Dashboard] Generating panel 2: Korean Exports...")
    value_signals, ratio_signals = _load_korea_exports()
    panel2 = _panel2_korea_exports(value_signals, ratio_signals)

    print("  [Dashboard] Generating panel 3: Spot Pricing...")
    spot_data = _load_spot_pricing()
    panel3 = _panel3_spot_pricing(spot_data)

    print("  [Dashboard] Generating panel 4: Cycle Phase + Inventory/Margin...")
    composites = _load_composites()
    inv_signals, gm_signals = _load_inventory_margin()
    panel4 = _panel4_cycle_phase_and_inv_gm(composites, inv_signals, gm_signals)

    print("  [Dashboard] Generating panel 5: Group A vs B Divergence...")
    panel5 = _panel5_divergence(composites)

    print("  [Dashboard] Generating panel 6: Sub-Cycle Health Cards...")
    panel6 = _panel6_health_cards(composites)

    print("  [Dashboard] Loading header data...")
    header = _load_latest_composite()

    print("  [Dashboard] Generating panel descriptions...")
    descs = _generate_descriptions(price_data, value_signals, ratio_signals, spot_data,
                                   composites, inv_signals, gm_signals, header)

    print("  [Dashboard] Loading data freshness...")
    freshness = _load_freshness()

    print("  [Dashboard] Assembling HTML...")
    html = _build_html(header, panel1, panel2, panel3, panel4, panel5, panel6,
                       descs=descs, freshness=freshness)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"  [Dashboard] Written to {OUTPUT_PATH}")
    print(f"  [Dashboard] File size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")

    return str(OUTPUT_PATH)


if __name__ == "__main__":
    run()
