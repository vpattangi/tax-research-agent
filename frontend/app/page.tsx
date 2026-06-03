"use client";
import { useState } from "react";

export default function Home() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  const sendQuery = async () => {
    if (!query.trim() || loading) return;
    const currentQuery = query.trim();
    setMessages(prev => [...prev, { role: "user", content: currentQuery }]);
    setQuery("");
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/query", {
	method: "POST",
  	headers: { "Content-Type": "application/json" },
  	body: JSON.stringify({
    		query: currentQuery,
    		...(sessionId ? { session_id: sessionId } : {})
  	}),
      });

const data = await res.json();
      if (!sessionId) setSessionId(data.session_id);
      setMessages(prev => [...prev, { role: "assistant", content: data.response, data }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: "assistant", content: "Error: " + err.message }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif", maxWidth: "900px", margin: "0 auto" }}>
      <div style={{ borderBottom: "1px solid #e2e8f0", paddingBottom: "1rem", marginBottom: "1rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: "bold", margin: 0 }}>India Tax Research Agent</h1>
        <p style={{ color: "#64748b", fontSize: "0.8rem", margin: "0.25rem 0 0" }}>Income Tax Act, 2025 · CBDT Circulars · AutoGen v0.4+ · Qdrant · BAAI/bge-large-en-v1.5</p>
      </div>

      <div style={{ minHeight: "400px", marginBottom: "1rem" }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", padding: "3rem", color: "#94a3b8" }}>
            <div style={{ fontSize: "3rem" }}>⚖️</div>
            <p>Ask a question about the Income Tax Act, 2025 or CBDT Circulars</p>
            {["Is Section 54 exemption available if the new property is purchased before the sale?", "What are the conditions for Section 80C deduction?", "Can a long-term capital loss be set off against short-term capital gains?"].map(q => (
              <button key={q} onClick={() => setQuery(q)} style={{ display: "block", width: "100%", textAlign: "left", padding: "0.5rem 1rem", margin: "0.5rem 0", background: "white", border: "1px solid #e2e8f0", borderRadius: "8px", cursor: "pointer", fontSize: "0.85rem", color: "#475569" }}>{q}</button>
            ))}
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} style={{ marginBottom: "1rem" }}>
            {msg.role === "user" && (
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <div style={{ background: "#2563eb", color: "white", padding: "0.75rem 1rem", borderRadius: "12px", maxWidth: "70%", fontSize: "0.9rem" }}>{msg.content}</div>
              </div>
            )}
            {msg.role === "assistant" && (
              <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: "12px", padding: "1rem", maxWidth: "90%" }}>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "sans-serif", fontSize: "0.85rem", margin: 0 }}>{msg.content}</pre>
                {msg.data && (
                  <div style={{ marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid #f1f5f9", fontSize: "0.75rem", color: "#64748b" }}>
                    <span style={{ background: msg.data.overall_confidence === "HIGH" ? "#dcfce7" : msg.data.overall_confidence === "MEDIUM" ? "#fef9c3" : "#fee2e2", color: msg.data.overall_confidence === "HIGH" ? "#16a34a" : msg.data.overall_confidence === "MEDIUM" ? "#ca8a04" : "#dc2626", padding: "0.2rem 0.5rem", borderRadius: "999px", marginRight: "0.5rem" }}>
                      {msg.data.overall_confidence}
                    </span>
                    <span style={{ marginRight: "0.5rem" }}>{msg.data.chunks_retrieved} chunks</span>
                    <span style={{ marginRight: "0.5rem" }}>Total: {msg.data.latency_ms ? Math.round(msg.data.latency_ms.total) : 0}ms</span>
                    {msg.data.unverified_count > 0 && <span style={{ color: "#f59e0b" }}>⚠ {msg.data.unverified_count} unverified</span>}
                    {msg.data.citations && msg.data.citations.length > 0 && (
                      <div style={{ marginTop: "0.5rem" }}>
                        {msg.data.citations.map((c, j) => (
                          <div key={j} style={{ display: "flex", gap: "0.5rem", marginBottom: "0.25rem" }}>
                            <span>{c.verified ? "✅" : "❌"}</span>
                            <span>{c.text}</span>
                            <span style={{ color: "#94a3b8" }}>{Math.round(c.confidence * 100)}%</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {loading && <div style={{ color: "#94a3b8", fontSize: "0.9rem" }}>Agents working: Retrieval → Synthesis → Citation Validation...</div>}
      </div>

      <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: "1rem" }}>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <textarea value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQuery(); }}} placeholder="Ask a tax research question... (Enter to send)" style={{ flex: 1, padding: "0.75rem", border: "1px solid #cbd5e1", borderRadius: "8px", fontSize: "0.9rem", resize: "none", height: "80px" }} disabled={loading} />
          <button onClick={sendQuery} disabled={loading || !query.trim()} style={{ padding: "0.75rem 1.5rem", background: "#2563eb", color: "white", border: "none", borderRadius: "8px", cursor: "pointer", opacity: loading || !query.trim() ? 0.5 : 1 }}>{loading ? "..." : "Send"}</button>
        </div>
        <p style={{ fontSize: "0.7rem", color: "#94a3b8", textAlign: "center", marginTop: "0.5rem" }}>For research and informational purposes only. Not legal or tax advice. Consult a qualified tax professional before acting on any information provided.</p>
      </div>
    </main>
  );
}