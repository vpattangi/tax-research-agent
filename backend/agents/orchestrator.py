import asyncio
import os
import json
import time
import uuid
from dotenv import load_dotenv
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient
from .retrieval_tool import retrieve_chunks
from .citation_tool import validate_citations

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
session_store = {}


def retrieve_tax_law(query: str) -> str:
    try:
        result = retrieve_chunks(query, top_k=5)
        return json.dumps(result)
    except Exception as e:
        print(f"[RetrievalTool] Error: {e}")
        return json.dumps({"query": query, "chunks": [], "error": str(e)})


def verify_citations(response_text: str) -> str:
    try:
        return validate_citations(response_text)
    except Exception as e:
        print(f"[CitationTool] Error: {e}")
        return json.dumps({"citations": [], "overall_confidence": "LOW", "unverified_count": 0})

def get_model_client():
    return OpenAIChatCompletionClient(
        model="llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY"),
        model_capabilities={
            "vision": False,
            "function_calling": True,
            "json_output": False,
        }
    )


def detect_followup(query: str) -> bool:
    phrases = [
        "this section", "that ruling", "above case", "the same section",
        "mentioned above", "you said", "as discussed", "from above",
        "the section you mentioned", "this case", "that circular",
        "the above", "previous answer", "as stated"
    ]
    return any(p in query.lower() for p in phrases)


def enrich_query_with_context(query: str, session: dict) -> str:
    if not session["history"]:
        return query
    prior = session["history"][-3:]
    ctx = []
    for h in prior:
        ctx.append("[Turn " + str(h["turn"]) + "]")
        ctx.append("Q: " + h["query"])
        ctx.append("A: " + h["answer_summary"])
    context = "\n".join(ctx)
    return "[Prior context:\n" + context + "\n]\n\nCurrent question: " + query


def build_agent_team():
    model_client = get_model_client()

    user_proxy = UserProxyAgent(name="UserProxy")

    retrieval_agent = AssistantAgent(
        name="RetrievalAgent",
        model_client=model_client,
        tools=[retrieve_tax_law],
        system_message=(
            "You are the RetrievalAgent. Your ONLY job is retrieval. "
            "Do NOT answer questions. Do NOT synthesize. "
            "When you receive a tax query: "
            "1. Call the retrieve_tax_law tool with the exact query. "
            "2. Report chunk IDs and section numbers found. "
            "3. Output RETRIEVAL_COMPLETE then the full JSON from the tool."
        ),
        reflect_on_tool_use=True,
    )

    citation_agent = AssistantAgent(
        name="CitationValidationAgent",
        model_client=model_client,
        tools=[verify_citations],
        system_message=(
            "You are the CitationValidationAgent — the quality gate and synthesizer. "
            "You will receive retrieved chunks from RetrievalAgent. "
            "Synthesize a structured answer using ONLY the text from those chunks. "
            "Never use training knowledge. If chunks do not contain the answer, say so. "
            "Format EXACTLY as:\n"
            "## Final Answer\n"
            "[2-4 sentence direct answer based ONLY on retrieved chunks]\n"
            "## Legal Reasoning\n"
            "- Statutory Basis: [quote the exact section from chunks, e.g. 'Section 80C(1)...']\n"
            "- Regulatory Guidance: [from chunks only, or 'None retrieved']\n"
            "- Judicial Position: [from chunks only, or 'None retrieved']\n"
            "## Supporting References\n"
            "[list each chunk_id and source]\n"
            "## Confidence & Disclaimer\n"
            "Confidence: HIGH/MEDIUM/LOW\n"
            "This response is generated for research and informational purposes only "
            "and does not constitute legal or tax advice. "
            "Consult a qualified tax professional before acting on any information provided.\n\n"
            "After writing the answer, call verify_citations with your full answer text. "
            "Append result as CITATION_VALIDATION_RESULT: <JSON>. "
            "End with TERMINATE."
        ),
        reflect_on_tool_use=True,
    )

    return user_proxy, retrieval_agent, citation_agent


async def run_pipeline_async(query: str, session_id: str) -> dict:
    total_start = time.time()
    print("[UserProxyAgent] Session: " + session_id)
    print("[UserProxyAgent] Query: " + query[:80])

    if session_id not in session_store:
        session_store[session_id] = {"history": [], "turn": 0, "created_at": time.time()}
        print("[UserProxyAgent] New session created")
    else:
        print("[UserProxyAgent] Resumed session")

    session = session_store[session_id]
    session["turn"] += 1

    enriched_query = query
    if detect_followup(query):
        print("[UserProxyAgent] Follow-up detected")
        enriched_query = enrich_query_with_context(query, session)

    user_proxy, retrieval_agent, citation_agent = build_agent_team()

    termination = MaxMessageTermination(4)
    team = RoundRobinGroupChat(
    	participants=[retrieval_agent, citation_agent],
    	termination_condition=termination
    )

    conversation_log = []
    final_response = None
    citation_validation_json = {}

    print("[UserProxyAgent] Routing to RetrievalAgent...")

    # Pre-retrieve chunks and inject into task so CitationValidationAgent sees them
    pre_retrieved = retrieve_chunks(enriched_query, top_k=5)
    chunks_context = ""
    if pre_retrieved["chunks"]:
        chunks_context = "\n\n[RETRIEVED CHUNKS FROM INDEX]\n"
        for i, chunk in enumerate(pre_retrieved["chunks"]):
            chunks_context += f"\nChunk {i+1} (ID: {chunk['chunk_id']}):\n{chunk['text'][:800]}\n"
            meta = chunk.get("metadata", {})
            if meta.get("section"):
                chunks_context += f"Section: {meta['section']}, Act: {meta.get('act','')}\n"

    task_with_context = enriched_query + chunks_context

    message_count = 0
    MAX_MESSAGES = 6
    found_final = False

    stream = team.run_stream(task=task_with_context)
    try:
      async for message in stream:
        message_count += 1
        if message_count > MAX_MESSAGES:
            print("⚠️ Forced break (max messages reached)")
            break

        if not hasattr(message, "source") or not hasattr(message, "content"):
            if hasattr(message, '__class__') and 'Error' in message.__class__.__name__:
                print(f"[UserProxyAgent] Skipping error event: {message.__class__.__name__}")
                break
            continue

        source = message.source
        content = message.content if isinstance(message.content, str) else str(message.content)

        conversation_log.append({
            "agent": source,
            "content_preview": content[:300]
        })

        print(f"[{source}]: {content[:200]}")

        if source == "CitationValidationAgent" and "## Final Answer" in content and not found_final:
            found_final = True
            cleaned = content.split("## Final Answer", 1)[-1].strip()

            noise_patterns = ["[FunctionCall", "[FunctionExecutionResult", "name='verify_citations'", 'name="verify_citations"', "CITATION_VALIDATION_RESULT"]
            for noise in noise_patterns:
                 if noise in cleaned:
                     cleaned = cleaned.split(noise, 1)[0].strip()

            if "CITATION_VALIDATION_RESULT:" in cleaned:
                parts = cleaned.split("CITATION_VALIDATION_RESULT:", 1)
                final_response = parts[0].strip()
                try:
                    citation_validation_json = json.loads(parts[1].strip())
                except Exception:
                    citation_validation_json = {}
            else:
                final_response = cleaned

            print("✅ Final answer captured — letting stream terminate naturally")
            # DO NOT break here — let AutoGen drain the stream cleanly

    except Exception as e:
        print(f"[UserProxyAgent] Stream ended: {e}")

    if not citation_validation_json and final_response:
        print("[UserProxyAgent] Running citation validation fallback...")
        validation_result = validate_citations(final_response)

        if isinstance(validation_result, str):
            try:
                citation_validation_json = json.loads(validation_result)
            except Exception:
                print("[UserProxyAgent] JSON parse failed, using raw fallback")
                citation_validation_json = {}
        elif isinstance(validation_result, dict):
            citation_validation_json = validation_result
        else:
            citation_validation_json = {}


    retrieval_result = pre_retrieved

    if retrieval_result["chunks"]:
        top_chunk = retrieval_result["chunks"][0]
        vector_score = top_chunk.get("vector_score", 0.0)
        confidence = round(vector_score * 100, 2)

        if confidence >= 60:
            verification_status = "VERIFIED"
        else:
            verification_status = "UNVERIFIED"

        source = top_chunk.get("metadata", {}).get("source", "Unknown Source")
    else:
        confidence = 0
        verification_status = "UNVERIFIED"
        source = None
    if not final_response:
        final_response = (
            "## Final Answer\n"
            "The pipeline could not produce a response. "
            "Ensure the vector index contains data and retry.\n\n"
            "## Confidence & Disclaimer\n"
            "Confidence: LOW\n"
            "This response is generated for research and informational purposes only "
            "and does not constitute legal or tax advice. "
            "Consult a qualified tax professional before acting on any information provided."
        )

    total_time = (time.time() - total_start) * 1000
    session["history"].append({
        "turn": session["turn"],
        "query": query,
        "answer_summary": final_response[:200]
    })
    print("[UserProxyAgent] Pipeline complete. Total: " + str(round(total_time)) + "ms")
    if not isinstance(citation_validation_json, dict):
        citation_validation_json = {}
    return {
        "session_id": session_id,
        "turn": session["turn"],
        "query": query,
        "response": final_response,
        "confidence": confidence,
        "verification_status": verification_status,
        "source": source,
        "citations": citation_validation_json.get("citations", []),
        "overall_confidence": citation_validation_json.get("overall_confidence", "LOW"),
        "unverified_count": citation_validation_json.get("unverified_count", 0),
        "chunks_retrieved": 5,
        "latency_ms": {
            "retrieval": citation_validation_json.get("retrieval_time_ms", 0),
            "synthesis": 0,
            "citation_validation": citation_validation_json.get("validation_time_ms", 0),
            "total": total_time
        },
        "conversation_log": conversation_log
    }


def run_pipeline(query: str, session_id: str = None) -> dict:
    if not session_id:
        session_id = str(uuid.uuid4())
    return asyncio.run(run_pipeline_async(query, session_id))