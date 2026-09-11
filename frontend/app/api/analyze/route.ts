// Server-side proxy: browser -> this route -> Python backend.
// Keeps BACKEND_URL private (not exposed to the client bundle) and avoids
// needing permissive CORS on the Python service in production -- only this
// Next.js server needs network access to it.
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 180;

const BACKEND_URL = process.env.BACKEND_URL || "https://clearview-backend.onrender.com";

export async function POST(request: NextRequest) {
  try {
    const incomingForm = await request.formData();

    // Re-package as a fresh FormData for the outgoing request -- forwarding
    // the parsed one directly works in most runtimes, but rebuilding it
    // explicitly avoids surprises across Next.js/Node fetch versions.
    const outgoingForm = new FormData();
    for (const [key, value] of incomingForm.entries()) {
      outgoingForm.append(key, value as any);
    }

    const backendResponse = await fetch(`${BACKEND_URL}/analyze`, {
      method: "POST",
      body: outgoingForm,
    });

    const data = await backendResponse.json();

    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: data?.detail || "Backend processing failed" },
        { status: backendResponse.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: `Could not reach backend: ${err?.message || err}` },
      { status: 502 }
    );
  }
}
