/** Human-friendly byte size (base-1000 units), e.g. "1.2 MB". */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes) || bytes < 0) {
    return "—";
  }
  if (bytes === 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1000)),
    units.length - 1,
  );
  const value = bytes / 1000 ** index;
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

/** Epoch seconds → localized date+time string, or "—" when absent/invalid. */
export function formatEpoch(epoch: number | null | undefined): string {
  if (epoch === null || epoch === undefined || Number.isNaN(epoch)) {
    return "—";
  }
  return new Date(epoch * 1000).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}