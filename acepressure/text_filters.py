"""Viewer text on stream and in the voice (1.6.2): hidden links, the spoken copy and the streamer's pronunciations.

Stored tips keep what the viewer typed. Links are hidden at the moment a message reaches the stream; emoji and long
repeats are dropped only from the copy the voice reads, so the alert card still shows them.
"""
import functools
import re

_LABEL = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
# Endings that are almost never typed as words, so "name.ending" alone is a link.
_LINK_ENDINGS = ('com|net|org|io|xyz|ly|tv|info|biz|cc|ru|cn|tk|ml|ga|cf|gq|ws|su|pw|icu|cyou|buzz|sbs|cfd|bond|shop|store|'
                 'site|online|app|dev|link|vip|uk|click|casino|website|blog|tech')
# Endings that are also words ("stream.in the end", "nice.top"): a link only with a path, like t.me/x or discord.gg/x.
_WORD_ENDINGS = ('in|me|to|gg|co|us|be|it|is|am|my|id|ai|at|so|no|do|go|la|sh|gl|fm|im|top|live|fun|win|bet|lol|club|pro|'
                 'one|world|today|news|chat|game|games|page|bio|art|space|zone|gold')
_LINK = re.compile(
    r'(?:\b(?:https?|ftp)://|\bwww\d{0,3}\.)[^\s<>"]+'
    r'|(?<![\w@.-])(?:[\w.+-]+@)?(?:' + _LABEL + r'\.)+(?:' + _LINK_ENDINGS +
    r'|(?:co|org|net|gov|ac|edu|nic|firm|gen|ind)\.in|(?:co|org|ac|gov)\.uk)\b(?:[/?#][^\s<>"]*)?'
    r'|(?<![\w@.-])(?:' + _LABEL + r'\.)+(?:' + _WORD_ENDINGS + r')/[^\s<>"]*',
    re.I)


def looks_like_link(text):
    return bool(text and _LINK.search(text))


def hide_links(text):
    """Replace web addresses and emails with [link], so a tip can't put a scam link on stream or in the voice."""
    return _LINK.sub('[link]', text) if text else text


# Emoji and pictographs (with their joiners, skin tones and variation selectors), arrows and shapes.
_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿⌀-⏿⬀-⯿←-⇿■-◿'
                    '︀-️‍⃣〰〽㊗㊙©®™\U000E0020-\U000E007F]+')
_REPEAT = re.compile(r'(.{1,6}?)\1{3,}', re.S)
_WORD_CHAR = r'\wऀ-ॿ'  # Devanagari vowel signs are not \w, so whole-word checks name the block


def _shorten(m):
    unit = m.group(1)
    return m.group(0) if unit.isdigit() else unit * 3  # "hahahahaha" -> "hahaha"; never touch numbers


def _clean(value, limit):
    return re.sub(r'[\x00-\x1f\x7f<>]', '', str(value or '')).strip()[:limit]


def normalize_pronunciations(value):
    """Check the Admin -> TTS list: at most 100 {word, say} pairs. A word is 1-40 characters and appears once; `say` is
    up to 80 characters and may be empty (the voice then skips the word). Blank rows are dropped. Raises ValueError."""
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('Keep at most 100 pronunciations.')
    out, seen = [], set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get('word', ''), str) or not isinstance(item.get('say', ''), str):
            raise ValueError('Each pronunciation needs a word and how to say it.')
        word, say = _clean(item.get('word'), 40), _clean(item.get('say'), 80)
        if not word:
            continue
        if word.lower() in seen:
            raise ValueError(f'“{word}” is in the pronunciation list twice.')
        seen.add(word.lower())
        out.append({'word': word, 'say': say})
    return out


def apply_pronunciations(text, entries):
    """Whole-word, case-insensitive; the longest entry wins. An entry with no letters (an emoji) matches anywhere."""
    if not text or not isinstance(entries, list):
        return text
    table = {e['word'].lower(): e.get('say') or '' for e in entries
             if isinstance(e, dict) and isinstance(e.get('word'), str) and e['word'].strip()}
    if not table:
        return text
    parts = []
    for word in sorted(table, key=len, reverse=True):
        esc = re.escape(word)
        parts.append(f'(?<![{_WORD_CHAR}]){esc}(?![{_WORD_CHAR}])' if re.search(f'[{_WORD_CHAR}]', word) else esc)

    def say(m):
        word = m.group(0).lower()
        out = table.get(word, m.group(0))
        return out if re.search(f'[{_WORD_CHAR}]', word) else f' {out} '  # "lol😂😂" -> "lol haha haha"
    return re.sub('|'.join(parts), say, text, flags=re.I)


def speech_text(text, pronunciations=None, cleanup=True, limit=600):
    """The copy of an on-stream message that the voice reads: pronunciations first (so an emoji can be given words),
    then, unless switched off, no emoji and no long repeats."""
    out = apply_pronunciations(text or '', pronunciations)
    if cleanup:
        out = _REPEAT.sub(_shorten, _EMOJI.sub(' ', out))
    out = re.sub(r'\s+', ' ', out).strip()
    return first_part(re.sub(r' (?=[,.!?;:।])', '', out), limit)  # "nice 🔥, bro" -> "nice, bro"


# 1.6.4: a cut never ends on a word that leads into the part left out ("...pehla tip of Rs").
_DANGLING = {'a', 'an', 'the', 'of', 'to', 'for', 'and', 'or', 'but', 'with', 'my', 'in', 'on', 'at', 'is', 'rs', 'rs.', 'inr', '₹',
             'aur', 'ki', 'ka', 'ke', 'ko', 'se', 'ne', 'mein', 'par', 'ya', 'और', 'की', 'का', 'के', 'को', 'से', 'ने', 'में', 'पर', 'या'}
_STOPS = '.,!?;:।॥…'


def first_part(text, limit):
    """At most `limit` characters of a spoken copy, ending after a whole word: ("gg bhai kya clutch tha", 12) -> "gg bhai kya".
    A word that ends right at the limit is kept, even when a full stop or comma follows it (1.6.4), a number is never
    split ("₹1,000"), and up to three words that lead into the part left out ("of", "Rs", "ka") are dropped."""
    if len(text) <= limit:
        return text
    nxt, prev = text[limit], text[limit - 1] if limit else ''
    in_number = nxt in ',.' and prev.isdigit() and text[limit + 1:limit + 2].isdigit()  # "1,000" or "5.30"
    if limit and (nxt.isspace() or (nxt in _STOPS and not in_number)):
        out = text[:limit]
    else:
        cut = text[:limit + 1].rfind(' ')
        if cut <= 0:
            return text[:limit].rstrip(' ,;:-–—')  # one long word is cut where the limit falls
        out = text[:cut]
    out = out.rstrip(' ,;:-–—')
    for _ in range(3):
        words = out.split(' ')
        if len(words) < 2 or words[-1].lower() not in _DANGLING:
            break
        out = ' '.join(words[:-1]).rstrip(' ,;:-–—')
    return out


def tidy_message(text):
    """What a viewer typed, ready to be stored and shown (1.6.4): a line break or tab between words becomes a space (it
    used to glue "bhai" and "kya" into "bhaikya"), and the text heart "<3" becomes ❤️ ("</3" 💔) instead of a bare "3"
    once < and > are removed."""
    if not isinstance(text, str):
        return text
    return re.sub(r'[\r\n\t\v\f]+', ' ', text.replace('</3', '💔').replace('<3', '❤️'))


_FILTER_CACHE = {}


def word_filter(text, words, whole_words=False):
    """Replace each filtered word or phrase with [filtered], ignoring case. With whole_words (1.6.4) a word matches only
    on its own ("shit" leaves "Kshitij" alone) and a trailing * matches any ending ("chut*" also catches "chutiya");
    without it every match counts, inside other words too, as before."""
    if not text or not isinstance(words, list):
        return text
    key = (tuple(w for w in words if isinstance(w, str)), bool(whole_words))
    pattern = _FILTER_CACHE.get(key)
    if pattern is None:
        parts = []
        for word in sorted({w.strip().lower() for w in key[0] if w.strip().rstrip('*').strip()}, key=len, reverse=True):
            stem = word.endswith('*')
            esc = re.escape(word.rstrip('*').strip())
            if whole_words:
                parts.append(f'(?<![{_WORD_CHAR}]){esc}' + (f'[{_WORD_CHAR}]*' if stem else f'(?![{_WORD_CHAR}])'))
            else:
                parts.append(esc)
        pattern = re.compile('|'.join(parts), re.I) if parts else False
        if len(_FILTER_CACHE) > 64:
            _FILTER_CACHE.clear()
        _FILTER_CACHE[key] = pattern
    return pattern.sub('[filtered]', text) if pattern else text


def _letter(ch):
    return ch.isalpha() or 'ऀ' <= ch <= 'ॿ'


def _word(ch):
    return ch.isalnum() or ch == '_' or 'ऀ' <= ch <= 'ॿ'


def _camel(a, b):
    return a.islower() and b.isupper()


def _part(name, i):
    """Does a new part of a gamer name start at name[i]? Where a small letter meets a capital (Noob|Master), and at the
    last capital of a run of capitals that small letters follow (BIG|Noob, SHIT|Lord: 1.6.6). "BIGSHIT" stays one word."""
    return 0 < i < len(name) and (_camel(name[i - 1], name[i]) or (
        i + 1 < len(name) and name[i - 1].isupper() and name[i].isupper() and name[i + 1].islower()))


def _name_edge(name, i, edge_char):
    """Can a filtered word start or end between name[i-1] and name[i]? A word in a name ends at anything that isn't a
    letter (a space, _, a digit, a dot) and where a new part starts (_part). A filtered word that starts or ends with
    a digit or _ ("69") needs no letter, digit or _ next to it, so "1969" keeps its 69."""
    if i <= 0 or i >= len(name):
        return True
    a, b = name[i - 1], name[i]
    return (not _letter(a) or not _letter(b) or _part(name, i)) if _letter(edge_char) else not (_word(a) and _word(b))


@functools.lru_cache(maxsize=1024)
def _filter_name(name, entries):
    out, i, n = [], 0, len(name)
    while i < n:
        end = None
        for core, stem in entries:  # longest first
            j = i + len(core)
            if j > n or name[i:j].lower() != core or not _name_edge(name, i, core[0]):
                continue
            if stem:  # noob* also takes the letters after it, up to the end of that word
                while j < n and _letter(name[j]) and not _part(name, j):
                    j += 1
            elif not _name_edge(name, j, core[-1]):
                continue
            end = j
            break
        if end is None:
            out.append(name[i]); i += 1
        else:
            out.append('[filtered]'); i = end
    return ''.join(out)


def name_filter(name, words):
    """Filtered words in a supporter's name on stream (1.6.5): always whole words, ignoring case, where _, a digit and a
    capital that starts a new part (NoobMaster, and BIGNoob since 1.6.6) also start a new word, as in gamer names. So with
    "shit" in the list, "Kshitij" and "BIGSHIT" stay whole while "Shit_Lord", "Shit69", "BigShit" and "SHITLord" are
    filtered; a trailing * matches any ending ("noob*": "NoobsRule" becomes "[filtered]Rule"). A word inside a longer one
    ("BULLSHIT") needs its own entry. Messages use word_filter and the Filter whole words only switch instead."""
    if not name or not isinstance(name, str) or not isinstance(words, list):
        return name
    entries = {(w.strip().rstrip('*').strip().lower(), w.strip().endswith('*')) for w in words if isinstance(w, str) and w.strip().rstrip('*').strip()}
    return _filter_name(name, tuple(sorted(entries, key=lambda e: (-len(e[0]), not e[1], e[0])))) if entries else name
