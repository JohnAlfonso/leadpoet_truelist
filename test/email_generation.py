import re
import hashlib
import unicodedata


def _normalize(text):
    """Lowercase, strip accents (josé -> jose), and keep only a-z."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", text.lower())


def _split_name(full_name):
    """Return (first, last) as normalized parts; single token uses it for both."""
    parts = [p for p in (_normalize(p) for p in re.split(r"\s+", full_name.strip())) if p]
    if not parts:
        return "", ""
    return parts[0], (parts[-1] if len(parts) > 1 else parts[0])


def _name_parts(full_name):
    """Return (first, [surname candidates]) normalized.

    Hispanic names usually carry two surnames: [given] [paternal] [maternal].
    Corporate email uses one of them, and which one is company-dependent
    ("Juan Valencia Tello" → juan.valencia OR juan.tello). So for 3+ token names
    we offer BOTH the last token and the second token as surname candidates and
    let verification / format-learning pick the real one.
    """
    parts = [p for p in (_normalize(p) for p in re.split(r"\s+", full_name.strip())) if p]
    if not parts:
        return "", []
    first = parts[0]
    if len(parts) == 1:
        return first, [first]
    surnames = [parts[-1]]            # last token — the existing default
    if len(parts) >= 3 and parts[1] not in surnames:
        surnames.append(parts[1])    # second token — likely paternal surname
    return first, surnames


# --- Nickname expansion -------------------------------------------------------
# Adds *correct* candidates when the stored name differs from the mailbox name
# (DB says "Robert", mailbox is "bob.smith@"). Each set is bidirectional.
_NICKNAME_GROUPS = [
    {"robert", "rob", "bob", "bobby"}, {"william", "will", "bill", "billy"},
    {"james", "jim", "jimmy"}, {"michael", "mike", "mick"},
    {"richard", "rick", "rich", "dick"}, {"david", "dave"},
    {"daniel", "dan", "danny"}, {"thomas", "tom", "tommy"},
    {"christopher", "chris"}, {"joseph", "joe", "joey"},
    {"steven", "stephen", "steve"}, {"edward", "ed", "eddie", "ted"},
    {"kenneth", "ken"}, {"anthony", "tony"}, {"andrew", "andy", "drew"},
    {"matthew", "matt"}, {"nicholas", "nick"}, {"samuel", "sam"},
    {"benjamin", "ben"}, {"jeffrey", "jeff"}, {"timothy", "tim"},
    {"ronald", "ron"}, {"donald", "don"}, {"charles", "charlie", "chuck"},
    {"elizabeth", "liz", "beth", "betty"},
    {"katherine", "catherine", "kate", "katie", "cathy"},
    {"jennifer", "jen", "jenny"}, {"margaret", "maggie", "peggy"},
    {"susan", "sue"}, {"patricia", "pat", "patty", "trish"},
    {"deborah", "deb", "debbie"}, {"rebecca", "becky"}, {"victoria", "vicky"},
]
_NICK = {}
for _g in _NICKNAME_GROUPS:
    for _n in _g:
        _NICK[_n] = _g


def _ordered_variants(first):
    """Primary first name first, then its known nicknames (deterministic order)."""
    group = _NICK.get(first)
    if not group:
        return [first]
    return [first] + sorted(group - {first})


# --- Patterns: single source of truth, ranked by real-world prevalence --------
PATTERNS = {
    "first.last": lambda f, l: f"{f}.{l}",
    "flast":      lambda f, l: f"{f[0]}{l}",
    "firstlast":  lambda f, l: f"{f}{l}",
    "first":      lambda f, l: f,
    "first_last": lambda f, l: f"{f}_{l}",
    "f.last":     lambda f, l: f"{f[0]}.{l}",
    "firstl":     lambda f, l: f"{f}{l[0]}",
    "last.first": lambda f, l: f"{l}.{f}",
}
# Dominant formats applied to nickname variants (avoids candidate explosion).
_VARIANT_PATTERNS = ("first.last", "flast", "firstlast")
_FORMAT_RANK = {name: i for i, name in enumerate(PATTERNS)}


def generate_work_emails(full_name, company_domain):
    """Return ranked candidate emails, covering nickname and surname variants."""
    first, surnames = _name_parts(full_name)
    if not first or not surnames:
        return []

    variants = _ordered_variants(first)
    primary, nicknames = variants[0], variants[1:]

    locals_ = []
    # Tier 1: the given name against each surname candidate, full pattern set.
    for last in surnames:
        for name in PATTERNS:
            locals_.append(PATTERNS[name](primary, last))
    # Tier 2: nicknames against each surname, dominant formats only.
    for f in nicknames:
        for last in surnames:
            for name in _VARIANT_PATTERNS:
                locals_.append(PATTERNS[name](f, last))

    seen, emails = set(), []
    for local in locals_:
        if local and local not in seen:
            seen.add(local)
            emails.append(f"{local}@{company_domain}")
    return emails


def smart_email_generator(full_name, company_domain, max_results=8):
    return generate_work_emails(full_name, company_domain)[:max_results]


def detect_format(full_name, email):
    """Return the PATTERNS key that produced `email` for this name, or None.

    Checks nickname variants too, so a confirmed `bob.smith@` for "Robert Smith"
    is still recognised as the `first.last` company format.
    """
    first, surnames = _name_parts(full_name)
    if not first or not surnames:
        return None
    target = email.split("@", 1)[0].strip().lower()
    for f in _ordered_variants(first):
        for last in surnames:
            for name, build in PATTERNS.items():
                if build(f, last) == target:
                    return name
    return None


def email_for_format(full_name, company_domain, fmt):
    """Build the address for a known company format using the primary name.

    Uses the last-token surname; surname position isn't encoded in the format,
    so this is a best-effort fallback for catch-all domains only.
    """
    first, surnames = _name_parts(full_name)
    if not first or not surnames or fmt not in PATTERNS:
        return None
    return f"{PATTERNS[fmt](first, surnames[0])}@{company_domain}"


def email_rank(full_name, email):
    """Lower is better — ranks a confirmed email by how common its format is."""
    return _FORMAT_RANK.get(detect_format(full_name, email), len(_FORMAT_RANK) + 1)


def catchall_probe(company_domain):
    """A deterministic address that cannot belong to a real person.

    If TrueList returns email_ok for this, the domain accepts everything
    (catch-all) and real guesses there cannot be confirmed by SMTP.
    """
    tag = hashlib.sha1(company_domain.encode("utf-8")).hexdigest()[:14]
    return f"zz{tag}qx@{company_domain}"


if __name__ == "__main__":
    for name in ("Juan Valencia Tello", "William Rivera Forero"):
        print(f"--- {name} ---")
        for i, email in enumerate(smart_email_generator(name, "fincomercio.com", 30), 1):
            print(f"{i:2}. {email}")
