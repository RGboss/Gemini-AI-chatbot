export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function api(path, options = {}) {
  let response;
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers = isFormData
    ? { ...options.headers }
    : { 'Content-Type': 'application/json', ...options.headers };

  try {
    response = await fetch(`/api${path}`, {
      credentials: 'include',
      ...options,
      headers,
    });
  } catch {
    throw new ApiError('Cannot reach the Orbit server. Please check if the backend is running.', 0);
  }
  if (response.status === 204) return null;
  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError('The server returned an unreadable response. Please try again.', response.status);
  }
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join(' ')
      : data.detail;
    throw new ApiError(detail || 'The request failed. Please try again.', response.status);
  }
  return data;
}
