# locales.py

# The keys (START_BTN, etc.) must be the same for all languages
TEXTS = {
    "English": {
        "START_BTN": "🚀 Start Matching",
        "CHANGE_INTERESTS": "🎯 Change Interests",
        "SETTINGS": "⚙️ Settings",
        "MY_ID": "🪪 My ID",
        "HELP": "🆘 Help",
        "STOP_SEARCH": "❌ Stop Searching",
        "SEARCHING_MSG": "📡 **Scanning...**\nLooking for: `{tags}`..."
    },
    "Indo": {
        "START_BTN": "🚀 Mulai Chat",
        "CHANGE_INTERESTS": "🎯 Ubah Minat",
        "SETTINGS": "⚙️ Pengaturan",
        "MY_ID": "🪪 ID Saya",
        "HELP": "🆘 Bantuan",
        "STOP_SEARCH": "❌ Berhenti Mencari",
        "SEARCHING_MSG": "📡 **Memindai...**\nMencari: `{tags}`..."
    },
    "Hindi": {
        "START_BTN": "🚀 Start Matching", # Keep English or translate to "🚀 जोड़ी बनाएं"
        "CHANGE_INTERESTS": "🎯 रुचियां बदलें",
        "SETTINGS": "⚙️ सेटिंग्स",
        "MY_ID": "🪪 मेरी आईडी",
        "HELP": "🆘 मदद",
        "STOP_SEARCH": "❌ खोज रोकें",
        "SEARCHING_MSG": "📡 **स्कैनिंग...**\nढूँढ रहा है: `{tags}`..."
    }
}

def get_text(lang, key):
    """Safely gets text. Defaults to English if lang/key is missing."""
    user_lang = TEXTS.get(lang, TEXTS["English"])
    return user_lang.get(key, TEXTS["English"][key])