# Chart Generation Specifications

Reference for generating financial charts in equity research. Adapted from Anthropic FSI equity-research plugin.

## Chart Library: 25 Standard + 10 Optional

### Revenue & Growth Charts
1. **Revenue Trend** — Line chart, quarterly, with YoY growth rate on secondary axis
2. **Revenue by Product/Segment** — Stacked area chart (shows mix evolution)
3. **Revenue by Geography** — Stacked bar chart (shows geographic diversification)
4. **Revenue Growth Decomposition** — Waterfall: Volume + Price/Mix + FX + Acquisitions = Total
5. **Revenue Beat/Miss History** — Bar chart: actual vs. consensus by quarter (last 8Q)

### Profitability Charts
6. **Margin Trend** — Multi-line: Gross, Operating, Net margins (quarterly)
7. **Margin Bridge** — Waterfall: Q-1 margin → headwinds/tailwinds → Q margin
8. **OpEx Breakdown** — Stacked bar: R&D, SG&A, Other as % of revenue
9. **EBITDA & FCF Trend** — Dual-axis: EBITDA bars + FCF line
10. **Earnings Bridge** — Waterfall: Prior EPS → Revenue/Margin/Tax/Shares → Current EPS

### Valuation Charts
11. **Forward P/E Trend** — Line chart: NTM P/E over 3-5 years with mean ± 1σ bands
12. **EV/EBITDA vs. Peers** — Horizontal bar chart: target company highlighted
13. **PEG Scatter** — X: EPS growth, Y: P/E, bubble size: market cap (peers + target)
14. **DCF Sensitivity Heatmap** — 2D heatmap: WACC vs. Terminal Growth → Implied Price
15. **Valuation Football Field** — Horizontal range chart: DCF, Comps, Precedent Tx ranges

### Operating Metrics Charts
16. **Market Share Trend** — Area chart: company vs. key competitors over time
17. **Customer/Volume Metrics** — Bar + line: unit volumes + pricing
18. **Backlog/Pipeline** — Stacked bar: by stage/product
19. **Working Capital Efficiency** — Multi-line: DSO, DIO, DPO over time
20. **CapEx & D&A Trend** — Grouped bar with CapEx intensity line

### Comparative Charts
21. **Indexed Stock Price** — Multi-line: target + peers + index, indexed to 100
22. **Relative Valuation Scatter** — X: Growth, Y: Multiple, color: Margin
23. **Revenue Growth Comparison** — Grouped bar: target vs. peers by quarter
24. **Margin Comparison** — Grouped bar: target vs. peers
25. **FCF Yield Comparison** — Bar chart: target vs. peers

### Optional / Situational
26. **TAM/SAM/SOM Funnel** — Funnel or nested pie chart
27. **Ownership Structure** — Pie: institutional, insider, retail
28. **Short Interest Trend** — Area chart with stock price overlay
29. **Analyst Rating Distribution** — Stacked bar: Buy/Hold/Sell over time
30. **Earnings Revision Trend** — Line: NTM EPS consensus revision over 12 months
31. **Dividend History** — Bar: DPS with yield line
32. **Debt Maturity Profile** — Bar chart by year
33. **Correlation Matrix** — Heatmap of stock correlations within peer group
34. **Seasonality Pattern** — Monthly average returns heatmap
35. **Options Skew** — Line: implied vol by strike for nearest expiry

## Matplotlib Code Templates

### Chart 2: Revenue by Segment (Stacked Area)
```python
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

def plot_revenue_by_segment(quarters, segments_data, segment_names, company_name):
    """
    quarters: list of strings like ['Q1 24', 'Q2 24', ...]
    segments_data: dict of {segment_name: [values]}
    segment_names: list of segment names (bottom to top)
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    colors = ['#1f4e79', '#2e75b6', '#5ba3d9', '#9cc5e8', '#d4e6f1']

    values = [segments_data[name] for name in segment_names]
    ax.stackplot(range(len(quarters)), *values, labels=segment_names, colors=colors[:len(segment_names)])

    ax.set_xticks(range(len(quarters)))
    ax.set_xticklabels(quarters, rotation=45)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x/1e9:.1f}B' if x >= 1e9 else f'${x/1e6:.0f}M'))
    ax.set_title(f'{company_name} — Revenue by Segment', fontsize=14, fontweight='bold')
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    return fig
```

### Chart 14: DCF Sensitivity Heatmap
```python
import matplotlib.pyplot as plt
import numpy as np

def plot_dcf_sensitivity(wacc_range, growth_range, implied_prices, current_price, company_name):
    """
    wacc_range: list of WACC values (e.g., [0.08, 0.085, 0.09, ...])
    growth_range: list of terminal growth rates (e.g., [0.02, 0.025, 0.03])
    implied_prices: 2D array [wacc_idx][growth_idx]
    current_price: float
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    data = np.array(implied_prices)

    # Color based on upside/downside vs current price
    cmap = plt.cm.RdYlGn  # Red (downside) to Green (upside)
    norm = plt.Normalize(vmin=data.min(), vmax=data.max())

    im = ax.imshow(data, cmap=cmap, norm=norm, aspect='auto')

    # Labels
    ax.set_xticks(range(len(growth_range)))
    ax.set_xticklabels([f'{g*100:.1f}%' for g in growth_range])
    ax.set_yticks(range(len(wacc_range)))
    ax.set_yticklabels([f'{w*100:.1f}%' for w in wacc_range])

    # Annotate cells
    for i in range(len(wacc_range)):
        for j in range(len(growth_range)):
            price = data[i, j]
            color = 'white' if abs(price - current_price) > (data.max() - data.min()) * 0.3 else 'black'
            weight = 'bold' if abs(price - current_price) < 2 else 'normal'
            ax.text(j, i, f'${price:.0f}', ha='center', va='center', color=color, fontweight=weight)

    ax.set_xlabel('Terminal Growth Rate', fontsize=12)
    ax.set_ylabel('WACC', fontsize=12)
    ax.set_title(f'{company_name} — DCF Sensitivity (Current: ${current_price:.0f})', fontsize=14, fontweight='bold')
    fig.colorbar(im, ax=ax, label='Implied Share Price ($)')
    plt.tight_layout()
    return fig
```

### Chart 15: Valuation Football Field
```python
import matplotlib.pyplot as plt

def plot_football_field(methods, current_price, company_name):
    """
    methods: list of dicts: [{'name': 'DCF', 'low': 42, 'mid': 55, 'high': 68}, ...]
    current_price: float
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    colors = ['#2e75b6', '#5ba3d9', '#9cc5e8', '#c5d9a4']
    y_positions = range(len(methods))

    for i, method in enumerate(methods):
        low, mid, high = method['low'], method['mid'], method['high']
        # Range bar
        ax.barh(i, high - low, left=low, height=0.4, color=colors[i % len(colors)], alpha=0.7)
        # Midpoint marker
        ax.plot(mid, i, 'D', color='black', markersize=8, zorder=5)
        # Labels
        ax.text(low - 1, i, f'${low:.0f}', ha='right', va='center', fontsize=10)
        ax.text(high + 1, i, f'${high:.0f}', ha='left', va='center', fontsize=10)

    # Current price line
    ax.axvline(x=current_price, color='red', linestyle='--', linewidth=2, label=f'Current: ${current_price:.0f}')

    ax.set_yticks(y_positions)
    ax.set_yticklabels([m['name'] for m in methods], fontsize=12)
    ax.set_xlabel('Share Price ($)', fontsize=12)
    ax.set_title(f'{company_name} — Valuation Summary', fontsize=14, fontweight='bold')
    ax.legend(loc='upper right')
    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout()
    return fig
```

## Chart Style Guide

- **Font:** Use system default (matplotlib default or `'DejaVu Sans'`)
- **Colors:** Professional palette — navy, blue, steel, muted tones. Avoid bright red/green except for emphasis.
- **Size:** 12×7 inches for standard, 12×5 for horizontal bars, 10×8 for heatmaps
- **Title:** `fontsize=14, fontweight='bold'`
- **Grid:** `alpha=0.3` on primary axis only
- **Currency:** Format as `$XM` or `$X.XB` with appropriate scaling
- **Percentage:** Format as `X.X%`
- **Source line:** Add `fig.text(0.99, 0.01, 'Source: Company filings, estimates', ha='right', fontsize=8, alpha=0.5)`
