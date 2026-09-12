export { cn } from "cn"

// snake_case key -> "Title Case" label, for any backend field that doesn't
// have a curated display name — a safe fallback rather than showing the
// raw key or silently dropping it.
export function humanizeKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
