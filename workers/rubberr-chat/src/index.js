// Rubberr coaching-chat Worker — BYOK (Bring Your Own Key).
// The user pastes their own Anthropic API key in the browser; it is forwarded
// per-request to the Anthropic API and never stored. One method, clean errors.

const SYSTEM_PROMPT =
  "You are 'Coach Rubberr', a concise, encouraging table tennis coach and analyst. " +
  "Give practical, specific coaching on technique, tactics, and match strategy. " +
  "Keep answers short and direct unless asked for depth.";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (request.method !== "POST") return json({ error: "Use POST." }, 405);

    let payload;
    try {
      payload = await request.json();
    } catch {
      return json({ error: "Invalid JSON body." }, 400);
    }

    const apiKey = (payload.apiKey || "").trim();
    const message = (payload.message || "").trim();
    if (!apiKey) return json({ error: "Missing Anthropic API key. Paste your key to chat." }, 400);
    if (!message) return json({ error: "Empty message." }, 400);

    const upstream = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-5",
        max_tokens: 1024,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: message }],
      }),
    });

    if (!upstream.ok) {
      const detail = await upstream.text();
      return json({ error: `Anthropic API error (${upstream.status})`, detail }, upstream.status);
    }

    const data = await upstream.json();
    const reply = (data.content || []).map((b) => b.text || "").join("").trim();
    return json({ reply });
  },
};
