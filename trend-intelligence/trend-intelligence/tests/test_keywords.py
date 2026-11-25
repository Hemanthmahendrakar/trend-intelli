from trendintel.processing.keywords import extract_terms, normalize_token


def test_extracts_unigrams_and_bigrams_and_skips_stopwords():
    terms = extract_terms("OpenAI launches GPT-5 for enterprise customers")
    assert "openai" in terms and terms["openai"] == "OpenAI"
    assert "gpt-5" in terms
    assert "enterprise customer" in terms  # plural normalised
    assert "launch" not in terms and "launches" not in terms
    assert "openai launches" not in terms  # no phrase across a stop-word


def test_no_phrases_across_punctuation():
    terms = extract_terms("Apple unveils chips, Google counters")
    assert "chip google" not in terms
    assert "google counter" in terms or "google" in terms


def test_short_allowed_terms():
    terms = extract_terms("AI chips surge")
    assert "ai" in terms and "ai chip" in terms


def test_pure_numbers_and_short_words_ignored_as_unigrams():
    terms = extract_terms("2025 is the year of cat")
    assert "2025" not in terms and "cat" not in terms


def test_possessive_and_plural_normalisation():
    assert normalize_token("Google's") == "google"
    assert normalize_token("chips") == "chip"
    assert normalize_token("status") == "status"
    assert normalize_token("class") == "class"
