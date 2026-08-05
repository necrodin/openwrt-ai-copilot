/**
 * Central frontend configuration for the OpenWrt AI Copilot product.
 *
 * Every external link (repository, issues, donations, socials) and every piece
 * of brand metadata lives here — a single source of truth for the About page,
 * the footer, and the sidebar's Open Source section.
 *
 * All values may be overridden at build/deploy time via `NEXT_PUBLIC_*`
 * environment variables.
 *
 * Browser-safe: values are read with direct `process.env.NEXT_PUBLIC_*` member
 * access (never `process` captured at module scope, never bracket access), so
 * Next.js statically replaces them with their build-time values in the client
 * bundle. This keeps the module safe to import from both server and client
 * components.
 */

export type DonationTarget = {
  id: string;
  label: string;
  /** Flat emoji-free short description shown on the Support page. */
  description: string;
  /**
   * External donation URL. `null` until the maintainer configures one — those
   * targets render as "Not configured" rather than linking to a made-up URL.
   */
  url: string | null;
};

export const SITE_CONFIG = {
  /** Product / repository branding */
  name: process.env.NEXT_PUBLIC_APP_NAME ?? "OpenWrt AI Copilot",
  tagline:
    process.env.NEXT_PUBLIC_APP_TAGLINE ??
    "Provider-independent AI copilot for managing OpenWrt router fleets.",
  description:
    process.env.NEXT_PUBLIC_APP_DESCRIPTION ??
    "A production-grade, provider-independent AI copilot for OpenWrt networks. " +
      "Ask questions in natural language, diagnose connectivity, and manage " +
      "your fleet — fully local, no cloud dependency.",
  company: process.env.NEXT_PUBLIC_COMPANY_NAME ?? "Necrodin",
  author:
    process.env.NEXT_PUBLIC_AUTHOR ?? "The OpenWrt AI Copilot contributors",
  license: process.env.NEXT_PUBLIC_LICENSE ?? "MIT",

  /** Versioning (build-time injected in the CI / Docker build). */
  version: process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0",
  frontendVersion: process.env.NEXT_PUBLIC_FRONTEND_VERSION ?? "0.0.0",
  gitCommit: process.env.NEXT_PUBLIC_GIT_COMMIT ?? null,
  buildDate: process.env.NEXT_PUBLIC_BUILD_DATE ?? null,
  environment: process.env.NEXT_PUBLIC_ENVIRONMENT ?? "development",

  /** Canonical site URL (used for Open Graph / Twitter metadata root). */
  appUrl: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",

  /** Repository */
  repositoryUrl:
    process.env.NEXT_PUBLIC_REPOSITORY_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot",
  documentationUrl:
    process.env.NEXT_PUBLIC_DOCUMENTATION_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot/tree/main/docs",
  issuesUrl:
    process.env.NEXT_PUBLIC_ISSUES_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot/issues/new/choose",
  releasesUrl:
    process.env.NEXT_PUBLIC_RELEASES_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot/releases",
  discussionsUrl:
    process.env.NEXT_PUBLIC_DISCUSSIONS_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot/discussions",
  wikiUrl:
    process.env.NEXT_PUBLIC_WIKI_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot/wiki",
  roadmapUrl:
    process.env.NEXT_PUBLIC_ROADMAP_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot/issues?q=is%3Aissue+is%3Aopen+label%3Aroadmap",
  changelogUrl:
    process.env.NEXT_PUBLIC_CHANGELOG_URL ??
    "https://github.com/necrodin/openwrt-ai-copilot/blob/main/CHANGELOG.md",

  /** Socials */
  socials: {
    github:
      process.env.NEXT_PUBLIC_SOCIAL_GITHUB ??
      "https://github.com/necrodin/openwrt-ai-copilot",
    openwrt: process.env.NEXT_PUBLIC_SOCIAL_OPENWRT ?? "https://openwrt.org",
  },

  /** Donation targets (Support Development page) — all external links. */
  donations: [
    {
      id: "github-sponsors",
      label: "GitHub Sponsors",
      description: "Sponsor the project directly on GitHub.",
      url: process.env.NEXT_PUBLIC_DONATE_GITHUB ?? null,
    },
    {
      id: "buy-me-a-coffee",
      label: "Buy Me a Coffee",
      description: "Support a coffee while we ship the next feature.",
      url: process.env.NEXT_PUBLIC_DONATE_BUYMEACOFFEE ?? null,
    },
    {
      id: "ko-fi",
      label: "Ko-fi",
      description: "Ko-fi supports creators and open source maintainers.",
      url: process.env.NEXT_PUBLIC_DONATE_KOFI ?? null,
    },
    {
      id: "paypal",
      label: "PayPal",
      description: "One-time donation via PayPal.",
      url: process.env.NEXT_PUBLIC_DONATE_PAYPAL ?? null,
    },
    {
      id: "amazon-gift-card",
      label: "Amazon Gift Card",
      description: "Send an Amazon gift card to the maintainer.",
      url: process.env.NEXT_PUBLIC_DONATE_AMAZON ?? null,
    },
    {
      id: "bitcoin",
      label: "Bitcoin (BTC)",
      description: "Donate Bitcoin to support development.",
      url: process.env.NEXT_PUBLIC_DONATE_BITCOIN ?? null,
    },
    {
      id: "ethereum",
      label: "Ethereum (ETH)",
      description: "Donate Ether to support development.",
      url: process.env.NEXT_PUBLIC_DONATE_ETHEREUM ?? null,
    },
    {
      id: "lightning",
      label: "Lightning Network",
      description: "Donate via the Bitcoin Lightning Network.",
      url: process.env.NEXT_PUBLIC_DONATE_LIGHTNING ?? null,
    },
  ] satisfies DonationTarget[],
} as const;

export type SiteConfig = typeof SITE_CONFIG;

export function githubUrl(
  section: "repo" | "issues" | "releases" | "discussions" | "wiki",
): string {
  switch (section) {
    case "repo":
      return SITE_CONFIG.repositoryUrl;
    case "issues":
      return SITE_CONFIG.issuesUrl;
    case "releases":
      return SITE_CONFIG.releasesUrl;
    case "discussions":
      return SITE_CONFIG.discussionsUrl;
    case "wiki":
      return SITE_CONFIG.wikiUrl;
  }
}
