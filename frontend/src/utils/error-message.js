import errorMessageMap from "../config/error-message-map.json";

const GENERIC_MESSAGE = "Qualcosa non ha funzionato.";
const GENERIC_NEXT_STEP = "Riprova tra poco o aggiorna il prompt e riprova.";

function composeMessage(message, nextStep) {
  return `${message}\n${nextStep}`;
}

function extractRawMessage(input) {
  if (!input) return "";
  if (typeof input === "string") return input;
  if (input instanceof Error) return input.message || "";
  if (typeof input === "object" && typeof input.detail === "string") return input.detail;
  return "";
}

function formatMissingColumns(rawMessage) {
  const match = rawMessage.match(/missing columns:\s*(.+)/i);
  if (!match) return null;

  const rawColumns = match[1] || "";
  const columns = rawColumns
    .split(",")
    .map((column) => column.trim().replace(/^['"]|['"]$/g, ""))
    .filter(Boolean);

  if (columns.length === 0) return null;
  if (columns.length === 1) {
    return composeMessage(
      `Non riesco a trovare la colonna '${columns[0]}'.`,
      "Controlla se ha un nome diverso nel file e riprova."
    );
  }
  return composeMessage(
    `Non riesco a trovare alcune colonne richieste: ${columns.join(", ")}.`,
    "Controlla i nomi delle colonne nel file e riprova."
  );
}

export function toUiErrorMessage(input, statusCode) {
  const rawMessage = extractRawMessage(input).trim();
  const lower = rawMessage.toLowerCase();

  if (statusCode === 429) {
    return composeMessage(
      "Hai raggiunto il limite delle elaborazioni gratuite.",
      "Passa al piano Pro per continuare."
    );
  }

  if (!rawMessage || lower.includes("traceback")) {
    return composeMessage(GENERIC_MESSAGE, GENERIC_NEXT_STEP);
  }

  if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
    return composeMessage(
      "Sembra che la connessione non sia stabile.",
      "Controlla la rete e riprova."
    );
  }

  if (lower.includes("unexpected token") || lower.includes("invalid_plan_json")) {
    return composeMessage(
      "Il piano non e scritto in modo corretto.",
      "Controlla il formato del testo oppure rigenera il piano."
    );
  }

  const missingColumnsMessage = formatMissingColumns(rawMessage);
  if (missingColumnsMessage) return missingColumnsMessage;

  for (const rule of errorMessageMap) {
    if (rule.matches.some((value) => lower.includes(value.toLowerCase()))) {
      return composeMessage(rule.message, rule.next_step);
    }
  }

  return composeMessage(GENERIC_MESSAGE, GENERIC_NEXT_STEP);
}

export { errorMessageMap };
