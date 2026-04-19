/**
 * Catch-all Next.js API proxy → FastAPI backend.
 *
 * FE5: All browser-originated API calls go through this route handler so
 * that API keys stay server-side and never reach the client. Server
 * components call lib/api.ts directly (they run on the server already).
 *
 * Proxies: GET/POST /api/* → BACKEND_URL/api/*
 */

import { NextRequest, NextResponse } from "next/server";
import {
  PatientsResponseSchema,
  ApproveResponseSchema,
} from "@/lib/api";
import type { z } from "zod";

// Server-side only — never exposed to browser
const BACKEND_URL =
  process.env.BACKEND_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";
const VIGIL_API_KEY = process.env.VIGIL_API_KEY ?? "";

// ---------------------------------------------------------------------------
// Schema map — reuses schemas from lib/api.ts (single source of truth)
// ---------------------------------------------------------------------------

const SCHEMA_MAP: Record<string, z.ZodType> = {
  patients: PatientsResponseSchema,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildUpstreamUrl(path: string[], searchParams: URLSearchParams): string {
  const apiPath = `/api/${path.join("/")}`;
  const qs = searchParams.toString();
  return `${BACKEND_URL}${apiPath}${qs ? `?${qs}` : ""}`;
}

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (VIGIL_API_KEY) {
    headers["X-API-Key"] = VIGIL_API_KEY;
  }
  return headers;
}

/**
 * Strip sensitive fields from response data before logging.
 * Never log API keys, tokens, or bearer credentials.
 */
function sanitizeForLog(data: unknown): unknown {
  if (data === null || data === undefined) return data;
  if (typeof data !== "object") return data;
  if (Array.isArray(data)) return data.map(sanitizeForLog);

  const sanitized: Record<string, unknown> = {};
  const REDACT_KEYS = new Set([
    "api_key", "apikey", "api-key",
    "token", "access_token", "fhir_token",
    "authorization", "secret", "password",
    "x-api-key", "x-fhir-access-token",
  ]);

  for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
    if (REDACT_KEYS.has(key.toLowerCase())) {
      sanitized[key] = "[REDACTED]";
    } else {
      sanitized[key] = sanitizeForLog(value);
    }
  }
  return sanitized;
}

/**
 * Validate response data against zod schema if one exists for the path.
 * Logs warnings on mismatch but still returns data (non-blocking).
 */
function validateResponse(pathSegments: string[], data: unknown): void {
  const firstSegment = pathSegments[0];
  if (!firstSegment) return;

  // Check for approve endpoint: patients/{id}/alerts/{alertId}/approve
  if (
    firstSegment === "patients" &&
    pathSegments.length === 5 &&
    pathSegments[4] === "approve"
  ) {
    const result = ApproveResponseSchema.safeParse(data);
    if (!result.success) {
      console.warn(
        "[proxy] approve response validation warning:",
        result.error.issues.map((i) => i.message).join(", ")
      );
    }
    return;
  }

  // Check top-level schema
  const schema = SCHEMA_MAP[firstSegment];
  if (schema) {
    const result = schema.safeParse(data);
    if (!result.success) {
      console.warn(
        `[proxy] ${firstSegment} response validation warning:`,
        result.error.issues.map((i) => i.message).join(", ")
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Route handlers
// ---------------------------------------------------------------------------

async function proxyRequest(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await params;
  const upstream = buildUpstreamUrl(path, req.nextUrl.searchParams);

  try {
    const fetchInit: RequestInit = {
      method: req.method,
      headers: buildHeaders(),
    };

    // Forward body for POST/PUT/PATCH
    if (req.method !== "GET" && req.method !== "HEAD") {
      try {
        const body = await req.text();
        if (body) fetchInit.body = body;
      } catch {
        // No body — that's fine for some POSTs
      }
    }

    const upstreamRes = await fetch(upstream, fetchInit);

    // Stream non-JSON responses through
    const contentType = upstreamRes.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      return new NextResponse(upstreamRes.body, {
        status: upstreamRes.status,
        headers: {
          "Content-Type": contentType,
          "X-Proxy": "vigil-nextjs",
        },
      });
    }

    const data = await upstreamRes.json();

    // Validate + sanitize log (never log keys)
    validateResponse(path, data);
    if (process.env.NODE_ENV === "development") {
      console.log(
        `[proxy] ${req.method} /api/${path.join("/")} → ${upstreamRes.status}`,
        JSON.stringify(sanitizeForLog(data)).slice(0, 200)
      );
    }

    return NextResponse.json(data, {
      status: upstreamRes.status,
      headers: { "X-Proxy": "vigil-nextjs" },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown proxy error";
    console.error(`[proxy] ${req.method} /api/${path.join("/")} error:`, message);

    return NextResponse.json(
      { error: "Backend unavailable", detail: message },
      { status: 502 }
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
