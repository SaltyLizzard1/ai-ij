import { VoiceProfile } from "./storage";

const FORBIDDEN_WORDS = [
  "delve", "navigate", "journey", "empower", "transformative", "leverage",
  "unlock", "game-changer", "holistic", "synergy", "curate", "bespoke",
  "in today's world", "in a world where", "it's time to", "don't wait",
  "DM me", "link in bio", "let's connect", "reach out", "I help people",
];

export const CONTENT_ANGLES = [
  { id: "fear", label: "The fear of leaving", description: "The terror of walking away from everything familiar" },
  { id: "grief", label: "The grief of the old life", description: "What it actually feels like to leave — the loss, not just the gain" },
  { id: "identity", label: "Who you become", description: "How moving changes you, for better and harder" },
  { id: "money", label: "Building income from anywhere", description: "The practical reality of creating a location-independent income" },
  { id: "myth", label: "Myth-busting", description: "Things people believe that are keeping them stuck" },
  { id: "story", label: "Your own story", description: "A moment or turning point from your own move" },
  { id: "permission", label: "Permission to want this", description: "For the person who feels guilty for wanting to leave" },
  { id: "practical", label: "First steps", description: "Concrete, small things someone can do right now" },
];

export function buildSystemPrompt(profile: VoiceProfile): string {
  return `You are a ghostwriter for a specific person. Your only job is to write in their exact voice — not your idea of "authentic," not polished marketing copy, not inspirational coach-speak. Their voice.

Here is everything you know about this person:

THEIR STORY:
${profile.yourMove}

WHAT SCARED THEM MOST:
${profile.biggestFear}

WHAT THEY WISH THEY'D KNOWN:
${profile.wisdomYouWish}

WHO THEY HELP:
${profile.whoYouHelp}

THEIR CLIENTS' FEAR:
${profile.theirFear}

THEIR CLIENTS' DREAM:
${profile.theirDream}

THEIR TONE:
${profile.yourTone}

PHRASES THEY ACTUALLY USE:
${profile.phrasesYouUse}

WORDS AND PHRASES THEY WOULD NEVER USE:
${profile.phrasesYouHate}

WHY THEY DO THIS WORK:
${profile.yourWhy}

WRITING RULES — follow these exactly:
- Write like a human texting a thoughtful friend, not a brand
- Short sentences. One idea per sentence. White space is good.
- Never use these words: ${FORBIDDEN_WORDS.join(", ")}
- No hashtag suggestions — leave that to the user
- No calls to action like "DM me" or "link in bio"
- No em dashes (—) — use a period or a new line instead
- Don't start sentences with "I" more than twice per post
- No rhetorical questions that feel like a marketing formula
- It should be impossible to tell this was written by AI
- Draw on their real story and real phrases when relevant

You will write two versions of every post: one for Instagram and one for LinkedIn.
Instagram: shorter, more emotional, more raw. 150-220 words max.
LinkedIn: slightly longer, more context and credibility, still human. 200-300 words max.

You will write three tone variations: raw/honest, practical, and reflective. Label them clearly.`;
}

export function buildUserPrompt(angle: { id: string; label: string; description: string }, extraContext?: string): string {
  return `Write content about: ${angle.label}
What this means: ${angle.description}
${extraContext ? `Additional context from the user: ${extraContext}` : ""}

Format your response exactly like this:

---
TONE: Raw / Honest
INSTAGRAM:
[post]

LINKEDIN:
[post]

---
TONE: Practical
INSTAGRAM:
[post]

LINKEDIN:
[post]

---
TONE: Reflective
INSTAGRAM:
[post]

LINKEDIN:
[post]`;
}
