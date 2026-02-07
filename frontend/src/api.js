import { toUiErrorMessage } from "./utils/error-message";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const INVALID_BASE_URL_MESSAGE =
  "Configurazione API non valida. Imposta VITE_API_BASE_URL con un URL valido (es. https://api.example.com).";

function normalizeBaseUrl(rawBaseUrl) {
  const candidate = typeof rawBaseUrl === "string" ? rawBaseUrl.trim() : "";
  const input = candidate || DEFAULT_API_BASE_URL;
  const withProtocol = /^https?:\/\//i.test(input) ? input : `https://${input}`;
  const withoutTrailingSlash = withProtocol.replace(/\/+$/, "");

  try {
    const parsed = new URL(withoutTrailingSlash);
    if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
      return { value: null, error: INVALID_BASE_URL_MESSAGE };
    }
    return {
      value: parsed.toString().replace(/\/+$/, ""),
      error: null
    };
  } catch {
    return { value: null, error: INVALID_BASE_URL_MESSAGE };
  }
}

const normalizedBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);
const API_BASE_URL = normalizedBaseUrl.value;
const API_BASE_URL_ERROR = normalizedBaseUrl.error;

function parseJson(raw) {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function toCamelCaseKey(key) {
  return key.replace(/_([a-z])/g, (_, char) => char.toUpperCase());
}

function normalizeKeys(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeKeys);
  }
  if (value && typeof value === "object") {
    const normalized = {};
    for (const [key, nestedValue] of Object.entries(value)) {
      normalized[toCamelCaseKey(key)] = normalizeKeys(nestedValue);
    }
    return normalized;
  }
  return value;
}

function ensureObjectPayload(payload, fallbackMessage) {
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return payload;
  }
  throw new Error(
    `${fallbackMessage}\nRiprova tra poco oppure aggiorna la pagina e ripeti l'operazione.`
  );
}

async function request(path, options = {}) {
  if (API_BASE_URL_ERROR || !API_BASE_URL) {
    throw new Error(API_BASE_URL_ERROR || INVALID_BASE_URL_MESSAGE);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, options);
  const bodyBlob = await response.blob();
  const raw = await bodyBlob.text();
  const payload = parseJson(raw);
  const normalizedPayload = normalizeKeys(payload);

  if (!response.ok) {
    const errorDetail =
      typeof payload?.detail === "string"
        ? payload.detail
        : raw || `Richiesta fallita (HTTP ${response.status}).`;

    throw new Error(toUiErrorMessage(errorDetail, response.status));
  }
  return {
    response,
    bodyBlob,
    raw,
    payload: normalizedPayload
  };
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const result = await request("/api/files/upload", {
    method: "POST",
    body: formData
  });
  return ensureObjectPayload(result.payload, "Il server ha risposto con dati non validi durante l'upload.");
}

export async function fetchUsage(userId) {
  const result = await request(`/api/usage/${encodeURIComponent(userId)}`);
  return ensureObjectPayload(result.payload, "Non riesco a leggere lo stato degli utilizzi.");
}

export async function generatePlan({ fileId, prompt, userId }) {
  const result = await request("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      prompt,
      user_id: userId
    })
  });
  return ensureObjectPayload(result.payload, "Il piano generato non e in un formato valido.");
}

export async function clarifyPlan({ fileId, prompt, clarifyId, answer }) {
  const result = await request("/api/plan/clarify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      prompt,
      clarify_id: clarifyId,
      answer
    })
  });
  return ensureObjectPayload(result.payload, "La risposta di chiarimento non e in un formato valido.");
}

export async function applyTransform({ fileId, userId, plan, outputFormat }) {
  const result = await request("/api/transform", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      user_id: userId,
      plan,
      output_format: outputFormat
    })
  });
  return ensureObjectPayload(result.payload, "La risposta dell'applicazione trasformazioni non e valida.");
}

export async function previewTransform({ fileId, plan }) {
  const result = await request("/api/transform/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      plan
    })
  });
  return ensureObjectPayload(result.payload, "La preview ricevuta non e valida.");
}

export function buildDownloadUrl(resultId) {
  return `${API_BASE_URL}/api/results/${encodeURIComponent(resultId)}/download`;
}
