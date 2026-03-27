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
        "SEARCHING_MSG": "📡 **Scanning...**\nLooking for: `{tags}`...",
	"BTN_SPICY_ON": "🌶️ Spicy Mode",
        "BTN_SPICY_OFF": "🧊 Turn off Spicy Mode",
        "SPICY_REQ": "🔥 **Your partner wants to switch Game level to spicy level. Do you want to try?**",
        "SPICY_ACCEPTED": "🔥 Bring it on!",
        "SPICY_REJECTED": "🛑 No",
        "SPICY_DECLINED_MSG": "🧊 Partner declined. Keeping it clean!",
        "SPICY_ACTIVATED_MSG": "🌶️ **Spicy Mode ACTIVATED!** Things are about to get hot...",
        "SPICY_DEACTIVATED_MSG": "💧 **Spicy Mode DEACTIVATED.** Back to normal questions.",
        "SPICY_COOLDOWN": "⏳ Wait {seconds}s before requesting Spicy Mode again.",
        "SPICY_PREFIX": "🔥 **(Spicy)** "
    },
    "Indo": {
        "START_BTN": "🚀 Mulai Chat",
        "CHANGE_INTERESTS": "🎯 Ubah Minat",
        "SETTINGS": "⚙️ Pengaturan",
        "MY_ID": "🪪 ID Saya",
        "HELP": "🆘 Bantuan",
        "STOP_SEARCH": "❌ Berhenti Mencari",
        "SEARCHING_MSG": "📡 **Memindai...**\nMencari: `{tags}`...",
	"BTN_SPICY_ON": "🌶️ Mode Pedas",
        "BTN_SPICY_OFF": "🧊 Matikan Mode Pedas",
        "SPICY_REQ": "🔥 **Pasanganmu ingin mengubah ke Mode Pedas (Spicy). Apakah kamu mau mencoba?**",
        "SPICY_ACCEPTED": "🔥 Ayo mulai!",
        "SPICY_REJECTED": "🛑 Tidak",
        "SPICY_DECLINED_MSG": "🧊 Pasangan menolak. Tetap main aman!",
        "SPICY_ACTIVATED_MSG": "🌶️ **Mode Pedas DIAKTIFKAN!** Suasana akan memanas...",
        "SPICY_DEACTIVATED_MSG": "💧 **Mode Pedas DINONAKTIFKAN.** Kembali ke pertanyaan normal.",
        "SPICY_COOLDOWN": "⏳ Tunggu {seconds}d sebelum meminta Mode Pedas lagi.",
        "SPICY_PREFIX": "🔥 **(Pedas)** "
    },
    "Hindi": {
        "START_BTN": "🚀 Start Matching", # Keep English or translate to "🚀 जोड़ी बनाएं"
        "CHANGE_INTERESTS": "🎯 रुचियां बदलें",
        "SETTINGS": "⚙️ सेटिंग्स",
        "MY_ID": "🪪 मेरी आईडी",
        "HELP": "🆘 मदद",
        "STOP_SEARCH": "❌ खोज रोकें",
        "SEARCHING_MSG": "📡 **स्कैनिंग...**\nढूँढ रहा है: `{tags}`...",
	"BTN_SPICY_ON": "🌶️ स्पाइसी मोड",
        "BTN_SPICY_OFF": "🧊 स्पाइसी मोड बंद करें",
        "SPICY_REQ": "🔥 **आपका पार्टनर गेम को स्पाइसी लेवल पर स्विच करना चाहता है। क्या आप तैयार हैं?**",
        "SPICY_ACCEPTED": "🔥 हाँ, चलो शुरू करें!",
        "SPICY_REJECTED": "🛑 नहीं",
        "SPICY_DECLINED_MSG": "🧊 पार्टनर ने मना कर दिया। हम नॉर्मल गेम ही खेलेंगे!",
        "SPICY_ACTIVATED_MSG": "🌶️ **स्पाइसी मोड चालू!** अब मज़ा आएगा...",
        "SPICY_DEACTIVATED_MSG": "💧 **स्पाइसी मोड बंद।** नॉर्मल सवालों पर वापस।",
        "SPICY_COOLDOWN": "⏳ स्पाइसी मोड दोबारा रिक्वेस्ट करने से पहले {seconds}s रुकें।",
        "SPICY_PREFIX": "🔥 **(स्पाइसी)** "
    }
}

def get_text(lang, key):
    """Safely gets text. Defaults to English if lang/key is missing."""
    user_lang = TEXTS.get(lang, TEXTS["English"])
    return user_lang.get(key, TEXTS["English"][key])
