// Answers are stored under a key made from the question, so owners never type one. A key
// stays fixed once answers may exist: only a key that still matches its question's old
// words follows the words when they change.
export function keyFor(ask: string, taken: string[]): string {
  let base = ask.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 36) || "answer";
  if (!/^[a-z]/.test(base)) base = `q_${base}`.slice(0, 36);
  if (base === "booking_type") base = "booking_type_answer";
  let key = base;
  for (let n = 2; taken.includes(key); n++) key = `${base}_${n}`;
  return key;
}
