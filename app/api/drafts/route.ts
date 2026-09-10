import { NextRequest, NextResponse } from "next/server";
import { getDrafts, saveDraft, deleteDraft } from "@/lib/storage";

export async function GET() {
  return NextResponse.json(getDrafts());
}

export async function POST(req: NextRequest) {
  const draft = await req.json();
  saveDraft(draft);
  return NextResponse.json({ ok: true });
}

export async function DELETE(req: NextRequest) {
  const { id } = await req.json();
  deleteDraft(id);
  return NextResponse.json({ ok: true });
}
