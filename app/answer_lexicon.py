"""Small deterministic local answer lists for constrained prompts."""

from __future__ import annotations

import re
from functools import lru_cache

_COUNTRIES = tuple("""Afghanistan|Albania|Algeria|Andorra|Angola|Antigua and Barbuda|Argentina|Armenia|Australia|Austria|Azerbaijan|Bahamas|Bahrain|Bangladesh|Barbados|Belarus|Belgium|Belize|Benin|Bhutan|Bolivia|Bosnia and Herzegovina|Botswana|Brazil|Brunei|Bulgaria|Burkina Faso|Burundi|Cabo Verde|Cambodia|Cameroon|Canada|Central African Republic|Chad|Chile|China|Colombia|Comoros|Congo|Costa Rica|Croatia|Cuba|Cyprus|Czechia|Denmark|Djibouti|Dominica|Dominican Republic|Ecuador|Egypt|El Salvador|Equatorial Guinea|Eritrea|Estonia|Eswatini|Ethiopia|Fiji|Finland|France|Gabon|Gambia|Georgia|Germany|Ghana|Greece|Grenada|Guatemala|Guinea|Guyana|Haiti|Honduras|Hungary|Iceland|India|Indonesia|Iran|Iraq|Ireland|Israel|Italy|Jamaica|Japan|Jordan|Kazakhstan|Kenya|Kiribati|Kuwait|Kyrgyzstan|Laos|Latvia|Lebanon|Lesotho|Liberia|Libya|Liechtenstein|Lithuania|Luxembourg|Madagascar|Malawi|Malaysia|Maldives|Mali|Malta|Marshall Islands|Mauritania|Mauritius|Mexico|Micronesia|Moldova|Monaco|Mongolia|Montenegro|Morocco|Mozambique|Myanmar|Namibia|Nauru|Nepal|Netherlands|New Zealand|Nicaragua|Niger|Nigeria|North Korea|North Macedonia|Norway|Oman|Pakistan|Palau|Palestine|Panama|Papua New Guinea|Paraguay|Peru|Philippines|Poland|Portugal|Qatar|Romania|Russia|Rwanda|Saint Kitts and Nevis|Saint Lucia|Samoa|San Marino|Saudi Arabia|Senegal|Serbia|Seychelles|Sierra Leone|Singapore|Slovakia|Slovenia|Solomon Islands|Somalia|South Africa|South Korea|South Sudan|Spain|Sri Lanka|Sudan|Suriname|Sweden|Switzerland|Syria|Taiwan|Tajikistan|Tanzania|Thailand|Timor-Leste|Togo|Tonga|Trinidad and Tobago|Tunisia|Turkey|Turkmenistan|Tuvalu|Uganda|Ukraine|United Arab Emirates|United Kingdom|United States|Uruguay|Uzbekistan|Vanuatu|Vatican City|Venezuela|Vietnam|Yemen|Zambia|Zimbabwe""".split("|"))
_REGIONAL_COUNTRIES = {
    "europe": set("Albania|Andorra|Austria|Belarus|Belgium|Bosnia and Herzegovina|Bulgaria|Croatia|Cyprus|Czechia|Denmark|Estonia|Finland|France|Germany|Greece|Hungary|Iceland|Ireland|Italy|Latvia|Liechtenstein|Lithuania|Luxembourg|Malta|Moldova|Monaco|Montenegro|Netherlands|North Macedonia|Norway|Poland|Portugal|Romania|Russia|San Marino|Serbia|Slovakia|Slovenia|Spain|Sweden|Switzerland|Ukraine|United Kingdom|Vatican City".split("|")),
    "asia": set("Afghanistan|Armenia|Azerbaijan|Bahrain|Bangladesh|Bhutan|Brunei|Cambodia|China|Georgia|India|Indonesia|Iran|Iraq|Israel|Japan|Jordan|Kazakhstan|Kuwait|Kyrgyzstan|Laos|Lebanon|Malaysia|Maldives|Mongolia|Myanmar|Nepal|North Korea|Oman|Pakistan|Palestine|Philippines|Qatar|Saudi Arabia|Singapore|South Korea|Sri Lanka|Syria|Taiwan|Tajikistan|Thailand|Timor-Leste|Turkey|Turkmenistan|United Arab Emirates|Uzbekistan|Vietnam|Yemen".split("|")),
    "africa": set("Algeria|Angola|Benin|Botswana|Burkina Faso|Burundi|Cabo Verde|Cameroon|Central African Republic|Chad|Comoros|Congo|Djibouti|Egypt|Equatorial Guinea|Eritrea|Eswatini|Ethiopia|Gabon|Gambia|Ghana|Guinea|Lesotho|Liberia|Libya|Madagascar|Malawi|Mali|Mauritania|Mauritius|Morocco|Mozambique|Namibia|Niger|Nigeria|Rwanda|Senegal|Seychelles|Sierra Leone|Somalia|South Africa|South Sudan|Sudan|Tanzania|Togo|Tunisia|Uganda|Zambia|Zimbabwe".split("|")),
    "north america": set("Antigua and Barbuda|Bahamas|Barbados|Belize|Canada|Costa Rica|Cuba|Dominica|Dominican Republic|El Salvador|Grenada|Guatemala|Haiti|Honduras|Jamaica|Mexico|Nicaragua|Panama|Saint Kitts and Nevis|Saint Lucia|Trinidad and Tobago|United States".split("|")),
    "south america": set("Argentina|Bolivia|Brazil|Chile|Colombia|Ecuador|Guyana|Paraguay|Peru|Suriname|Uruguay|Venezuela".split("|")),
    "oceania": set("Australia|Fiji|Kiribati|Marshall Islands|Micronesia|Nauru|New Zealand|Palau|Papua New Guinea|Samoa|Solomon Islands|Tonga|Tuvalu|Vanuatu".split("|")),
}

_ENDING = re.compile(r"\b(?:what|which|word|words|name|give me|think of|something)\b.*?\b(?:ends?\s+(?:in|with)|ending\s+(?:in|with))\s+(?:(?:the\s+)?(?:letter\s+)?) [-\"'“”]?([a-z]{1,20})\b", re.I | re.X)
_STARTING = re.compile(r"\b(?:what|which|word|words|name|give me|think of|something)\b.*?\b(?:start(?:s|ing)?\s+(?:with|in)|beginning\s+with)\s+(?:(?:the\s+)?(?:letter\s+)?) [-\"'“”]?([a-z]{1,20})\b", re.I | re.X)
_COMPOUND = re.compile(r"\bcompound(?:\s+words?)?\b.*?\b(?:with|containing|including|contains?|has)\s+[\"'“”]?([a-z]{2,20})\b", re.I)
_CONTAINS = re.compile(r"\b(?:what|which|word|words|name|give me|think of|something)\b.*?\b(?:contains?|containing|includes?|including|with|has)\s+(?:(?:the\s+)?(?:letter\s+)?) [-\"'“”]?([a-z]{1,20})\b", re.I | re.X)
_ENGLISH_WORD = re.compile(r"\benglish\s+words?\b", re.I)
_COMMON_ENGLISH_WORDS = "apple|bridge|candle|dragon|ember|forest|garden|harbor|island|jacket|kingdom|lantern|meadow|needle|orange|pocket|quartz|river|silver|thunder|umbrella|village|window|yellow|zephyr".split("|")
_COUNTRY = re.compile(
    r"\b(?:name|give me|list|think of|which|what|any|one)\b.*?\bcountr(?:y|ies)\b"
    r"|\bcountr(?:y|ies)\b.{0,100}\b(?:with|whose|that|in|on|above|over|under|near)\b",
    re.I,
)
_REGION = re.compile(r"\b(?:european|asian|african|north american|south american|oceanian|in europe|in asia|in africa|in north america|in south america|in oceania)\b", re.I)
_FLAG_COLORS = {
    "red": "Canada|China|France|Germany|India|Indonesia|Italy|Japan|Mexico|Netherlands|Norway|Poland|Portugal|Russia|Spain|Sweden|Switzerland|Turkey|United Kingdom|United States|Vietnam",
    "blue": "Argentina|Australia|Brazil|France|Greece|India|Israel|Japan|Netherlands|New Zealand|Russia|Sweden|United Kingdom|United States",
    "white": "Canada|Finland|France|Greece|India|Indonesia|Israel|Italy|Japan|Mexico|Netherlands|Poland|Russia|Sweden|Switzerland|United Kingdom|United States",
    "green": "Brazil|India|Ireland|Italy|Mexico|Nigeria|Pakistan|Saudi Arabia|South Africa|Portugal",
    "yellow": "Brazil|China|Germany|India|Spain|Sweden|Ukraine|Vietnam",
    "black": "Belgium|Germany|Jamaica|South Africa",
}
_LANDLOCKED = set("Afghanistan|Armenia|Austria|Azerbaijan|Belarus|Bhutan|Bolivia|Botswana|Burkina Faso|Burundi|Central African Republic|Chad|Czechia|Eswatini|Ethiopia|Hungary|Kazakhstan|Kyrgyzstan|Laos|Lesotho|Liechtenstein|Luxembourg|Malawi|Mali|Moldova|Mongolia|Nepal|Niger|North Macedonia|Paraguay|Rwanda|San Marino|Serbia|Slovakia|South Sudan|Switzerland|Tajikistan|Turkmenistan|Uganda|Uzbekistan|Vatican City|Zambia|Zimbabwe".split("|"))
_SMALL_POPULATION = set("Andorra|Antigua and Barbuda|Dominica|Kiribati|Liechtenstein|Marshall Islands|Monaco|Nauru|Palau|Saint Kitts and Nevis|San Marino|Seychelles|Tuvalu|Vatican City".split("|"))
_COMMON_COUNTRIES = "United States|Canada|China|India|Brazil|Australia|Japan|Germany|France|Italy|Mexico|United Kingdom|Spain|South Korea|South Africa|Argentina|New Zealand|Sweden|Norway|Switzerland".split("|")
_FALLBACK_WORDS = set("""prototype stereotype archetype genotype phenotype subtype bloodtype prototype textile stereotype sea food seafood dogfood catfood fastfood junkfood soulfood brainfood foodtruck
stop watch stopwatch stoplight stopgap stopover stopcock stopword non nonstop bus busstop laptop laptopcase flower sunflower football snowball airport airplane raincoat overcoat breakfast bookshelfs bookshelf toothbrush toothpaste firehouse lighthouse lighthouse keeper
""".split()) | set(_COMMON_ENGLISH_WORDS)
_DISPLAY_FORMS = {"foodtruck": "food truck", "busstop": "bus stop"}


@lru_cache(maxsize=1)
def _words() -> set[str]:
    try:
        import cmudict
        return {word.casefold() for word in cmudict.words() if word.isalpha() and 2 <= len(word) <= 24} | _FALLBACK_WORDS
    except (ImportError, OSError):
        return set(_FALLBACK_WORDS)


def _country_name(value: str) -> bool:
    return value.casefold() in {country.casefold() for country in _COUNTRIES}


def _dictionary_form(value: str) -> str:
    """Normalize a displayed answer to the form stored in the word lexicon."""
    return re.sub(r"[^a-z]", "", value.casefold())


def prompt_kind(prompt: str) -> tuple[str, str] | None:
    match = _ENDING.search(prompt)
    if match:
        return "ending", match.group(1).casefold()
    match = _STARTING.search(prompt)
    if match:
        return "starting", match.group(1).casefold()
    match = _COMPOUND.search(prompt)
    if match:
        return "compound", next(value for value in match.groups() if value).casefold()
    if _COUNTRY.search(prompt):
        region = _REGION.search(prompt)
        if region:
            region_name = region.group(0).casefold().replace("in ", "").replace("north american", "north america").replace("south american", "south america").replace("oceanian", "oceania").replace("european", "europe").replace("asian", "asia").replace("african", "africa")
            return "country_region", region_name
        return "country", ""
    match = _CONTAINS.search(prompt)
    if match:
        return "contains", match.group(1).casefold()
    if _ENGLISH_WORD.search(prompt):
        return "english_word", ""
    return None


def _qualified_countries(prompt: str, category: str, region: str) -> list[str]:
    eligible = list(_COUNTRIES)
    lowered = prompt.casefold()
    if "coast" in lowered or "coastal" in lowered or "shoreline" in lowered or "landlocked" in lowered:
        if "landlocked" in lowered or re.search(r"\b(?:no|without|lack(?:s|ing)?)\b.{0,30}\b(?:coast|coastal|shoreline)", lowered):
            eligible = [name for name in eligible if name in _LANDLOCKED]
        else:
            eligible = [name for name in eligible if name not in _LANDLOCKED]
    colors = [name for name in _FLAG_COLORS if re.search(rf"\b{name}\b", lowered)]
    if colors and re.search(r"\bflag|banner\b", lowered):
        eligible = [name for name in eligible if all(name in _FLAG_COLORS[color].split("|") for color in colors)]
    if re.search(r"\b(?:over|more than|greater than|above|at least)\s+100[,.]?000\b|\bpopulation.{0,30}100[,.]?000\b", lowered):
        eligible = [name for name in eligible if name not in _SMALL_POPULATION]
    region_name = region
    if category != "country_region":
        region_match = _REGION.search(prompt)
        region_name = region_match.group(0).casefold().replace("in ", "").replace("north american", "north america").replace("south american", "south america").replace("oceanian", "oceania").replace("european", "europe").replace("asian", "asia").replace("african", "africa") if region_match else ""
    if region_name:
        region_names = _REGIONAL_COUNTRIES.get(region_name, set())
        eligible = [name for name in eligible if name in region_names]
    return eligible


def candidate_check(answer: str, prompt: str) -> str:
    """Return ``match``, ``uncertain``, or ``reject`` for a local prompt check.

    A missing dictionary or country entry is uncertain rather than invalid. This
    prevents the deliberately small local data from hiding plausible model
    answers while still removing candidates that plainly break a text rule.
    """
    kind = prompt_kind(prompt)
    if not kind:
        return "uncertain"
    category, value = kind
    if category == "ending":
        word = _dictionary_form(answer)
        if not word.endswith(value) or len(word) <= len(value):
            return "reject"
        return "match" if word in _words() else "uncertain"
    if category == "starting":
        word = _dictionary_form(answer)
        if not word.startswith(value) or len(word) <= len(value):
            return "reject"
        return "match" if word in _words() else "uncertain"
    if category == "contains":
        word = _dictionary_form(answer)
        if value not in word or word == value:
            return "reject"
        return "match" if word in _words() else "uncertain"
    if category.startswith("country"):
        qualified = {name.casefold() for name in _qualified_countries(prompt, category, value)}
        return "match" if answer.casefold() in qualified else "uncertain"
    if category == "compound":
        word = _dictionary_form(answer)
        lexicon = _words()
        if not word or value not in word or word == value:
            return "reject"
        for start in (match.start() for match in re.finditer(re.escape(value), word)):
            end = start + len(value)
            left, right = word[:start], word[end:]
            if (not left and right in lexicon) or (not right and left in lexicon) or (left in lexicon and right in lexicon):
                return "match"
        return "uncertain"
    if category == "english_word":
        return "match" if _dictionary_form(answer) in _words() else "uncertain"
    return "uncertain"


def satisfies_constraint(answer: str, prompt: str) -> bool:
    """Return whether the local data positively confirms a candidate."""
    return candidate_check(answer, prompt) == "match"


def local_candidates(prompt: str, excluded: list[str] | None = None, limit: int = 8) -> list[dict[str, object]]:
    kind = prompt_kind(prompt)
    if not kind:
        return []
    category, value = kind
    if category == "ending":
        candidates = [word for word in _words() if word.endswith(value) and len(word) > len(value)]
        # Prefer compact familiar-looking entries; this is a display ordering, not a frequency claim.
        answers = sorted(candidates, key=lambda word: (len(word), word))[:limit]
        source = "CMU pronunciation dictionary"
    elif category == "starting":
        candidates = [word for word in _words() if word.startswith(value) and len(word) > len(value)]
        answers = sorted(candidates, key=lambda word: (len(word), word))[:limit]
        source = "CMU pronunciation dictionary"
    elif category == "contains":
        candidates = [word for word in _words() if value in word and word != value]
        answers = sorted(candidates, key=lambda word: (len(word), word))[:limit]
        source = "CMU pronunciation dictionary"
    elif category == "compound":
        words = _words()
        candidates = [word for word in words if value in word and len(word) > len(value) and satisfies_constraint(word, prompt)]
        answers = sorted(candidates, key=lambda word: (len(word), word))[:limit]
        source = "Dictionary word and component match"
    elif category in {"country", "country_region"}:
        country_source = _qualified_countries(prompt, category, value)
        priority = {name: index for index, name in enumerate(_COMMON_COUNTRIES)}
        answers = sorted(country_source, key=lambda name: (priority.get(name, len(priority)), name))[:limit]
        source = "Local country list"
    elif category == "english_word":
        words = _words()
        answers = [word for word in _COMMON_ENGLISH_WORDS if word in words][:limit]
        if len(answers) < limit:
            answers.extend(word for word in sorted(words) if word not in answers and len(word) >= 4 and len(answers) < limit)
        source = "English pronunciation dictionary"
    else:
        return []
    excluded_keys = {item.casefold().strip() for item in (excluded or [])}
    return [
        {"answer": _DISPLAY_FORMS.get(answer, answer)}
        for answer in answers if answer.casefold() not in excluded_keys
    ]
