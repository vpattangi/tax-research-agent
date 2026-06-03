import json, sys, os, asyncio
sys.path.insert(0, '.')
from backend.agents.orchestrator import run_pipeline_async
import uuid

queries = {
    "DT05": "LCo gave a loan to BCo on 2 April 2023 and the same was repaid on 6 June 2023. BCo is a shareholder of LCo and LCo has sufficient accumulated reserves. As on 31 March 2024 no loan is outstanding. Whether deemed dividend provisions under Section 2(22)(e) will apply?",
    "DT02": "What are the conditions for claiming deduction under Section 80C? List qualifying instruments and the investment ceiling.",
    "DT03": "Can a long-term capital loss be set off against short-term capital gains? What is the carry-forward period?"
}

async def main():
    traces = {}
    for qid, query in queries.items():
        print(f"Running {qid}...")
        session_id = str(uuid.uuid4())
        result = await run_pipeline_async(query, session_id)
        traces[qid] = {
            "query_id": qid,
            "query": query,
            "session_id": session_id,
            "response": result.get("response", ""),
            "citations": result.get("citations", []),
            "overall_confidence": result.get("overall_confidence", ""),
            "unverified_count": result.get("unverified_count", 0),
            "latency_ms": result.get("latency_ms", {}),
            "conversation_log": result.get("conversation_log", [])
        }
        print(f"{qid} done - {result.get('overall_confidence')} confidence")

    with open("traces/agent_traces.json", "w") as f:
        json.dump(traces, f, indent=2)
    print("Saved to traces/agent_traces.json")

asyncio.run(main())