"""
app.py - ResearchAI Web Dashboard with Multilingual Research & Pedagogical Tutor Experience.
Supports English, Hindi, Telugu, and Arabic with RTL layouts, "Explain Simply" vs "Deep Research" modes,
dynamic language switching without re-searching, interactive source cards, and citation inspectors.
"""

import os
import time
from typing import Any, Dict, List, Optional
import streamlit as st

from agent import ResearchAgent, ResearchSessionResult
from config import AppConfig, config as default_config
from report_generator import SUPPORTED_LANGUAGES
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
    page_title="ResearchAI — Autonomous AI Research & Tutor Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# CUSTOM CSS: MINIMALIST, GOOGLE-QUALITY ENTERPRISE & RTL SUPPORT
# -----------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+Arabic:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;600;700&family=Noto+Sans+Telugu:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Noto Sans Devanagari', 'Noto Sans Telugu', 'Noto Sans Arabic', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* Main Container padding */
.main .block-container {
    max-width: 1060px;
    padding-top: 1.5rem;
    padding-bottom: 4rem;
    padding-left: 1.5rem;
    padding-right: 1.5rem;
}

/* RTL Layout Mode */
.rtl-container {
    direction: rtl;
    text-align: right;
    font-family: 'Noto Sans Arabic', 'Inter', sans-serif;
}
.rtl-container .source-meta,
.rtl-container code,
.rtl-container pre,
.rtl-container a.source-title {
    direction: ltr;
    text-align: left;
    display: inline-block;
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
    margin-bottom: 1.5rem;
    line-height: 1.5;
}

/* Card Containers */
.research-card {
    background: rgba(128, 128, 128, 0.07);
    border: 1px solid rgba(128, 128, 128, 0.22);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    margin-bottom: 1.25rem;
    color: inherit;
}

.tutor-card {
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-left: 4px solid #3b82f6;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.25rem;
    color: inherit;
}
.rtl-container .tutor-card {
    border-left: 1px solid rgba(59, 130, 246, 0.3);
    border-right: 4px solid #3b82f6;
}

/* Metric Badges */
.metric-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: rgba(128, 128, 128, 0.1);
    color: inherit;
    border: 1px solid rgba(128, 128, 128, 0.25);
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
    background: rgba(128, 128, 128, 0.08);
    border: 1px solid rgba(128, 128, 128, 0.22);
    border-radius: 6px;
    margin-bottom: 0.5rem;
    font-size: 0.92rem;
    color: inherit;
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
    background: rgba(128, 128, 128, 0.07);
    border: 1px solid rgba(128, 128, 128, 0.22);
    border-radius: 8px;
    padding: 1.1rem 1.25rem;
    margin-bottom: 0.85rem;
    transition: all 0.15s ease;
    color: inherit;
}
.source-card:hover {
    border-color: #3b82f6;
    background: rgba(59, 130, 246, 0.05);
}
.source-title {
    font-size: 1.02rem;
    font-weight: 600;
    color: #3b82f6 !important;
    text-decoration: none;
}
.source-title:hover {
    text-decoration: underline;
}
.source-meta {
    font-size: 0.82rem;
    opacity: 0.85;
    margin-top: 0.25rem;
    margin-bottom: 0.5rem;
    font-family: 'JetBrains Mono', monospace;
    color: inherit;
}
.source-rationale {
    font-size: 0.89rem;
    color: inherit;
    background: rgba(59, 130, 246, 0.1);
    border-left: 3px solid #3b82f6;
    padding: 0.45rem 0.75rem;
    margin-top: 0.45rem;
    border-radius: 0 6px 6px 0;
}
.rtl-container .source-rationale {
    border-left: none;
    border-right: 3px solid #3b82f6;
    border-radius: 6px 0 0 6px;
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
if "selected_language" not in st.session_state:
    st.session_state["selected_language"] = "en"
if "research_mode" not in st.session_state:
    st.session_state["research_mode"] = "deep"


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
            st.info("Enter your Gemini API Key or set `GEMINI_API_KEY` in `.env` / Cloud Secrets.", icon="💡")

    st.divider()
    
    # Model Selection
    model_choice = st.selectbox(
        "LLM Provider & Model",
        options=["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0,
        help="Gemini 2.5 Flash offers superior speed and up-to-date reasoning for empirical research synthesis.",
    )

    # Search Rigor
    search_depth = st.selectbox(
        "Web Retrieval Rigor",
        options=["Standard (4 Queries, ~8 Sources)", "Deep (6 Queries, ~12 Sources)"],
        index=0,
    )
    
    max_queries = 6 if "Deep" in search_depth else 4
    max_sources = 12 if "Deep" in search_depth else 8

    st.divider()

    st.markdown("### 🌐 Multilingual Research & Tutor")
    st.caption("• English\n• हिन्दी (Hindi)\n• తెలుగు (Telugu)\n• العربية (Arabic RTL)\n\n• Zero-Hallucination Citation Grounding\n• Intelligent 'Understand This Topic' Tutor")

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
    '<p style="font-size: 1.05rem; opacity: 0.85; margin-bottom: 1.5rem; line-height: 1.5;">Autonomous research engine & intelligent topic tutor. Investigates the web, cross-checks evidence, and teaches concepts in your preferred language with verified citations.</p>',
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# RESEARCH QUESTION INPUT, LANGUAGE, & MODE CONTROLS
# -----------------------------------------------------------------------------
lang_options = {
    "English": "en",
    "हिन्दी (Hindi)": "hi",
    "తెలుగు (Telugu)": "te",
    "العربية (Arabic)": "ar",
}
lang_keys = list(lang_options.keys())

# Row 1: Language and Mode Selector Pills
col_mode, col_lang = st.columns([3, 2])
with col_mode:
    selected_mode_ui = st.radio(
        "Research & Teaching Depth:",
        options=["💡 Explain Simply (Beginner Mode)", "🔬 Deep Research (Detailed Mode)"],
        index=1 if st.session_state.get("research_mode") == "deep" else 0,
        horizontal=True,
    )
    chosen_mode = "deep" if "Deep" in selected_mode_ui else "simple"
    st.session_state["research_mode"] = chosen_mode

with col_lang:
    current_lang_code = st.session_state.get("selected_language", "en")
    default_lang_idx = 0
    for idx, (lbl, code) in enumerate(lang_options.items()):
        if code == current_lang_code:
            default_lang_idx = idx
            break

    selected_lang_label = st.selectbox(
        "🌐 Research Language:",
        options=lang_keys,
        index=default_lang_idx,
    )
    chosen_lang = lang_options[selected_lang_label]
    st.session_state["selected_language"] = chosen_lang


def populate_example_query(q_text: str):
    st.session_state["main_query_input"] = q_text


# Row 2: Search Input & Action Button
col_input, col_btn = st.columns([5, 1.3])

with col_input:
    user_query = st.text_input(
        "Enter your research question:",
        placeholder="e.g., What are the latest breakthroughs in solid-state battery technology?",
        label_visibility="collapsed",
        key="main_query_input",
    )

with col_btn:
    start_clicked = st.button("Start Research 🚀", type="primary", use_container_width=True)

# Example pills
example_questions = [
    "What is Generative AI and how does it work?",
    "How is AI transforming modern healthcare?",
    "Compare Python and R for data science in 2026.",
    "What are autonomous AI agents and multi-agent systems?",
]

st.markdown("<p style='font-size: 0.85rem; opacity: 0.8; margin-top: 0.35rem; margin-bottom: 0.4rem;'>💡 <b>Example investigations:</b></p>", unsafe_allow_html=True)
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
            "report": {"status": "pending", "desc": f"Synthesize report & tutor guide in {selected_lang_label}"},
        }
        st.session_state["activity_logs"] = []

        # Render Progress Stepper Container
        stepper_container = st.container()
        
        stages_ui = {
            "plan": "1. Research Planning & Search Formulation",
            "search": "2. Multi-Angle Web Search Retrieval",
            "collect": "3. Content Extraction & Normalization",
            "analyze": "4. Cross-Source Fact & Contradiction Check",
            "report": f"5. Citation Synthesis & Tutor Guide ({SUPPORTED_LANGUAGES[chosen_lang]['native']})",
        }

        def render_stepper():
            with stepper_container:
                st.markdown("### 🔄 Research & Tutoring In Progress")
                for key, title in stages_ui.items():
                    info = st.session_state["research_stages"].get(key, {"status": "pending", "desc": ""})
                    st_val = info["status"]
                    if st_val == "completed":
                        icon_html = '<span class="step-icon-completed">✓</span>'
                    elif st_val == "running":
                        icon_html = '<span class="step-icon-running">●</span>'
                    else:
                        icon_html = '<span class="step-icon-pending">○</span>'
                    
                    desc_txt = f" — <span style='opacity: 0.75; font-size: 0.85rem;'>{info.get('desc', '')}</span>" if info.get("desc") else ""
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
            with st.spinner("Autonomous agent is investigating the web & formulating explanations..."):
                result = agent.run(
                    question=target_question,
                    language=chosen_lang,
                    mode=chosen_mode,
                    on_progress=on_progress_update,
                )
                st.session_state["research_result"] = result
                st.rerun()
        except Exception as e:
            st.error(f"Research execution failed: {str(e)}", icon="❌")


# -----------------------------------------------------------------------------
# RESULTS DASHBOARD & TUTOR EXPERIENCE
# -----------------------------------------------------------------------------
result: Optional[ResearchSessionResult] = st.session_state.get("research_result")

if result:
    if not result.success:
        st.error(f"Research Incomplete: {result.error_message or 'Unknown error.'}", icon="⚠️")
        if result.plan:
            with st.expander("View Formulated Research Plan"):
                st.json(result.plan)
    else:
        # Dynamic Language Switching Bar in Results
        col_res_hdr, col_switch_lang = st.columns([3, 1.5])
        
        with col_res_hdr:
            m = result.metrics
            current_lang = result.language
            is_rtl = current_lang == "ar"
            rtl_class = "rtl-container" if is_rtl else ""

            st.markdown(
                f"""
                <div>
                    <span class="metric-pill">⏱️ <b>{m.get('duration_seconds', 0)}s</b></span>
                    <span class="metric-pill">🌐 Sources: <b>{m.get('sources_retrieved', 0)}</b></span>
                    <span class="metric-pill">📌 Citations: <b>{m.get('citations_referenced', 0)}</b></span>
                    <span class="metric-pill">🗣️ Language: <b>{SUPPORTED_LANGUAGES.get(current_lang, {}).get('native', current_lang)}</b></span>
                    <span class="metric-pill">🎯 Mode: <b>{result.mode.title()}</b></span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_switch_lang:
            # Language switcher without re-searching
            curr_idx = 0
            for idx, (lbl, code) in enumerate(lang_options.items()):
                if code == current_lang:
                    curr_idx = idx
                    break
            
            switch_to_label = st.selectbox(
                "🔄 Change Language (Instant):",
                options=lang_keys,
                index=curr_idx,
                key="results_lang_switcher",
            )
            target_switch_code = lang_options[switch_to_label]

            if target_switch_code != result.language:
                runtime_config = AppConfig(
                    gemini_api_key=api_key_input,
                    gemini_model=model_choice,
                )
                agent = ResearchAgent(api_key=api_key_input, config=runtime_config)
                with st.spinner(f"Translating & adapting report into {SUPPORTED_LANGUAGES[target_switch_code]['native']}..."):
                    updated_res = agent.switch_language(result, target_switch_code)
                    st.session_state["research_result"] = updated_res
                    st.session_state["selected_language"] = target_switch_code
                    st.rerun()

        # Tabs for Pedagogical Tutor, Deep Report, Sources, Evidence Matrix, Plan, and Exports
        tab_tutor, tab_report, tab_sources, tab_evidence, tab_plan, tab_export = st.tabs([
            "🎓 Understand This Topic",
            "📊 Deep Research Report",
            f"🌐 Verified Sources ({len(result.sources)})",
            "⚖️ Cross-Check & Discrepancies",
            "📐 Research Plan & Trace",
            "💾 Export Dossier",
        ])

        # TAB 1: UNDERSTAND THIS TOPIC (TEACHING TUTOR)
        with tab_tutor:
            st.markdown(
                f"<div class='tutor-card {rtl_class}'>"
                f"<h2 style='font-size: 1.45rem; font-weight: 700; margin-top: 0;'>🎓 Understand This Topic: {result.question}</h2>"
                f"<p style='opacity: 0.8; margin-bottom: 0;'>Intelligent topic guide explaining core mechanisms, terminology, and real-world impact in {SUPPORTED_LANGUAGES.get(result.language, {}).get('native', 'English')}.</p>"
                f"</div>",
                unsafe_allow_html=True,
            )
            
            if is_rtl:
                st.markdown(f'<div class="rtl-container">{result.teaching_markdown}</div>', unsafe_allow_html=True)
            else:
                st.markdown(result.teaching_markdown)

        # TAB 2: DEEP RESEARCH REPORT
        with tab_report:
            st.markdown(
                f"<div class='research-card {rtl_class}'>"
                f"<h2 style='font-size: 1.45rem; font-weight: 700; margin-top: 0;'>📊 Intelligence Report: {result.question}</h2>"
                f"<p style='opacity: 0.8; margin-bottom: 0;'>Evidence-backed research report with verified bracketed source citations ([1], [2]).</p>"
                f"</div>",
                unsafe_allow_html=True,
            )
            
            if is_rtl:
                st.markdown(f'<div class="rtl-container">{result.report_markdown}</div>', unsafe_allow_html=True)
            else:
                st.markdown(result.report_markdown)

        # TAB 3: VERIFIED SOURCES
        with tab_sources:
            st.markdown("### 🌐 Verified Web References")
            st.caption("All factual claims, numbers, and citations are grounded strictly in the following retrieved web documents.")

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
                            <span style="font-size: 0.75rem; opacity: 0.75;">{status_badge} ({word_c} words)</span>
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

        # TAB 4: EVIDENCE & CROSS-CHECK MATRIX
        with tab_evidence:
            st.markdown("### ⚖️ Cross-Source Verification & Discrepancy Matrix")
            
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

        # TAB 5: PLAN & ACTIVITY TRACE
        with tab_plan:
            st.markdown("### 📐 Autonomous Research Plan Breakdown")
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

        # TAB 6: EXPORTS
        with tab_export:
            st.markdown("### 💾 Export Research Dossier")
            st.caption("Download the compiled report and teaching guide as clean Markdown or structured JSON for data analysis pipelines.")

            combined_report_text = f"{result.teaching_markdown}\n\n---\n\n{result.report_markdown}"

            md_content = build_markdown_report_export(
                question=result.question,
                report_content=combined_report_text,
                sources=result.sources,
            )

            json_content = build_json_export(
                question=result.question,
                plan=result.plan or {},
                report=combined_report_text,
                sources=result.sources,
                contradictions=result.analysis.get("contradictions_and_divergences", []) if result.analysis else [],
                metrics=result.metrics,
            )

            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                st.download_button(
                    label="📥 Download Markdown Dossier (.md)",
                    data=md_content,
                    file_name=f"ResearchAI_{result.language}_{int(time.time())}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with col_ex2:
                st.download_button(
                    label="📥 Download Structured JSON (.json)",
                    data=json_content,
                    file_name=f"ResearchAI_{result.language}_{int(time.time())}.json",
                    mime="application/json",
                    use_container_width=True,
                )

            with st.expander("Preview Raw Markdown Dossier"):
                st.code(md_content, language="markdown")
