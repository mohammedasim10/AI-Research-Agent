"""
voice_component.py - Client-Side Web Speech API Voice Engine & Highlight-to-Listen Controller.
Provides in-browser zero-latency text-to-speech, interactive selection read-aloud,
section-by-section listen buttons, speed regulation (0.75x - 1.5x), strict language-to-voice matching
(English, Hindi, Telugu, Arabic), dynamic voice discovery, and guaranteed speech synthesis.
"""

import json
from typing import Optional


HTML_TEMPLATE = r"""
<div id="voice-engine-root" style="margin-top: 0.35rem; margin-bottom: 0.85rem;">
    <style>
        :root {
            --voice-text: #1e293b;
            --voice-bg: rgba(0, 0, 0, 0.04);
            --voice-border: rgba(0, 0, 0, 0.16);
            --voice-sec-bg: #e2e8f0;
            --voice-sec-border: #cbd5e1;
            --voice-badge-ok-bg: rgba(34, 197, 94, 0.12);
            --voice-badge-ok-border: #22c55e;
            --voice-badge-ok-text: #15803d;
            --voice-badge-info-bg: rgba(59, 130, 246, 0.12);
            --voice-badge-info-border: #3b82f6;
            --voice-badge-info-text: #1d4ed8;
            --voice-badge-warn-bg: rgba(234, 179, 8, 0.14);
            --voice-badge-warn-border: #eab308;
            --voice-badge-warn-text: #a16207;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --voice-text: #f1f5f9;
                --voice-bg: rgba(255, 255, 255, 0.06);
                --voice-border: rgba(255, 255, 255, 0.18);
                --voice-sec-bg: rgba(255, 255, 255, 0.12);
                --voice-sec-border: rgba(255, 255, 255, 0.25);
                --voice-badge-ok-bg: rgba(34, 197, 94, 0.18);
                --voice-badge-ok-border: #22c55e;
                --voice-badge-ok-text: #4ade80;
                --voice-badge-info-bg: rgba(59, 130, 246, 0.18);
                --voice-badge-info-border: #3b82f6;
                --voice-badge-info-text: #60a5fa;
                --voice-badge-warn-bg: rgba(234, 179, 8, 0.18);
                --voice-badge-warn-border: #eab308;
                --voice-badge-warn-text: #fde047;
            }
        }
        body {
            margin: 0;
            padding: 0;
            background: transparent;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: var(--voice-text);
            box-sizing: border-box;
        }
        .voice-dock {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            padding: 0.75rem 1rem;
            background: var(--voice-bg);
            border: 1.5px solid var(--voice-border);
            border-radius: 8px;
            color: var(--voice-text);
        }
        .voice-controls-row, .voice-sections-row {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.5rem;
        }
        .voice-btn {
            background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
            color: #ffffff !important;
            border: 1px solid #1e40af !important;
            border-radius: 6px;
            padding: 0.35rem 0.75rem;
            font-size: 0.825rem;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            transition: all 0.15s ease;
            box-shadow: 0 1px 3px rgba(37, 99, 235, 0.3);
            white-space: nowrap;
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
        .voice-section-btn {
            background: rgba(59, 130, 246, 0.1) !important;
            color: var(--voice-text) !important;
            border: 1px solid rgba(59, 130, 246, 0.35) !important;
            border-radius: 5px;
            padding: 0.25rem 0.6rem;
            font-size: 0.775rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            white-space: nowrap;
        }
        .voice-section-btn:hover {
            background: #2563eb !important;
            color: #ffffff !important;
            border-color: #1d4ed8 !important;
        }
        .voice-select, .voice-speed-select {
            background: var(--voice-sec-bg);
            color: var(--voice-text);
            border: 1.5px solid var(--voice-sec-border);
            border-radius: 6px;
            padding: 0.3rem 0.55rem;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            max-width: 220px;
        }
        .voice-status-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 0.5rem;
            font-size: 0.8rem;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.2rem 0.6rem;
            border-radius: 5px;
            font-weight: 600;
        }
        .status-ok {
            background: var(--voice-badge-ok-bg);
            border: 1px solid var(--voice-badge-ok-border);
            color: var(--voice-badge-ok-text);
        }
        .status-info {
            background: var(--voice-badge-info-bg);
            border: 1px solid var(--voice-badge-info-border);
            color: var(--voice-badge-info-text);
        }
        .status-warn {
            background: var(--voice-badge-warn-bg);
            border: 1px solid var(--voice-badge-warn-border);
            color: var(--voice-badge-warn-text);
        }
        
        /* Warning Banner */
        #voice-warning-banner {
            display: none;
            background: rgba(239, 68, 68, 0.12);
            border: 1.5px solid #ef4444;
            color: #ef4444;
            border-radius: 6px;
            padding: 0.5rem 0.75rem;
            font-size: 0.825rem;
            margin-top: 0.25rem;
            line-height: 1.4;
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
        <!-- Row 1: Primary Controls & Dropdowns -->
        <div class="voice-controls-row">
            <button class="voice-btn" id="btn-speak-main" onclick="handleMainListenClick()">
                🔊 <span>Listen</span>
            </button>
            <button class="voice-btn voice-btn-secondary" id="btn-pause" onclick="pauseSpeech()">
                ⏸ <span>Pause</span>
            </button>
            <button class="voice-btn voice-btn-secondary" id="btn-stop" onclick="stopSpeech()">
                ⏹ <span>Stop</span>
            </button>

            <span style="font-size: 0.8rem; font-weight: 600; margin-left: 0.15rem;">Voice:</span>
            <select class="voice-select" id="voice-select" onchange="updateSelectedVoice(this.value)">
                <option value="" disabled selected>🔍 Scanning device voices...</option>
            </select>

            <span style="font-size: 0.8rem; font-weight: 600;">Speed:</span>
            <select class="voice-speed-select" id="speed-select" onchange="updateRate(this.value)">
                <option value="0.75">0.75x</option>
                <option value="1.0" selected>1.0x (Normal)</option>
                <option value="1.25">1.25x</option>
                <option value="1.5">1.5x</option>
            </select>
        </div>

        <!-- Row 2: Section Quick-Listen Buttons -->
        <div class="voice-sections-row">
            <span style="font-size: 0.775rem; font-weight: 700; opacity: 0.85;">Read Section:</span>
            <button class="voice-section-btn" onclick="speakSection('direct')">🎯 Direct Answer</button>
            <button class="voice-section-btn" onclick="speakSection('what')">🎓 Understand</button>
            <button class="voice-section-btn" onclick="speakSection('how')">⚙️ How It Works</button>
            <button class="voice-section-btn" onclick="speakSection('example')">💡 Simple Example</button>
            <button class="voice-section-btn" onclick="speakSection('takeaway')">📌 Key Takeaway</button>
        </div>

        <!-- Row 3: Status & Tips -->
        <div class="voice-status-row">
            <div id="voice-status-container">
                <span class="status-badge status-info" id="voice-status-badge">
                    🌐 Speech configured for __TARGET_LANG_NAME__ (__TARGET_LANG_CODE__)
                </span>
            </div>
            <div style="opacity: 0.8; font-size: 0.75rem;">
                💡 Highlight text on screen to speak selection in <b>__TARGET_NATIVE_NAME__</b>
            </div>
        </div>

        <!-- Warning Container -->
        <div id="voice-warning-banner"></div>
    </div>

    <!-- Floating Selection Listener Tooltip -->
    <button id="floating-listen-pill" onclick="speakSelectedText(event)">
        🔊 Read Selected Text (__TARGET_NATIVE_NAME__)
    </button>

    <script>
        (function() {
            const targetLangCode = "__TARGET_LANG_CODE__";
            const targetLangName = "__TARGET_LANG_NAME__";
            const targetNativeName = "__TARGET_NATIVE_NAME__";
            const langPrefix = "__TARGET_LANG_PREFIX__".toLowerCase();
            
            let currentRate = 1.0;
            let synth = window.speechSynthesis;
            let compatibleVoices = [];
            let activeVoice = null;
            let defaultArticleText = __DEFAULT_TEXT_JSON__;
            let currentSelectionText = "";

            function updateStatusDisplay(isExplicitMatch, voiceName) {
                const badge = document.getElementById('voice-status-badge');
                if (!badge) return;

                if (isExplicitMatch && voiceName) {
                    badge.className = "status-badge status-ok";
                    badge.innerHTML = "✓ Native " + targetLangName + " voice: <b>" + voiceName + "</b>";
                } else {
                    badge.className = "status-badge status-info";
                    badge.innerHTML = "🗣️ Speaking in " + targetLangName + " (" + targetLangCode + ")";
                }
            }

            function showWarningMessage(msg) {
                const banner = document.getElementById('voice-warning-banner');
                if (banner) {
                    banner.innerText = msg;
                    banner.style.display = 'block';
                    setTimeout(() => {
                        banner.style.display = 'none';
                    }, 8000);
                }
            }

            function isVoiceMatch(v) {
                if (!v) return false;
                const l = (v.lang || "").toLowerCase().replace(/_/g, '-');
                const n = (v.name || "").toLowerCase();
                
                if (l.startsWith(langPrefix) || l.startsWith(targetLangCode.toLowerCase())) {
                    return true;
                }
                if (langPrefix === "hi" && (n.includes("hindi") || n.includes("kalpana") || n.includes("hemant") || n.includes("swara") || n.includes("madhur") || l.startsWith("hin"))) {
                    return true;
                }
                if (langPrefix === "te" && (n.includes("telugu") || n.includes("mohan") || n.includes("chitra") || l.startsWith("tel"))) {
                    return true;
                }
                if (langPrefix === "ar" && (n.includes("arabic") || n.includes("hoda") || n.includes("naayf") || n.includes("salma") || n.includes("shakir") || n.includes("maged") || l.startsWith("ara"))) {
                    return true;
                }
                if (langPrefix === "en" && (l.startsWith("en") || n.includes("english"))) {
                    return true;
                }
                return false;
            }

            function populateVoices() {
                if (!synth) return;
                const allVoices = synth.getVoices() || [];
                if (allVoices.length === 0) return;
                
                compatibleVoices = allVoices.filter(isVoiceMatch);

                const voiceSelect = document.getElementById('voice-select');
                if (voiceSelect) {
                    voiceSelect.innerHTML = '';
                    if (compatibleVoices.length > 0) {
                        compatibleVoices.forEach((v, index) => {
                            const opt = document.createElement('option');
                            opt.value = index;
                            opt.text = v.name + " (" + v.lang + ")";
                            voiceSelect.appendChild(opt);
                        });
                        activeVoice = compatibleVoices[0];
                        voiceSelect.selectedIndex = 0;
                        updateStatusDisplay(true, activeVoice.name);
                    } else {
                        const opt = document.createElement('option');
                        opt.value = "-1";
                        opt.text = "🗣️ Browser " + targetLangName + " Speech (" + targetLangCode + ")";
                        opt.selected = true;
                        voiceSelect.appendChild(opt);
                        activeVoice = null;
                        updateStatusDisplay(false);
                    }
                }
            }

            window.updateSelectedVoice = function(indexStr) {
                const idx = parseInt(indexStr, 10);
                if (compatibleVoices && compatibleVoices[idx]) {
                    activeVoice = compatibleVoices[idx];
                    updateStatusDisplay(true, activeVoice.name);
                }
            };

            if (synth) {
                populateVoices();
                if (synth.onvoiceschanged !== undefined) {
                    synth.onvoiceschanged = populateVoices;
                }
                // Polling retries to catch delayed voice loading in Chrome / Android / Safari
                setTimeout(populateVoices, 150);
                setTimeout(populateVoices, 500);
                setTimeout(populateVoices, 1200);
            }

            window.updateRate = function(val) {
                currentRate = parseFloat(val);
            };

            window.stopSpeech = function() {
                if (synth) {
                    synth.cancel();
                }
                const btn = document.getElementById('btn-speak-main');
                if (btn) btn.innerHTML = "🔊 <span>Listen</span>";
            };

            window.pauseSpeech = function() {
                if (!synth) return;
                if (synth.speaking && !synth.paused) {
                    synth.pause();
                    const pBtn = document.getElementById('btn-pause');
                    if (pBtn) pBtn.innerHTML = "▶ <span>Resume</span>";
                } else if (synth.paused) {
                    synth.resume();
                    const pBtn = document.getElementById('btn-pause');
                    if (pBtn) pBtn.innerHTML = "⏸ <span>Pause</span>";
                }
            };

            window.speakTextContent = function(text) {
                if (!synth) {
                    showWarningMessage("Web Speech API is not supported in this browser.");
                    return;
                }

                // Unfreeze speech synthesis engine in Chrome
                try {
                    synth.cancel();
                    if (synth.paused) synth.resume();
                } catch (e) {}

                const clean = text.replace(/\[\d+\]/g, '')
                                  .replace(/[*#_~`]/g, '')
                                  .trim();
                if (!clean) return;

                const utterance = new SpeechSynthesisUtterance(clean);
                utterance.rate = currentRate;
                
                // Set language code strictly to target language (e.g. hi-IN, te-IN, ar-SA, en-US)
                utterance.lang = activeVoice ? activeVoice.lang : targetLangCode;
                if (activeVoice) {
                    utterance.voice = activeVoice;
                }

                const btn = document.getElementById('btn-speak-main');
                utterance.onstart = function() {
                    if (btn) btn.innerHTML = "🔊 <span>Speaking...</span>";
                };
                utterance.onend = function() {
                    if (btn) btn.innerHTML = "🔊 <span>Listen</span>";
                };
                utterance.onerror = function(err) {
                    console.log("SpeechSynthesis error:", err);
                    if (btn) btn.innerHTML = "🔊 <span>Listen</span>";
                };

                synth.speak(utterance);
            };

            // Main Listen Button: Priority given to selected text if highlighted, otherwise speaks summary
            window.handleMainListenClick = function() {
                if (currentSelectionText && currentSelectionText.length >= 3) {
                    speakTextContent(currentSelectionText);
                } else if (defaultArticleText) {
                    speakTextContent(defaultArticleText.slice(0, 1500));
                } else {
                    try {
                        const parentDoc = window.parent.document;
                        const textElem = parentDoc.querySelector('.tutor-card') || parentDoc.querySelector('.main');
                        if (textElem) {
                            speakTextContent(textElem.innerText.slice(0, 1500));
                        }
                    } catch (e) {
                        console.log("Cross-frame speech fallback:", e);
                    }
                }
            };

            // Section Reader: Extracts and reads ONLY that section
            window.speakSection = function(sectionKey) {
                const text = defaultArticleText || "";
                let sectionText = "";

                if (sectionKey === 'direct') {
                    const m = text.match(/(?:Direct Answer|प्रत्यक्ष उत्तर|ప్రత్యక్ష సమాధానం|الإجابة المباشرة)([\s\S]*?)(?:###|##|$)/i);
                    sectionText = m ? m[1] : text.slice(0, 500);
                } else if (sectionKey === 'what') {
                    const m = text.match(/(?:What is it|यह क्या है|ఇది ఏమిటి|ما هو)([\s\S]*?)(?:###|##|$)/i);
                    sectionText = m ? m[1] : text.slice(0, 600);
                } else if (sectionKey === 'how') {
                    const m = text.match(/(?:How Does It Work|यह कैसे काम करता है|ఇది ఎలా పనిచేస్తుంది|كيف يعمل)([\s\S]*?)(?:###|##|$)/i);
                    sectionText = m ? m[1] : text.slice(200, 800);
                } else if (sectionKey === 'example') {
                    const m = text.match(/(?:Simple Everyday Example|सरल उदाहरण|సాధారణ ఉదాహరణ|مثال بسيط)([\s\S]*?)(?:###|##|$)/i);
                    sectionText = m ? m[1] : text.slice(400, 1000);
                } else if (sectionKey === 'takeaway') {
                    const m = text.match(/(?:Key Takeaway|मुख्य निष्कर्ष|ముఖ్యమైన ముగింపు|الخلاصة الرئيسية)([\s\S]*?)(?:###|##|$)/i);
                    sectionText = m ? m[1] : text.slice(-400);
                }

                if (!sectionText || sectionText.trim().length < 5) {
                    sectionText = text.slice(0, 600);
                }
                speakTextContent(sectionText);
            };

            // Selection Listener across parent and iframe window
            function handleTextSelection(e) {
                try {
                    const parentDoc = window.parent.document || document;
                    const selection = parentDoc.getSelection();
                    const selectedText = selection ? selection.toString().trim() : "";
                    const pill = document.getElementById('floating-listen-pill');

                    if (selectedText.length >= 3) {
                        currentSelectionText = selectedText;
                        const range = selection.getRangeAt(0);
                        const rect = range.getBoundingClientRect();
                        if (pill) {
                            pill.style.display = 'block';
                            pill.style.top = Math.max(10, rect.top - 45) + 'px';
                            pill.style.left = Math.max(10, rect.left + (rect.width / 2) - 60) + 'px';
                            pill.dataset.selected = selectedText;
                        }
                    } else {
                        currentSelectionText = "";
                        if (pill) pill.style.display = 'none';
                    }
                } catch (err) {}
            }

            window.speakSelectedText = function(e) {
                if (e) e.stopPropagation();
                const pill = document.getElementById('floating-listen-pill');
                const text = pill ? pill.dataset.selected : currentSelectionText;
                if (text) {
                    speakTextContent(text);
                }
                if (pill) pill.style.display = 'none';
            };

            try {
                const parentDoc = window.parent.document || document;
                parentDoc.addEventListener('mouseup', handleTextSelection);
                parentDoc.addEventListener('touchend', handleTextSelection);
                parentDoc.addEventListener('mousedown', function(e) {
                    const pill = document.getElementById('floating-listen-pill');
                    if (pill && e.target !== pill) {
                        pill.style.display = 'none';
                    }
                });
            } catch (e) {}
        })();
    </script>
</div>
"""


def get_voice_controller_html(language_code: str = "en", default_text: str = "") -> str:
    """
    Renders the browser speech synthesis controller and floating text-selection listener.
    Zero server dependency; runs directly in the user's browser using native Web Speech APIs.

    Strictly maps:
      - 'en' -> en-US (English)
      - 'hi' -> hi-IN (Hindi)
      - 'te' -> te-IN (Telugu)
      - 'ar' -> ar-SA (Arabic)
    """
    lang_map = {
        "en": {
            "code": "en-US",
            "name": "English",
            "native_name": "English",
            "prefix": "en",
        },
        "hi": {
            "code": "hi-IN",
            "name": "Hindi",
            "native_name": "हिन्दी",
            "prefix": "hi",
        },
        "te": {
            "code": "te-IN",
            "name": "Telugu",
            "native_name": "తెలుగు",
            "prefix": "te",
        },
        "ar": {
            "code": "ar-SA",
            "name": "Arabic",
            "native_name": "العربية",
            "prefix": "ar",
        },
    }
    lang_config = lang_map.get(language_code, lang_map["en"])
    sanitized_default = json.dumps(default_text)

    html = HTML_TEMPLATE
    html = html.replace("__TARGET_LANG_CODE__", lang_config["code"])
    html = html.replace("__TARGET_LANG_NAME__", lang_config["name"])
    html = html.replace("__TARGET_NATIVE_NAME__", lang_config["native_name"])
    html = html.replace("__TARGET_LANG_PREFIX__", lang_config["prefix"])
    html = html.replace("__DEFAULT_TEXT_JSON__", sanitized_default)

    return html
