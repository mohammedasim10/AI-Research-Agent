"""
app.py - ResearchAI Web Dashboard.
Production-grade Streamlit application with minimal, enterprise-grade typography,
real-time research orchestration, verified citation inspection, and multi-format exports.
"""

import os
import time
from typing import Any, Dict, List, Optional
import streamlit as st

from agent import ResearchAgent, ResearchSessionResult
from config import AppConfig, config as default_config
from utils.helpers import (
    build_json_export,
    build_markdown_report_export,
    clean_text,
    extract_domain,
    truncate_text,
)

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION & METADATA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ResearchAI — Autonomous AI Research Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# CUSTOM CSS: MINIMALIST, GOOGLE-QUALITY ENTERPRISE DESIGN
# -----------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* Main Container padding */
.main .block-container {
    max-width: 1040px;
    padding-top: 1.5rem;
    padding-bottom: 4rem;
    padding-left: 1.5rem;
    padding-right: 1.5rem;
}

/* Header Styles */
.brand-title {
    font-size: 2.3rem;
    font-weight: 800;
    letter-spacing: -0.025em;
    margin-bottom: 0.35rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-color, #0f172a);
}

.brand-subtitle {
    font-size: 1.05rem;
    color: var(--text-color, #475569);
    opacity: 0.85;
    font-weight: 400;
    margin-bottom: 1.75rem;
    line-height: 1.5;
}

/* Card Containers */
.research-card {
    background: var(--secondary-background-color, #ffffff);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    margin-bottom: 1.25rem;
    color: var(--text-color, inherit);
}

/* Metric Badges */
.metric-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: var(--secondary-background-color, #f1f5f9);
    color: var(--text-color, #334155);
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 6px;
    padding: 0.25rem 0.65rem;
    font-size: 0.825rem;
    font-weight: 500;
    margin-right: 0.5rem;
    margin-bottom: 0.5rem;
}

/* Stepper Stage Box */
.step-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.65rem 0.85rem;
    background: var(--secondary-background-color, #ffffff);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 6px;
    margin-bottom: 0.5rem;
    font-size: 0.92rem;
    color: var(--text-color, inherit);
}
.step-icon-completed {
    color: #22c55e;
    font-weight: 700;
}
.step-icon-running {
    color: #3b82f6;
    font-weight: 700;
    animation: pulse 1.5s infinite;
}
.step-icon-pending {
    color: #94a3b8;
}

@keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.4; }
    100% { opacity: 1; }
}

/* Source Card */
.source-card {
    background: var(--secondary-background-color, #ffffff);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 6px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.15s ease;
    color: var(--text-color, inherit);
}
.source-card:hover {
    border-color: #3b82f6;
}
.source-title {
    font-size: 0.98rem;
    font-weight: 600;
    color: #3b82f6;
    text-decoration: none;
}
.source-title:hover {
    text-decoration: underline;
}
.source-meta {
    font-size: 0.8rem;
    opacity: 0.75;
    margin-top: 0.2rem;
    margin-bottom: 0.5rem;
    font-family: 'JetBrains Mono', monospace;
}
.source-rationale {
    font-size: 0.875rem;
    color: var(--text-color, #334155);
    background: rgba(59, 130, 246, 0.08);
    border-left: 3px solid #3b82f6;
    padding: 0.4rem 0.65rem;
    margin-top: 0.4rem;
    border-radius: 0 4px 4px 0;
}

/* Action Buttons */
div.stButton > button {
    border-radius: 6px;
    font-weight: 500;
    font-size: 0.925rem;
    transition: all 0.15s ease;
}
div.stButton > button:first-child[kind="primary"] {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
}
div.stButton > button:first-child[kind="primary"]:hover {
    background-color: #1d4ed8;
    border-color: #1e40af;
}

/* Citation Highlighting */
.citation-badge {
    background-color: rgba(59, 130, 246, 0.15);
    color: #3b82f6;
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
    font-size: 0.775rem;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# -----------------------------------------------------------------------------
if "research_result" not in st.session_state:
    st.session_state["research_result"] = None
if "current_question" not in st.session_state:
    st.session_state["current_question"] = ""
if "main_query_input" not in st.session_state:
    st.session_state["main_query_input"] = ""
if "research_stages" not in st.session_state:
    st.session_state["research_stages"] = {}
if "activity_logs" not in st.session_state:
    st.session_state["activity_logs"] = []


# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS & SETTINGS
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Engine Settings")
    
    # Environment status
    env_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    has_env_key = bool(env_api_key and len(env_api_key) > 10)
    
    if has_env_key:
        st.success("API Key detected from environment", icon="🔒")
        api_key_input = env_api_key
    else:
        api_key_input = st.text_input(
            "Gemini API Key",
            type="password",
            placeholder="AIzaSy...",
            help="Get your key at https://aistudio.google.com/app/apikey. Key is held securely in runtime memory only.",
        )
        if not api_key_input:
            st.info("Enter your Gemini API Key or set `GEMINI_API_KEY` in `.env`.", icon="💡")

    st.divider()
    
    # Model Selection
    model_choice = st.selectbox(
        "LLM Provider & Model",
        options=["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0,
        help="Gemini 2.5 Flash offers superior speed and up-to-date reasoning for empirical research synthesis.",
    )

    # Research Rigor
    search_depth = st.selectbox(
        "Research Rigor",
        options=["Standard (4 Queries, ~8 Sources)", "Deep (6 Queries, ~12 Sources)"],
        index=0,
    )
    
    max_queries = 6 if "Deep" in search_depth else 4
    max_sources = 12 if "Deep" in search_depth else 8

    st.divider()

    st.markdown("### 📋 Architecture Highlights")
    st.caption("• Zero-Hallucination Citation Grounding\n• Multi-Source Cross-Verification\n• Live DuckDuckGo Extraction\n• Modular LLM Provider Architecture")

    if st.session_state.get("research_result"):
        st.divider()
        if st.button("🗑️ Clear Session & Start Fresh", use_container_width=True):
            st.session_state["research_result"] = None
            st.session_state["current_question"] = ""
            st.session_state["main_query_input"] = ""
            st.session_state["research_stages"] = {}
            st.session_state["activity_logs"] = []
            st.rerun()


# -----------------------------------------------------------------------------
# MAIN HEADER
# -----------------------------------------------------------------------------
st.markdown(
    '<h1 style="font-weight: 800; font-size: 2.3rem; margin-bottom: 0.2rem; display: flex; align-items: center; gap: 0.5rem; letter-spacing: -0.02em;">🔬 Research<span style="color: #3b82f6;">AI</span></h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="font-size: 1.05rem; opacity: 0.85; margin-bottom: 1.75rem; line-height: 1.5;">Autonomous multi-source research engine. Searches the live web, cross-checks evidence, and produces structured, cited intelligence reports.</p>',
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# RESEARCH QUESTION INPUT & QUICK EXAMPLES
# -----------------------------------------------------------------------------
example_questions = [
    "How is generative AI changing enterprise data analytics?",
    "Compare Python and R for data science in 2026.",
    "What are the major architectural patterns for autonomous AI agents?",
    "How does retrieval-augmented generation (RAG) mitigate LLM hallucinations?",
]

def populate_example_query(q_text: str):
    st.session_state["main_query_input"] = q_text

col_input, col_btn = st.columns([5, 1.2])

with col_input:
    user_query = st.text_input(
        "Enter your research question:",
        placeholder="e.g., What are the latest breakthroughs in solid-state battery technology?",
        label_visibility="collapsed",
        key="main_query_input",
    )

with col_btn:
    start_clicked = st.button("Start Research", type="primary", use_container_width=True)

# Example pills
st.markdown("<p style='font-size: 0.85rem; opacity: 0.8; margin-top: 0.25rem; margin-bottom: 0.4rem;'>💡 <b>Example investigations:</b></p>", unsafe_allow_html=True)
pill_cols = st.columns(len(example_questions))
for i, eq in enumerate(example_questions):
    with pill_cols[i]:
        st.button(
            eq,
            key=f"pill_{i}",
            use_container_width=True,
            on_click=populate_example_query,
            args=(eq,),
        )

st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# RESEARCH EXECUTION HANDLER
# -----------------------------------------------------------------------------
if start_clicked:
    target_question = user_query.strip()
    if not target_question:
        st.error("Please enter a research question before starting.", icon="⚠️")
    elif not api_key_input:
        st.error("Gemini API Key required. Please provide it in the sidebar or via .env file.", icon="🔑")
    else:
        # Reset previous run data
        st.session_state["research_result"] = None
        st.session_state["current_question"] = target_question
        st.session_state["research_stages"] = {
            "plan": {"status": "pending", "desc": "Deconstruct question & formulate search angles"},
            "search": {"status": "pending", "desc": "Retrieve live web results across queries"},
            "collect": {"status": "pending", "desc": "Extract body text and normalize source articles"},
            "analyze": {"status": "pending", "desc": "Cross-check facts & detect contradictions"},
            "report": {"status": "pending", "desc": "Synthesize report with verified citations"},
        }
        st.session_state["activity_logs"] = []

        # Render Progress Stepper Container
        stepper_container = st.container()
        status_box = st.empty()
        
        stages_ui = {
            "plan": "1. Research Planning & Query Generation",
            "search": "2. Multi-Angle Web Search Retrieval",
            "collect": "3. Content Extraction & Normalization",
            "analyze": "4. Cross-Source Fact & Contradiction Check",
            "report": "5. Citation Synthesis & Report Generation",
        }

        def render_stepper():
            with stepper_container:
                st.markdown("### 🔄 Research In Progress")
                for key, title in stages_ui.items():
                    info = st.session_state["research_stages"].get(key, {"status": "pending", "desc": ""})
                    st_val = info["status"]
                    if st_val == "completed":
                        icon_html = '<span class="step-icon-completed">✓</span>'
                    elif st_val == "running":
                        icon_html = '<span class="step-icon-running">●</span>'
                    else:
                        icon_html = '<span class="step-icon-pending">○</span>'
                    
                    desc_txt = f" — <span style='color: #64748b; font-size: 0.85rem;'>{info.get('desc', '')}</span>" if info.get("desc") else ""
                    st.markdown(
                        f'<div class="step-row">{icon_html} <b>{title}</b>{desc_txt}</div>',
                        unsafe_allow_html=True,
                    )

        def on_progress_update(stage: str, status: str, message: str, data: Optional[Dict[str, Any]] = None):
            if stage in st.session_state["research_stages"]:
                st.session_state["research_stages"][stage] = {
                    "status": status,
                    "desc": message,
                    "data": data,
                }
            st.session_state["activity_logs"].append(f"[{time.strftime('%H:%M:%S')}] [{stage.upper()}] {message}")

        # Execute Agent
        render_stepper()
        
        runtime_config = AppConfig(
            gemini_api_key=api_key_input,
            gemini_model=model_choice,
            max_search_queries=max_queries,
            max_total_sources=max_sources,
        )
        
        try:
            agent = ResearchAgent(api_key=api_key_input, config=runtime_config)
            with st.spinner("Autonomous agent is investigating the web..."):
                result = agent.run(
                    question=target_question,
                    on_progress=on_progress_update,
                )
                st.session_state["research_result"] = result
                st.rerun()
        except Exception as e:
            st.error(f"Research execution failed: {str(e)}", icon="❌")


# -----------------------------------------------------------------------------
# RESULTS DASHBOARD DISPLAY
# -----------------------------------------------------------------------------
result: Optional[ResearchSessionResult] = st.session_state.get("research_result")

if result:
    if not result.success:
        st.error(f"Research Incomplete: {result.error_message or 'Unknown error.'}", icon="⚠️")
        if result.plan:
            with st.expander("View Formulated Research Plan"):
                st.json(result.plan)
    else:
        # Success state: Render Metrics Bar
        m = result.metrics
        st.markdown(
            f"""
            <div style="margin-bottom: 1rem;">
                <span class="metric-pill">⏱️ Duration: <b>{m.get('duration_seconds', 0)}s</b></span>
                <span class="metric-pill">🔍 Queries: <b>{m.get('queries_executed', 0)}</b></span>
                <span class="metric-pill">🌐 Sources Sourced: <b>{m.get('sources_retrieved', 0)}</b></span>
                <span class="metric-pill">📑 Words Analyzed: <b>{m.get('total_words_analyzed', 0):,}</b></span>
                <span class="metric-pill">📌 Grounded Citations: <b>{m.get('citations_referenced', 0)}</b></span>
                <span class="metric-pill">🤖 Engine: <b>{m.get('model_used', 'Gemini')}</b></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Tabs for Report, Verified Sources, Plan & Trace, and Exports
        tab_report, tab_sources, tab_evidence, tab_plan, tab_export = st.tabs([
            "📑 Research Report",
            f"🌐 Verified Sources ({len(result.sources)})",
            "🔍 Evidence & Cross-Check Matrix",
            "📐 Research Plan & Trace",
            "💾 Export & Download",
        ])

        # TAB 1: RESEARCH REPORT
        with tab_report:
            st.markdown(
                f"<div class='research-card'>"
                f"<h2 style='font-size: 1.45rem; font-weight: 700; margin-top: 0; color: #0f172a;'>Intelligence Report: {result.question}</h2>"
                f"</div>",
                unsafe_allow_html=True,
            )
            
            # Display formatted Markdown
            st.markdown(result.report_markdown)

        # TAB 2: VERIFIED SOURCES
        with tab_sources:
            st.markdown("### Verified Web References")
            st.caption("All factual claims and citations in the report are grounded in the following retrieved sources.")

            for src in result.sources:
                src_id = src.get("id", 1)
                title = src.get("title", "Untitled Source")
                url = src.get("url", "#")
                domain = src.get("domain", extract_domain(url))
                why = src.get("why_relevant", "Relevant source retrieved during investigation.")
                extracted = src.get("extracted_facts", [])
                word_c = src.get("word_count", 0)
                status = src.get("status", "success")
                
                status_badge = "🟢 Full Body Verified" if status == "success" else "🟡 Excerpt Only"

                st.markdown(
                    f"""
                    <div class="source-card">
                        <div style="display: flex; justify-content: space-between; align-items: baseline;">
                            <a href="{url}" target="_blank" class="source-title">[{src_id}] {title} ↗</a>
                            <span style="font-size: 0.75rem; color: #64748b;">{status_badge} ({word_c} words)</span>
                        </div>
                        <div class="source-meta">Domain: {domain} | Origin Query: "{src.get('query_origin', '')}"</div>
                        <div class="source-rationale"><b>Why Relevant:</b> {why}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if extracted:
                    with st.expander(f"Inspect Extracted Evidence for [{src_id}] {truncate_text(title, 50)}"):
                        for fact in extracted:
                            st.markdown(f"- {fact}")
                        if src.get("snippet"):
                            st.caption(f"**Search Snippet:** {src.get('snippet')}")

        # TAB 3: EVIDENCE & CROSS-CHECK MATRIX
        with tab_evidence:
            st.markdown("### Cross-Source Verification & Discrepancy Matrix")
            
            analysis = result.analysis or {}
            consensus = analysis.get("consensus_findings", [])
            contradictions = analysis.get("contradictions_and_divergences", [])
            gaps = analysis.get("evidence_gaps_and_limitations", [])

            col_con, col_div = st.columns(2)
            with col_con:
                st.markdown("#### ✅ Multi-Source Consensus")
                if consensus:
                    for c in consensus:
                        st.success(c, icon="✔️")
                else:
                    st.info("No explicit multi-source overlaps cataloged.")

            with col_div:
                st.markdown("#### ⚠️ Divergences & Contradictions")
                if contradictions:
                    for d in contradictions:
                        st.warning(
                            f"**{d.get('topic', 'Divergence')}**\n\n{d.get('discrepancy', '')}\n\n*Sources involved: {d.get('involved_sources', [])}*",
                            icon="⚖️",
                        )
                else:
                    st.success("No significant factual contradictions discovered among sources.", icon="🤝")

            st.markdown("#### 🔭 Evidence Gaps & Analytical Blind Spots")
            if gaps:
                for g in gaps:
                    st.markdown(f"- ⚠️ {g}")
            else:
                st.markdown("- No major analytical gaps flagged.")

        # TAB 4: PLAN & ACTIVITY TRACE
        with tab_plan:
            st.markdown("### Autonomous Research Plan Breakdown")
            plan_data = result.plan or {}
            
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown(f"**Research Intent:**\n> {plan_data.get('intent_summary', 'N/A')}")
                st.markdown("**Target Analytical Dimensions:**")
                for dim in plan_data.get("research_dimensions", []):
                    st.markdown(f"- {dim}")
            
            with col_p2:
                st.markdown("**Generated Search Queries:**")
                for q in plan_data.get("search_queries", []):
                    st.markdown(f"- `🔍 {q}`")
                st.markdown("**Target Evidence Types:**")
                for ev in plan_data.get("target_evidence_types", []):
                    st.markdown(f"- {ev}")

            st.divider()
            st.markdown("### Detailed Execution Activity Log")
            if st.session_state.get("activity_logs"):
                for log in st.session_state["activity_logs"]:
                    st.text(log)
            else:
                st.caption("No log entries recorded.")

        # TAB 5: EXPORTS
        with tab_export:
            st.markdown("### Export Research Session")
            st.caption("Download the compiled report as clean Markdown or structured JSON for data analysis pipelines.")

            md_content = build_markdown_report_export(
                question=result.question,
                report_content=result.report_markdown,
                sources=result.sources,
            )

            json_content = build_json_export(
                question=result.question,
                plan=result.plan or {},
                report=result.report_markdown,
                sources=result.sources,
                contradictions=result.analysis.get("contradictions_and_divergences", []) if result.analysis else [],
                metrics=result.metrics,
            )

            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                st.download_button(
                    label="📥 Download Markdown Report (.md)",
                    data=md_content,
                    file_name=f"ResearchAI_{int(time.time())}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with col_ex2:
                st.download_button(
                    label="📥 Download Structured Session (.json)",
                    data=json_content,
                    file_name=f"ResearchAI_{int(time.time())}.json",
                    mime="application/json",
                    use_container_width=True,
                )

            with st.expander("Preview Raw Markdown Export"):
                st.code(md_content, language="markdown")
