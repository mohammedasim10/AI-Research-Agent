"""
voice_component.py - Client-Side Web Speech API Voice Engine & Highlight-to-Listen Controller.
Provides in-browser zero-latency text-to-speech, interactive selection read-aloud,
speed regulation (0.75x - 1.5x), strict language-to-voice matching (English, Hindi, Telugu, Arabic),
dynamic voice discovery, and explicit no-fallback device voice warning badges.
"""

import json
from typing import Optional


def get_voice_controller_html(language_code: str = "en", default_text: str = "") -> str:
    """
    Renders the browser speech synthesis controller and floating text-selection listener.
    Zero server dependency; runs directly in the user's browser using native Web Speech APIs.

    Strictly maps:
      - 'en' -> en-US / en-IN / en-* (English)
      - 'hi' -> hi-IN / hi-* (Hindi)
      - 'te' -> te-IN / te-* (Telugu)
      - 'ar' -> ar-SA / ar-* (Arabic)

    Never falls back to an English voice for Hindi, Telugu, or Arabic.
    If a compatible voice is not found on the device, explicitly warns the user.
    """
    lang_map = {
        "en": {
            "code": "en-US",
            "fallback_codes": ["en-US", "en-IN", "en-GB", "en"],
            "name": "English",
            "native_name": "English",
            "regex": r"^en",
        },
        "hi": {
            "code": "hi-IN",
            "fallback_codes": ["hi-IN", "hi"],
            "name": "Hindi",
            "native_name": "हिन्दी",
            "regex": r"^hi",
        },
        "te": {
            "code": "te-IN",
            "fallback_codes": ["te-IN", "te"],
            "name": "Telugu",
            "native_name": "తెలుగు",
            "regex": r"^te",
        },
        "ar": {
            "code": "ar-SA",
            "fallback_codes": ["ar-SA", "ar-EG", "ar-AE", "ar-QA", "ar-KW", "ar"],
            "name": "Arabic",
            "native_name": "العربية",
            "regex": r"^ar",
        },
    }
    lang_config = lang_map.get(language_code, lang_map["en"])
    sanitized_default = json.dumps(default_text)

    html_code = f"""
    <div id="voice-engine-root" style="margin-top: 0.35rem; margin-bottom: 0.85rem;">
        <style>
            :root {{
                --voice-text: #1e293b;
                --voice-bg: rgba(0, 0, 0, 0.04);
                --voice-border: rgba(0, 0, 0, 0.16);
                --voice-sec-bg: #e2e8f0;
                --voice-sec-border: #cbd5e1;
                --voice-badge-ok-bg: rgba(34, 197, 94, 0.12);
                --voice-badge-ok-border: #22c55e;
                --voice-badge-ok-text: #15803d;
                --voice-badge-warn-bg: rgba(234, 179, 8, 0.14);
                --voice-badge-warn-border: #eab308;
                --voice-badge-warn-text: #a16207;
            }}
            @media (prefers-color-scheme: dark) {{
                :root {{
                    --voice-text: #f1f5f9;
                    --voice-bg: rgba(255, 255, 255, 0.06);
                    --voice-border: rgba(255, 255, 255, 0.18);
                    --voice-sec-bg: rgba(255, 255, 255, 0.12);
                    --voice-sec-border: rgba(255, 255, 255, 0.25);
                    --voice-badge-ok-bg: rgba(34, 197, 94, 0.18);
                    --voice-badge-ok-border: #22c55e;
                    --voice-badge-ok-text: #4ade80;
                    --voice-badge-warn-bg: rgba(234, 179, 8, 0.18);
                    --voice-badge-warn-border: #eab308;
                    --voice-badge-warn-text: #fde047;
                }}
            }}
            body {{
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                color: var(--voice-text);
            }}
            .voice-dock {{
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
                padding: 0.75rem 1rem;
                background: var(--voice-bg);
                border: 1.5px solid var(--voice-border);
                border-radius: 8px;
                color: var(--voice-text);
            }}
            .voice-controls-row {{
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: 0.65rem;
            }}
            .voice-btn {{
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
            }}
            .voice-btn:hover {{
                background: #1d4ed8 !important;
                transform: translateY(-1px);
            }}
            .voice-btn-secondary {{
                background: var(--voice-sec-bg) !important;
                color: var(--voice-text) !important;
                border: 1.5px solid var(--voice-sec-border) !important;
                box-shadow: none;
                font-weight: 600;
            }}
            .voice-btn-secondary:hover {{
                border-color: #3b82f6 !important;
                color: #3b82f6 !important;
                transform: translateY(-1px);
            }}
            .voice-select, .voice-speed-select {{
                background: var(--voice-sec-bg);
                color: var(--voice-text);
                border: 1.5px solid var(--voice-sec-border);
                border-radius: 6px;
                padding: 0.35rem 0.6rem;
                font-size: 0.825rem;
                font-weight: 600;
                cursor: pointer;
                max-width: 220px;
            }}
            .voice-status-row {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 0.5rem;
                font-size: 0.8rem;
            }}
            .status-badge {{
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.2rem 0.6rem;
                border-radius: 5px;
                font-weight: 600;
            }}
            .status-ok {{
                background: var(--voice-badge-ok-bg);
                border: 1px solid var(--voice-badge-ok-border);
                color: var(--voice-badge-ok-text);
            }}
            .status-warn {{
                background: var(--voice-badge-warn-bg);
                border: 1px solid var(--voice-badge-warn-border);
                color: var(--voice-badge-warn-text);
            }}
            
            /* Warning Banner Modal / Toast */
            #voice-warning-banner {{
                display: none;
                background: rgba(239, 68, 68, 0.12);
                border: 1.5px solid #ef4444;
                color: #ef4444;
                border-radius: 6px;
                padding: 0.5rem 0.75rem;
                font-size: 0.825rem;
                margin-top: 0.35rem;
                line-height: 1.4;
            }}

            /* Floating Highlight-to-Listen Action Pill */
            #floating-listen-pill {{
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
            }}
            #floating-listen-pill:hover {{
                background: #2563eb;
                transform: scale(1.05);
            }}
        </style>

        <div class="voice-dock">
            <!-- Top Controls Row -->
            <div class="voice-controls-row">
                <button class="voice-btn" id="btn-speak-main" onclick="speakTargetText()">
                    🔊 <span>Listen to Summary</span>
                </button>
                <button class="voice-btn voice-btn-secondary" id="btn-pause" onclick="pauseSpeech()">
                    ⏸ <span>Pause</span>
                </button>
                <button class="voice-btn voice-btn-secondary" id="btn-stop" onclick="stopSpeech()">
                    ⏹ <span>Stop</span>
                </button>

                <span style="font-size: 0.825rem; font-weight: 600; margin-left: 0.25rem;">Voice:</span>
                <select class="voice-select" id="voice-select" onchange="updateSelectedVoice(this.value)">
                    <option value="" disabled selected>🔍 Scanning device voices...</option>
                </select>

                <span style="font-size: 0.825rem; font-weight: 600;">Speed:</span>
                <select class="voice-speed-select" id="speed-select" onchange="updateRate(this.value)">
                    <option value="0.75">0.75x</option>
                    <option value="1.0" selected>1.0x (Normal)</option>
                    <option value="1.25">1.25x</option>
                    <option value="1.5">1.5x</option>
                </select>
            </div>

            <!-- Bottom Status Row -->
            <div class="voice-status-row">
                <div id="voice-status-container">
                    <span class="status-badge status-warn" id="voice-status-badge">
                        🔍 Inspecting device voices for {lang_config['name']}...
                    </span>
                </div>
                <div style="opacity: 0.8; font-size: 0.775rem;">
                    💡 Highlight any text on screen to listen in <b>{lang_config['native_name']}</b>
                </div>
            </div>

            <!-- Warning Container (shown when voice unavailable upon click) -->
            <div id="voice-warning-banner"></div>
        </div>

        <!-- Floating Selection Listener Tooltip -->
        <button id="floating-listen-pill" onclick="speakSelectedText(event)">
            🔊 Read Selected Text ({lang_config['native_name']})
        </button>

        <script>
            (function() {{
                const targetLangCode = "{lang_config['code']}";
                const targetLangName = "{lang_config['name']}";
                const targetNativeName = "{lang_config['native_name']}";
                const langRegex = new RegExp("{lang_config['regex']}", "i");
                
                let currentRate = 1.0;
                let synth = window.speechSynthesis;
                let compatibleVoices = [];
                let activeVoice = null;
                let defaultArticleText = {sanitized_default};

                function updateStatusDisplay(isAvailable, voiceName) {{
                    const badge = document.getElementById('voice-status-badge');
                    if (!badge) return;

                    if (isAvailable && voiceName) {{
                        badge.className = "status-badge status-ok";
                        badge.innerHTML = "✓ Native " + targetLangName + " voice active: <b>" + voiceName + "</b>";
                    }} else {{
                        badge.className = "status-badge status-warn";
                        badge.innerHTML = "⚠️ Native " + targetLangName + " voice unavailable on this device";
                    }}
                }}

                function showWarningMessage(msg) {{
                    const banner = document.getElementById('voice-warning-banner');
                    if (banner) {{
                        banner.innerText = msg;
                        banner.style.display = 'block';
                        setTimeout(() => {{
                            banner.style.display = 'none';
                        }}, 7000);
                    }}
                }}

                function populateVoices() {{
                    if (!synth) {{
                        updateStatusDisplay(false);
                        return;
                    }}
                    const allVoices = synth.getVoices() || [];
                    
                    // Filter specifically for voices matching the target language regex
                    compatibleVoices = allVoices.filter(v => {{
                        return langRegex.test(v.lang) || (v.lang && v.lang.toLowerCase().startsWith(targetLangCode.slice(0, 2).toLowerCase()));
                    }});

                    const voiceSelect = document.getElementById('voice-select');
                    if (voiceSelect) {{
                        voiceSelect.innerHTML = '';
                        if (compatibleVoices.length > 0) {{
                            compatibleVoices.forEach((v, index) => {{
                                const opt = document.createElement('option');
                                opt.value = index;
                                opt.text = v.name + " (" + v.lang + ")";
                                voiceSelect.appendChild(opt);
                            }});
                            // Pick the first compatible voice
                            activeVoice = compatibleVoices[0];
                            voiceSelect.selectedIndex = 0;
                            updateStatusDisplay(true, activeVoice.name);
                        }} else {{
                            const opt = document.createElement('option');
                            opt.value = "-1";
                            opt.text = "⚠️ No " + targetLangName + " voice installed";
                            opt.disabled = true;
                            opt.selected = true;
                            voiceSelect.appendChild(opt);
                            activeVoice = null;
                            updateStatusDisplay(false);
                        }}
                    }}
                }}

                window.updateSelectedVoice = function(indexStr) {{
                    const idx = parseInt(indexStr, 10);
                    if (compatibleVoices && compatibleVoices[idx]) {{
                        activeVoice = compatibleVoices[idx];
                        updateStatusDisplay(true, activeVoice.name);
                    }}
                }};

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
                        showWarningMessage("Web Speech API is not supported in this browser.");
                        return;
                    }}

                    // STRICT VALIDATION: DO NOT silently use English voice if target language is not English
                    if (!activeVoice && targetLangCode !== 'en-US') {{
                        showWarningMessage("Your device does not currently provide a " + targetLangName + " (" + targetNativeName + ") voice. Please install/enable a " + targetLangName + " speech voice in your device/browser settings.");
                        return;
                    }}

                    synth.cancel();

                    const clean = text.replace(/\\[\\d+\\]/g, '')
                                      .replace(/[*#_~`]/g, '')
                                      .trim();
                    if (!clean) return;

                    const utterance = new SpeechSynthesisUtterance(clean);
                    utterance.rate = currentRate;
                    utterance.lang = activeVoice ? activeVoice.lang : targetLangCode;
                    if (activeVoice) {{
                        utterance.voice = activeVoice;
                    }}

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
