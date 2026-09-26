export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const res = await fetch(path, {
    credentials: "include",
    ...init,
  });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json() as { detail?: string };
      if (body.detail) message = String(body.detail);
    } catch {
      // use default message
    }
    throw new ApiError(message, res.status);
  }

  return res;
}
