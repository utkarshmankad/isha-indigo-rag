"""Audit the bundled static corpus for stale/missing provenance (Weeks 3-4,
item 4).

The bundled corpus (`data/*.py`) predates authoritative source URLs and
effective/verified dates as fields — every document only ever carried
`last_updated`. This script does not fabricate that missing data (URLs and
dates are policy/product facts, not something to guess); it reports exactly
what's missing or old so a human can go fill it in.

Usage: python scripts/audit_bundled_corpus.py [--stale-days N] [--json]

Read-only: does not modify data/*.py or touch Qdrant.
"""
import argparse
import json
import sys
from datetime import date, datetime

sys.path.insert(0, ".")

DEFAULT_STALE_DAYS = 365


def _load_all_documents() -> list[dict]:
    from data.air_india_documents import DOCUMENTS as AI_DOCS
    from data.dgca_documents import DOCUMENTS as DGCA_DOCS
    from data.indigo_documents import DOCUMENTS as INDIGO_DOCS
    from data.spicejet_documents import DOCUMENTS as SJ_DOCS

    return INDIGO_DOCS + AI_DOCS + SJ_DOCS + DGCA_DOCS


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def audit(documents: list[dict], *, today: date, stale_days: int = DEFAULT_STALE_DAYS) -> dict:
    findings = []
    for doc in documents:
        last_updated = _parse_date(doc.get("last_updated"))
        age_days = (today - last_updated).days if last_updated else None
        findings.append({
            "doc_id": doc["id"],
            "title": doc["title"],
            "airline": doc.get("airline", "indigo"),
            "last_updated": doc.get("last_updated"),
            "age_days": age_days,
            "stale": age_days is not None and age_days > stale_days,
            "unparseable_last_updated": last_updated is None and doc.get("last_updated") is not None,
            "has_source_url": bool(doc.get("source_url")),
            "has_effective_date": bool(doc.get("effective_date")),
            "has_verified_date": bool(doc.get("verified_date")),
        })

    return {
        "audited_at": today.isoformat(),
        "stale_threshold_days": stale_days,
        "total_documents": len(findings),
        "missing_source_url": sum(1 for f in findings if not f["has_source_url"]),
        "missing_effective_date": sum(1 for f in findings if not f["has_effective_date"]),
        "missing_verified_date": sum(1 for f in findings if not f["has_verified_date"]),
        "stale_by_last_updated": sum(1 for f in findings if f["stale"]),
        "unparseable_last_updated": sum(1 for f in findings if f["unparseable_last_updated"]),
        "documents": findings,
    }


def _print_report(report: dict) -> None:
    print(f"Bundled corpus audit — {report['audited_at']} (stale threshold: {report['stale_threshold_days']} days)")
    print(f"  Total documents:            {report['total_documents']}")
    print(f"  Missing source_url:         {report['missing_source_url']}")
    print(f"  Missing effective_date:     {report['missing_effective_date']}")
    print(f"  Missing verified_date:      {report['missing_verified_date']}")
    print(f"  Stale (by last_updated):    {report['stale_by_last_updated']}")
    print(f"  Unparseable last_updated:   {report['unparseable_last_updated']}")
    if report["stale_by_last_updated"]:
        print("\nStale documents:")
        for doc in report["documents"]:
            if doc["stale"]:
                print(f"  {doc['doc_id']:12s} {doc['airline']:10s} last_updated={doc['last_updated']}"
                      f" ({doc['age_days']}d ago)  {doc['title']}")
    print(
        "\nNote: source_url/effective_date/verified_date are not fabricated here — "
        "the bundled corpus schema simply doesn't carry them yet. Filling them in "
        "is a content/product decision, not something this script can do safely."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON instead of a table")
    args = parser.parse_args()

    documents = _load_all_documents()
    report = audit(documents, today=date.today(), stale_days=args.stale_days)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)


if __name__ == "__main__":
    main()
