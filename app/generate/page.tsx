"use client";
import { useState } from "react";
import { CONTENT_ANGLES } from "@/lib/prompts";

interface GeneratedTone {
  tone: string;
  instagram: string;
  linkedin: string;
}

function parseResponse(raw: string): GeneratedTone[] {
  const blocks = raw.split(/---/).filter((b) => b.trim());
  return blocks.map((block) => {
    const toneMatch = block.match(/TONE:\s*(.+)/i);
    const igMatch = block.match(/INSTAGRAM:\s*([\s\S]*?)(?=LINKEDIN:|$)/i);
    const liMatch = block.match(/LINKEDIN:\s*([\s\S]*?)$/i);
    return {
      tone: toneMatch?.[1]?.trim() || "Unknown",
      instagram: igMatch?.[1]?.trim() || "",
      linkedin: liMatch?.[1]?.trim() || "",
    };
  });
}

export default function GeneratePage() {
  const [selectedAngle, setSelectedAngle] = useState("");
  const [extraContext, setExtraContext] = useState("");
  const [generating, setGenerating] = useState(false);
  const [results, setResults] = useState<GeneratedTone[]>([]);
  const [activeTab, setActiveTab] = useState<"instagram" | "linkedin">("instagram");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Record<string, boolean>>({});

  async function generate() {
    if (!selectedAngle) return;
    setGenerating(true);
    setResults([]);
    setError("");
    setSaved({});
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ angleId: selectedAngle, extraContext }),
      });
      const data = await res.json();
      if (data.error) { setError(data.error); return; }
      setResults(parseResponse(data.raw));
    } catch {
      setError("Something went wrong. Check your API key in .env.local.");
    } finally {
      setGenerating(false);
    }
  }

  async function saveDraft(tone: GeneratedTone) {
    const angle = CONTENT_ANGLES.find((a) => a.id === selectedAngle);
    const draft = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      createdAt: new Date().toISOString(),
      angle: angle?.label || selectedAngle,
      instagram: tone.instagram,
      linkedin: tone.linkedin,
      tone: tone.tone.toLowerCase().includes("raw") ? "raw" : tone.tone.toLowerCase().includes("practical") ? "practical" : "reflective",
    };
    await fetch("/api/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    setSaved((s) => ({ ...s, [tone.tone]: true }));
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-stone-900 mb-1">Generate a post</h1>
        <p className="text-stone-500 text-sm">Pick an angle. The app writes in your voice.</p>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          {CONTENT_ANGLES.map((angle) => (
            <button
              key={angle.id}
              onClick={() => setSelectedAngle(angle.id)}
              className={`text-left p-4 rounded-xl border text-sm transition-all ${
                selectedAngle === angle.id
                  ? "border-stone-800 bg-stone-800 text-white"
                  : "border-stone-200 bg-white text-stone-700 hover:border-stone-400"
              }`}
            >
              <div className="font-medium">{angle.label}</div>
              <div className={`text-xs mt-0.5 ${selectedAngle === angle.id ? "text-stone-300" : "text-stone-400"}`}>
                {angle.description}
              </div>
            </button>
          ))}
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-500 mb-1.5">
            Add context (optional) — a specific moment, a thought you had, something you want to say
          </label>
          <textarea
            value={extraContext}
            onChange={(e) => setExtraContext(e.target.value)}
            placeholder="e.g. I was thinking about how I almost didn't go because I was convinced I'd lose all my friends..."
            rows={3}
            className="w-full rounded-lg border border-stone-200 px-4 py-3 text-stone-800 text-sm placeholder:text-stone-300 focus:outline-none focus:ring-2 focus:ring-stone-300 resize-none bg-white"
          />
        </div>

        <button
          onClick={generate}
          disabled={!selectedAngle || generating}
          className="w-full py-3 bg-stone-800 text-white text-sm font-medium rounded-xl hover:bg-stone-700 disabled:opacity-30 transition-colors"
        >
          {generating ? "Writing..." : "Generate posts"}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{error}</div>
      )}

      {results.length > 0 && (
        <div className="space-y-6">
          <div className="flex gap-2 border-b border-stone-200">
            {(["instagram", "linkedin"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setActiveTab(p)}
                className={`pb-3 px-1 text-sm font-medium border-b-2 transition-colors capitalize ${
                  activeTab === p ? "border-stone-800 text-stone-900" : "border-transparent text-stone-400 hover:text-stone-700"
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          {results.map((result) => (
            <div key={result.tone} className="bg-white rounded-xl border border-stone-200 p-6 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-stone-400 uppercase tracking-wider">{result.tone}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => navigator.clipboard.writeText(activeTab === "instagram" ? result.instagram : result.linkedin)}
                    className="text-xs text-stone-400 hover:text-stone-700 px-2 py-1 rounded border border-stone-200 hover:border-stone-400 transition-colors"
                  >
                    Copy
                  </button>
                  <button
                    onClick={() => saveDraft(result)}
                    disabled={saved[result.tone]}
                    className="text-xs text-stone-400 hover:text-stone-700 px-2 py-1 rounded border border-stone-200 hover:border-stone-400 transition-colors disabled:opacity-50"
                  >
                    {saved[result.tone] ? "Saved" : "Save to calendar"}
                  </button>
                </div>
              </div>
              <p className="text-stone-700 text-sm leading-relaxed whitespace-pre-wrap">
                {activeTab === "instagram" ? result.instagram : result.linkedin}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
