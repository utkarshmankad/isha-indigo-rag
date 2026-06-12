TOOL_REGISTRY: dict[str, dict] = {
    "baggage": {
        "keywords": [
            "baggage", "luggage", "carry-on", "cabin bag", "checked bag",
            "allowance", "kg", "kilo", "excess baggage", "overweight",
            "pir", "oversized", "hand baggage",
        ],
        "description": "Carry-on and checked baggage allowances, excess fees, and lost/damaged baggage (PIR).",
    },
    "check_in": {
        "keywords": [
            "check-in", "check in", "web check-in", "online check-in",
            "boarding pass", "seat selection", "kiosk", "airport counter",
            "advance seat", "document check", "self-service", "boarding",
        ],
        "description": "Web, kiosk, and airport counter check-in procedures and seat selection.",
    },
    "fares_and_ticketing": {
        "keywords": [
            "fare", "ticket", "6e prime", "flexi", "super6e",
            "booking", "upgrade", "name change", "pnr", "itinerary",
            "reschedule", "fare class",
        ],
        "description": "Fare types (6E Prime, Flexi), ticket booking, name changes, and upgrades.",
    },
    "cancellations_and_refunds": {
        "keywords": [
            "refund", "cancel", "cancellation", "credit shell",
            "no-show", "waiver", "penalty", "voucher", "reimburse",
            "partial refund", "full refund",
        ],
        "description": "Ticket cancellation policies, refund timelines, and credit shell rules.",
    },
    "flight_delays_and_cancellations": {
        "keywords": [
            "delay", "delayed", "dgca", "compensation", "stranded",
            "diverted", "tarmac", "meal voucher", "hotel accommodation",
            "rebooking", "passenger rights", "flight disruption",
        ],
        "description": "DGCA passenger rights, compensation, and rebooking for delayed or cancelled flights.",
    },
    "loyalty_bluchip": {
        "keywords": [
            "bluchip", "blu chip", "tier", "gold member", "platinum member",
            "points", "earn points", "redeem points", "lounge access",
            "priority boarding", "status", "6e rewards", "loyalty",
        ],
        "description": "BluChip loyalty programme — tiers, points earning/redemption, and member benefits.",
    },
    "special_assistance": {
        "keywords": [
            "wheelchair", "wchr", "wchs", "wchc", "oxygen",
            "stretcher", "cpap", "unaccompanied minor", "infant",
            "bassinet", "medical device", "disability", "pwd", "deaf", "blind",
        ],
        "description": "Wheelchair (WCHR/WCHS/WCHC), medical equipment, unaccompanied minors, and accessibility.",
    },
    "6e_addons_and_services": {
        "keywords": [
            "add-on", "6e add", "meal", "snack", "xl seat",
            "fast forward", "comfort kit", "extra legroom", "pre-order",
            "in-flight service", "add on", "seat upgrade",
        ],
        "description": "Optional add-ons: meals, seat upgrades, Fast Forward, and in-flight services.",
    },
    "international_travel": {
        "keywords": [
            "international", "passport", "visa", "immigration", "customs",
            "transit", "layover", "codeshare", "overseas", "duty-free",
            "iata", "international route", "foreign",
        ],
        "description": "International travel requirements — passports, visas, customs, and transit rules.",
    },
    "safety_and_security": {
        "keywords": [
            "dangerous goods", "prohibited item", "lithium battery", "hazmat",
            "vape", "e-cigarette", "firearm", "explosive", "aerosol",
            "flammable", "bcas", "restricted item", "dg",
        ],
        "description": "Dangerous goods, prohibited items, BCAS security rules, and lithium battery restrictions.",
    },
}


def score_tools(query: str, top_k: int = 2) -> list[str]:
    q = query.lower()

    scores: dict[str, float] = {}
    for tool, config in TOOL_REGISTRY.items():
        keywords = config["keywords"]
        matches = sum(1 for kw in keywords if kw.lower() in q)
        scores[tool] = matches / len(keywords) if matches else 0.0

    print("[tool_selector] scores:", {t: f"{s:.4f}" for t, s in scores.items() if s > 0})

    nonzero = [(t, s) for t, s in scores.items() if s > 0]
    if not nonzero:
        print("[tool_selector] no keyword match — returning all tools (fallback)")
        return list(TOOL_REGISTRY.keys())

    ranked = sorted(nonzero, key=lambda x: x[1], reverse=True)
    return [t for t, _ in ranked[:top_k]]


def route_query(query: str, top_k: int = 2) -> dict:
    selected = score_tools(query, top_k=top_k)

    if len(selected) == len(TOOL_REGISTRY):
        reasoning = "No category-specific keywords matched — searching all tools."
        search_all = True
    else:
        descs = [TOOL_REGISTRY[t]["description"] for t in selected]
        reasoning = "Matched: " + " | ".join(
            f"{t} ({TOOL_REGISTRY[t]['description']})" for t in selected
        )
        search_all = False

    return {
        "selected_tools": selected,
        "search_all": search_all,
        "reasoning": reasoning,
    }


if __name__ == "__main__":
    queries = [
        "How many kg can I carry in cabin baggage?",
        "Can I get a refund on a cancelled 6E Prime ticket?",
        "I am a BluChip Gold member, do I get lounge access?",
        "IndiGo cancelled my flight, what compensation under DGCA?",
        "Can I carry my CPAP machine on board?",
        "What is the excess baggage fee on international routes?",
        "Can I bring a vape in checked baggage?",
    ]

    for q in queries:
        print(f"\nQ: {q}")
        result = route_query(q)
        print(f"   tools    : {result['selected_tools']}")
        print(f"   reasoning: {result['reasoning']}")
