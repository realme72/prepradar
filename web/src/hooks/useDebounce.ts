import { useEffect, useState } from "react";

// Returns `value`, but only after it has stopped changing for `ms` milliseconds.
// Typing "kafka" fires one search instead of five (k, ka, kaf, ...).
//
// Each keystroke changes `value`, so the effect's cleanup cancels the pending
// timer and a new one starts. Only the last timer survives long enough to fire.
export function useDebounce<T>(value: T, ms = 300) {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}
