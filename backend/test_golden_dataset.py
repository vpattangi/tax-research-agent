import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents.orchestrator import run_pipeline

GOLDEN_QUERIES = [
    {"id": "DT-01", "complexity": "Foundational", "query": "Is exemption under Section 54 available if the new residential property is purchased before the date of sale of the original property? Cite the relevant proviso and any CBDT clarification."},
    {"id": "DT-02", "complexity": "Foundational", "query": "What are the conditions for claiming deduction under Section 80C? List qualifying instruments and the investment ceiling. Has the ceiling changed across Finance Acts?"},
    {"id": "DT-03", "complexity": "Intermediate", "query": "Explain the set-off and carry-forward rules for capital losses. Can a long-term capital loss be set off against short-term capital gains? What is the carry-forward period?"},
    {"id": "DT-04", "complexity": "Intermediate", "query": "What is the difference between Section 54 and Section 54F? A taxpayer sells a plot of land and wants to claim exemption on purchase of a new residential house. Which section applies and what are the additional conditions?"},
    {"id": "DT-05", "complexity": "Advanced", "query": "LCo. gave a loan to BCo. on 2 April 2023 and the same was repaid on 6 June 2023. BCo. is a shareholder of LCo. and LCo. has sufficient accumulated reserves. As on 31 March 2024, no loan is outstanding. Whether deemed dividend provisions under Section 2(22)(e) will apply? Explain with the help of relevant case laws."},
    {"id": "DT-06", "complexity": "Advanced", "query": "A company pays management fees to its foreign parent at 15% of revenue. The Assessing Officer invokes Section 40A(2)(b) to disallow the excess. What is the standard for determining fair market value of such services under Section 40A(2)? How does this interact with Transfer Pricing provisions under Chapter X?"},
    {"id": "DT-07", "complexity": "Advanced", "query": "An individual receives a cash gift of Rs. 8 lakhs from a non-relative friend. He also receives a plot of land (stamp duty value Rs. 12 lakhs, consideration paid Rs. 5 lakhs) from another friend. Compute the total income taxable under Section 56(2)(x) and explain each applicable clause."},
    {"id": "DT-08", "complexity": "Advanced", "query": "Explain the concept of substantial question of law under Section 260A. Can an appeal lie to the High Court on a question of fact? What is the difference between an appeal under Section 260A and a writ under Article 226 of the Constitution in the context of income tax disputes?"},
    {"id": "DT-09", "complexity": "Advanced", "query": "A private limited company has been making losses for 5 consecutive years. The Assessing Officer proposes to invoke Section 68 to treat unexplained cash credits in the books as income. What is the burden of proof under Section 68 and what must the assessee demonstrate? Cite relevant Supreme Court and High Court precedents."},
]

DT10_TURNS = [
    "Explain the reassessment framework under Section 147.",
    "What is the time limit for issuing notice under Section 148 after the Finance Act 2021 amendments? Is there a distinction between escaped income above and below Rs. 50 lakhs?",
    "Can the assessee challenge the validity of the reassessment notice at the threshold without waiting for the assessment to be completed? Cite the Supreme Court ruling in this regard."
]

def run_single(q):
    start = time.time()
    result = run_pipeline(q["query"], session_id="golden_" + q["id"])
    elapsed = round((time.time() - start) * 1000)
    unverified = result.get("unverified_count", 0)
    total_cites = len(result.get("citations", []))
    if total_cites > 0 and unverified == 0:
        status = "VERIFIED"
    elif unverified > 0:
        status = "PARTIAL"
    else:
        status = "NO_CITATIONS"
    return {
        "id": q["id"],
        "complexity": q["complexity"],
        "answer_preview": result["response"][:300],
        "citations_returned": total_cites,
        "verification_status": status,
        "overall_confidence": result["overall_confidence"],
        "unverified_count": unverified,
        "latency_ms_total": elapsed,
        "latency_ms_retrieval": round(result["latency_ms"].get("retrieval", 0)),
    }

def run_dt10():
    print("\nRunning DT-10 Multi-Turn...")
    session_id = "golden_DT10"
    turns = []
    for i, q in enumerate(DT10_TURNS):
        print(f"Turn {i+1}: {q[:60]}...")
        start = time.time()
        result = run_pipeline(q, session_id=session_id)
        elapsed = round((time.time() - start) * 1000)
        turns.append({"turn": i+1, "query": q, "latency_ms": elapsed, "confidence": result["overall_confidence"]})
        print(f"Turn {i+1} done: {elapsed}ms")
    return turns

def main():
    print("=" * 60)
    print("GOLDEN DATASET EVALUATION")
    print("=" * 60)
    all_results = []
    all_latencies = []

    for q in GOLDEN_QUERIES:
        print(f"\nRunning {q['id']} ({q['complexity']})...")
        row = run_single(q)
        all_results.append(row)
        all_latencies.append(row["latency_ms_total"])
        print(f"{q['id']}: {row['verification_status']} | {row['overall_confidence']} | {row['latency_ms_total']}ms")

    dt10_turns = run_dt10()
    for t in dt10_turns:
        all_latencies.append(t["latency_ms"])

    sorted_l = sorted(all_latencies)
    p50 = sorted_l[len(sorted_l) // 2]
    p95 = sorted_l[int(len(sorted_l) * 0.95)]

    print("\n" + "=" * 60)
    print("RESULTS TABLE")
    print("=" * 60)
    print(f"{'ID':<8} {'Status':<12} {'Conf':<8} {'Cites':<7} {'Latency(ms)'}")
    print("-" * 50)
    for r in all_results:
        print(f"{r['id']:<8} {r['verification_status']:<12} {r['overall_confidence']:<8} {r['citations_returned']:<7} {r['latency_ms_total']}")
    print(f"\nDT-10: Multi-Turn (3 turns)")
    for t in dt10_turns:
        print(f"  Turn {t['turn']}: {t['latency_ms']}ms | {t['confidence']}")
    print(f"\nP50: {p50}ms")
    print(f"P95: {p95}ms")

    os.makedirs("traces", exist_ok=True)
    with open("traces/golden_dataset_results.json", "w") as f:
        json.dump({"results": all_results, "dt10": dt10_turns, "p50": p50, "p95": p95}, f, indent=2)
    print("\nSaved to traces/golden_dataset_results.json")

if __name__ == "__main__":
    main()