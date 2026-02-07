import { toUiErrorMessage } from "./utils/error-message";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    const raw = await response.text();
    let errorDetail = raw;

    try {
      const payload = JSON.parse(raw);
      errorDetail =
        typeof payload?.detail === "string"
          ? payload.detail
          : JSON.stringify(payload);
    } catch {
      // raw non era JSON, va bene cosi
    }

    throw new Error(toUiErrorMessage(errorDetail, response.status));
  }
  return response;
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await request("/api/files/upload", {
    method: "POST",
    body: formData
  });
  return response.json();
}

export async function fetchUsage(userId) {
  const response = await request(`/api/usage/${encodeURIComponent(userId)}`);
  return response.json();
}

export async function generatePlan({ fileId, prompt, userId }) {
  const response = await request("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      prompt,
      user_id: userId
    })
  });
  return response.json();
}

export async function applyTransform({ fileId, userId, plan, outputFormat }) {
  const response = await request("/api/transform", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      user_id: userId,
      plan,
      output_format: outputFormat
    })
  });
  return response.json();
}

export async function previewTransform({ fileId, plan }) {
  const response = await request("/api/transform/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      plan
    })
  });
  return response.json();
}

export function buildDownloadUrl(resultId) {
  return `${API_BASE_URL}/api/results/${encodeURIComponent(resultId)}/download`;
}
