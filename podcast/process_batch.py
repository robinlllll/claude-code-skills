#!/usr/bin/env python3
"""Batch process podcast files for investment insight extraction."""

import sys
import re
from pathlib import Path
from datetime import datetime
import yaml

# Add shared modules to path
sys.path.insert(0, str(Path.home() / ".claude" / "skills"))


def read_file_safe(filepath):
    """Read file with UTF-8 encoding."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def write_file_safe(filepath, content):
    """Write file with UTF-8 encoding."""
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def extract_frontmatter(content):
    """Extract YAML frontmatter from markdown content."""
    pattern = r"^---\n(.*?)\n---\n(.*)"
    match = re.match(pattern, content, re.DOTALL)
    if match:
        fm_text = match.group(1)
        body = match.group(2)
        try:
            fm = yaml.safe_load(fm_text)
            return fm, body
        except:
            return {}, content
    return {}, content


def detect_tickers_simple(text):
    """Simple ticker detection from text."""
    tickers = set()

    # Common patterns
    ticker_map = {
        "台积电": "TSM",
        "TSMC": "TSM",
        "英伟达": "NVDA",
        "Nvidia": "NVDA",
        "NVIDIA": "NVDA",
        "微软": "MSFT",
        "Microsoft": "MSFT",
        "苹果": "AAPL",
        "Apple": "AAPL",
        "Google": "GOOGL",
        "Alphabet": "GOOGL",
        "Meta": "META",
        "Facebook": "META",
        "Amazon": "AMZN",
        "亚马逊": "AMZN",
        "博通": "AVGO",
        "Broadcom": "AVGO",
        "OpenAI": "OPENAI",
        "Anthropic": "ANTHROPIC",
        "Intel": "INTC",
        "英特尔": "INTC",
        "AMD": "AMD",
        "长江存储": "YMTC",
        "YMTC": "YMTC",
        "Samsung": "SSNLF",
        "三星": "SSNLF",
        "Cisco": "CSCO",
        "思科": "CSCO",
        "Arista": "ANET",
        "Applied Materials": "AMAT",
        "AMAT": "AMAT",
        "Micron": "MU",
        "美光": "MU",
        "Burger King": "QSR",
        "Tim Hortons": "QSR",
        "Kraft Heinz": "KHC",
        "Skechers": "SKX",
        "Hunter Douglas": "HD",
        "3G Capital": "3G",
        "Nebius": "NBIS",
        "CoreWeave": "COREWEAVE",
        "Astera Labs": "ALAB",
    }

    for key, ticker in ticker_map.items():
        if key in text:
            tickers.add(ticker)

    # $TICKER pattern
    dollar_tickers = re.findall(r"\$([A-Z]{2,5})", text)
    tickers.update(dollar_tickers)

    return sorted(list(tickers))


def extract_topics(text, tickers):
    """Extract investment topics from text."""
    topics = []

    topic_keywords = {
        "AI Infrastructure": [
            "AI",
            "算力",
            "数据中心",
            "data center",
            "GPU",
            "compute",
        ],
        "Semiconductors": ["半导体", "semiconductor", "芯片", "chip", "wafer"],
        "Memory": ["存储", "memory", "HBM", "DRAM", "NAND"],
        "Software/SaaS": ["软件", "software", "SaaS", "cloud"],
        "Private Equity": ["私募", "private equity", "3G", "buyout"],
        "AI Models": ["模型", "model", "LLM", "foundation model"],
        "Supply Chain": ["供应链", "supply chain", "材料", "materials"],
        "Valuation": ["估值", "valuation", "DCF", "multiple"],
        "Market Cycles": ["周期", "cycle", "bull market", "bear market"],
    }

    for topic, keywords in topic_keywords.items():
        for keyword in keywords:
            if keyword.lower() in text.lower():
                topics.append(topic)
                break

    return list(set(topics))


def assess_portfolio_relevance(tickers):
    """Assess portfolio relevance based on tickers."""
    # High priority tickers from portfolio
    high_priority = ["NVDA", "TSM", "MSFT", "GOOGL", "META", "AMZN", "AAPL"]

    if any(t in high_priority for t in tickers):
        return "high"
    elif len(tickers) > 0:
        return "medium"
    else:
        return "low"


def generate_insights_section(content, tickers, topics, relevance):
    """Generate investment insights section."""
    insights = []

    insights.append("## 🎯 Investment Insights (Auto-Generated)\n")

    # Ticker mentions
    if tickers:
        ticker_links = ", ".join([f"[[{t}]]" for t in tickers])
        insights.append(f"**Tickers Mentioned:** {ticker_links}")
    else:
        insights.append("**Tickers Mentioned:** None detected")

    # Topics
    if topics:
        insights.append(f"**Topics:** {', '.join(topics)}")

    # Portfolio relevance
    relevance_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    insights.append(
        f"**Portfolio Relevance:** {relevance_emoji.get(relevance, '🟢')} {relevance.capitalize()}\n"
    )

    # Extract key points from summary/takeaways
    insights.append("### 关键投资论点")
    summary_section = (
        content.split("# Takeaways")[0] if "# Takeaways" in content else content[:2000]
    )

    # Look for bullet points in takeaways
    if "# Takeaways" in content:
        takeaways = content.split("# Takeaways")[1].split("#")[0]
        bullets = [
            line.strip("* ").strip()
            for line in takeaways.split("\n")
            if line.strip().startswith("*")
        ]
        for i, bullet in enumerate(bullets[:5], 1):  # Top 5
            if bullet:
                insights.append(
                    f"{i}. {bullet[:200]}{'...' if len(bullet) > 200 else ''}"
                )

    insights.append("\n---\n")

    return "\n".join(insights)


def update_frontmatter(fm, tickers, topics, relevance):
    """Update frontmatter with enrichment data."""
    fm["status"] = "已处理"
    fm["enriched"] = True
    fm["enriched_date"] = datetime.now().strftime("%Y-%m-%d")

    if tickers:
        fm["tickers"] = tickers
    if topics:
        fm["topics"] = topics

    fm["portfolio_relevance"] = relevance

    # Update tags
    if "tags" not in fm:
        fm["tags"] = []
    if "enriched" not in fm["tags"]:
        fm["tags"].append("enriched")

    return fm


def process_podcast_file(filepath):
    """Process a single podcast file."""
    print(f"\n[*] Processing: {Path(filepath).name}")

    try:
        # Read file
        content = read_file_safe(filepath)

        # Extract frontmatter
        fm, body = extract_frontmatter(content)

        # Check if already enriched
        if fm.get("enriched"):
            print(f"  [WARN]  Already enriched (enriched_date: {fm.get('enriched_date')})")
            return {"status": "skipped", "reason": "already_enriched"}

        # Detect tickers
        tickers = detect_tickers_simple(content)
        print(
            f"  [OK] Detected {len(tickers)} tickers: {', '.join(tickers) if tickers else 'None'}"
        )

        # Extract topics
        topics = extract_topics(content, tickers)
        print(
            f"  [OK] Extracted {len(topics)} topics: {', '.join(topics) if topics else 'None'}"
        )

        # Assess relevance
        relevance = assess_portfolio_relevance(tickers)
        print(f"  [OK] Portfolio relevance: {relevance}")

        # Generate insights section
        insights = generate_insights_section(content, tickers, topics, relevance)

        # Update frontmatter
        fm = update_frontmatter(fm, tickers, topics, relevance)

        # Reconstruct file
        fm_yaml = yaml.dump(fm, allow_unicode=True, sort_keys=False)
        new_content = f"---\n{fm_yaml}---\n{insights}\n{body}"

        # Write back
        write_file_safe(filepath, new_content)
        print("  [SUCCESS] Successfully enriched and saved")

        return {
            "status": "success",
            "tickers": tickers,
            "topics": topics,
            "relevance": relevance,
        }

    except Exception as e:
        print(f"  [ERROR] Error: {str(e)}")
        return {"status": "error", "error": str(e)}


def main():
    """Main entry point."""
    # Set UTF-8 output for Windows console
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if len(sys.argv) < 2:
        print("Usage: python process_batch.py <file1> <file2> ...")
        sys.exit(1)

    files = sys.argv[1:]
    print(f"Processing {len(files)} podcast files...\n")

    results = []
    for filepath in files:
        result = process_podcast_file(filepath)
        result["file"] = Path(filepath).name
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("[SUMMARY] Processing Summary")
    print("=" * 60)

    success = [r for r in results if r["status"] == "success"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors = [r for r in results if r["status"] == "error"]

    print(f"\n[SUCCESS] Successfully processed: {len(success)}")
    print(f"[WARN]  Skipped: {len(skipped)}")
    print(f"[ERROR] Errors: {len(errors)}")

    if success:
        print("\n[ENRICHED] Enriched files:")
        for r in success:
            print(f"  - {r['file']}")
            print(
                f"    - Tickers: {', '.join(r['tickers']) if r['tickers'] else 'None'}"
            )
            print(
                f"    - Topics: {', '.join(r['topics'][:3]) if r['topics'] else 'None'}"
            )
            print(f"    - Relevance: {r['relevance']}")

    if errors:
        print("\n[ERROR] Failed files:")
        for r in errors:
            print(f"  - {r['file']}: {r.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
