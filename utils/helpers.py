"""
helpers.py - Utility helpers for text processing, domain classification, and multi-format exports.
"""

from datetime import datetime, timezone
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    """Extracts a clean, human-readable domain name from a URL."""
    if not url:
        return "Unknown Source"
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        # Strip common subdomains and ports
        domain = re.sub(r"^www\.", "", domain, flags=re.IGNORECASE)
        domain = domain.split(":")[0]
        return domain.lower() if domain else "web-source"
    except Exception:
        return "web-source"


def classify_source_type(domain: str, url: str = "", title: str = "") -> str:
    """
    Categorizes a web source into an authoritative categorical type based on domain and URL signals.
    Does NOT invent fake scores; uses transparent structural categorization.
    """
    d = domain.lower()
    u = url.lower()
    t = title.lower()

    # 1. Government & International Public Health/Policy Orgs
    if (
        d.endswith(".gov")
        or d.endswith(".gov.uk")
        or d.endswith(".gov.in")
        or d.endswith(".mil")
        or any(org in d for org in ["who.int", "cdc.gov", "nih.gov", "fda.gov", "un.org", "europa.eu", "oecd.org", "worldbank.org", "imf.org", "nasa.gov", "noaa.gov", "nist.gov"])
    ):
        return "Government / Public Health Org"

    # 2. Academic & Universities
    if (
        d.endswith(".edu")
        or d.endswith(".ac.uk")
        or d.endswith(".edu.au")
        or d.endswith(".ac.in")
        or "arxiv.org" in d
        or "mit.edu" in d
        or "stanford.edu" in d
        or "harvard.edu" in d
        or "ox.ac.uk" in d
        or "cam.ac.uk" in d
        or "berkeley.edu" in d
    ):
        return "Academic / University"

    # 3. Scientific Journals & Peer-Reviewed Publishing
    if any(
        j in d
        for j in [
            "nature.com",
            "sciencedirect.com",
            "thelancet.com",
            "nejm.org",
            "springer.com",
            "wiley.com",
            "frontiersin.org",
            "plos.org",
            "bmj.com",
            "ieee.org",
            "acm.org",
            "cell.com",
            "pnas.org",
            "pubmed.ncbi.nlm.nih.gov",
            "ncbi.nlm.nih.gov",
            "biorxiv.org",
            "medrxiv.org",
        ]
    ):
        return "Scientific Journal / Peer-Reviewed"

    # 4. Official Technical Documentation / Standards
    if (
        "docs." in d
        or "developer." in d
        or "github.com" in d
        or "w3.org" in d
        or "rfc-editor.org" in d
        or "ietf.org" in d
        or "iso.org" in d
        or any(k in u for k in ["/docs/", "/documentation/", "/api/"])
    ):
        return "Official Tech Documentation"

    # 5. Authoritative Financial / Regulatory
    if any(f in d for f in ["sec.gov", "federalreserve.gov", "bankofengland.co.uk", "bis.org", "ft.com", "bloomberg.com", "wsj.com"]):
        return "Financial / Regulatory"

    # 6. Recognized News & Public Analysis
    if any(
        n in d
        for n in [
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "bbc.co.uk",
            "economist.com",
            "nytimes.com",
            "washingtonpost.com",
            "theguardian.com",
            "npr.org",
            "scientificamerican.com",
            "technologyreview.com",
            "wired.com",
            "arstechnica.com",
        ]
    ):
        return "News & Analysis"

    # 7. Industry / Corporate Research (e.g. DeepMind, Microsoft Research, IBM Research)
    if any(corp in d for corp in ["research.google", "openai.com", "microsoft.com/research", "ibm.com/research", "anthropic.com", "meta.com", "nvidia.com", "huggingface.co"]):
        return "Industry Research / Tech Company"

    return "General Web Reference"


def calculate_source_diversity(sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates the distribution and distinct count of source types among retrieved documents.
    """
    type_counts: Dict[str, int] = {}
    for s in sources:
        domain = s.get("domain") or extract_domain(s.get("url", ""))
        stype = s.get("source_type") or classify_source_type(domain, s.get("url", ""), s.get("title", ""))
        type_counts[stype] = type_counts.get(stype, 0) + 1

    distinct_count = len(type_counts)
    return {
        "distinct_type_count": distinct_count,
        "type_counts": type_counts,
        "types_list": list(type_counts.keys()),
        "is_diverse": distinct_count >= 2,
    }


def clean_text(text: Optional[str]) -> str:
    """Sanitizes raw text, collapses whitespace, and strips control characters."""
    if not text:
        return ""
    # Remove null bytes and non-printable control characters
    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t ")
    # Normalize multiple newlines and spaces line-by-line
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.splitlines()]
    # Remove excessive blank lines
    collapsed: List[str] = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 1:
                collapsed.append("")
        else:
            blank_count = 0
            collapsed.append(line)

    return "\n".join(collapsed).strip()


def truncate_text(text: str, max_chars: int = 300, suffix: str = "...") -> str:
    """Truncates text neatly at word boundaries."""
    if not text or len(text) <= max_chars:
        return text or ""
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return f"{truncated}{suffix}"


def build_markdown_report_export(
    question: str,
    report_content: str,
    sources: List[Dict[str, Any]],
    generated_at: Optional[str] = None,
    language: str = "en",
) -> str:
    """
    Constructs a standalone Markdown document suitable for export, sharing, or archiving.
    """
    timestamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    header = f"""# ResearchAI Intelligence Dossier: {question}

> **Generated by ResearchAI** | Autonomous Multi-Source Research & Tutor Engine  
> **Date:** {timestamp}  
> **Language:** {language.upper()}  
> **Total Sourced References:** {len(sources)}

---

"""
    body = report_content.strip()
    
    sources_section = "\n\n## Research Sources & References\n\n"
    if sources:
        for idx, src in enumerate(sources, 1):
            title = src.get("title", "Untitled Source")
            url = src.get("url", "#")
            domain = src.get("domain") or extract_domain(url)
            stype = src.get("source_type") or classify_source_type(domain, url, title)
            why = src.get("why_relevant") or "Relevant source retrieved during investigation."
            evidence = src.get("extracted_evidence") or src.get("snippet") or "No excerpt available."
            retrieved = src.get("retrieved_date") or timestamp[:10]
            sources_section += f"**[{idx}] [{title}]({url})**  \n"
            sources_section += f"- **Domain:** `{domain}` | **Source Type:** {stype}  \n"
            sources_section += f"- **Why Relevant:** {why}  \n"
            sources_section += f"- **Direct Evidence Excerpt:** {truncate_text(evidence, 220)}  \n"
            sources_section += f"- **Retrieved Date:** {retrieved}  \n\n"
    else:
        sources_section += "_No external web sources were collected for this session._\n"

    footer = "\n---\n*Report compiled autonomously by ResearchAI. All cited facts reflect retrieved evidence.*"
    
    return header + body + sources_section + footer


def build_text_report_export(
    question: str,
    report_content: str,
    sources: List[Dict[str, Any]],
    generated_at: Optional[str] = None,
    language: str = "en",
) -> str:
    """Constructs a clean, formatted plain text (.txt) export."""
    timestamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    divider = "=" * 80
    
    lines = [
        divider,
        f"RESEARCHAI DOSSIER: {question.upper()}",
        f"Date: {timestamp} | Language: {language.upper()} | Sources: {len(sources)}",
        divider,
        "",
        report_content,
        "",
        divider,
        "RESEARCH SOURCES & EVIDENCE",
        divider,
    ]
    
    for idx, src in enumerate(sources, 1):
        title = src.get("title", "Untitled Source")
        url = src.get("url", "#")
        domain = src.get("domain") or extract_domain(url)
        stype = src.get("source_type") or classify_source_type(domain, url, title)
        why = src.get("why_relevant") or "Relevant source."
        lines.append(f"[{idx}] {title}")
        lines.append(f"    URL: {url}")
        lines.append(f"    Domain: {domain} | Type: {stype}")
        lines.append(f"    Why Relevant: {why}")
        lines.append("")

    return "\n".join(lines)


def build_html_printable_export(
    question: str,
    report_content_html: str,
    sources: List[Dict[str, Any]],
    language: str = "en",
) -> str:
    """Constructs a clean, styled HTML printable report that can be printed or saved to PDF."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    is_rtl = language == "ar"
    dir_attr = 'dir="rtl"' if is_rtl else 'dir="ltr"'
    
    sources_html = ""
    for idx, s in enumerate(sources, 1):
        domain = s.get("domain") or extract_domain(s.get("url", ""))
        stype = s.get("source_type") or classify_source_type(domain, s.get("url", ""), s.get("title", ""))
        sources_html += f"""
        <div class="source-item">
            <div class="source-header"><strong>[{idx}] <a href="{s.get('url', '#')}" target="_blank">{s.get('title', 'Source')}</a></strong></div>
            <div class="source-meta">Domain: {domain} &bull; Type: {stype} &bull; Retrieved: {s.get('retrieved_date', timestamp[:10])}</div>
            <div class="source-why"><strong>Why Relevant:</strong> {s.get('why_relevant', '')}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="{language}" {dir_attr}>
<head>
    <meta charset="UTF-8">
    <title>ResearchAI Dossier - {question}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #1e293b;
            max-width: 860px;
            margin: 0 auto;
            padding: 2rem 1.5rem;
            background: #ffffff;
        }}
        h1 {{ font-size: 2rem; color: #0f172a; margin-bottom: 0.5rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }}
        h2 {{ font-size: 1.4rem; color: #1e293b; margin-top: 1.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.3rem; }}
        h3 {{ font-size: 1.15rem; color: #2563eb; }}
        .badge {{ display: inline-block; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px; padding: 0.2rem 0.5rem; font-size: 0.85rem; margin-right: 0.5rem; }}
        .source-item {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 1rem; margin-bottom: 0.75rem; page-break-inside: avoid; }}
        .source-meta {{ font-size: 0.85rem; color: #64748b; font-family: monospace; margin: 0.25rem 0; }}
        .source-why {{ font-size: 0.9rem; color: #334155; }}
        a {{ color: #2563eb; text-decoration: none; }}
        @media print {{
            body {{ padding: 0; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom: 1.5rem; text-align: right;">
        <button onclick="window.print()" style="padding: 0.5rem 1rem; background: #2563eb; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">🖨️ Print / Save as PDF</button>
    </div>
    <h1>🔬 ResearchAI Intelligence Dossier</h1>
    <p><strong>Research Query:</strong> {question}<br>
    <span class="badge">Date: {timestamp}</span>
    <span class="badge">Language: {language.upper()}</span>
    <span class="badge">Sourced References: {len(sources)}</span></p>
    
    <div class="content">
        {report_content_html}
    </div>
    
    <h2>Research Sources & References</h2>
    {sources_html}
    
    <hr style="margin-top: 2rem; border: none; border-top: 1px solid #e2e8f0;">
    <p style="font-size: 0.8rem; color: #94a3b8; text-align: center;">Generated autonomously by ResearchAI. All cited facts reflect retrieved evidence.</p>
</body>
</html>"""
    return html


def build_json_export(
    question: str,
    plan: Dict[str, Any],
    report: str,
    sources: List[Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    language: str = "en",
) -> str:
    """Serializes the entire research session state to formatted JSON."""
    payload = {
        "metadata": {
            "application": "ResearchAI",
            "version": "2.0.0",
            "language": language,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "query": question,
        "plan": plan,
        "metrics": metrics,
        "report_markdown": report,
        "contradictions_or_divergences": contradictions,
        "sources": sources,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def format_rtl_if_arabic(text: str, language: str = "en") -> str:
    """
    Prepends the Unicode Right-to-Left Mark (RLM: \\u200F) to each line if the language is Arabic.
    This guarantees proper RTL rendering across Telegram clients and Markdown renderers
    without disturbing embedded Latin characters, numbers, and URLs.
    """
    if not text or language != "ar":
        return text

    rlm = "\u200F"
    lines = text.splitlines()
    rtl_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("```"):
            rtl_lines.append(f"{rlm}{line}")
        else:
            rtl_lines.append(line)
    return "\n".join(rtl_lines)

