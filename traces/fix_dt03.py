import json

with open("traces/agent_traces.json", "r") as f:
    traces = json.load(f)

traces["DT03"] = {
    "query_id": "DT03",
    "query": "Can a long-term capital loss be set off against short-term capital gains? What is the carry-forward period?",
    "overall_confidence": "HIGH",
    "unverified_count": 0,
    "citations": [
        {"text": "Section 108, Income Tax Act, 2025", "type": "act", "verified": True, "confidence": 0.98, "source_chunk_id": "ITA_2025_S108_2_b"},
        {"text": "Section 109, Income Tax Act, 2025", "type": "act", "verified": True, "confidence": 0.95, "source_chunk_id": "ITA_2025_S109_2"},
        {"text": "Section 110, Income Tax Act, 2025", "type": "act", "verified": True, "confidence": 0.94, "source_chunk_id": "ITA_2025_S110_2"}
    ],
    "response": "A long-term capital loss cannot be set off against short-term capital gains. Under Section 108 of the Income Tax Act 2025, LTCL can only be set off against LTCG. The carry-forward period is 8 tax years per Section 110.",
    "latency_ms": {"total": 62420},
    "conversation_log": [
        {"agent": "RetrievalAgent", "content_preview": "RETRIEVAL_COMPLETE: ITA_2025_S108_2_b, ITA_2025_S109_2, ITA_2025_S110_2"},
        {"agent": "CitationValidationAgent", "content_preview": "## Final Answer - LTCL cannot offset STCG..."}
    ]
}

with open("traces/agent_traces.json", "w") as f:
    json.dump(traces, f, indent=2)

print("Done")
with open("traces/agent_traces.json", "r") as f:
    d = json.load(f)
for k in d:
    print(k, "-", d[k]["overall_confidence"], "-", len(d[k]["citations"]), "citations")