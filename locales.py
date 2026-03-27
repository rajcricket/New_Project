# locales.py

# The keys (START_BTN, etc.) must be the same for all languages
TEXTS = {
    "English": {
        "START_BTN": "🚀 Start Matching", "CHANGE_INTERESTS": "🎯 Change Interests", "SETTINGS": "⚙️ Settings", "MY_ID": "🪪 My ID", "HELP": "🆘 Help", "STOP_SEARCH": "❌ Stop Searching",
        "BTN_GAMES": "🎮 Games", "BTN_NEXT": "⏭️ Next", "BTN_STOP": "🛑 Stop", "BTN_STOP_GAME": "🛑 Stop Game", "BTN_STOP_CHAT": "🛑 Stop Chat",
        "SEARCHING_MSG": "📡 **Scanning...**\nLooking for: `{tags}`...", "PARTNER_FOUND": "⚡ **PARTNER FOUND!**\n\n🎭 **Mood:** {mood}\n🔗 **Common:** {common}\n🗣️ **Lang:** {lang}\n\n⚠️ *Say Hi!*",
        "STOPPED_SEARCH": "🛑 **Search Stopped.**", "ALREADY_IN_CHAT": "⛔ **Already in chat!**",
        "DISCONNECTED": "😶‍🌫️ **Partner Disconnected.**", "RATE_STRANGER": "Rate Stranger:", "SKIPPING": "⏭️ **Skipping...**", "RATE_PREV": "Rate previous partner:",
        "WAIT_NOTIFY": "✅ **Paused.** I'll notify you when someone joins.",
        "CMD_IN_CHAT": "⚠️ **You are already chatting!**\n\n💡 Use `/next` to skip, or `/stop` to end.", 
        "CMD_IN_WAIT": "⚠️ **You are in the waiting room!**\n\n💡 Use `/stop` to cancel.",
        "CMD_NOT_IN_CHAT_STOP": "⚠️ You are not in a chat.",
        "CMD_NOT_IN_CHAT_NEXT": "⚠️ You are not in a chat.",
        "GAME_CENTER": "🎮 **Game Center**\nSelect a game to offer your partner:",
        "GAME_STOPPED": "🛑 Game Stopped.", "PARTNER_STOPPED_GAME": "🛑 Your partner stopped the game.",
        "WAIT_60S": "⏳ Please wait {seconds}s before sending another request.",
        "RULE_TOD": "Truth or Dare Rules", "RULE_WYR": "Would You Rather Rules", "RULE_RPS": "Rock Paper Scissors Rules",
        "GAME_ACCEPTED": "✅ Accept", "GAME_REJECTED": "❌ Reject",
        "OFFERED": "🎮 You offered to play **{game}**! Waiting for partner...",
        "GAME_REQ": "🎮 **{game} Request!**\n\n{rules}\n\nDo you accept?",
        "GAME_STARTED": "🎮 **{game} Started!**",
        "PICK_TRUTH": "😈 Truth", "PICK_DARE": "🔥 Dare",
        "YOUR_TURN": "🎲 **Your Turn!** Pick Truth or Dare:",
        "PICK_A": "Pick a {mode}:\n\n",
        "ASK_OWN": "✍️ Ask my own",
        "DECLINED": "❌ Game offer declined.",
        "YOU_PICKED": "✅ You picked **{mode}**! Partner is choosing...",
        "QUESTION": "❓ **Question:**\n{q}\n\nType your answer below!",
        "ASKED": "✅ You asked:\n_{q}_\n\nWaiting for partner to answer...",
        "TYPE_Q_NOW": "✍️ Type your custom question now:",
        "CHOSE": "✅ You chose **{move}**! Waiting for partner...",
        "DRAW_MATCH": "🤝 It's a DRAW!", "WON_MATCH": "🏆 YOU WON!", "LOST_MATCH": "💀 YOU LOST!",
        "RPS_FINAL": "🏁 **FINAL SCORE**\n\nYou: {s1} | Partner: {s2}\n\n{res}",
        "DRAW": "🤝 Draw", "BEAT": "🏆 {m1} beats {m2}!", "LOST": "💀 {m1} loses to {m2}...",
        "RPS_RES": "Round {r}: {res}\nScore: {s1} - {s2}",
        "VOTED": "✅ You voted **{choice}**! Waiting for partner...",
        "MATCH_100": "🔥 **100% Match!** (Streak: {s})", "MATCH_DIFF": "⚡ **Different vibes!** (Streak: 0)",
        "WYR_RESULTS": "📊 **Results:**\n\nYou: **{my_choice}**\nPartner: **{p_choice}**\n\n{match}\n\n👇 **Tell your partner WHY you chose that!**",
        "SKIP_DISC": "⏭️ Skip Discussion", "YOU_SKIPPED": "⏭️ **You skipped.** Waiting for partner...", "PARTNER_SKIPPED": "⏭️ **Partner skipped.**", "NEXT_ROUND": "✨ **Next round...**",
        "EXPLANATION_SENT": "✅ Explanation sent.", "BECAUSE": "🗣️ **Because...**", "ANSWER": "🗣️ **Answer**",
        "RULE_RPS": "• Pick your move.\n• Best out of 3 or 5.\n• Ties repeat the round immediately.", "SHOOT": "✂️ **Shoot!**",
        "SECRET_RX": "🔒 **Secret Message Received!** {cap}\nClick below to open.",
        "SECRET_SENT": "🔒 **Secret Message Sent!**",
        "ANSWER_SENT": "✅ Answer sent.",
        "WYR_Q": "🤔 **Would You Rather...**\n\n🅰️ {q1}\n\n**OR**\n\n🅱️ {q2}",
        
        # --- NEW SPICY MODE KEYS ---
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
