import type { PackageSearchResponse } from "@/lib/router-management";

export type SearchEmptyState =
  | { kind: "no-match"; title: string }
  | {
      kind: "manager-unavailable";
      title: string;
      reason?: string;
      detail?: string[];
    }
  | {
      kind: "repository-unavailable";
      title: string;
      reason?: string;
      detail?: string[];
    }
  | {
      kind: "index-unavailable";
      title: string;
      reason?: string;
      detail?: string[];
    };

/**
 * Decide why a repository search returned no results. A search that comes back
 * empty because the repository is unavailable must not be presented as "the
 * package does not exist" — the two are distinct and the operator can refresh
 * feeds. The backend reports a structured repository status so each failure
 * class gets its own message: the package manager is missing, the repository
 * index is empty/never updated, or the repository metadata cannot be read.
 */
export function searchEmptyState(
  response: PackageSearchResponse,
): SearchEmptyState {
  const repo = response.repository;
  if (repo && repo.available === false) {
    const status = repo.status ?? "repository-unavailable";
    const base = { reason: repo.reason ?? undefined, detail: repo.detail };
    switch (status) {
      case "manager-unavailable":
        return {
          kind: "manager-unavailable",
          title: "The package manager is unavailable on the router.",
          ...base,
        };
      case "index-unavailable":
        return {
          kind: "index-unavailable",
          title: "The package repository metadata is unavailable on the router.",
          ...base,
        };
      case "repository-unavailable":
      default:
        return {
          kind: "repository-unavailable",
          title: "The package repository is unavailable on the router.",
          ...base,
        };
    }
  }
  return {
    kind: "no-match",
    title: `No packages match “${response.query}” in the repository.`,
  };
}
