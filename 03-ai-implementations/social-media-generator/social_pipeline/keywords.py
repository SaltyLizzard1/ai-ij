"""Keyword, theme and mood extraction for a text chunk.

* Keywords: a small RAKE-style extractor (no external NLP dependency).
* Themes: lexicon lookup onto the controlled vocabulary in ``models.THEMES``.
* Moods: lexicon lookup onto ``models.MOODS``.

The same THEMES / MOODS lists constrain the vision tagger, so both sides of
the image match speak the same language.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .models import MOODS, THEMES, normalize_term

STOPWORDS = set(
    """
a about above after again against all am an and any are aren't as at be because been
before being below between both but by can can't cannot could couldn't did didn't do does
doesn't doing don't down during each few for from further had hadn't has hasn't have haven't
having he he'd he'll he's her here here's hers herself him himself his how how's i i'd i'll
i'm i've if in into is isn't it it's its itself let's me more most mustn't my myself no nor
not of off on once only or other ought our ours ourselves out over own same shan't she she'd
she'll she's should shouldn't so some such than that that's the their theirs them themselves
then there there's these they they'd they'll they're they've this those through to too under
until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where
where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're
you've your yours yourself yourselves also just like get got one two thing things really
much many even still way ways lot lots make made time day days year years week weeks
""".split()
)

THEME_LEXICON: dict[str, set[str]] = {
    "city_streets": {"city", "street", "downtown", "traffic", "urban", "neighbourhood", "neighborhood", "old town", "walk", "alley", "building", "skyline"},
    "nature_landscape": {"nature", "landscape", "forest", "jungle", "field", "trail", "hike", "hiking", "waterfall", "river", "valley", "green", "tree", "park", "garden", "countryside"},
    "mountains": {"mountain", "hill", "peak", "summit", "doi", "viewpoint", "ridge", "altitude"},
    "beach_water": {"beach", "ocean", "sea", "island", "wave", "sand", "coast", "lake", "swim", "snorkel", "boat", "pool"},
    "food_drink": {"food", "eat", "meal", "restaurant", "coffee", "cafe", "café", "tea", "breakfast", "lunch", "dinner", "noodle", "curry", "street food", "fruit", "cook", "cooking", "kitchen", "drink", "beer", "wine", "smoothie"},
    "cafe_coworking": {"cafe", "café", "cowork", "coworking", "laptop", "wifi", "remote work", "workspace", "desk"},
    "home_daily_life": {"home", "apartment", "flat", "condo", "room", "morning", "evening", "routine", "laundry", "grocery", "tuesday", "ordinary", "daily", "living", "rent", "landlord", "balcony"},
    "transport_road": {"road", "drive", "driving", "motorbike", "motorcycle", "scooter", "car", "bus", "train", "taxi", "grab", "songthaew", "tuk-tuk", "licence", "license", "traffic", "ride", "riding", "airport", "flight", "commute"},
    "people_community": {"friend", "friends", "people", "community", "group", "meet", "meetup", "family", "neighbour", "neighbor", "locals", "expat", "expats", "conversation", "together"},
    "solo_moment": {"alone", "solo", "myself", "by myself", "quiet", "on my own", "independent"},
    "work_laptop": {"work", "business", "client", "clients", "laptop", "project", "build", "building", "tool", "app", "product", "software", "code", "workflow", "email", "meeting"},
    "planning_paperwork": {"plan", "planning", "visa", "passport", "paperwork", "form", "application", "bank", "banking", "account", "insurance", "document", "documents", "appointment", "checklist", "immigration", "embassy", "permit"},
    "markets_shopping": {"market", "shop", "shopping", "mall", "stall", "vendor", "buy", "bought", "bargain", "night market", "supermarket"},
    "temples_culture": {"temple", "wat", "monk", "buddha", "festival", "ceremony", "culture", "cultural", "tradition", "traditional", "lantern", "songkran", "loy krathong", "history", "museum"},
    "animals": {"dog", "cat", "elephant", "bird", "monkey", "animal", "animals", "pet", "puppy", "kitten", "buffalo", "cow"},
    "night_lights": {"night", "evening", "sunset", "dusk", "lights", "neon", "bar", "nightlife", "stars", "dark"},
    "weather_seasons": {"rain", "rainy", "monsoon", "hot", "heat", "humid", "season", "burning season", "smoke", "cool season", "weather", "storm", "sun", "sunny", "cloud", "fog", "mist"},
    "travel_moving": {"travel", "trip", "journey", "move", "moved", "moving", "relocate", "relocation", "arrive", "arrived", "leave", "left", "suitcase", "pack", "packing", "luggage", "abroad", "overseas", "country", "thailand", "chiang mai", "bangkok"},
    "health_wellbeing": {"health", "healthy", "doctor", "hospital", "clinic", "dentist", "massage", "yoga", "gym", "exercise", "sleep", "rest", "walk", "walking", "wellbeing", "well-being", "mental", "therapy", "anxiety", "stress"},
    "celebration": {"celebrate", "celebration", "birthday", "party", "milestone", "anniversary", "finally", "achieved", "success", "cheers", "toast", "win", "won"},
}

MOOD_LEXICON: dict[str, set[str]] = {
    "calm": {"calm", "peace", "peaceful", "quiet", "slow", "slowly", "rest", "breathe", "still", "serene", "relax", "relaxed", "gentle", "settled"},
    "energetic": {"energy", "fast", "action", "hustle", "power", "drive", "momentum", "push", "busy", "rush", "excited", "exciting"},
    "inspiring": {"dream", "inspire", "inspired", "vision", "possible", "believe", "courage", "brave", "hope", "leap", "decide", "decided", "decision", "began", "begin"},
    "adventurous": {"adventure", "explore", "exploring", "discover", "wild", "trip", "road", "ride", "climb", "trail", "new", "first time", "unknown"},
    "reflective": {"think", "thought", "reflect", "lesson", "learned", "learnt", "remember", "realise", "realize", "realised", "realized", "why", "meaning", "looking back", "years", "rebuild", "rebuilding", "doubt", "fear", "afraid"},
    "playful": {"fun", "funny", "laugh", "laughed", "play", "joy", "silly", "smile", "joke", "absurd", "ridiculous", "😂"},
    "professional": {"business", "strategy", "team", "client", "growth", "career", "work", "leadership", "process", "system", "workflow"},
    "cozy": {"home", "warm", "coffee", "tea", "blanket", "evening", "kitchen", "comfortable", "comfort", "cosy", "cozy", "sofa"},
    "melancholic": {"loss", "grief", "sad", "miss", "missed", "alone", "hard", "difficult", "stuck", "failed", "failure", "cried", "lonely"},
    "celebratory": {"win", "celebrate", "celebration", "milestone", "success", "finally", "achieved", "passed", "cheers", "proud"},
}

_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z'-]*")
_PHRASE_BREAK = re.compile(r"[.,;:!?()\[\]{}\"“”‘’…/\n]|\s-\s|—|–")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


def extract_keywords(text: str, heading: str | None = None, *, top_n: int = 10) -> list[str]:
    """RAKE-style keyword phrases (1-3 words), heading terms boosted."""
    phrases: list[list[str]] = []
    for segment in _PHRASE_BREAK.split(text):
        current: list[str] = []
        for tok in _tokens(segment):
            if tok in STOPWORDS or len(tok) < 3:
                if current:
                    phrases.append(current)
                    current = []
                continue
            current.append(tok)
            if len(current) == 3:
                phrases.append(current)
                current = []
        if current:
            phrases.append(current)

    if not phrases:
        return []

    freq: Counter[str] = Counter()
    degree: Counter[str] = Counter()
    for phrase in phrases:
        for w in phrase:
            freq[w] += 1
            degree[w] += len(phrase)
    heading_words = set(_tokens(heading or "")) - STOPWORDS
    word_score = {
        w: (degree[w] / freq[w]) * (2.0 if w in heading_words else 1.0) for w in freq
    }

    phrase_scores: dict[str, float] = defaultdict(float)
    phrase_counts: Counter[str] = Counter()
    for phrase in phrases:
        key = " ".join(phrase)
        phrase_counts[key] += 1
        phrase_scores[key] = sum(word_score[w] for w in phrase)

    ranked = sorted(
        phrase_scores.items(),
        key=lambda kv: (kv[1] * (1 + 0.3 * (phrase_counts[kv[0]] - 1)), phrase_counts[kv[0]]),
        reverse=True,
    )
    out: list[str] = []
    seen: set[str] = set()
    for phrase, _ in ranked:
        norm = normalize_term(phrase)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(phrase)
        if len(out) >= top_n:
            break
    return out


def _lexicon_hits(text: str, lexicon: dict[str, set[str]]) -> dict[str, int]:
    lowered = " " + re.sub(r"\s+", " ", text.lower()) + " "
    tokens = _tokens(text)
    normalized = {normalize_term(t) for t in tokens}
    hits: dict[str, int] = {}
    for label, terms in lexicon.items():
        count = 0
        for term in terms:
            if " " in term or "-" in term or not term.isascii():
                if f" {term} " in lowered or term in lowered:
                    count += 2
            elif normalize_term(term) in normalized:
                count += 1
        if count:
            hits[label] = count
    return hits


def detect_themes(text: str, *, max_themes: int = 4) -> list[str]:
    hits = _lexicon_hits(text, THEME_LEXICON)
    ranked = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
    return [label for label, _ in ranked[:max_themes] if label in THEMES]


def detect_moods(text: str, *, max_moods: int = 3) -> list[str]:
    hits = _lexicon_hits(text, MOOD_LEXICON)
    ranked = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
    return [label for label, _ in ranked[:max_moods] if label in MOODS]


def analyse_chunk_text(text: str, heading: str | None = None, context: str | None = None) -> dict[str, list[str]]:
    """Convenience: keywords + themes + moods in one call.

    ``context`` (the surrounding paragraph of a hook) is used for themes and
    moods only, so a one-line hook still inherits the topic of its paragraph.
    """
    full = f"{heading or ''}\n{text}\n{context or ''}"
    return {
        "keywords": extract_keywords(f"{heading or ''}\n{text}", heading),
        "themes": detect_themes(full),
        "moods": detect_moods(full),
    }
