NEWS_TOPIC_CHOICES = [
    ("politics", "Politics"),
    ("government_policy", "Government & Policy"),
    ("assembly_watch", "Assembly Watch"),
    ("economy_welfare", "Economy & Welfare"),
    ("education", "Education"),
    ("health", "Health"),
    ("law_order", "Law & Order"),
    ("infrastructure_transport", "Infrastructure & Transport"),
    ("agriculture_farmers", "Agriculture & Farmers"),
    ("cinema_culture", "Cinema & Culture"),
    ("district_local", "District & Local Governance"),
    ("jobs_employment", "Jobs & Employment"),
    ("general", "General"),
]

NEWS_TOPIC_LABELS = dict(NEWS_TOPIC_CHOICES)


NEWS_TOPIC_KEYWORDS = {
    "politics": [
        "dmk", "aiadmk", "bjp", "tvk", "ntk", "vck", "pmk",
        "stalin", "eps", "vijay", "annamalai", "seeman",
        "election", "alliance", "opposition", "party",
        "திமுக", "அதிமுக", "பாஜக", "தவெக", "நாம் தமிழர்",
    ],
    "government_policy": [
        "chief minister", "deputy chief minister", "minister",
        "scheme", "welfare", "policy", "government order",
        "department", "secretariat", "announcement",
        "முதல்வர்", "துணை முதல்வர்", "அமைச்சர்", "திட்டம்", "அரசு",
    ],
    "assembly_watch": [
        "assembly", "legislative assembly", "question hour",
        "bill", "debate", "resolution", "speaker",
        "சட்டசபை", "சட்டமன்றம்", "மசோதா", "விவாதம்",
    ],
    "economy_welfare": [
        "investment", "industry", "factory", "employment",
        "welfare", "subsidy", "ration", "price", "tax",
        "முதலீடு", "தொழில்", "வேலைவாய்ப்பு", "நலத்திட்டம்",
    ],
    "education": [
        "school", "college", "student", "teacher", "exam",
        "university", "neet", "education", "syllabus",
        "பள்ளி", "கல்லூரி", "மாணவர்", "ஆசிரியர்", "தேர்வு",
    ],
    "health": [
        "hospital", "doctor", "nurse", "health", "disease",
        "medical", "phc", "medicine",
        "மருத்துவம்", "மருத்துவர்", "மருத்துவமனை", "சுகாதாரம்",
    ],
    "law_order": [
        "police", "court", "crime", "arrest", "murder",
        "case", "violence", "protest", "fir",
        "காவல்", "குற்றம்", "கைது", "நீதிமன்றம்", "வழக்கு",
    ],
    "infrastructure_transport": [
        "road", "bridge", "bus", "train", "metro", "airport",
        "highway", "water supply", "drainage", "power cut",
        "சாலை", "பாலம்", "பேருந்து", "ரயில்", "மின்தடை",
    ],
    "agriculture_farmers": [
        "farmer", "crop", "paddy", "sugarcane", "rain",
        "irrigation", "water release", "delta", "fertilizer",
        "விவசாயி", "நெல்", "மழை", "நீர்ப்பாசனம்", "டெல்டா",
    ],
    "cinema_culture": [
        "cinema", "actor", "film", "movie", "director",
        "vijay", "ajith", "rajinikanth", "kamal",
        "சினிமா", "நடிகர்", "திரைப்படம்", "விஜய்", "ரஜினி",
    ],
    "district_local": [
        "collector", "municipality", "corporation", "panchayat",
        "district", "local body", "village", "town",
        "மாவட்ட", "ஆட்சியர்", "நகராட்சி", "ஊராட்சி",
    ],
    "jobs_employment": [
        "job", "jobs", "recruitment", "vacancy", "tnpsc",
        "mrb", "trb", "employment", "apprentice",
        "வேலை", "வேலைவாய்ப்பு", "பணி", "ஆட்சேர்ப்பு",
    ],
}


JOB_RECRUITING_BODY_CHOICES = [
    ("tnpsc", "TNPSC"),
    ("mrb", "Medical Recruitment Board"),
    ("trb", "Teachers Recruitment Board"),
    ("tnusrb", "Police / Uniformed Services"),
    ("tn_govt_department", "Tamil Nadu Government Department"),
    ("central_govt", "Central Government"),
    ("psu_bank_railway", "PSU / Bank / Railway"),
    ("apprenticeship", "Apprenticeship"),
    ("private_verified", "Verified Private Jobs"),
    ("unknown", "Unknown"),
]

JOB_QUALIFICATION_CHOICES = [
    ("below_10th", "Below 10th"),
    ("10th_pass", "10th Pass"),
    ("12th_pass", "12th Pass"),
    ("iti_diploma", "ITI / Diploma"),
    ("graduate", "Graduate"),
    ("postgraduate", "Postgraduate"),
    ("professional", "Professional Degree"),
    ("phd", "PhD"),
    ("unknown", "Unknown"),
]