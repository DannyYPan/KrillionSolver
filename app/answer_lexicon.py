"""Small deterministic local answer lists for constrained prompts."""

from __future__ import annotations

import re
from functools import lru_cache

_COUNTRIES = tuple("""Afghanistan|Albania|Algeria|Andorra|Angola|Antigua and Barbuda|Argentina|Armenia|Australia|Austria|Azerbaijan|Bahamas|Bahrain|Bangladesh|Barbados|Belarus|Belgium|Belize|Benin|Bhutan|Bolivia|Bosnia and Herzegovina|Botswana|Brazil|Brunei|Bulgaria|Burkina Faso|Burundi|Cabo Verde|Cambodia|Cameroon|Canada|Central African Republic|Chad|Chile|China|Colombia|Comoros|Congo|Costa Rica|Croatia|Cuba|Cyprus|Czechia|Denmark|Djibouti|Dominica|Dominican Republic|Ecuador|Egypt|El Salvador|Equatorial Guinea|Eritrea|Estonia|Eswatini|Ethiopia|Fiji|Finland|France|Gabon|Gambia|Georgia|Germany|Ghana|Greece|Grenada|Guatemala|Guinea|Guyana|Haiti|Honduras|Hungary|Iceland|India|Indonesia|Iran|Iraq|Ireland|Israel|Italy|Jamaica|Japan|Jordan|Kazakhstan|Kenya|Kiribati|Kuwait|Kyrgyzstan|Laos|Latvia|Lebanon|Lesotho|Liberia|Libya|Liechtenstein|Lithuania|Luxembourg|Madagascar|Malawi|Malaysia|Maldives|Mali|Malta|Marshall Islands|Mauritania|Mauritius|Mexico|Micronesia|Moldova|Monaco|Mongolia|Montenegro|Morocco|Mozambique|Myanmar|Namibia|Nauru|Nepal|Netherlands|New Zealand|Nicaragua|Niger|Nigeria|North Korea|North Macedonia|Norway|Oman|Pakistan|Palau|Palestine|Panama|Papua New Guinea|Paraguay|Peru|Philippines|Poland|Portugal|Qatar|Romania|Russia|Rwanda|Saint Kitts and Nevis|Saint Lucia|Samoa|San Marino|Saudi Arabia|Senegal|Serbia|Seychelles|Sierra Leone|Singapore|Slovakia|Slovenia|Solomon Islands|Somalia|South Africa|South Korea|South Sudan|Spain|Sri Lanka|Sudan|Suriname|Sweden|Switzerland|Syria|Taiwan|Tajikistan|Tanzania|Thailand|Timor-Leste|Togo|Tonga|Trinidad and Tobago|Tunisia|Turkey|Turkmenistan|Tuvalu|Uganda|Ukraine|United Arab Emirates|United Kingdom|United States|Uruguay|Uzbekistan|Vanuatu|Vatican City|Venezuela|Vietnam|Yemen|Zambia|Zimbabwe""".split("|"))
_REGIONAL_COUNTRIES = {
    "europe": set("Albania|Andorra|Austria|Belarus|Belgium|Bosnia and Herzegovina|Bulgaria|Croatia|Cyprus|Czechia|Denmark|Estonia|Finland|France|Germany|Greece|Hungary|Iceland|Ireland|Italy|Latvia|Liechtenstein|Lithuania|Luxembourg|Malta|Moldova|Monaco|Montenegro|Netherlands|North Macedonia|Norway|Poland|Portugal|Romania|Russia|San Marino|Serbia|Slovakia|Slovenia|Spain|Sweden|Switzerland|Ukraine|United Kingdom|Vatican City".split("|")),
    "asia": set("Afghanistan|Armenia|Azerbaijan|Bahrain|Bangladesh|Bhutan|Brunei|Cambodia|China|Georgia|India|Indonesia|Iran|Iraq|Israel|Japan|Jordan|Kazakhstan|Kuwait|Kyrgyzstan|Laos|Lebanon|Malaysia|Maldives|Mongolia|Myanmar|Nepal|North Korea|Oman|Pakistan|Palestine|Philippines|Qatar|Saudi Arabia|Singapore|South Korea|Sri Lanka|Syria|Taiwan|Tajikistan|Thailand|Timor-Leste|Turkey|Turkmenistan|United Arab Emirates|Uzbekistan|Vietnam|Yemen".split("|")),
    "africa": set("Algeria|Angola|Benin|Botswana|Burkina Faso|Burundi|Cabo Verde|Cameroon|Central African Republic|Chad|Comoros|Congo|Djibouti|Egypt|Equatorial Guinea|Eritrea|Eswatini|Ethiopia|Gabon|Gambia|Ghana|Guinea|Kenya|Lesotho|Liberia|Libya|Madagascar|Malawi|Mali|Mauritania|Mauritius|Morocco|Mozambique|Namibia|Niger|Nigeria|Rwanda|Senegal|Seychelles|Sierra Leone|Somalia|South Africa|South Sudan|Sudan|Tanzania|Togo|Tunisia|Uganda|Zambia|Zimbabwe".split("|")),
    "north america": set("Antigua and Barbuda|Bahamas|Barbados|Belize|Canada|Costa Rica|Cuba|Dominica|Dominican Republic|El Salvador|Grenada|Guatemala|Haiti|Honduras|Jamaica|Mexico|Nicaragua|Panama|Saint Kitts and Nevis|Saint Lucia|Trinidad and Tobago|United States".split("|")),
    "south america": set("Argentina|Bolivia|Brazil|Chile|Colombia|Ecuador|Guyana|Paraguay|Peru|Suriname|Uruguay|Venezuela".split("|")),
    "oceania": set("Australia|Fiji|Kiribati|Marshall Islands|Micronesia|Nauru|New Zealand|Palau|Papua New Guinea|Samoa|Solomon Islands|Tonga|Tuvalu|Vanuatu".split("|")),
    "nordic": set("Denmark|Finland|Iceland|Norway|Sweden|Greenland|Faroe Islands|Åland".split("|")),
    "scandinavia": set("Denmark|Norway|Sweden".split("|")),
}

_TERRITORIES = ("Greenland", "Faroe Islands", "Åland")

_ENDING = re.compile(r"\b(?:what|which|word|words|name|give me|think of|something)\b.*?\b(?:ends?\s+(?:in|with)|ending\s+(?:in|with))\s+(?:(?:the\s+)?(?:letter\s+)?) [-\"'“”]?([a-z]{1,20})\b", re.I | re.X)
_STARTING = re.compile(r"\b(?:what|which|word|words|name|give me|think of|something)\b.*?\b(?:start(?:s|ing)?\s+(?:with|in)|beginning\s+with)\s+(?:(?:the\s+)?(?:letter\s+)?) [-\"'“”]?([a-z]{1,20})\b", re.I | re.X)
_COMPOUND = re.compile(r"\bcompound(?:\s+words?)?\b.*?\b(?:with|containing|including|contains?|has)\s+[\"'“”]?([a-z]{2,20})\b", re.I)
# Only treat "with" as a spelling constraint when the prompt explicitly asks
# for a word. This avoids reading semantic prompts such as "animal with a shell"
# as "a word containing the letter a".
_CONTAINS = re.compile(
    r"\bwords?\b.*?\b(?:contains?|containing|includes?|including|with|has)\s+"
    r"(?:(?:the\s+)?(?:letters?|substring)\s+)?[-\"']?([a-z]{1,20})\b",
    re.I,
)
_ENGLISH_WORD = re.compile(r"\benglish\s+words?\b", re.I)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_SYLLABLE = re.compile(
    r"\b(?P<count>[1-8]|one|two|three|four|five|six|seven|eight)(?:\s*[- ]\s*|\s+)syllables?\b",
    re.I,
)
_COMMON_ENGLISH_WORDS = "apple|bridge|candle|dragon|ember|forest|garden|harbor|island|jacket|kingdom|lantern|meadow|needle|orange|pocket|quartz|river|silver|thunder|umbrella|village|window|yellow|zephyr".split("|")
_COUNTRY = re.compile(
    r"\b(?:name|give me|list|think of|which|what|any|one)\b.*?\bcountr(?:y|ies)\b"
    r"|\bcountr(?:y|ies)\b.{0,100}\b(?:with|whose|that|in|on|above|over|under|near)\b",
    re.I,
)
_REGION = re.compile(r"\b(?:european|asian|african|north american|south american|oceanian|nordic|scandinavian|in europe|in asia|in africa|in north america|in south america|in oceania|in scandinavia)\b", re.I)
_FLAG_COLORS = {
    "red": "Canada|China|France|Germany|Indonesia|Italy|Japan|Mexico|Netherlands|Norway|Poland|Portugal|Russia|Spain|Switzerland|Turkey|United Kingdom|United States|Vietnam",
    "blue": "Argentina|Australia|Brazil|France|Greece|India|Israel|Netherlands|New Zealand|Russia|Sweden|United Kingdom|United States",
    "white": "Canada|Finland|France|Greece|India|Indonesia|Israel|Italy|Japan|Mexico|Netherlands|Poland|Russia|Switzerland|United Kingdom|United States",
    "green": "Brazil|India|Ireland|Italy|Mexico|Nigeria|Pakistan|Saudi Arabia|South Africa|Portugal",
    "yellow": "Brazil|China|Germany|Spain|Sweden|Ukraine|Vietnam",
    "black": "Belgium|Germany|Jamaica|South Africa",
}
_EXACT_FLAG_COLORS = {
    "Argentina": {"blue", "white", "yellow"}, "Australia": {"red", "white", "blue"},
    "Belgium": {"black", "yellow", "red"}, "Brazil": {"green", "yellow", "blue", "white"},
    "Canada": {"red", "white"}, "China": {"red", "yellow"},
    "France": {"red", "white", "blue"}, "Germany": {"black", "red", "yellow"},
    "Greece": {"blue", "white"}, "India": {"orange", "white", "green", "blue"},
    "Indonesia": {"red", "white"}, "Ireland": {"green", "white", "orange"},
    "Israel": {"blue", "white"}, "Italy": {"green", "white", "red"},
    "Jamaica": {"black", "green", "yellow"}, "Japan": {"red", "white"},
    "Netherlands": {"red", "white", "blue"}, "New Zealand": {"red", "white", "blue"},
    "Nigeria": {"green", "white"}, "Norway": {"red", "white", "blue"},
    "Poland": {"red", "white"}, "Russia": {"red", "white", "blue"},
    "Saudi Arabia": {"green", "white"}, "Sweden": {"blue", "yellow"},
    "Switzerland": {"red", "white"}, "Turkey": {"red", "white"},
    "Ukraine": {"blue", "yellow"}, "United Kingdom": {"red", "white", "blue"},
    "United States": {"red", "white", "blue"}, "Vietnam": {"red", "yellow"},
}
_FLAG_SYMBOLS = {
    "star": set("Algeria|Angola|Australia|Azerbaijan|Bosnia and Herzegovina|Brazil|Burkina Faso|Burundi|Cameroon|Cape Verde|Central African Republic|Chile|China|Comoros|Cuba|Democratic Republic of the Congo|Djibouti|Dominica|East Timor|Equatorial Guinea|Ethiopia|Ghana|Grenada|Guinea-Bissau|Honduras|Israel|Jordan|Liberia|Libya|Malaysia|Marshall Islands|Mauritania|Micronesia|Morocco|Mozambique|Myanmar|Nauru|New Zealand|North Korea|Pakistan|Panama|Papua New Guinea|Paraguay|Philippines|Saint Kitts and Nevis|Samoa|Senegal|Singapore|Slovenia|Solomon Islands|Somalia|South Sudan|Suriname|Syria|Tajikistan|Togo|Tunisia|Turkey|Turkmenistan|Tuvalu|United States|Uzbekistan|Venezuela|Vietnam|Zimbabwe".split("|")),
    "cross": set("Denmark|Dominican Republic|Finland|Georgia|Greece|Iceland|Norway|Sweden|Switzerland|United Kingdom".split("|")),
    "crescent": set("Algeria|Azerbaijan|Libya|Malaysia|Maldives|Mauritania|Pakistan|Singapore|Tunisia|Turkey|Turkmenistan|Uzbekistan".split("|")),
}
_LANDLOCKED = set("Afghanistan|Armenia|Austria|Azerbaijan|Belarus|Bhutan|Bolivia|Botswana|Burkina Faso|Burundi|Central African Republic|Chad|Czechia|Eswatini|Ethiopia|Hungary|Kazakhstan|Kyrgyzstan|Laos|Lesotho|Liechtenstein|Luxembourg|Malawi|Mali|Moldova|Mongolia|Nepal|Niger|North Macedonia|Paraguay|Rwanda|San Marino|Serbia|Slovakia|South Sudan|Switzerland|Tajikistan|Turkmenistan|Uganda|Uzbekistan|Vatican City|Zambia|Zimbabwe".split("|"))
_SMALL_POPULATION = set("Andorra|Antigua and Barbuda|Dominica|Liechtenstein|Marshall Islands|Monaco|Nauru|Palau|Saint Kitts and Nevis|San Marino|Tuvalu|Vatican City".split("|"))
_ISLAND_COUNTRIES = set("Antigua and Barbuda|Australia|Bahamas|Bahrain|Barbados|Brunei|Cabo Verde|Comoros|Cuba|Cyprus|Dominica|Dominican Republic|Fiji|Grenada|Haiti|Iceland|Indonesia|Ireland|Jamaica|Japan|Kiribati|Madagascar|Maldives|Malta|Marshall Islands|Mauritius|Micronesia|Nauru|New Zealand|Palau|Papua New Guinea|Philippines|Saint Kitts and Nevis|Saint Lucia|Saint Vincent and the Grenadines|Samoa|Seychelles|Singapore|Solomon Islands|Sri Lanka|Taiwan|Timor-Leste|Tonga|Trinidad and Tobago|Tuvalu|United Kingdom|Vanuatu".split("|"))
_COUNTRY_BORDERS = {
    "china": set("Afghanistan|Bhutan|India|Kazakhstan|North Korea|Kyrgyzstan|Laos|Mongolia|Myanmar|Nepal|Pakistan|Russia|Tajikistan|Vietnam".split("|")),
    "united states": {"Canada", "Mexico"},
    "canada": {"United States"},
    "mexico": {"Belize", "Guatemala", "United States"},
    "india": set("Bangladesh|Bhutan|China|Myanmar|Nepal|Pakistan".split("|")),
    "brazil": set("Argentina|Bolivia|Colombia|Guyana|Paraguay|Peru|Suriname|Uruguay|Venezuela".split("|")),
    "france": set("Andorra|Belgium|Germany|Italy|Luxembourg|Monaco|Spain|Switzerland".split("|")),
    "germany": set("Austria|Belgium|Czechia|Denmark|France|Luxembourg|Netherlands|Poland|Switzerland".split("|")),
    "russia": set("Azerbaijan|Belarus|China|Estonia|Finland|Georgia|Kazakhstan|Latvia|Lithuania|Mongolia|North Korea|Norway|Poland|Ukraine".split("|")),
}
_COMMON_COUNTRIES = "United States|Canada|China|India|Brazil|Australia|Japan|Germany|France|Italy|Mexico|United Kingdom|Spain|South Korea|South Africa|Argentina|New Zealand|Sweden|Norway|Switzerland".split("|")
_TV_CHARACTERS = {
    "how_i_met_your_mother": (
        "Ted Mosby", "Marshall Eriksen", "Lily Aldrin", "Barney Stinson",
        "Robin Scherbatsky", "Tracy McConnell", "Ranjit", "Carl MacLaren",
        "Victoria", "Quinn Garvey", "Patrice", "Stella Zinman",
    ),
    "spongebob": (
        "SpongeBob SquarePants", "Patrick Star", "Squidward Tentacles",
        "Mr. Krabs", "Sandy Cheeks", "Plankton", "Gary the Snail",
        "Pearl Krabs", "Mrs. Puff", "Karen Plankton", "Larry the Lobster",
        "Mermaid Man", "Barnacle Boy", "Bubble Bass",
    ),
}
_SHOW_ALIASES = {
    "how_i_met_your_mother": re.compile(r"\bhow\s+i\s+met\s+(?:your|ur)\s+mother\b", re.I),
    "spongebob": re.compile(r"\bsponge\s*bob(?:\s+square\s*pants)?\b", re.I),
}
_SITCOMS = (
    "Arrested Development", "Community", "30 Rock", "Frasier", "Cheers",
    "Seinfeld", "The Office", "Parks and Recreation", "Brooklyn Nine-Nine",
    "Modern Family", "Superstore", "The Good Place", "Abbott Elementary",
    "Schitt's Creek", "It's Always Sunny in Philadelphia", "New Girl",
    "Scrubs", "Malcolm in the Middle", "Everybody Hates Chris", "Black-ish",
    "The IT Crowd", "Kim's Convenience", "Derry Girls", "Party Down",
    "What We Do in the Shadows", "Ghosts", "Veep",
    "Silicon Valley", "Unbreakable Kimmy Schmidt", "Happy Endings",
    "Fresh Off the Boat", "My Name Is Earl", "The Middle", "Mom",
    "How I Met Your Mother", "Friends", "The Big Bang Theory",
)
_TV_CHARACTER_PROMPT = re.compile(r"\bcharacters?\b.*?\b(?:from|in|on)\b|\bname\b.*?\bcharacters?\b", re.I)
_SITCOM_PROMPT = re.compile(r"\b(?:sitcom|situation\s+comedy|sit[ -]?down\s+comedy)\b", re.I)
_TV_SHOW_PROMPT = re.compile(r"\b(?:tv|television)?\s*shows?\b", re.I)
_TRIVIA_LISTS = {
    "animal": "Dog|Cat|Elephant|Tiger|Lion|Giraffe|Zebra|Kangaroo|Panda|Dolphin|Whale|Shark|Octopus|Penguin|Eagle|Owl|Bat|Snake|Crocodile|Turtle|Tortoise|Snail|Crab|Lobster|Clam|Oyster|Mussel|Nautilus|Chiton|Horseshoe Crab|Armadillo|Rhinoceros|Cheetah|Leopard|Butterfly|Bee".split("|"),
    "food": "Pizza|Taco|Sushi|Curry|Lasagna|Paella|Falafel|Ramen|Pierogi|Gnocchi|Risotto|Kimchi|Hummus|Burrito|Dumpling|Croissant|Biryani|Gazpacho|Shakshuka|Poutine".split("|"),
    "fruit": "Apple|Banana|Orange|Mango|Papaya|Guava|Lychee|Rambutan|Durian|Persimmon|Pomegranate|Dragon Fruit|Passion Fruit|Starfruit|Boysenberry|Gooseberry|Quince|Plantain".split("|"),
    "vegetable": "Carrot|Broccoli|Spinach|Cabbage|Turnip|Parsnip|Artichoke|Asparagus|Eggplant|Zucchini|Kohlrabi|Rutabaga|Fennel|Okra|Chard|Leek".split("|"),
    "sport": "Soccer|Basketball|Baseball|Tennis|Cricket|Rugby|Hockey|Volleyball|Badminton|Squash|Lacrosse|Curling|Fencing|Archery|Biathlon|Handball|Water Polo".split("|"),
    "instrument": "Piano|Guitar|Violin|Trumpet|Flute|Cello|Oboe|Bassoon|Clarinet|Trombone|Tuba|Harp|Mandolin|Sitar|Marimba|Accordion|Theremin|Bass Clarinet".split("|"),
    "occupation": "Teacher|Doctor|Engineer|Carpenter|Plumber|Electrician|Architect|Paramedic|Geologist|Cartographer|Actuary|Arborist|Locksmith|Meteorologist|Archivist|Interpreter|Surveyor".split("|"),
    "vehicle": "Car|Bus|Truck|Bicycle|Motorcycle|Train|Tram|Ferry|Submarine|Helicopter|Glider|Hovercraft|Gondola|Rickshaw|Snowmobile|Funicular".split("|"),
    "flower": "Rose|Tulip|Daisy|Sunflower|Orchid|Daffodil|Chrysanthemum|Marigold|Peony|Iris|Zinnia|Begonia|Anemone|Foxglove|Snapdragon".split("|"),
    "tree": "Oak|Maple|Pine|Birch|Willow|Cedar|Redwood|Baobab|Ginkgo|Sycamore|Dogwood|Hawthorn|Juniper|Sequoia|Eucalyptus".split("|"),
    "planet": "Mercury|Venus|Earth|Mars|Jupiter|Saturn|Uranus|Neptune".split("|"),
    "gemstone": "Diamond|Ruby|Sapphire|Emerald|Amethyst|Opal|Topaz|Garnet|Aquamarine|Peridot|Tourmaline|Tanzanite|Moonstone|Citrine".split("|"),
    "board_game": "Chess|Checkers|Monopoly|Scrabble|Clue|Risk|Catan|Carcassonne|Azul|Pandemic|Stratego|Backgammon|Codenames|Ticket to Ride".split("|"),
    "dinosaur": "Tyrannosaurus|Triceratops|Stegosaurus|Velociraptor|Brachiosaurus|Ankylosaurus|Spinosaurus|Allosaurus|Iguanodon|Parasaurolophus|Pachycephalosaurus|Deinonychus".split("|"),
    "body_part": "Heart|Lung|Liver|Kidney|Stomach|Pancreas|Spleen|Femur|Patella|Clavicle|Scapula|Retina|Cochlea|Tendon|Ligament".split("|"),
    "interjection": "Wow|Oh|Hey|Ouch|Oops|Alas|Hooray|Yikes|Gosh|Gee|Bravo|Bingo|Aha|Huh|Ugh|Phew|Shh|Psst|Meh|Whoa|Eureka|Darn|Drat|Jeez".split("|"),
    "filler_word": "Um|Uh|Er|Ah|Like|Well|So|Actually|Basically|Literally|You Know|I Mean|Anyway|Right|Okay|Kind Of|Sort Of|Let Me See|You See".split("|"),
}
_TRIVIA_ALIASES = {
    "animal": re.compile(r"\b(?:animal|creature)s?\b", re.I),
    "food": re.compile(r"\bfoods?\b", re.I),
    "fruit": re.compile(r"\bfruits?\b", re.I),
    "vegetable": re.compile(r"\bvegetables?\b", re.I),
    "sport": re.compile(r"\bsports?\b", re.I),
    "instrument": re.compile(r"\b(?:musical\s+)?instruments?\b", re.I),
    "occupation": re.compile(r"\b(?:jobs?|occupations?|professions?)\b", re.I),
    "vehicle": re.compile(r"\bvehicles?\b", re.I),
    "flower": re.compile(r"\bflowers?\b", re.I),
    "tree": re.compile(r"\btrees?\b", re.I),
    "planet": re.compile(r"\bplanets?\b", re.I),
    "gemstone": re.compile(r"\b(?:gemstones?|gems?)\b", re.I),
    "board_game": re.compile(r"\bboard\s+games?\b", re.I),
    "dinosaur": re.compile(r"\bdinosaurs?\b", re.I),
    "body_part": re.compile(r"\bbody\s+parts?\b", re.I),
    "interjection": re.compile(r"\binterjections?\b", re.I),
    "filler_word": re.compile(r"\b(?:filler|hesitation)\s+(?:words?|phrases?)\b", re.I),
}
_ANIMAL_TRAITS = {
    "shell": {"Turtle", "Tortoise", "Snail", "Crab", "Lobster", "Clam", "Oyster", "Mussel", "Nautilus", "Chiton", "Horseshoe Crab", "Armadillo"},
    "stripes": {"Tiger", "Zebra"},
    "spots": {"Cheetah", "Leopard"},
    "horn": {"Rhinoceros"},
    "wings": {"Eagle", "Owl", "Bat", "Penguin", "Butterfly", "Bee"},
    "scales": {"Snake", "Crocodile", "Shark"},
}
_SEA_ANIMALS = {
    "Dolphin", "Whale", "Octopus", "Turtle", "Crab", "Lobster", "Clam",
    "Oyster", "Mussel", "Nautilus", "Chiton", "Horseshoe Crab",
}
_FISH_OR_BIRDS = {"Shark", "Penguin", "Eagle", "Owl"}
_FALLBACK_WORDS = set("""prototype stereotype archetype genotype phenotype subtype bloodtype prototype textile stereotype sea food seafood dogfood catfood fastfood junkfood soulfood brainfood foodtruck
stop watch stopwatch stoplight stopgap stopover stopcock stopword non nonstop bus busstop laptop laptopcase flower sunflower football snowball airport airplane raincoat overcoat breakfast bookshelfs bookshelf toothbrush toothpaste firehouse lighthouse lighthouse keeper
""".split()) | set(_COMMON_ENGLISH_WORDS)
_DISPLAY_FORMS = {"foodtruck": "food truck", "busstop": "bus stop"}


@lru_cache(maxsize=1)
def _word_list() -> tuple[str, ...]:
    """Return a compact, frequency-ranked general English vocabulary.

    CMUdict is a pronunciation resource and contains many names, abbreviations,
    specialist terms, and generated-looking entries.  Wordfreq's most common
    English words are a better fit for game answers and make constraint scans
    considerably smaller.  CMUdict remains available to `_syllable_counts`.
    """
    try:
        from wordfreq import top_n_list

        common = [
            word.casefold() for word in top_n_list("en", 30_000, wordlist="best")
            if word.isascii() and word.isalpha() and 2 <= len(word) <= 24
        ]
        return tuple(dict.fromkeys(common + sorted(_FALLBACK_WORDS)))
    except (ImportError, OSError):
        return tuple(sorted(_FALLBACK_WORDS, key=lambda word: (len(word), word)))


@lru_cache(maxsize=1)
def _words() -> set[str]:
    return set(_word_list())


@lru_cache(maxsize=1)
def _syllable_counts() -> dict[str, set[int]]:
    """Load pronunciation-based syllable counts once for fast prompt checks."""
    try:
        import cmudict
        allowed_words = _words()
        counts: dict[str, set[int]] = {}
        for word, pronunciations in cmudict.dict().items():
            clean = _dictionary_form(word)
            if not clean or clean not in allowed_words:
                continue
            counts[clean] = {
                sum(bool(re.search(r"\d", phoneme)) for phoneme in pronunciation)
                for pronunciation in pronunciations
            }
        return counts
    except (AttributeError, ImportError, OSError):
        return {}


def warm_local_data() -> None:
    """Load local word and pronunciation data before the first game prompt."""
    _word_list()
    _syllable_counts()


def _country_name(value: str) -> bool:
    return value.casefold() in {country.casefold() for country in _COUNTRIES}


def _dictionary_form(value: str) -> str:
    """Normalize a displayed answer to the form stored in the word lexicon."""
    return re.sub(r"[^a-z]", "", value.casefold())


def _requested_subject(prompt: str) -> str:
    """Extract the noun phrase the player was asked to name."""
    match = re.search(
        r"\b(?:name|give(?:\s+me)?|list|think\s+of)\b\s+"
        r"(?:(?:any|one\s+of|one|some|the|an?)\s+)*(?P<subject>.+)",
        prompt, re.I,
    )
    if not match:
        return prompt
    return re.split(
        r"\s+(?:that|which|whose|who|with|without|from|in|on|of|used|having|"
        r"ending|starting|containing|including)\b|\s*\(",
        match.group("subject"), maxsplit=1, flags=re.I,
    )[0].strip(" .,:;?!\"'")


def _region_name(value: str) -> str:
    name = value.casefold().removeprefix("in ")
    return {
        "north american": "north america", "south american": "south america",
        "oceanian": "oceania", "european": "europe", "asian": "asia",
        "african": "africa", "scandinavian": "scandinavia",
    }.get(name, name)


def prompt_kind(prompt: str) -> tuple[str, str] | None:
    if _TV_CHARACTER_PROMPT.search(prompt):
        for show_key, alias in _SHOW_ALIASES.items():
            if alias.search(prompt):
                return "tv_character", show_key
    if _SITCOM_PROMPT.search(prompt) and _TV_SHOW_PROMPT.search(prompt):
        return "sitcom", ""
    subject = _requested_subject(prompt)
    if not _CONTAINS.search(prompt) and re.search(r"\b(?:name|give|list|think of|what|which)\b", prompt, re.I):
        for trivia_key, alias in _TRIVIA_ALIASES.items():
            if alias.search(subject):
                return "trivia", trivia_key
    syllable = _SYLLABLE.search(prompt)
    if syllable and re.search(r"\b(?:word|name|something|thing|answer)\b", prompt, re.I):
        raw_count = syllable.group("count").casefold()
        return "syllables", str(_NUMBER_WORDS.get(raw_count, int(raw_count) if raw_count.isdigit() else 0))
    # Keep the requested category authoritative. Letter constraints on a
    # country prompt filter countries; they must not turn it into a generic
    # pronunciation-dictionary lookup.
    if re.search(r"\b(?:countr(?:y|ies)|nations?|territor(?:y|ies))\b", subject, re.I):
        region = _REGION.search(prompt)
        if region:
            return "country_region", _region_name(region.group(0))
        return "country", ""
    if (re.search(r"\b(?:double|repeated)\s+letter\b", prompt, re.I)
            and re.search(r"\bword\b", subject, re.I)):
        return "english_word", ""
    ending_is_negated = bool(re.search(
        r"\b(?:doesn[^a-z0-9]{1,8}t|does\s+not|mustn[^a-z0-9]{1,8}t|must\s+not|not)\b"
        r".{0,30}\b(?:ends?|ending)\s+(?:in|with)\b",
        prompt, re.I,
    ))
    match = None if ending_is_negated else _ENDING.search(prompt)
    if not match and not ending_is_negated:
        # Curly quotes copied through a mismatched encoding can become several
        # punctuation characters. Ignore that punctuation before the suffix.
        match = re.search(
            r"\b(?:ends?\s+(?:in|with)|ending\s+(?:in|with))\s+"
            r"(?:(?:the\s+)?(?:letter\s+)?)?[^a-z0-9]{0,12}-?([a-z]{1,20})\b",
            prompt, re.I,
        )
    if match:
        return "ending", match.group(1).casefold()
    match = _STARTING.search(prompt)
    if not match:
        match = re.search(
            r"\b(?:start(?:s|ing)?\s+(?:with|in)|beginning\s+with)\s+"
            r"(?:(?:the\s+)?(?:letter\s+)?)?[^a-z0-9]{0,12}-?([a-z]{1,20})\b",
            prompt, re.I,
        )
    if match:
        return "starting", match.group(1).casefold()
    match = _COMPOUND.search(prompt)
    if match:
        return "compound", next(value for value in match.groups() if value).casefold()
    match = _CONTAINS.search(prompt)
    if not match:
        constraint = re.search(
            r"\bwords?\b.*?\b(?:contains?|containing|includes?|including|with|has)\s+(.{1,60})",
            prompt, re.I,
        )
        if constraint:
            tokens = re.findall(r"[a-z]{1,20}", constraint.group(1).casefold())
            tokens = [token for token in tokens if token not in {"the", "letter", "letters", "substring"}]
            if tokens:
                # Present the same group interface as the compiled patterns.
                match = re.match(r"([a-z]{1,20})", tokens[0], re.I)
    if match:
        return "contains", match.group(1).casefold()
    if _ENGLISH_WORD.search(prompt):
        return "english_word", ""
    return None


def _qualified_countries(prompt: str, category: str, region: str) -> list[str]:
    eligible = list(_COUNTRIES)
    lowered = prompt.casefold()
    starting = _STARTING.search(prompt)
    ending = _ENDING.search(prompt)
    containing = _CONTAINS.search(prompt)
    if starting:
        prefix = starting.group(1).casefold().lstrip("-")
        eligible = [name for name in eligible if name.casefold().startswith(prefix)]
    if ending:
        suffix = ending.group(1).casefold().lstrip("-")
        eligible = [name for name in eligible if name.casefold().endswith(suffix)]
    if containing:
        fragment = containing.group(1).casefold().lstrip("-")
        eligible = [name for name in eligible if fragment in name.casefold()]
    if re.search(r"\bterritor(?:y|ies)\b", lowered):
        eligible.extend(name for name in _TERRITORIES if name not in eligible)
    if re.search(r"\bisland\s+(?:country|nation)|(?:country|nation)\s+(?:that\s+)?is\s+an?\s+island\b", lowered):
        eligible = [name for name in eligible if name in _ISLAND_COUNTRIES]
    border_match = re.search(
        r"\b(?:borders?|bordering|neighbou?rs?|adjacent\s+to)\s+"
        r"(?:the\s+)?([a-z][a-z .'-]{1,40}?)(?=\s*(?:[,;?.]|$|\b(?:and|or|but|with|without|that|which)\b))",
        lowered,
    )
    if border_match:
        bordered = border_match.group(1).strip()
        allowed = _COUNTRY_BORDERS.get(bordered)
        # An unrecognized geographic qualifier must never fall back to the
        # unfiltered common-country list.
        eligible = [name for name in eligible if allowed is not None and name in allowed]
    if "coast" in lowered or "coastal" in lowered or "shoreline" in lowered or "landlocked" in lowered:
        if "landlocked" in lowered or re.search(r"\b(?:no|without|lack(?:s|ing)?)\b.{0,30}\b(?:coast|coastal|shoreline)", lowered):
            eligible = [name for name in eligible if name in _LANDLOCKED]
        else:
            eligible = [name for name in eligible if name not in _LANDLOCKED]
    colors = [name for name in _FLAG_COLORS if re.search(rf"\b{name}\b", lowered)]
    if colors and re.search(r"\bflag|banner\b", lowered):
        if re.search(r"\b(?:no|without)\s+(?:any\s+)?other\s+colou?rs?\b", lowered):
            requested = set(colors)
            eligible = [name for name in eligible if _EXACT_FLAG_COLORS.get(name) == requested]
        else:
            eligible = [name for name in eligible if all(name in _FLAG_COLORS[color].split("|") for color in colors)]
    if re.search(r"\bflag|banner\b", lowered):
        for symbol, matching in _FLAG_SYMBOLS.items():
            if re.search(rf"\b{re.escape(symbol)}s?\b", lowered):
                eligible = [name for name in eligible if name in matching]
    if re.search(r"\b(?:over|more than|greater than|above|at least)\s+100[,.]?000\b|\bpopulation.{0,30}100[,.]?000\b", lowered):
        eligible = [name for name in eligible if name not in _SMALL_POPULATION]
    requested_regions = list(dict.fromkeys(
        _region_name(match.group(0)) for match in _REGION.finditer(prompt)
    ))
    if not requested_regions and region:
        requested_regions = [region]
    if requested_regions:
        allowed = set().union(*(
            _REGIONAL_COUNTRIES.get(name, set()) for name in requested_regions
        ))
        eligible = [name for name in eligible if name in allowed]
    qualifier_present = re.search(
        r"\b(?:countr(?:y|ies)|nations?)\b\s+(?:that|which|whose|with|without|having|in|on)\b",
        lowered,
    )
    known_qualifier = re.search(
        r"\b(?:flag|banner|coast|coastal|coastline|shoreline|landlocked|population|island|"
        r"borders?|bordering|neighbou?rs?|adjacent|start(?:s|ing)?|begin(?:s|ning)?|"
        r"ends?|ending|contains?|containing|europe|asia|africa|north america|south america|oceania|"
        r"nordic|scandinavia)\b",
        lowered,
    )
    if qualifier_present and not known_qualifier:
        return []
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
    if category == "tv_character":
        known = {name.casefold() for name in _TV_CHARACTERS.get(value, ())}
        return "match" if answer.casefold().strip() in known else "uncertain"
    if category == "sitcom":
        return "match" if answer.casefold().strip() in {show.casefold() for show in _SITCOMS} else "uncertain"
    if category == "trivia":
        known = {item.casefold() for item in _qualified_trivia(prompt, value)}
        return "match" if answer.casefold().strip() in known else "uncertain"
    if category == "syllables":
        counts = _syllable_counts().get(_dictionary_form(answer))
        if not counts:
            return "uncertain"
        return "match" if int(value) in counts else "reject"
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
        # A broad dictionary cannot prove compounds by arbitrary splitting:
        # "sunny" could otherwise become "sun" + "ny", and "stopping"
        # could become "stop" + "ping". Positively confirm only the curated
        # compounds; unfamiliar model answers remain uncertain and visible.
        if word not in _FALLBACK_WORDS:
            return "uncertain"
        for start in (match.start() for match in re.finditer(re.escape(value), word)):
            end = start + len(value)
            left, right = word[:start], word[end:]
            if (not left and right in lexicon) or (not right and left in lexicon) or (left in lexicon and right in lexicon):
                return "match"
        return "uncertain"
    if category == "english_word":
        word = _dictionary_form(answer)
        if re.search(r"\b(?:double|repeated)\s+letter\b", prompt, re.I):
            if not re.search(r"([a-z])\1$", word):
                return "reject"
            return "match" if word in _words() else "uncertain"
        # Avoid loading the full CMU dictionary for an unconstrained prompt.
        # Unknown model answers remain available rather than becoming false negatives.
        return "match" if _dictionary_form(answer) in _FALLBACK_WORDS else "uncertain"
    return "uncertain"


def satisfies_constraint(answer: str, prompt: str) -> bool:
    """Return whether the local data positively confirms a candidate."""
    return candidate_check(answer, prompt) == "match"


def _qualified_trivia(prompt: str, category: str) -> list[str]:
    answers = list(_TRIVIA_LISTS.get(category, ()))
    subject = _requested_subject(prompt).casefold()
    lowered = prompt.casefold()
    simple_subjects = {
        "animal": r"(?:(?:sea|marine|ocean)\s+)?(?:animal|creature)s?",
        "food": r"foods?", "fruit": r"fruits?", "vegetable": r"vegetables?",
        "sport": r"sports?", "instrument": r"(?:musical\s+)?instruments?",
        "occupation": r"(?:job|occupation|profession)s?", "vehicle": r"vehicles?",
        "flower": r"flowers?", "tree": r"trees?", "planet": r"planets?",
        "gemstone": r"(?:gemstone|gem)s?", "board_game": r"board\s+games?",
        "dinosaur": r"dinosaurs?", "body_part": r"body\s+parts?",
        "interjection": r"interjections?",
        "filler_word": r"(?:filler|hesitation)\s+(?:word|phrase)s?",
    }
    expected_subject = simple_subjects.get(category)
    if expected_subject and not re.fullmatch(expected_subject, subject, re.I):
        return []
    semantic_qualifier = re.search(
        r"\b(?:that|which|whose|who|with|without|having|used\s+(?:for|to)|"
        r"found\s+in|lives?\s+in|from)\b",
        lowered,
    )
    if category != "animal" and semantic_qualifier:
        return []
    if category == "animal":
        # Habitat and other semantic qualifiers need prompt-specific knowledge;
        # a generic animal list would be actively misleading.
        if re.search(r"\b(?:lives?|living|found|habitats?)\b", lowered):
            return []
        known_animal_qualifier = bool(
            re.search(r"\b(?:sea|marine|ocean|fish|bird)\b", lowered)
            or any(re.search(rf"\b{re.escape(trait)}s?\b", lowered) for trait in _ANIMAL_TRAITS)
        )
        if semantic_qualifier and not known_animal_qualifier:
            return []
        if re.search(r"\b(?:sea|marine|ocean)\b", lowered):
            answers = [answer for answer in answers if answer in _SEA_ANIMALS]
        if re.search(r"\b(?:isn['’]?t|is not|not)\b.{0,25}\b(?:fish|bird)\b", lowered):
            answers = [answer for answer in answers if answer not in _FISH_OR_BIRDS]
        for trait, matching in _ANIMAL_TRAITS.items():
            if re.search(rf"\b{re.escape(trait)}s?\b", lowered):
                answers = [answer for answer in answers if answer in matching]
    return answers


def local_candidates(
    prompt: str, excluded: list[str] | None = None, limit: int = 8, *, mode: str = "Krillion",
    include_learned: bool = True,
) -> list[dict[str, object]]:
    # Answers previously accepted by the game are the fastest and strongest
    # local matches. Import here to avoid coupling lexicon initialization to
    # the feedback store during application startup.
    from .learned_answers import get_learned

    excluded_keys = {item.casefold().strip() for item in (excluded or [])}
    learned = (
        [
            answer for answer in get_learned(prompt, excluded, mode=mode)
            if answer.casefold().strip() not in excluded_keys
        ]
        if include_learned else []
    )
    kind = prompt_kind(prompt)
    if not kind:
        return [{"answer": answer, "confirmed": True} for answer in learned[:limit]]
    category, value = kind
    if category == "tv_character":
        answers = list(_TV_CHARACTERS.get(value, ()))[:limit]
        source = "Local TV character list"
    elif category == "sitcom":
        answers = list(_SITCOMS)[:limit]
        source = "Local sitcom list"
    elif category == "trivia":
        answers = _qualified_trivia(prompt, value)[:limit]
        source = "Local general-knowledge list"
    elif category == "syllables":
        target = int(value)
        counts = _syllable_counts()
        answers = [
            word for word in _word_list()
            if target in counts.get(word, ()) and 3 <= len(word) <= 18
        ][:limit]
        source = "General English word list"
    elif category == "ending":
        answers = [word for word in _word_list() if word.endswith(value) and len(word) > len(value)][:limit]
        source = "General English word list"
    elif category == "starting":
        answers = [word for word in _word_list() if word.startswith(value) and len(word) > len(value)][:limit]
        source = "General English word list"
    elif category == "contains":
        answers = [word for word in _word_list() if value in word and word != value][:limit]
        source = "General English word list"
    elif category == "compound":
        words = _words()
        answers = [
            word for word in sorted(_FALLBACK_WORDS, key=lambda item: (len(item), item))
            if word in words and value in word and len(word) > len(value)
            and satisfies_constraint(word, prompt)
        ][:limit]
        source = "Dictionary word and component match"
    elif category in {"country", "country_region"}:
        country_source = _qualified_countries(prompt, category, value)
        priority = {name: index for index, name in enumerate(_COMMON_COUNTRIES)}
        answers = sorted(country_source, key=lambda name: (priority.get(name, len(priority)), name))[:limit]
        source = "Local country list"
    elif category == "english_word":
        if re.search(r"\b(?:double|repeated)\s+letter\b", prompt, re.I):
            answers = [word for word in _word_list() if re.search(r"([a-z])\1$", word)][:limit]
        else:
            answers = list(_COMMON_ENGLISH_WORDS)[:limit]
        source = "General English word list"
    else:
        answers = []

    combined: list[dict[str, object]] = []
    seen: set[str] = set()
    for answer in learned:
        key = answer.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            combined.append({"answer": answer, "confirmed": True})
    for answer in answers:
        displayed = _DISPLAY_FORMS.get(answer, answer)
        key = displayed.casefold().strip()
        if key and key not in excluded_keys and key not in seen:
            seen.add(key)
            combined.append({"answer": displayed})
    return combined[:limit]
