"""Golden Q&A set for RAGAS evaluation (S3-T1).

Each entry: query, airline scope, ground-truth reference answer (used for
answer-correctness style checks), and the doc_id(s) the answer should be
grounded in (used to sanity-check retrieval separately from RAGAS scores).
`expect_refusal=True` entries are out-of-scope queries that must trigger the
confidence-based refusal path (S3-T3) rather than a hallucinated answer.
"""

GOLDEN_QA = [
    {
        "query": "What is the carry-on baggage weight limit on IndiGo?",
        "airline": "indigo",
        "reference": (
            "One piece of hand baggage up to 7 kg, dimensions 55x35x25 cm, plus one "
            "small personal item, provided combined weight stays within 7 kg."
        ),
        "doc_ids": ["BAG-001"],
    },
    {
        "query": "How much does IndiGo charge for a gate-checked oversized carry-on bag?",
        "airline": "indigo",
        "reference": "A gate-check fee of ₹500 applies for domestic sectors.",
        "doc_ids": ["BAG-001"],
    },
    {
        "query": "What is the process for filing a lost baggage claim with IndiGo?",
        "airline": "indigo",
        "reference": "Passengers file a PIR (Property Irregularity Report) and follow IndiGo's claims process.",
        "doc_ids": ["BAG-003"],
    },
    {
        "query": "Is there a fee for airport check-in on IndiGo?",
        "airline": "indigo",
        "reference": "IndiGo charges an airport check-in fee, with certain waivers described in the check-in fee policy.",
        "doc_ids": ["CHK-002"],
    },
    {
        "query": "What are the rules for booking an unaccompanied minor on IndiGo?",
        "airline": "indigo",
        "reference": "IndiGo has age-based rules and a dedicated procedure for unaccompanied minor check-in and travel.",
        "doc_ids": ["CHK-003", "SPC-002"],
    },
    {
        "query": "What fare change fees apply if I change the date on my IndiGo ticket?",
        "airline": "indigo",
        "reference": "A date-change fee applies per IndiGo's date and name change fee schedule.",
        "doc_ids": ["FAR-002"],
    },
    {
        "query": "What is IndiGo's cancellation policy by fare class?",
        "airline": "indigo",
        "reference": "Cancellation charges vary by fare class per IndiGo's cancellation policy.",
        "doc_ids": ["CAN-001"],
    },
    {
        "query": "How long is an IndiGo credit shell valid and how do I redeem it?",
        "airline": "indigo",
        "reference": "Credit shells have a defined validity window and redemption rules described in IndiGo's credit shell policy.",
        "doc_ids": ["CAN-002"],
    },
    {
        "query": "How long does an IndiGo refund take to process by payment method?",
        "airline": "indigo",
        "reference": "Refund timelines vary by payment method per IndiGo's refund processing policy.",
        "doc_ids": ["CAN-003"],
    },
    {
        "query": "My IndiGo flight was cancelled 3 days before departure — what am I entitled to under DGCA rules?",
        "airline": "indigo",
        "reference": "DGCA passenger rights rules define compensation/entitlements for cancellations depending on notice period.",
        "doc_ids": ["DEL-001"],
    },
    {
        "query": "How does IndiGo communicate flight delays to passengers?",
        "airline": "indigo",
        "reference": "IndiGo follows a defined delay communication protocol to notify passengers.",
        "doc_ids": ["DEL-002"],
    },
    {
        "query": "What compensation applies for a tarmac delay or denied boarding on IndiGo?",
        "airline": "indigo",
        "reference": "Tarmac delay and denied boarding compensation rules apply per DGCA-aligned IndiGo policy.",
        "doc_ids": ["DEL-003"],
    },
    {
        "query": "What are the tier benefits of IndiGo's BluChip loyalty programme?",
        "airline": "indigo",
        "reference": "BluChip has a tier structure with benefits described in the loyalty programme policy.",
        "doc_ids": ["LYL-001"],
    },
    {
        "query": "How do I earn and redeem 6E Rewards points?",
        "airline": "indigo",
        "reference": "6E Rewards points are earned and redeemed per IndiGo's loyalty points policy.",
        "doc_ids": ["LYL-002"],
    },
    {
        "query": "What wheelchair assistance categories does IndiGo offer?",
        "airline": "indigo",
        "reference": "IndiGo offers WCHR, WCHS, and WCHC wheelchair assistance categories.",
        "doc_ids": ["SPC-001"],
    },
    {
        "query": "Can I carry a lithium power bank over 20000mAh on IndiGo?",
        "airline": "indigo",
        "reference": "Lithium battery power banks are subject to capacity limits under cabin baggage / BCAS security rules.",
        "doc_ids": ["BAG-001"],
    },
    {
        "query": "What is the group booking policy for 10 or more passengers on IndiGo?",
        "airline": "indigo",
        "reference": "IndiGo has a dedicated group booking policy for bookings of 10+ passengers.",
        "doc_ids": ["FAR-003"],
    },
    {
        "query": "What baggage allowance comes with IndiGo's 6E Prime fare?",
        "airline": "indigo",
        "reference": "6E Prime includes carry-on plus checked baggage allowance per the fare class policy.",
        "doc_ids": ["BAG-002", "FAR-001"],
    },
    {
        "query": "What is Air India's baggage policy?",
        "airline": "air_india",
        "reference": "Air India's baggage allowance and fees are described in its baggage policy documents.",
        "doc_ids": [],
    },
    {
        "query": "What is SpiceJet's refund policy for cancelled tickets?",
        "airline": "spicejet",
        "reference": "SpiceJet's refund timelines and rules are described in its cancellation/refund policy documents.",
        "doc_ids": [],
    },
    # Out-of-scope — must trigger refusal, not a hallucinated answer.
    {
        "query": "What is the capital of France?",
        "airline": "all",
        "reference": "Out of scope for an airline policy assistant.",
        "doc_ids": [],
        "expect_refusal": True,
    },
    {
        "query": "Can you recommend a good stock to invest in this year?",
        "airline": "all",
        "reference": "Out of scope for an airline policy assistant.",
        "doc_ids": [],
        "expect_refusal": True,
    },
    {
        "query": "What's the weather like in Mumbai today?",
        "airline": "all",
        "reference": "Out of scope for an airline policy assistant.",
        "doc_ids": [],
        "expect_refusal": True,
    },
]
