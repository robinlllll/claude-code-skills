#!/usr/bin/env python3
"""
ChatGPT API Skill — OpenAI API wrapper with history persistence.

Replaces browser automation with direct API calls.
"""

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULT_MODEL = "gpt-5.2-chat-latest"

DEFAULT_CONFIG = {
    "openai_api_key": "",
    "default_model": DEFAULT_MODEL,
}


# ── Config ────────────────────────────────────────────────────


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_api_key() -> str:
    """Resolve API key: env var > config file."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    return load_config().get("openai_api_key", "")


def get_client():
    from openai import OpenAI

    key = get_api_key()
    if not key:
        print("Error: No OpenAI API key found.", file=sys.stderr)
        print("Set OPENAI_API_KEY env var or run:", file=sys.stderr)
        print(
            "  python scripts/chatgpt_api.py config set openai_api_key sk-...",
            file=sys.stderr,
        )
        sys.exit(1)
    return OpenAI(api_key=key)


# ── History ───────────────────────────────────────────────────


def _get_history_manager():
    sys.path.insert(0, str(Path(__file__).parent))
    from history_manager import HistoryManager

    return HistoryManager()


# ── One-Shot ──────────────────────────────────────────────────


def ask_chatgpt(
    question: str,
    model: str | None = None,
    system: str | None = None,
    no_history: bool = False,
) -> str:
    """
    Ask a single question via OpenAI API.

    Args:
        question: The user prompt.
        model: Model ID (default: gpt-5.2-chat-latest).
        system: Optional system prompt.
        no_history: Skip persisting to history/Obsidian.

    Returns:
        The assistant's response text.
    """
    client = get_client()
    model = model or load_config().get("default_model", DEFAULT_MODEL)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": question})

    resp = client.chat.completions.create(model=model, messages=messages)
    answer = resp.choices[0].message.content

    if not no_history:
        mgr = _get_history_manager()
        mgr.save(question, answer, model=model)

    return answer


# ── Multi-Turn Session ────────────────────────────────────────


class ChatGPTSession:
    """Multi-turn conversation via OpenAI API."""

    def __init__(self, model: str | None = None, system: str | None = None):
        self.client = get_client()
        self.model = model or load_config().get("default_model", DEFAULT_MODEL)
        self.messages: list[dict] = []
        self._qa_pairs: list[tuple[str, str]] = []
        if system:
            self.messages.append({"role": "system", "content": system})

    def ask(self, question: str) -> str:
        self.messages.append({"role": "user", "content": question})
        resp = self.client.chat.completions.create(
            model=self.model, messages=self.messages
        )
        answer = resp.choices[0].message.content
        self.messages.append({"role": "assistant", "content": answer})
        self._qa_pairs.append((question, answer))
        return answer

    def end(self):
        """Persist all Q&A pairs to history."""
        mgr = _get_history_manager()
        for q, a in self._qa_pairs:
            mgr.save(q, a, model=self.model)
        self._qa_pairs.clear()


# ── CLI ───────────────────────────────────────────────────────


def cmd_ask(args):
    answer = ask_chatgpt(
        args.question,
        model=args.model,
        system=args.system,
        no_history=args.no_history,
    )
    print(answer)


def cmd_conversation(args):
    session = ChatGPTSession(model=args.model, system=args.system)
    model_display = args.model or load_config().get("default_model", DEFAULT_MODEL)
    print(f"ChatGPT conversation ({model_display}). Empty line to end.\n")
    try:
        while True:
            q = input("You: ").strip()
            if not q:
                break
            answer = session.ask(q)
            print(f"\nGPT: {answer}\n")
    except (KeyboardInterrupt, EOFError):
        pass
    session.end()
    print("\nConversation saved.")


def cmd_config(args):
    if args.action == "show":
        cfg = load_config()
        for k, v in cfg.items():
            if "key" in k.lower() and v:
                v = v[:8] + "..." + v[-4:] if len(v) > 12 else "***"
            print(f"  {k}: {v}")
    elif args.action == "set" and args.key and args.value:
        cfg = load_config()
        cfg[args.key] = args.value
        save_config(cfg)
        display = args.value
        if "key" in args.key.lower():
            display = args.value[:8] + "..." + args.value[-4:]
        print(f"Set {args.key} = {display}")
    else:
        print("Usage: config show | config set <key> <value>")


def cmd_history(args):
    mgr = _get_history_manager()
    if args.action == "search":
        results = mgr.search(args.query, limit=args.limit)
        if results:
            print(f"\nFound {len(results)} results for '{args.query}':\n")
            for e in results:
                tag = f" [{e.get('model', '')}]" if e.get("model") else ""
                print(f"  [{e['date']}]{tag}")
                print(f"  Q: {e['question'][:100]}")
                print(f"  A: {e['answer'][:150]}...\n")
        else:
            print(f"No results for '{args.query}'")
    elif args.action == "list":
        entries = mgr.get_history(limit=args.limit)
        if entries:
            print(f"\nRecent Q&A ({len(entries)} entries):\n")
            for e in entries:
                tag = f" [{e.get('model', '')}]" if e.get("model") else ""
                print(f"  [{e['date']} {e['time']}]{tag}")
                print(f"  Q: {e['question'][:100]}")
                print(f"  A: {e['answer'][:150]}...\n")
        else:
            print("No history entries yet.")
    elif args.action == "stats":
        stats = mgr.get_stats()
        print(f"\n  Total Q&A pairs: {stats['total']}")
        if stats["by_model"]:
            print("  By model:")
            for m, c in stats["by_model"].items():
                print(f"    {m}: {c}")
    else:
        print("Usage: history search --query ... | history list | history stats")


def main():
    parser = argparse.ArgumentParser(description="ChatGPT API Skill")
    sub = parser.add_subparsers(dest="command")

    # ask
    p_ask = sub.add_parser("ask", help="One-shot question")
    p_ask.add_argument("question", help="Question text")
    p_ask.add_argument("--model", default=None, help="Model ID")
    p_ask.add_argument("--system", default=None, help="System prompt")
    p_ask.add_argument("--no-history", action="store_true", help="Skip history")

    # conversation
    p_conv = sub.add_parser("conversation", help="Multi-turn REPL")
    p_conv.add_argument("--model", default=None, help="Model ID")
    p_conv.add_argument("--system", default=None, help="System prompt")

    # config
    p_cfg = sub.add_parser("config", help="Manage configuration")
    p_cfg.add_argument("action", choices=["show", "set"], help="Action")
    p_cfg.add_argument("key", nargs="?", help="Config key")
    p_cfg.add_argument("value", nargs="?", help="Config value")

    # history
    p_hist = sub.add_parser("history", help="Q&A history")
    p_hist.add_argument("action", choices=["search", "list", "stats"], help="Action")
    p_hist.add_argument("--query", default="", help="Search term")
    p_hist.add_argument("--limit", type=int, default=20, help="Max results")

    args = parser.parse_args()

    if args.command == "ask":
        cmd_ask(args)
    elif args.command == "conversation":
        cmd_conversation(args)
    elif args.command == "config":
        cmd_config(args)
    elif args.command == "history":
        cmd_history(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
