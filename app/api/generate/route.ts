import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { getProfile } from "@/lib/storage";
import { buildSystemPrompt, buildUserPrompt, CONTENT_ANGLES } from "@/lib/prompts";

function getClient() {
  return new OpenAI({
    baseURL: "https://openrouter.ai/api/v1",
    apiKey: process.env.OPENROUTER_API_KEY || "placeholder",
  });
}

export async function POST(req: NextRequest) {
  const { angleId, extraContext } = await req.json();

  const profile = getProfile();
  if (!profile) {
    return NextResponse.json({ error: "No voice profile found. Complete setup first." }, { status: 400 });
  }

  const angle = CONTENT_ANGLES.find((a) => a.id === angleId);
  if (!angle) {
    return NextResponse.json({ error: "Unknown content angle." }, { status: 400 });
  }

  const response = await getClient().chat.completions.create({
    model: process.env.OPENROUTER_MODEL || "anthropic/claude-sonnet-4-5",
    max_tokens: 2000,
    messages: [
      { role: "system", content: buildSystemPrompt(profile) },
      { role: "user", content: buildUserPrompt(angle, extraContext) },
    ],
  });

  const text = response.choices[0]?.message?.content || "";

  return NextResponse.json({ raw: text, angle: angle.label });
}
