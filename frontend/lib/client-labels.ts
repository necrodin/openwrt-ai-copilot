import { API_BASE_URL } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { ClientLabel } from "@/lib/clients";

export type { ClientLabel } from "@/lib/clients";

export type ClientLabelList = {
  labels: ClientLabel[];
};

/**
 * Fetch every stored client label. Read-only; requires any authenticated role.
 */
export async function listClientLabels(): Promise<ClientLabelList> {
  const res = await fetch(`${API_BASE_URL}/clients/labels`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Labels request failed with status ${res.status}`);
  }
  return (await res.json()) as ClientLabelList;
}

/**
 * Create or update the label for a MAC (admin/write scope required). The MAC
 * may be in any common format; the backend normalizes it.
 */
export async function saveClientLabel(
  mac: string,
  label: string,
): Promise<ClientLabel> {
  const res = await fetch(
    `${API_BASE_URL}/clients/labels/${encodeURIComponent(mac)}`,
    {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ label }),
    },
  );
  if (!res.ok) {
    throw new Error(`Label save failed with status ${res.status}`);
  }
  return (await res.json()) as ClientLabel;
}

/**
 * Remove the label for a MAC (admin/write scope required).
 */
export async function deleteClientLabel(mac: string): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/clients/labels/${encodeURIComponent(mac)}`,
    {
      method: "DELETE",
      headers: authHeaders(),
    },
  );
  if (!res.ok) {
    throw new Error(`Label delete failed with status ${res.status}`);
  }
}
