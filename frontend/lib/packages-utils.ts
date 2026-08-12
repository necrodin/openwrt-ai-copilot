import type { PackageSearchResponse } from "@/lib/router-management";

export type SearchEmptyState =
  | { kind: "no-match"; title: string }
  | {
      kind: "repository-unavailable";
      title: string;
      reason?: string;
      detail?: string[];
    };

/**
 * Decide why a repository search returned no results. A search that comes back
 * empty because the repository index is unavailable (e.g. the router has never
 * run ``apk update`` and has no cache) must not be presented as "the package
 * does not exist" — the two are distinct and the operator can refresh feeds.
 */
export function searchEmptyState(
  response: PackageSearchResponse,
): SearchEmptyState {
  if (response.repository?.available === false) {
    return {
      kind: "repository-unavailable",
      title: "The package repository is unavailable on the router.",
      reason: response.repository.reason ?? undefined,
      detail: response.repository.detail,
    };
  }
  return {
    kind: "no-match",
    title: `No packages match “${response.query}” in the repository.`,
  };
}
