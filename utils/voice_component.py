"""
voice_component.py - Client-Side Web Speech API Voice Engine & Highlight-to-Listen Controller.
Provides in-browser zero-latency text-to-speech, interactive selection read-aloud,
speed regulation (0.75x - 1.5x), and native language voice detection for English, Hindi, Telugu, and Arabic.
"""

import json
from typing import Optional


def get_voice_controller_html(language_code: str = "en", default_text: str = "") -> str:
    """
    Renders the browser speech synthesis controller and floating text-selection listener.
    Zero server dependency; runs directly in the user's browser using native Web Speech APIs.
    """
    lang_map = {
        "en": {"code": "en-US", "name": "English", "test": "en"},
        "hi": {"code": "hi-IN", "name": "हिन्दी (Hindi)", "test": "hi"},
        "te": {"code": "te-IN", "name": "తెలుగు (Telugu)", "test": "te"},
        "ar": {"code": "ar-SA", "name": "العربية (Arabic)", "test": "ar"},
    }
    lang_config = lang_map.get(language_code, lang_map["en"])
    sanitized_default = json.dumps(default_text)

    html_code = f"""
    <div id="voice-engine-root" style="margin-top: 0.5rem; margin-bottom: 1rem;">
        <style>
            :root {
                --voice-text: #1e293b;
                --voice-bg: rgba(0, 0, 0, 0.04);
                --voice-border: rgba(0, 0, 0, 0.15);
                --voice-sec-bg: #e2e8f0;
                --voice-sec-border: #cbd5e1;
            }
            @media (prefers-color-scheme: dark) {
                :root {
                    --voice-text: #f1f5f9;
                    --voice-bg: rgba(255, 255, 255, 0.06);
                    --voice-border: rgba(255, 255, 255, 0.18);
                    --voice-sec-bg: rgba(255, 255, 255, 0.12);
                    --voice-sec-border: rgba(255, 255, 255, 0.25);
                }
            }
            body {
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                color: var(--voice-text);
            }
            .voice-dock {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: 0.65rem;
                padding: 0.65rem 0.95rem;
                background: var(--voice-bg);
                border: 1.5px solid var(--voice-border);
                border-radius: 8px;
                color: var(--voice-text);
            }
            .voice-btn {
                background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
                color: #ffffff !important;
                border: 1px solid #1e40af !important;
                border-radius: 6px;
                padding: 0.4rem 0.85rem;
                font-size: 0.85rem;
                font-weight: 600;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                transition: all 0.15s ease;
                box-shadow: 0 1px 3px rgba(37, 99, 235, 0.3);
            }
            .voice-btn:hover {
                background: #1d4ed8 !important;
                transform: translateY(-1px);
            }
            .voice-btn-secondary {
                background: var(--voice-sec-bg) !important;
                color: var(--voice-text) !important;
                border: 1.5px solid var(--voice-sec-border) !important;
                box-shadow: none;
                font-weight: 600;
            }
            .voice-btn-secondary:hover {
                border-color: #3b82f6 !important;
                color: #3b82f6 !important;
                transform: translateY(-1px);
            }
            .voice-speed-select {
                background: var(--voice-sec-bg);
                color: var(--voice-text);
                border: 1.5px solid var(--voice-sec-border);
                border-radius: 6px;
                padding: 0.35rem 0.6rem;
                font-size: 0.825rem;
                font-weight: 600;
                cursor: pointer;
            }
            .voice-status {
                font-size: 0.8rem;
                opacity: 0.9;
                font-family: monospace;
                font-weight: 500;
            }
            
            /* Floating Highlight-to-Listen Action Pill */
            #floating-listen-pill {
                position: fixed;
                display: none;
                z-index: 999999;
                background: #0f172a;
                color: #ffffff;
                border: 1.5px solid #3b82f6;
                box-shadow: 0 4px 16px rgba(0,0,0,0.35);
                border-radius: 20px;
                padding: 0.45rem 0.95rem;
                font-size: 0.85rem;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.1s ease, opacity 0.15s ease;
            }
            #floating-listen-pill:hover {
                background: #2563eb;
                transform: scale(1.05);
            }
        </style>

        <div class="voice-dock">
            <button class="voice-btn" id="btn-speak-main" onclick="speakTargetText()">
                🔊 <span>Listen to Summary</span>
            </button>
            <button class="voice-btn voice-btn-secondary" id="btn-pause" onclick="pauseSpeech()">
                ⏸ <span>Pause</span>
            </button>
            <button class="voice-btn voice-btn-secondary" id="btn-stop" onclick="stopSpeech()">
                ⏹ <span>Stop</span>
            </button>
            
            <span style="font-size: 0.85rem; opacity: 0.9;">Speed:</span>
            <select class="voice-speed-select" id="speed-select" onchange="updateRate(this.value)">
                <option value="0.75">0.75x (Slow)</option>
                <option value="1.0" selected>1.0x (Normal)</option>
                <option value="1.25">1.25x (Fast)</option>
                <option value="1.5">1.5x (Faster)</option>
            </select>

            <span class="voice-status" id="voice-indicator">🔍 Ready ({lang_config['name']})</span>
            <span style="font-size: 0.775rem; opacity: 0.7; margin-left: auto;">💡 Tip: Highlight any text on screen to listen!</span>
        </div>

        <!-- Floating Selection Listener Tooltip -->
        <button id="floating-listen-pill" onclick="speakSelectedText(event)">
            🔊 Read Selected Text
        </button>

        <script>
            (function() {{
                const targetLang = "{lang_config['code']}";
                const langFamily = "{lang_config['test']}";
                let currentRate = 1.0;
                let synth = window.speechSynthesis;
                let availableVoices = [];
                let activeVoice = null;
                let defaultArticleText = {sanitized_default};

                function populateVoices() {{
                    if (!synth) return;
                    availableVoices = synth.getVoices();
                    
                    // Search for matching voice
                    activeVoice = availableVoices.find(v => v.lang === targetLang || v.lang.startsWith(langFamily));
                    const indicator = document.getElementById('voice-indicator');
                    
                    if (activeVoice) {{
                        if (indicator) indicator.innerText = "🗣️ " + activeVoice.name;
                    }} else {{
                        // Fallback voice
                        activeVoice = availableVoices.find(v => v.lang.startsWith('en')) || availableVoices[0] || null;
                        if (indicator) indicator.innerText = "🗣️ Standard Voice (" + targetLang + ")";
                    }}
                }}

                if (synth) {{
                    populateVoices();
                    if (synth.onvoiceschanged !== undefined) {{
                        synth.onvoiceschanged = populateVoices;
                    }}
                }}

                window.updateRate = function(val) {{
                    currentRate = parseFloat(val);
                }};

                window.stopSpeech = function() {{
                    if (synth) synth.cancel();
                    const btn = document.getElementById('btn-speak-main');
                    if (btn) btn.innerHTML = "🔊 <span>Listen to Summary</span>";
                }};

                window.pauseSpeech = function() {{
                    if (!synth) return;
                    if (synth.speaking && !synth.paused) {{
                        synth.pause();
                        const pBtn = document.getElementById('btn-pause');
                        if (pBtn) pBtn.innerHTML = "▶ <span>Resume</span>";
                    }} else if (synth.paused) {{
                        synth.resume();
                        const pBtn = document.getElementById('btn-pause');
                        if (pBtn) pBtn.innerHTML = "⏸ <span>Pause</span>";
                    }}
                }};

                window.speakTextContent = function(text) {{
                    if (!synth) {{
                        alert("Speech Synthesis is not supported in this browser.");
                        return;
                    }}
                    synth.cancel();

                    const clean = text.replace(/\\[\\d+\\]/g, '')
                                      .replace(/[*#_~`]/g, '')
                                      .trim();
                    if (!clean) return;

                    const utterance = new SpeechSynthesisUtterance(clean);
                    utterance.rate = currentRate;
                    utterance.lang = targetLang;
                    if (activeVoice) utterance.voice = activeVoice;

                    const btn = document.getElementById('btn-speak-main');
                    utterance.onstart = function() {{
                        if (btn) btn.innerHTML = "🔊 <span>Speaking...</span>";
                    }};
                    utterance.onend = function() {{
                        if (btn) btn.innerHTML = "🔊 <span>Listen to Summary</span>";
                    }};
                    utterance.onerror = function() {{
                        if (btn) btn.innerHTML = "🔊 <span>Listen to Summary</span>";
                    }};

                    synth.speak(utterance);
                }};

                window.speakTargetText = function() {{
                    if (defaultArticleText) {{
                        speakTextContent(defaultArticleText);
                    }} else {{
                        // Read first available paragraph in parent frame
                        try {{
                            const parentDoc = window.parent.document;
                            const textElem = parentDoc.querySelector('.tutor-card') || parentDoc.querySelector('.main');
                            if (textElem) {{
                                speakTextContent(textElem.innerText.slice(0, 1500));
                            }}
                        }} catch (e) {{
                            console.log("Cross-frame speech fallback:", e);
                        }}
                    }}
                }};

                // Selection Listener across parent and iframe window
                function handleTextSelection(e) {{
                    try {{
                        const parentDoc = window.parent.document || document;
                        const selection = parentDoc.getSelection();
                        const selectedText = selection ? selection.toString().trim() : "";
                        const pill = document.getElementById('floating-listen-pill');

                        if (selectedText.length >= 3) {{
                            const range = selection.getRangeAt(0);
                            const rect = range.getBoundingClientRect();
                            if (pill) {{
                                pill.style.display = 'block';
                                pill.style.top = Math.max(10, rect.top - 45) + 'px';
                                pill.style.left = Math.max(10, rect.left + (rect.width / 2) - 60) + 'px';
                                pill.dataset.selected = selectedText;
                            }}
                        }} else {{
                            if (pill) pill.style.display = 'none';
                        }}
                    }} catch (err) {{}}
                }}

                window.speakSelectedText = function(e) {{
                    if (e) e.stopPropagation();
                    const pill = document.getElementById('floating-listen-pill');
                    const text = pill ? pill.dataset.selected : "";
                    if (text) {{
                        speakTextContent(text);
                    }}
                    if (pill) pill.style.display = 'none';
                }};

                try {{
                    const parentDoc = window.parent.document || document;
                    parentDoc.addEventListener('mouseup', handleTextSelection);
                    parentDoc.addEventListener('touchend', handleTextSelection);
                    parentDoc.addEventListener('mousedown', function(e) {{
                        const pill = document.getElementById('floating-listen-pill');
                        if (pill && e.target !== pill) {{
                            pill.style.display = 'none';
                        }}
                    }});
                }} catch (e) {{}}
            }})();
        </script>
    </div>
    """
    return html_code
