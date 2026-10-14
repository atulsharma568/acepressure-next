"""Explicit local/cloud speech providers. Cloud credentials never reach clients.

Hinglish support (v1.3.0):
    - SSML `xml:lang` is derived from the selected voice's locale, not hardcoded.
    - Devanagari characters and common romanized-Hindi tokens trigger segment-level
      <lang xml:lang="hi-IN"> wrapping so Hindi words get Hindi phonetics even when
      the chosen voice is English-primary.
    - Azure MultilingualNeural voices (code-switching) are surfaced in the catalog.
"""
import hashlib, io, json, os, re, subprocess, threading, time, urllib.request, wave
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from flask import request, send_file
from .domain import Problem, now
from .speech import render_speech
from .text_filters import looks_like_link
LOCK = threading.Lock()

# ---------- Hinglish detection + transliteration ----------
# Devanagari block: U+0900..U+097F (हिंदी script). If present, text is clearly Hindi.
_DEVANAGARI = re.compile(r'[ऀ-ॿ]')

# Roman Hindi → Devanagari, applied before a voice that can read Hindi (a hi-* locale or a Multilingual Neural voice)
# speaks, so it says "भाई" and not "bai", "क्या" and not "kiya". English-only voices get the text unchanged.
#
# 1.6.2 reads the sentence instead of skipping every word that is also English. Three kinds of word:
#   always    words that are only Hindi in a tipping chat (bhai, kya, gaya): converted wherever they appear.
#   _SHORT    short Hindi words that are also names, abbreviations or other languages (ka, se, lo, hum, tu):
#             converted only inside a Hindi clause.
#   _CONTEXT  Hindi words that are also English words (main, mat, to, do): converted inside a Hindi clause unless
#             the words around them make them English ("the main role", "Jett main", "mera main duelist", "mouse mat").
# A clause is the text between . , ! ? ; : or a danda. It is Hindi when its Hindi words outnumber its English grammar
# words (the, is, my, ...), or equal them and include an always-Hindi word.
HINGLISH_TRANSLITERATION = {
    # People and pronouns
    'bhai': 'भाई', 'bhaai': 'भाई', 'bhaiya': 'भैया', 'bhaiyya': 'भैया', 'bhaiyo': 'भाइयो', 'bhaiyon': 'भाइयों',
    'didi': 'दीदी', 'behen': 'बहन', 'yaar': 'यार', 'yar': 'यार', 'yaaro': 'यारो', 'yaaron': 'यारों',
    'dost': 'दोस्त', 'dosto': 'दोस्तो', 'doston': 'दोस्तों', 'banda': 'बंदा', 'bande': 'बंदे',
    'ladka': 'लड़का', 'ladki': 'लड़की', 'aadmi': 'आदमी',
    'aap': 'आप', 'tum': 'तुम', 'mai': 'मैं', 'apun': 'अपुन', 'tu': 'तू', 'hum': 'हम',
    'mera': 'मेरा', 'meri': 'मेरी', 'tera': 'तेरा', 'teri': 'तेरी', 'tere': 'तेरे',
    'hamara': 'हमारा', 'hamari': 'हमारी', 'tumhara': 'तुम्हारा', 'tumhari': 'तुम्हारी',
    'apna': 'अपना', 'apni': 'अपनी', 'apne': 'अपने',
    'uska': 'उसका', 'uski': 'उसकी', 'uske': 'उसके', 'iska': 'इसका', 'iski': 'इसकी', 'iske': 'इसके',
    'unka': 'उनका', 'unki': 'उनकी', 'unke': 'उनके', 'aapka': 'आपका', 'aapki': 'आपकी', 'aapke': 'आपके',
    'mujhe': 'मुझे', 'tujhe': 'तुझे', 'tumhe': 'तुम्हें', 'tumhein': 'तुम्हें', 'hume': 'हमें', 'humein': 'हमें',
    'mujhko': 'मुझको', 'tumko': 'तुमको', 'aapko': 'आपको', 'sabko': 'सबको', 'usko': 'उसको', 'isko': 'इसको', 'unko': 'उनको',
    'maine': 'मैंने', 'humne': 'हमने', 'tumne': 'तुमने', 'aapne': 'आपने', 'usne': 'उसने', 'unhone': 'उन्होंने',
    'ye': 'ये', 'woh': 'वो', 'wo': 'वो', 'vo': 'वो', 'kis': 'किस', 'kisko': 'किसको', 'kiska': 'किसका', 'kisi': 'किसी',
    # Little words that hold Hinglish together
    'ka': 'का', 'ki': 'की', 'ke': 'के', 'se': 'से', 'ne': 'ने', 'pe': 'पे', 'mein': 'में', 'bhi': 'भी', 'toh': 'तो',
    'tak': 'तक', 'liye': 'लिए', 'saath': 'साथ', 'sath': 'साथ', 'aur': 'और', 'lekin': 'लेकिन', 'magar': 'मगर',
    'kyunki': 'क्योंकि', 'agar': 'अगर', 'bas': 'बस', 'sirf': 'सिर्फ़', 'ji': 'जी', 'haan': 'हाँ',
    'wala': 'वाला', 'wali': 'वाली', 'wale': 'वाले', 'waala': 'वाला', 'waali': 'वाली', 'waale': 'वाले',
    'yahan': 'यहाँ', 'wahan': 'वहाँ', 'idhar': 'इधर', 'udhar': 'उधर', 'kidhar': 'किधर',
    # Question words
    'kya': 'क्या', 'kyun': 'क्यों', 'kyu': 'क्यों', 'kyon': 'क्यों', 'kaise': 'कैसे', 'kaisa': 'कैसा', 'kaisi': 'कैसी',
    'kahan': 'कहाँ', 'kaha': 'कहा', 'kab': 'कब', 'kaun': 'कौन', 'kitna': 'कितना', 'kitni': 'कितनी', 'kitne': 'कितने',
    # Being, having, becoming
    'hai': 'है', 'hain': 'हैं', 'tha': 'था', 'thi': 'थी', 'hoga': 'होगा', 'hogi': 'होगी', 'honge': 'होंगे',
    'hoon': 'हूँ', 'hu': 'हूँ', 'hua': 'हुआ', 'hui': 'हुई', 'hue': 'हुए', 'hota': 'होता', 'hoti': 'होती', 'hote': 'होते',
    'hogaya': 'हो गया', 'hogya': 'हो गया',
    'raha': 'रहा', 'rahi': 'रही', 'rahe': 'रहे', 'rha': 'रहा', 'rhi': 'रही', 'rhe': 'रहे',
    'nahi': 'नहीं', 'nahin': 'नहीं', 'nhi': 'नहीं', 'naa': 'ना',
    # Doing, going, giving
    'kar': 'कर', 'karo': 'करो', 'karna': 'करना', 'karke': 'करके', 'karte': 'करते', 'karta': 'करता', 'karti': 'करती',
    'kari': 'करी', 'kiya': 'किया', 'kiye': 'किए', 'karunga': 'करूँगा', 'karenge': 'करेंगे',
    'gaya': 'गया', 'gayi': 'गई', 'gaye': 'गए', 'aaya': 'आया', 'aayi': 'आई', 'aaye': 'आए', 'aa': 'आ', 'aaja': 'आजा',
    'aao': 'आओ', 'aana': 'आना', 'aunga': 'आऊँगा', 'aaunga': 'आऊँगा',
    'ja': 'जा', 'jaa': 'जा', 'jao': 'जाओ', 'jana': 'जाना', 'jaana': 'जाना', 'jaunga': 'जाऊँगा',
    'de': 'दे', 'dena': 'देना', 'diya': 'दिया', 'di': 'दी', 'dedo': 'दे दो', 'dunga': 'दूँगा',
    'le': 'ले', 'lo': 'लो', 'lena': 'लेना', 'liya': 'लिया', 'lunga': 'लूँगा',
    'dekh': 'देख', 'dekha': 'देखा', 'dekhna': 'देखना', 'dekhte': 'देखते', 'dekho': 'देखो',
    'suna': 'सुना', 'sunna': 'सुनना', 'suno': 'सुनो', 'bol': 'बोल', 'bola': 'बोला', 'bolo': 'बोलो', 'bolna': 'बोलना',
    'bata': 'बता', 'batao': 'बताओ', 'batana': 'बताना', 'samajh': 'समझ', 'samjha': 'समझा', 'samjhe': 'समझे',
    'chal': 'चल', 'chala': 'चला', 'chalo': 'चलो', 'chalega': 'चलेगा', 'ruk': 'रुक', 'ruko': 'रुको',
    'sakta': 'सकता', 'sakti': 'सकती', 'sakte': 'सकते', 'chahiye': 'चाहिए', 'chahta': 'चाहता', 'chahti': 'चाहती',
    'mila': 'मिला', 'mili': 'मिली', 'laga': 'लगा', 'lagi': 'लगी', 'lage': 'लगे', 'lagta': 'लगता', 'lagti': 'लगती',
    'pata': 'पता', 'maar': 'मार', 'maara': 'मारा', 'maro': 'मारो', 'rakh': 'रख', 'rakho': 'रखो', 'bhej': 'भेज',
    'bhejo': 'भेजो', 'soch': 'सोच', 'socha': 'सोचा', 'jaldi': 'जल्दी', 'dheere': 'धीरे',
    # Playing, winning, losing
    'khel': 'खेल', 'khela': 'खेला', 'khelna': 'खेलना', 'khelo': 'खेलो', 'khelte': 'खेलते', 'khelta': 'खेलता',
    'khelti': 'खेलती', 'khelunga': 'खेलूँगा', 'jeet': 'जीत', 'jeeta': 'जीता', 'jeeto': 'जीतो', 'jeetna': 'जीतना',
    'jeetega': 'जीतेगा', 'haar': 'हार', 'haara': 'हारा',
    # How much
    'bahut': 'बहुत', 'bohot': 'बहुत', 'bahot': 'बहुत', 'bohut': 'बहुत', 'bhot': 'बहुत', 'thoda': 'थोड़ा',
    'zyada': 'ज़्यादा', 'kam': 'कम', 'sab': 'सब', 'kuch': 'कुछ', 'koi': 'कोई', 'kaafi': 'काफ़ी', 'kafi': 'काफ़ी',
    'itna': 'इतना', 'itni': 'इतनी', 'itne': 'इतने',
    # Praise and everyday adjectives
    'achha': 'अच्छा', 'accha': 'अच्छा', 'acha': 'अच्छा', 'achhi': 'अच्छी', 'achhe': 'अच्छे', 'acche': 'अच्छे',
    'bura': 'बुरा', 'buri': 'बुरी', 'badiya': 'बढ़िया', 'badhiya': 'बढ़िया', 'jhakaas': 'झकास', 'jhakas': 'झकास',
    'theek': 'ठीक', 'thik': 'ठीक', 'sahi': 'सही', 'galat': 'ग़लत', 'bilkul': 'बिल्कुल', 'ekdum': 'एकदम',
    'bada': 'बड़ा', 'badi': 'बड़ी', 'bade': 'बड़े', 'chota': 'छोटा', 'chhota': 'छोटा', 'choti': 'छोटी',
    'pyara': 'प्यारा', 'pyari': 'प्यारी', 'sundar': 'सुंदर', 'zabardast': 'ज़बरदस्त', 'jabardast': 'ज़बरदस्त',
    'kamaal': 'कमाल', 'shaandaar': 'शानदार', 'shandaar': 'शानदार', 'shandar': 'शानदार', 'gazab': 'ग़ज़ब',
    'ghazab': 'ग़ज़ब', 'khatarnak': 'ख़तरनाक', 'khatarnaak': 'ख़तरनाक', 'kadak': 'कड़क', 'bindaas': 'बिंदास',
    'dhamaal': 'धमाल', 'dhamaka': 'धमाका', 'bawaal': 'बवाल', 'bawal': 'बवाल', 'faadu': 'फाड़ू', 'aag': 'आग',
    'pagal': 'पागल', 'sach': 'सच', 'sachi': 'सच्ची', 'sacchi': 'सच्ची', 'asli': 'असली', 'naya': 'नया', 'nayi': 'नई',
    'purana': 'पुराना',
    # Greetings and exclamations
    'namaste': 'नमस्ते', 'namaskar': 'नमस्कार', 'dhanyavaad': 'धन्यवाद', 'dhanyawad': 'धन्यवाद',
    'shukriya': 'शुक्रिया', 'badhai': 'बधाई', 'mubarak': 'मुबारक', 'janamdin': 'जन्मदिन',
    'arre': 'अरे', 'arrey': 'अरे', 'oye': 'ओए', 'abe': 'अबे', 'abey': 'अबे', 'waah': 'वाह', 'wah': 'वाह',
    'ohho': 'ओहो', 'oho': 'ओहो', 'haye': 'हाय', 'uff': 'उफ़',
    # Time
    'kal': 'कल', 'aaj': 'आज', 'parso': 'परसों', 'abhi': 'अभी', 'kabhi': 'कभी', 'ab': 'अब', 'phir': 'फिर', 'fir': 'फिर',
    'pehle': 'पहले', 'baad': 'बाद', 'hamesha': 'हमेशा', 'subah': 'सुबह', 'shaam': 'शाम', 'raat': 'रात',
    'saal': 'साल', 'baar': 'बार',
    # Things, money, feelings, numbers
    'baat': 'बात', 'kaam': 'काम', 'naam': 'नाम', 'dil': 'दिल', 'jaan': 'जान', 'duniya': 'दुनिया',
    'zindagi': 'ज़िंदगी', 'gaana': 'गाना', 'khushi': 'ख़ुशी', 'khana': 'खाना', 'pani': 'पानी', 'paani': 'पानी',
    'chai': 'चाय', 'ghar': 'घर', 'paisa': 'पैसा', 'paise': 'पैसे', 'rupaye': 'रुपये', 'rupay': 'रुपये',
    'rupaiya': 'रुपया', 'maza': 'मज़ा', 'mazaa': 'मज़ा', 'maja': 'मज़ा', 'majaa': 'मज़ा', 'mazaak': 'मज़ाक़',
    'pyaar': 'प्यार', 'pyar': 'प्यार', 'mohabbat': 'मोहब्बत', 'mehnat': 'मेहनत', 'koshish': 'कोशिश',
    'agla': 'अगला', 'agli': 'अगली', 'agle': 'अगले', 'pakka': 'पक्का', 'zaroor': 'ज़रूर', 'zarur': 'ज़रूर',
    'jarur': 'ज़रूर', 'jaroor': 'ज़रूर', 'sabse': 'सबसे', 'shabaash': 'शाबाश', 'shabash': 'शाबाश',
    'bekaar': 'बेकार', 'bekar': 'बेकार', 'bakwas': 'बकवास', 'acchi': 'अच्छी', 'achchi': 'अच्छी',
    'jeetenge': 'जीतेंगे', 'bolu': 'बोलूँ', 'dekhenge': 'देखेंगे', 'milenge': 'मिलेंगे', 'raho': 'रहो', 'rehna': 'रहना',
    'ek': 'एक', 'paanch': 'पाँच', 'saat': 'सात', 'aath': 'आठ', 'sau': 'सौ', 'hazaar': 'हज़ार', 'hazar': 'हज़ार',
    'lakh': 'लाख',
    # Faith, country
    'bhagwan': 'भगवान', 'ishwar': 'ईश्वर', 'jai': 'जय', 'shri': 'श्री', 'shree': 'श्री', 'mahadev': 'महादेव',
    'radhe': 'राधे', 'bharat': 'भारत', 'hindustan': 'हिन्दुस्तान', 'desi': 'देसी',
}
# Short words that are also names, abbreviations or other languages: Hindi only in a Hindi clause.
_SHORT = {'tu', 'hum', 'ye', 'wo', 'vo', 'kis', 'ka', 'ki', 'ke', 'se', 'ne', 'pe', 'tak', 'bas', 'ji', 'hu',
          'aa', 'ja', 'jaa', 'jana', 'de', 'di', 'dena', 'le', 'lo', 'lena', 'bata', 'kari', 'mila', 'kafi', 'ab',
          'fir', 'abe', 'oho', 'haye', 'uff', 'naa', 'ek', 'sau', 'hue'}
# Hindi words that are also English words.
HINGLISH_CONTEXT = {'main': 'मैं', 'mat': 'मत', 'mere': 'मेरे', 'din': 'दिन', 'mast': 'मस्त', 'na': 'ना', 'ho': 'हो',
                    'to': 'तो', 'do': 'दो', 'ko': 'को', 'ram': 'राम', 'yeh': 'यह', 'sun': 'सुन', 'log': 'लोग',
                    'par': 'पर', 'jab': 'जब'}
_NEEDS_HINDI_NEIGHBOUR = {'to', 'do', 'ko', 'log', 'par', 'jab'}  # "welcome to stream bhai" keeps its "to"
_ENGLISH_GRAMMAR = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'am', 'be', 'been', 'being', 'i', 'you', 'he', 'she', 'it', 'we',
    'they', 'him', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'this', 'that', 'these', 'those',
    'of', 'for', 'with', 'on', 'in', 'at', 'by', 'from', 'and', 'or', 'but', 'not', 'have', 'has', 'had', 'will',
    'would', 'can', 'could', 'should', 'shall', 'may', 'might', 'must', 'does', 'did', 'what', 'who', 'how', 'why',
    'when', 'where', 'which', 'there', 'here', 'if', 'then', 'than', 'so', 'because', 'about', 'into', 'just',
    'very', 'really', 'also', 'too', 'im', 'dont', 'cant', 'wont', 'didnt', 'isnt', 'thats', 'youre', 'ive', 'lets'}
_ENGLISH_BEFORE = {'the', 'a', 'an', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'this', 'that', 'these',
                   'those', 'every', 'each', 'any', 'some', 'no'}
_ENGLISH_AFTER = {'the', 'a', 'an', 'it', 'this', 'that', 'these', 'those', 'my', 'your', 'his', 'her', 'our',
                  'their', 'is', 'are', 'was', 'were', 'of', 'for', 'with', 'you', 'in', 'on', 'out', 'off'}
_POSSESSIVES = {'mera', 'meri', 'mere', 'tera', 'teri', 'tere', 'apna', 'apni', 'apne', 'hamara', 'hamari',
                'tumhara', 'tumhari', 'uska', 'uski', 'uske', 'iska', 'iski', 'iske', 'unka', 'unki', 'unke',
                'aapka', 'aapki', 'aapke', 'kiska'}
# "Jett main", "op main": a main in a game. Valorant agents and guns, roles, games.
_GAME_WORDS = {
    'astra', 'breach', 'brimstone', 'brim', 'chamber', 'clove', 'cypher', 'deadlock', 'fade', 'gekko', 'harbor',
    'iso', 'jett', 'kayo', 'killjoy', 'kj', 'neon', 'omen', 'phoenix', 'raze', 'reyna', 'sage', 'skye', 'sova',
    'tejo', 'viper', 'vyse', 'waylay', 'yoru', 'duelist', 'controller', 'initiator', 'sentinel', 'support', 'tank',
    'healer', 'dps', 'sniper', 'entry', 'igl', 'flex', 'lurker', 'awp', 'awper', 'vandal', 'phantom', 'operator',
    'op', 'sheriff', 'ghost', 'spectre', 'judge', 'odin', 'marshal', 'outlaw', 'bulldog', 'guardian', 'jungle',
    'mid', 'adc', 'valo', 'valorant', 'csgo', 'pubg', 'bgmi', 'apex', 'fortnite', 'minecraft', 'gta'}
_MAIN_ENGLISH_NEXT = {'account', 'acc', 'character', 'char', 'role', 'agent', 'menu', 'channel', 'server', 'event',
                      'stage', 'story', 'quest', 'gate', 'door', 'lobby', 'id', 'screen', 'page', 'hero', 'weapon',
                      'branch', 'road', 'street', 'course', 'reason', 'point', 'source', 'thing', 'part'}
_MAT_ENGLISH_BEFORE = {'mouse', 'yoga', 'door', 'desk', 'gaming', 'table', 'floor', 'bath', 'play', 'welcome',
                       'rubber', 'prayer', 'exercise', 'rgb', 'xl', 'big', 'new', 'nice'}
_RAM_BEFORE, _RAM_AFTER = {'jai', 'jay', 'shri', 'shree', 'sri', 'siya', 'ram', 'hare'}, {'ram', 'ji'}
# Devanagari a viewer typed counts as Hindi, and "मेरा main" is as possessive as "mera main".
_ROMAN_OF = {dev: roman for roman, dev in {**HINGLISH_TRANSLITERATION, **HINGLISH_CONTEXT}.items()}
_TOKEN = re.compile(r'[A-Za-z]+|[ऀ-ॣ०-ॿ]+')
_CLAUSE_BREAK = re.compile(r'[.!?;:,\n।॥]|\s[-–—]\s')
_ATTACHED = set("-'’_/@#")


def _chunk_around(text, start, end):
    """The run of non-space characters that holds text[start:end]."""
    while start and not text[start - 1].isspace():
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    return text[start:end]


def transliterate_hinglish(text):
    """Convert Roman Hindi words to Devanagari, reading each clause (see above). Everything else is left as typed."""
    if not text:
        return text
    toks, clause, last = [], 0, 0
    for m in _TOKEN.finditer(text):
        if toks and _CLAUSE_BREAK.search(text, last, m.start()):
            clause += 1
        word = m.group()
        low = word.lower()
        kind = ('dev' if word[0] >= 'ऀ' else 'short' if low in _SHORT else 'always' if low in HINGLISH_TRANSLITERATION
                else 'context' if low in HINGLISH_CONTEXT else 'english' if low in _ENGLISH_GRAMMAR else 'other')
        before = text[m.start() - 1] if m.start() else ' '
        after = text[m.end()] if m.end() < len(text) else ' '
        # Part of "lo-fi", "bhai's", @name, #tag, 2din or a web address: not a word on its own.
        chunk = _chunk_around(text, m.start(), m.end())
        attached = (before in _ATTACHED or after in _ATTACHED or before.isdigit() or after.isdigit()
                    or ('.' in chunk and looks_like_link(chunk)))
        toks.append(dict(start=m.start(), end=m.end(), word=word, low=_ROMAN_OF.get(word, low), kind=kind,
                         clause=clause, attached=attached, hindi=False))
        last = m.end()
    clauses = {}
    for t in toks:
        c = clauses.setdefault(t['clause'], dict(hindi_words=0, english=0, strong=0, letters=[]))
        c['hindi_words'] += t['kind'] in ('dev', 'always', 'short')
        c['strong'] += t['kind'] in ('dev', 'always')
        c['english'] += t['kind'] == 'english'
        if t['kind'] != 'dev' and len(t['word']) > 1:
            c['letters'].append(t['word'])
    for c in clauses.values():
        c['is_hindi'] = c['hindi_words'] > c['english'] or (c['hindi_words'] == c['english'] and c['strong'] > 0)
        c['shouting'] = bool(c['letters']) and all(w.isupper() for w in c['letters'])  # "BHAI MAIN AA GAYA"
    for t in toks:
        c = clauses[t['clause']]
        if t['attached'] or t['kind'] == 'dev':
            t['hindi'] = t['kind'] == 'dev'
        elif t['kind'] == 'always':
            t['hindi'] = True
        elif t['kind'] == 'short':
            t['hindi'] = c['is_hindi'] and not (len(t['word']) == 2 and t['word'].isupper() and not c['shouting'])

    def neighbour(i, step):
        j = i + step
        return toks[j] if 0 <= j < len(toks) and toks[j]['clause'] == toks[i]['clause'] else None

    def context_is_hindi(i):
        t, c = toks[i], clauses[toks[i]['clause']]
        if t['attached'] or not c['is_hindi'] or (len(t['word']) > 1 and t['word'].isupper() and not c['shouting']):
            return False  # NA, RAM, KO, DO: an acronym inside lower-case text
        p, n = neighbour(i, -1), neighbour(i, 1)
        pl, nl = (p['low'] if p else ''), (n['low'] if n else '')
        if t['low'] == 'ram':
            return pl in _RAM_BEFORE or nl in _RAM_AFTER  # "jai shri ram", never "16gb ram"
        if pl in _ENGLISH_BEFORE or nl in _ENGLISH_AFTER:
            return False
        if t['low'] == 'main' and (pl in _POSSESSIVES or pl in _GAME_WORDS or nl in _MAIN_ENGLISH_NEXT):
            return False
        if t['low'] == 'mat' and pl in _MAT_ENGLISH_BEFORE:
            return False
        if t['low'] in _NEEDS_HINDI_NEIGHBOUR:
            return bool((p and p['hindi']) or (n and n['hindi']))
        return True

    for _ in range(2):  # a second pass lets "main to gaya" convert "main" once "to" has
        for i, t in enumerate(toks):
            if t['kind'] == 'context' and not t['hindi'] and context_is_hindi(i):
                t['hindi'] = True
    out, pos = [], 0
    for t in toks:
        if t['hindi'] and t['kind'] != 'dev':
            out += [text[pos:t['start']], HINGLISH_TRANSLITERATION.get(t['word'].lower()) or HINGLISH_CONTEXT[t['word'].lower()]]
            pos = t['end']
    return ''.join(out) + text[pos:]


def voice_handles_hindi(voice):
    """True if the voice can pronounce Devanagari — Hindi locale or Multilingual Neural.

    Case-insensitive against the voice id: accepts 'hi-IN-...', 'HI-IN-...', mixed
    case Multilingual Neural identifiers, etc.
    """
    if not voice:
        return False
    v = voice.lower()
    # Normalize to standard-cased locale before checking the prefix.
    m = re.match(r'^([a-z]{2,3})[-_]([a-z]{2,3})', v)
    locale = (m.group(1) + '-' + m.group(2)) if m else _voice_locale(voice)
    return locale.lower().startswith('hi-') or 'multilingual' in v


def maybe_transliterate(text, voice):
    """Apply transliteration when it will actually help.

    Transliterate when the text is Hinglish AND the voice can pronounce Devanagari.
    English-only voices stay as-is (Devanagari would make them silent/noisy,
    which is NOT better than mispronunciation).
    """
    if not is_hinglish(text):
        return text
    if not voice_handles_hindi(voice):
        return text
    return transliterate_hinglish(text)


def hindi_speech(text):
    """(what a Hindi-capable voice should read, whether the text is Hinglish). Sent with each alert so the browser
    engine in OBS reads exactly what the server voices read; a 1.6.1 overlay ignores both."""
    hinglish = is_hinglish(text)
    return (transliterate_hinglish(text) if hinglish else text), hinglish


# Words that mark Roman text as Hindi for detection: the always-Hindi words plus a few that are never converted.
_HINDI_ROMAN_WORDS = (set(HINGLISH_TRANSLITERATION) - _SHORT) | {'bina', 'ishq', 'allah', 'krishna', 'videsi'}
_ROMAN_RE = re.compile(r"\b([A-Za-z]{2,20})\b")


def has_devanagari(text):
    return bool(_DEVANAGARI.search(text or ''))


def hinglish_score(text):
    """Return a float 0..1 estimating how 'Hinglish' the text is.

    >= 0.15 is a reasonable threshold for 'contains meaningful Hindi content'. Short words (ka, se, lo) count only
    beside an always-Hindi word or each other, so "lo and behold" stays English.
    """
    if not text:
        return 0.0
    if has_devanagari(text):
        return 1.0
    tokens = _ROMAN_RE.findall(text.lower())
    if not tokens:
        return 0.0
    strong = sum(1 for t in tokens if t in _HINDI_ROMAN_WORDS)
    short = sum(1 for t in tokens if t in _SHORT)
    return (strong + (short if strong or short >= 2 else 0)) / len(tokens)


def is_hinglish(text):
    return hinglish_score(text) >= 0.15


def _voice_locale(voice):
    """Infer the primary locale from a voice id. Returns 'hi-IN' or 'en-IN' etc.

    Handles:
      - Azure / Edge: 'hi-IN-SwaraNeural', 'en-US-AvaMultilingualNeural'
      - Piper: 'hi_IN-pratham-medium', 'en_US-amy-medium' (underscore separator)
      - Windows SAPI: bare 'en-US' / 'hi-IN' culture names
    Defaults to 'en-IN' when nothing matches.
    """
    if not voice:
        return 'en-IN'
    # Accept both 'hi-IN' and 'hi_IN' prefixes (Piper uses underscore).
    m = re.match(r'^([a-z]{2,3})[-_]([A-Z]{2,3})', voice)
    if m:
        return m.group(1) + '-' + m.group(2)
    # If it's already a bare locale string like 'en-IN', pass it through
    if re.fullmatch(r'[a-z]{2,3}-[A-Z]{2,3}', voice):
        return voice
    return 'en-IN'


def _is_multilingual_voice(voice):
    return 'multilingual' in (voice or '').lower()


def build_ssml(text, voice, add_hinglish_wrapper=True):
    """Build Azure-compatible SSML with Hinglish-aware language tagging.

    Strategy:
      - Outer <speak xml:lang=...> uses the voice's own locale.
      - If text is Hinglish and the voice is English-primary (not Multilingual,
        not already hi-IN), wrap the full inner text in <lang xml:lang="hi-IN">
        so Azure engages its Hindi phoneme model for mixed-script tokens.
      - Multilingual Neural voices handle code-switching natively — no <lang> wrap.
      - Pure Hindi voices (hi-IN-*) also need no wrap — the voice's locale drives it.
    """
    locale = _voice_locale(voice)
    inner_text = escape(text)
    if add_hinglish_wrapper and is_hinglish(text) and not _is_multilingual_voice(voice) and not locale.startswith('hi-'):
        inner_text = "<lang xml:lang='hi-IN'>" + inner_text + "</lang>"
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        "xml:lang='" + locale + "'>"
        "<voice name=" + quoteattr(voice) + ">" + inner_text + "</voice>"
        "</speak>"
    ).encode('utf-8')


# ---------- Azure HTTP ----------
def azure_request(path, body=None, timeout=None):
    key = os.getenv('AZURE_SPEECH_KEY', '')
    region = os.getenv('AZURE_SPEECH_REGION', '')
    if not key or not re.fullmatch(r'[a-z0-9]{3,40}', region):
        raise Problem('Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION locally, then restart.', 503)
    req = urllib.request.Request(
        'https://' + region + '.tts.speech.microsoft.com/' + path,
        data=body,
        headers={
            'Ocp-Apim-Subscription-Key': key,
            'Content-Type': 'application/ssml+xml',
            'X-Microsoft-OutputFormat': 'riff-24khz-16bit-mono-pcm',
            'User-Agent': 'AcePressure',
        },
    )
    try:
        # 1.6.4: speaking text waits 12 s at most, inside the OBS page's 20 s with room for the backup voice
        with urllib.request.urlopen(req, timeout=timeout or (12 if body is not None else 25)) as res:
            payload = res.read(8 * 1024 * 1024 + 1)
            if len(payload) > 8 * 1024 * 1024:
                raise ValueError()
            return payload
    except Exception:
        raise Problem('Azure Speech request failed. Check key, region, network and quota; no credentials were logged.', 503)


# ---------- Catalog ----------
# Locales relevant to Indian streamers. Multilingual voices are included via a
# separate name-based filter below.
_ALLOWED_LOCALES = {'en-IN', 'hi-IN', 'en-US', 'en-GB'}


def _mimetype_for(path):
    """Return the audio mimetype for a cached speech file, derived from extension."""
    return 'audio/mpeg' if str(path).lower().endswith('.mp3') else 'audio/wav'


def catalog(engine, directory=None):
    """Dispatch to the right engine. `directory` is required for Piper (where models live)."""
    if engine == 'edge':
        from . import edge_tts_service
        return edge_tts_service.catalog()
    if engine == 'piper':
        from . import piper_tts_service
        if directory is None:
            raise Problem('Piper catalog requires a data directory. Internal routing error.', 500)
        return piper_tts_service.catalog(directory)
    if engine == 'azure':
        items = json.loads(azure_request('cognitiveservices/voices/list'))
        out = []
        for x in items:
            if x.get('Gender') not in ['Male', 'Female']:
                continue
            short = x.get('ShortName', '')
            locale = x.get('Locale', '')
            # Keep: all en-IN / hi-IN voices, plus any MultilingualNeural voice
            # (regardless of base locale — these handle Hinglish best).
            keep = locale in ('en-IN', 'hi-IN') or 'Multilingual' in short
            if not keep:
                continue
            tag = ''
            if 'Multilingual' in short:
                tag = ' · HINGLISH-READY'
            elif locale == 'hi-IN':
                tag = ' · हिंदी'
            label = x['Gender'] + ' · ' + locale + ' · ' + x['DisplayName'] + tag
            out.append({'id': short, 'label': label, 'gender': x['Gender'], 'locale': locale})
        # Put Multilingual voices first (best for Hinglish), then hi-IN, then en-IN
        def sort_key(v):
            if 'Multilingual' in v['id']:
                return (0, v['id'])
            if v['locale'] == 'hi-IN':
                return (1, v['id'])
            return (2, v['id'])
        out.sort(key=sort_key)
        return out
    if engine == 'windows':
        if os.name != 'nt':
            raise Problem('Windows voice detection must run on your Windows PC.', 503)
        script = Path(__file__).resolve().parent.parent / 'scripts' / 'Voice_Catalog.ps1'
        try:
            r = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                capture_output=True, encoding='utf-8-sig', timeout=15, check=True,
            )
            return json.loads(r.stdout)
        except Exception:
            raise Problem('Could not enumerate Windows SAPI voices. Run List_Voices.bat.', 503)
    raise Problem('Choose Windows, Edge, Piper, or Azure for server voice detection.')


# ---------- Synthesize ----------
def synthesize(directory, text, voice, engine):
    if engine == 'edge':
        from . import edge_tts_service
        return edge_tts_service.synthesize(directory, text, voice)
    if engine == 'piper':
        from . import piper_tts_service
        return piper_tts_service.synthesize(directory, text, voice)
    if engine == 'windows':
        return render_speech(directory, text, voice)
    if engine != 'azure':
        raise Problem('Select Windows, Edge, Piper, or Azure for server audio preview.', 400)
    if not re.fullmatch(r'[A-Za-z0-9:-]{3,100}', voice):
        raise Problem('Invalid voice identifier.')
    # Transliterate Roman Hindi tokens → Devanagari for Hindi / Multilingual voices
    # so Azure reads them with correct phonetics (fixes "bhai → bai", "kya → kiya").
    final_text = maybe_transliterate(text, voice)
    # XML encoding + Hinglish-aware language wrapping (see build_ssml).
    body = build_ssml(final_text, voice)
    folder = directory / 'speech'
    folder.mkdir(exist_ok=True)
    # 'v3' bumps the cache key when transliteration behavior changes.
    cache_key = hashlib.sha256((voice + '\0' + final_text + '\0v3').encode()).hexdigest()
    path = folder / ('azure-' + cache_key + '.wav')
    with LOCK:
        for old in folder.glob('azure-*.wav'):
            if old.stat().st_mtime < time.time() - 86400:
                old.unlink(missing_ok=True)
        if path.exists():
            return path
        payload = azure_request('cognitiveservices/v1', body)
        try:
            with wave.open(io.BytesIO(payload)) as w:
                if not 0 < w.getnframes() / w.getframerate() <= 60:
                    raise ValueError()
        except Exception:
            raise Problem('Speech provider returned invalid or overlong audio.', 503)
        path.write_bytes(payload)
        return path


# ---------- Backup voice (1.6.4) ----------
BACKUP_HOLD = 120  # after a failure the backup reads for 2 minutes, then the main voice is tried again
FAILURES = ('voice_missing', 'playback_failed', 'provider_failed', 'unavailable')


def backup_choice(s):
    """(engine, voice) for Admin -> TTS "If the voice service fails", or None to stay silent."""
    value = s.get('tts_backup')
    if not isinstance(value, str) or ':' not in value:
        return None
    engine, voice = value.split(':', 1)
    return (engine, voice) if engine in ('piper', 'windows') and voice else None


def synthesize_alert(app, store, text, voice, s):
    """The voice for one OBS alert; returns (path, used_backup). When the engine fails or takes too long and a backup
    voice is set, the backup (Piper or Windows, both offline) reads the same words and keeps reading for BACKUP_HOLD
    seconds before the engine is tried again. Every failure is saved for the dashboard and Voice Studio."""
    engine, backup, ext = s['tts_engine'], backup_choice(s), app.extensions
    if backup == (engine, voice):
        backup = None  # the same voice: nothing to fall back to
    if backup and ext.get('ace_tts_backup_until', 0) > now():
        try:
            path = synthesize(store.path, text, backup[1], backup[0])
            ext['ace_tts_backup'] = {'at': now(), 'engine': backup[0]}
            return path, True
        except Problem:
            pass  # the backup fails too: try the engine
    try:
        path = synthesize(store.path, text, voice, engine)
        ext.pop('ace_tts_backup_until', None)
        return path, False
    except Problem as e:
        ext['ace_tts_error'] = {'message': str(e.message)[:240], 'engine': engine, 'at': now()}
        if not backup:
            raise
        try:
            path = synthesize(store.path, text, backup[1], backup[0])
        except Problem:
            raise e
        ext['ace_tts_backup_until'] = now() + BACKUP_HOLD
        ext['ace_tts_backup'] = {'at': now(), 'engine': backup[0]}
        return path, True


def voice_report(app, db, since):
    """The last OBS voice report since `since` for the dashboard and the OBS dock, or None: {code, at, error, engine,
    backup}. backup: the backup voice read that alert; error: why the engine failed, when it failed at about that time."""
    try:
        r = db.execute('SELECT code, at FROM tts_health WHERE id=1').fetchone()
    except Exception:
        return None
    if not r or not r['at'] or r['at'] < since:
        return None
    near = lambda x: isinstance(x, dict) and abs(x.get('at', 0) - r['at']) <= 120
    error, backup = app.extensions.get('ace_tts_error'), app.extensions.get('ace_tts_backup')
    used = r['code'] == 'played' and near(backup)
    told = near(error) and (r['code'] == 'provider_failed' or used)
    return {'code': r['code'], 'at': r['at'], 'error': error['message'] if told else None,
            'engine': error.get('engine') if told else None, 'backup': used}


def offline_voices(directory):
    """Voices that can be the backup: Piper (if installed) and Windows SAPI (on Windows), Hindi-capable first."""
    out = []
    for engine, name in (('piper', 'Piper'), ('windows', 'Windows')):
        try:
            for v in catalog(engine, directory):
                locale = str(v.get('locale') or '')
                out.append({'value': engine + ':' + v['id'], 'label': name + ' · ' + str(v.get('label') or v['id']),
                            'hindi': locale.lower().startswith('hi')})
        except Exception:
            continue  # not installed, or not on Windows
    out.sort(key=lambda v: (not v['hindi'], v['label']))
    return out


# ---------- Flask routes ----------
def register_tts(app, store):
    with store.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS tts_health(id INTEGER PRIMARY KEY CHECK(id=1), code TEXT, at INTEGER)')

    def body():
        d = request.get_json(silent=True)
        if not isinstance(d, dict):
            raise Problem('Expected a JSON object.')
        return d

    @app.get('/api/admin/tts/catalog')
    def voices():
        return {'voices': catalog(request.args.get('engine', 'windows'), store.path)}

    @app.post('/api/admin/tts/configure')
    def configure():
        d = body()
        engine = d.get('engine')
        selected = d.get('voices')
        if not isinstance(selected, list) or not 1 <= len(selected) <= 12 or any(not isinstance(x, str) for x in selected):
            raise Problem('Choose 1–12 detected voices.')
        available = {x['id']: x for x in catalog(engine, store.path)}
        if any(x not in available for x in selected):
            raise Problem('A selected voice is no longer available.')
        with store.db(True) as db:
            for key, value in [
                ('tts_engine', engine),
                ('voices', selected),
                ('voice_labels', {x: available[x]['label'] for x in selected}),
                ('voice_locales', {x: available[x].get('locale', '') for x in selected}),
                ('voice_genders', {x: available[x].get('gender', 'Any') for x in selected}),
            ]:
                db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                           (key, json.dumps(value)))
            store.audit(db, 'tts_voices_selected', detail={'engine': engine, 'voices': selected})
        return {'ok': True}

    @app.post('/api/admin/tts/preview')
    def preview():
        store.rate('tts-admin-preview', 12, 60)
        d = body()
        s = store.settings()
        voice = d.get('voice')
        if d.get('backup') is True:  # Admin -> TTS "If the voice service fails" (1.6.4): the saved backup voice
            choice = backup_choice(s)
            if not choice:
                raise Problem('Save a backup voice first.')
            text = store.speech(store.on_stream(d.get('text') or 'GG bhai, kya clutch tha! Bahut badhiya stream, thanks!', s), s)
            if not text:
                raise Problem('Nothing to read aloud: the voice skips emoji and the words you set to be skipped.')
            path = synthesize(store.path, text, choice[1], choice[0])
            return send_file(path, mimetype=_mimetype_for(path))
        if voice not in s['voices']:
            raise Problem('Save this voice before previewing it.')
        # Default preview text is intentionally Hinglish so operators hear whether
        # their chosen voice handles code-switching.
        # The voice reads what OBS would: links hidden, filtered words, pronunciations, no emoji (1.6.2).
        text = store.speech(store.on_stream(d.get('text') or 'GG bhai, kya clutch tha! Bahut badhiya stream, thanks!', s), s)
        if not text:
            raise Problem('Nothing to read aloud: the voice skips emoji and the words you set to be skipped.')
        path = synthesize(store.path, text, voice, s['tts_engine'])
        return send_file(path, mimetype=_mimetype_for(path))

    @app.post('/api/admin/tts/spoken')
    def spoken():
        """What a voice will read for a message, without making audio: shown under the Voice Studio sample."""
        d = body()
        s = store.settings()
        voice, engine = d.get('voice'), s['tts_engine']
        if not isinstance(d.get('text'), str) or voice not in s['voices']:
            raise Problem('Choose a saved voice and type a sample.')
        shown = store.on_stream(d['text'], s)
        text = store.speech(shown, s)
        shortened = text != store.speech(shown, s | {'tts_read_full': True})  # "Read whole messages" is off (1.6.3)
        hindi, hinglish = hindi_speech(text)
        if engine == 'browser':  # OBS picks the browser voice; a Hindi one reads the Devanagari copy
            reads = hindi if voice.lower().startswith('hi') else text
        else:
            reads = maybe_transliterate(text, voice)
        return {'reads': reads, 'hindi': hindi if hinglish and reads != hindi else None, 'shortened': shortened}

    @app.get('/api/public/voice-preview')
    def public_preview():
        store.rate('tts-public-preview', 30, 60)
        s = store.settings()
        voice = request.args.get('voice')
        if not s['tts_enabled'] or s['tts_engine'] not in ['windows', 'azure', 'edge', 'piper'] or voice not in s['voices']:
            raise Problem('Voice preview is not available.', 400)
        # Fixed samples only: no unauthenticated arbitrary cloud synthesis.
        path = synthesize(store.path, store.speech('GG bhai, kya clutch tha! Bahut badhiya stream, thanks!', s), voice, s['tts_engine'])
        return send_file(path, mimetype=_mimetype_for(path))

    @app.post('/api/overlay/tts-status')
    def tts_status():
        code = body().get('code')
        if code not in ['played', 'voice_missing', 'playback_failed', 'provider_failed', 'unavailable']:
            raise Problem('Invalid speech status.')
        with store.db(True) as db:
            db.execute(
                'INSERT INTO tts_health VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET code=excluded.code,at=excluded.at',
                (code, now()),
            )
        return {'ok': True}

    @app.get('/api/admin/tts/health')
    def tts_health():
        with store.db() as db:
            r = db.execute('SELECT code, at FROM tts_health WHERE id=1').fetchone()
        last = dict(r) if r else None
        # The synthesis error saved by /api/overlay/tts explains a provider_failed report made at about the same time.
        error = app.extensions.get('ace_tts_error')
        paired = bool(last and error and last['code'] == 'provider_failed' and abs(last['at'] - error['at']) <= 120)
        backup = app.extensions.get('ace_tts_backup')
        used = bool(last and backup and last['code'] == 'played' and abs(last['at'] - backup['at']) <= 120)
        return {'last': last, 'provider_error': error if paired or used else None, 'backup_used': used}

    @app.get('/api/admin/tts/backup')
    def backup_voices():
        """1.6.4: the offline voices that can read when the voice service fails, and the saved choice."""
        return {'voices': offline_voices(store.path), 'value': store.settings().get('tts_backup') or ''}

    @app.post('/api/admin/tts/backup')
    def backup_save():
        value = body().get('voice')
        if value != '' and (not isinstance(value, str) or value not in {v['value'] for v in offline_voices(store.path)}):
            raise Problem('That voice isn’t available on this PC any more. Detect the voices again.')
        with store.db(True) as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       ('tts_backup', json.dumps(value)))
            store.audit(db, 'tts_backup_voice', detail={'voice': value or 'stay silent'})
        return {'ok': True}
