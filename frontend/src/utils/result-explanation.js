function summarizeOperation(type) {
  if (!type || typeof type !== "string") return null;
  const normalized = type.toLowerCase();

  if (normalized === "rename_column") return "Abbiamo reso piu chiare alcune etichette dei dati.";
  if (normalized === "drop_columns") return "Abbiamo tolto le parti non utili per semplificare la vista.";
  if (normalized === "fill_null") return "Abbiamo completato i dati mancanti.";
  if (normalized === "cast_type") return "Abbiamo uniformato il formato dei dati.";
  if (normalized === "trim_whitespace") return "Abbiamo ripulito i testi da spazi superflui.";
  if (normalized === "change_case") return "Abbiamo reso coerente lo stile dei testi.";
  if (normalized === "derive_numeric") return "Abbiamo calcolato nuovi valori a partire dai dati esistenti.";
  if (normalized === "filter_rows") return "Abbiamo tenuto solo le righe davvero rilevanti.";
  if (normalized === "sort_rows") return "Abbiamo ordinato i risultati per una lettura piu immediata.";
  if (normalized.includes("group")) return "Abbiamo raggruppato i dati per creare un riepilogo chiaro.";
  if (normalized.includes("merge") || normalized.includes("join")) return "Abbiamo unito i dati in un unico risultato.";
  return "Abbiamo riorganizzato i dati per renderli piu utili.";
}

export function buildHumanResultExplanation(plan) {
  const operations = plan?.operations;
  if (!Array.isArray(operations) || operations.length === 0) {
    return ["Abbiamo lasciato i dati invariati perche non erano necessarie modifiche."];
  }

  const bullets = [];
  const seen = new Set();
  for (const operation of operations) {
    if (!operation || typeof operation !== "object") continue;
    const sentence = summarizeOperation(operation.type);
    if (!sentence) continue;
    if (seen.has(sentence)) continue;
    seen.add(sentence);
    bullets.push(sentence);
    if (bullets.length >= 3) break;
  }

  if (bullets.length === 0) {
    return ["Abbiamo applicato una trasformazione per rendere il risultato piu leggibile."];
  }
  return bullets;
}
