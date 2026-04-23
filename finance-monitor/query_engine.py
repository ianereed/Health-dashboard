"""
Finance Q&A engine.

Routes questions to transaction mode or document mode based on keywords,
fetches relevant data from SQLite, builds a prompt, and calls Ollama.

Privacy: raw transaction data and document text are never logged.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import requests

import config
import db

logger = logging.getLogger(__name__)

_DOCUMENT_KEYWORDS = frozenset([
    "plan", "advisor", "portfolio", "allocation", "securities",
    "etf", "fund", "invest", "retire", "analyze", "analysis",
    "strategy", "asset", "stock", "bond", "equity", "vanguard",
    "schwab", "fidelity", "proposal",
])

_TEXT_MAX_CHARS = 60_000
_OLLAMA_TIMEOUT = 120


def _question_mode(question: str) -> str:
    lower = question.lower()
    words = set(lower.split())
    has_doc = bool(words & _DOCUMENT_KEYWORDS)
    return "combined" if has_doc else "transaction"


# ── Data fetch helpers ────────────────────────────────────────────────────────

def _fetch_spending_summary(days: int = 90) -> dict:
    """Return aggregated spending data: monthly totals + top categories."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = db.get_connection()

    monthly = conn.execute(
        """SELECT substr(date,1,7) AS month,
                  ROUND(SUM(outflow),2) AS total_outflow,
                  ROUND(SUM(inflow),2)  AS total_inflow,
                  ROUND(SUM(amount),2)  AS net
           FROM transactions
           WHERE date >= ? AND is_transfer = 0
           GROUP BY month
           ORDER BY month""",
        (cutoff,),
    ).fetchall()

    categories = conn.execute(
        """SELECT category, ROUND(SUM(outflow),2) AS total
           FROM transactions
           WHERE date >= ? AND is_transfer = 0 AND category IS NOT NULL
           GROUP BY category
           ORDER BY total DESC
           LIMIT 10""",
        (cutoff,),
    ).fetchall()

    conn.close()
    return {
        "monthly": [dict(r) for r in monthly],
        "categories": [dict(r) for r in categories],
        "days": days,
    }


def _fetch_recent_transactions(days: int = 30) -> list[dict]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = db.get_connection()
    rows = conn.execute(
        """SELECT date, payee, outflow, inflow, category, account
           FROM transactions
           WHERE date >= ? AND is_transfer = 0
           ORDER BY date DESC
           LIMIT 300""",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _fetch_most_recent_document(keywords: list[str] | None = None) -> dict | None:
    """Return the most recently imported document, preferring financial_plan type."""
    conn = db.get_connection()
    if keywords:
        like_clauses = " OR ".join("LOWER(filename) LIKE ?" for _ in keywords)
        params = [f"%{k}%" for k in keywords] + ["financial_plan"]
        row = conn.execute(
            f"""SELECT id, filename, doc_type, page_count, extracted_text
                FROM documents
                WHERE ({like_clauses}) OR doc_type = ?
                ORDER BY imported_at DESC LIMIT 1""",
            params,
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT id, filename, doc_type, page_count, extracted_text
               FROM documents
               ORDER BY CASE doc_type WHEN 'financial_plan' THEN 0 ELSE 1 END,
                        imported_at DESC
               LIMIT 1""",
        ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Prompt builders ───────────────────────────────────────────────────────────

def _format_monthly_table(monthly: list[dict]) -> str:
    if not monthly:
        return "(no data)"
    lines = ["Month       | Outflow    | Inflow     | Net"]
    lines.append("-" * 47)
    for r in monthly:
        lines.append(
            f"{r['month']:<12}| ${r['total_outflow']:>9.2f} | ${r['total_inflow']:>9.2f} | ${r['net']:>9.2f}"
        )
    return "\n".join(lines)


def _format_categories(cats: list[dict]) -> str:
    if not cats:
        return "(no data)"
    return "\n".join(f"  {r['category']}: ${r['total']:.2f}" for r in cats)


def _format_transactions(txns: list[dict]) -> str:
    if not txns:
        return "(no transactions in range)"
    lines = ["Date       | Payee                          | Out      | In       | Category"]
    lines.append("-" * 85)
    for t in txns:
        payee = (t["payee"] or "")[:30]
        cat = (t["category"] or "")[:25]
        lines.append(
            f"{t['date']} | {payee:<30} | ${t['outflow']:>7.2f} | ${t['inflow']:>7.2f} | {cat}"
        )
    return "\n".join(lines)


def _build_transaction_prompt(question: str, summary: dict, recent: list[dict]) -> str:
    today = date.today().isoformat()
    return f"""Today is {today}. All amounts in USD.
You are a personal finance assistant. Answer using ONLY the data provided below. Be concise and specific.

SPENDING SUMMARY — last {summary['days']} days (excluding transfers):

{_format_monthly_table(summary['monthly'])}

Top 10 categories by spending:
{_format_categories(summary['categories'])}

RECENT TRANSACTIONS — last 30 days:
{_format_transactions(recent)}

QUESTION: {question}"""


def _compute_savings_rate(monthly: list[dict]) -> float:
    total_in = sum(r["total_inflow"] for r in monthly)
    total_out = sum(r["total_outflow"] for r in monthly)
    if total_in == 0:
        return 0.0
    return max(0.0, (total_in - total_out) / total_in * 100)


def _build_document_prompt(question: str, doc: dict, summary: dict) -> str:
    today = date.today().isoformat()
    months = len(summary["monthly"])
    avg_out = sum(r["total_outflow"] for r in summary["monthly"]) / max(months, 1)
    avg_in = sum(r["total_inflow"] for r in summary["monthly"]) / max(months, 1)
    savings_rate = _compute_savings_rate(summary["monthly"])
    top5 = summary["categories"][:5]
    top5_str = ", ".join(f"{r['category']} (${r['total']:.0f})" for r in top5)

    doc_text = doc["extracted_text"]
    if len(doc_text) > _TEXT_MAX_CHARS:
        doc_text = doc_text[:_TEXT_MAX_CHARS] + "\n[truncated]"

    return f"""Today is {today}. All amounts in USD.
You are a personal finance assistant analyzing a financial document.

FINANCIAL SNAPSHOT (last {summary['days']} days, excluding transfers):
  Avg monthly spending: ${avg_out:.2f}
  Avg monthly income:   ${avg_in:.2f}
  Savings rate:         {savings_rate:.0f}%
  Top spending categories: {top5_str}

DOCUMENT: "{doc['filename']}" ({doc['page_count']} pages, type: {doc['doc_type']})
--- BEGIN DOCUMENT ---
{doc_text}
--- END DOCUMENT ---

QUESTION: {question}"""


# ── Ollama call ───────────────────────────────────────────────────────────────

def _call_ollama(prompt: str, num_ctx: int = 16384) -> str:
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "10s",
        "think": False,  # required for qwen3; safe no-op on other models
        "options": {"num_ctx": num_ctx},
    }
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=_OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


# ── Public API ────────────────────────────────────────────────────────────────

def answer(question: str) -> str:
    """
    Answer a plain-English finance question. Returns a plain-text response.
    Never raises — returns an error string on failure.
    """
    mode = _question_mode(question)
    summary = _fetch_spending_summary(days=90)

    if mode == "transaction":
        recent = _fetch_recent_transactions(days=30)
        prompt = _build_transaction_prompt(question, summary, recent)
        num_ctx = 16384
    else:
        # Extract keywords from question to find the best matching document
        q_words = [w for w in question.lower().split() if len(w) > 3]
        doc = _fetch_most_recent_document(keywords=q_words)
        if doc:
            prompt = _build_document_prompt(question, doc, summary)
            num_ctx = 32768
        else:
            # No documents — fall back to transaction mode with a note
            recent = _fetch_recent_transactions(days=30)
            prompt = _build_transaction_prompt(question, summary, recent)
            prompt += "\n\nNote: No financial documents have been uploaded yet."
            num_ctx = 16384

    for attempt in range(3):
        try:
            return _call_ollama(prompt, num_ctx=num_ctx)
        except (requests.RequestException, KeyError) as exc:
            if attempt < 2:
                delay = 2 ** attempt
                logger.warning("query_engine: attempt %d failed: %s — retrying in %ds", attempt + 1, exc, delay)
                time.sleep(delay)
            else:
                logger.error("query_engine: all 3 attempts failed: %s", exc)
                return "Sorry, I couldn't reach the local AI model. Check that Ollama is running."

    return "Sorry, something went wrong."
