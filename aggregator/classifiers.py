from aggregator.taxonomy import NEWS_TOPIC_KEYWORDS


def classify_news_topic(text):
    text = (text or "").lower()

    scores = {}

    for topic, keywords in NEWS_TOPIC_KEYWORDS.items():
        score = 0

        for keyword in keywords:
            if keyword.lower() in text:
                score += 1

        if score:
            scores[topic] = score

    if not scores:
        return "general", []

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    primary_topic = ranked[0][0]
    secondary_topics = [topic for topic, score in ranked[1:4]]

    return primary_topic, secondary_topics


def classify_recruiting_body(source_name, text):
    combined = f"{source_name} {text}".lower()

    if "tnpsc" in combined:
        return "tnpsc"

    if "medical recruitment board" in combined or "mrb" in combined:
        return "mrb"

    if "teachers recruitment board" in combined or "trb" in combined:
        return "trb"

    if "police" in combined or "uniformed services" in combined or "tnusrb" in combined:
        return "tnusrb"

    if "apprentice" in combined or "apprenticeship" in combined:
        return "apprenticeship"

    if "railway" in combined or "bank" in combined or "psu" in combined:
        return "psu_bank_railway"

    if "government" in combined or "govt" in combined:
        return "tn_govt_department"

    if "private" in combined:
        return "private_verified"

    return "unknown"


def classify_qualification(text):
    text = (text or "").lower()

    if "ph.d" in text or "phd" in text or "doctorate" in text:
        return "phd"

    if "mbbs" in text or "b.e" in text or "b.tech" in text or "b.sc nursing" in text:
        return "professional"

    if "post graduate" in text or "postgraduate" in text or "master" in text or "m.sc" in text or "m.a" in text:
        return "postgraduate"

    if "degree" in text or "graduate" in text or "b.a" in text or "b.sc" in text or "b.com" in text:
        return "graduate"

    if "iti" in text or "diploma" in text or "polytechnic" in text:
        return "iti_diploma"

    if "12th" in text or "higher secondary" in text or "+2" in text:
        return "12th_pass"

    if "10th" in text or "sslc" in text or "secondary school" in text:
        return "10th_pass"

    return "unknown"