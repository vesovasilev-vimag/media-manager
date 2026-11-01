export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (method !== "GET") {
    headers["Idempotency-Key"] = key ?? crypto.randomUUID();
    headers["X-CSRF-Token"] = decodeURIComponent(
      document.cookie
        .split("; ")
        .find((c) => c.startsWith("vimag_csrf="))
        ?.split("=")[1] ?? "",
    );
  }
  const result = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await result.json();
  if (!result.ok)
    throw new ApiError(
      result.status,
      data.code ?? data.detail ?? "REQUEST_FAILED",
    );
  return data as T;
}
