from trendintel.processing.topics import build_topics, slugify


def terms(*names):
    return {n: n.title() if n != "openai" else "OpenAI" for n in names}


def test_jaccard_merge_and_label_selection():
    docs = [
        terms("openai", "gpt-5"),
        terms("openai", "gpt-5"),
        terms("openai"),
        terms("tesla"),
        terms("tesla"),
        terms("lonely"),
    ]
    topics = build_topics(docs, min_df=2)
    by_slug = {t.slug: t for t in topics}
    assert set(by_slug) == {"openai", "tesla"}
    assert by_slug["openai"].article_indices == (0, 1, 2)
    assert by_slug["openai"].label == "OpenAI"
    assert "gpt-5" in by_slug["openai"].terms


def test_unrelated_terms_not_merged():
    docs = [terms("alpha", "beta"), terms("alpha"), terms("alpha"), terms("alpha"), terms("beta"), terms("beta"), terms("beta")]
    slugs = {t.slug for t in build_topics(docs, min_df=2)}
    assert slugs == {"alpha", "beta"}


def test_containment_merge_when_general_term_not_too_common():
    # "apple" in 6 docs, "apple vision" in 3 of them: Jaccard 0.5 but containment 1.0 and ratio 2.0 -> merge
    docs = [terms("apple", "apple vision")] * 3 + [terms("apple")] * 3
    topics = build_topics(docs, min_df=2)
    assert len(topics) == 1 and topics[0].slug == "apple"


def test_containment_not_merged_when_general_term_far_more_common():
    docs = [terms("apple", "apple vision")] * 3 + [terms("apple")] * 5
    slugs = {t.slug for t in build_topics(docs, min_df=2)}
    assert slugs == {"apple", "apple-vision"}


def test_min_df_filters_rare_terms():
    assert build_topics([terms("solo")], min_df=2) == []


def test_slugify():
    assert slugify("GPT-5") == "gpt-5"
    assert slugify("C++") == "c-plus-plus"
    assert slugify("Sam Altman!") == "sam-altman"
