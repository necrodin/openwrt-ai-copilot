# Sprint 29 — Open Source Identity & Project Branding

## Objective

Transform the project from a prototype into a professional open-source product
with complete branding, repository integration, version information, licensing,
and community support links — **without touching the backend APIs**, and
**without breaking router onboarding, discovery, telemetry, or the dashboard**
(Sprints 27 and 28 remain intact).

The project stays completely free and open source: there are **no
subscriptions, no license checks, no paywalls, and no in-app payment
processing**. Donations are purely external links; unconfigured targets render
as "Not configured" rather than pointing at invented addresses.

## Scope guards honored

- **Backend untouched.** No API signature, route, or response shape changed.
- **Onboarding preserved.** The wizard, SSH connection test, and Save Router
  flow are unchanged apart from using the new `Logo` mark and a page footer.
- **Dashboard / telemetry preserved.** Widgets and data layer are untouched.
- **No mock data.** The About/Support pages render only config + live backend
  health; nothing is fabricated.
- **No invented donation URLs.** Any donation target without a configured URL
  shows as "Not configured" instead of linking somewhere fake.

## Architecture

### Brand assets (static files)

| Asset | Path | Purpose |
| --- | --- | --- |
| Logo mark | `frontend/public/logo.svg` | Brand mark (themed ink + gradient globe) |
| Favicon | `frontend/public/favicon.svg` | Browser tab icon |
| App icon | `frontend/public/app-icon.svg` | PWA / Apple touch icon |
| Web manifest | `frontend/public/manifest.webmanifest` | PWA metadata |
| README banner | `assets/banner.svg` | Repo README hero |
| README logo | `assets/logo.svg` | Repo README logo |
| Screenshot placeholder | `assets/screenshots/placeholder.svg` | README screenshots slot |
| Architecture placeholder | `assets/architecture/placeholder.svg` | README architecture slot |

### Reusable logo component

`frontend/components/ui/logo.tsx` provides `<Logo />` and an exported `<Mark />`.
The mark is an **inline SVG** that inherits `currentColor`, so it themes with
dark/light mode and scales at any size. `<Logo withText />` renders the
wordmark. Used across the sidebar, the landing page, and onboarding.

## Configuration

The single source of truth is `frontend/lib/site-config.ts`, which reads
`NEXT_PUBLIC_*` environment variables and falls back to safe defaults:

| Category | Keys |
| --- | --- |
| Branding | `NEXT_PUBLIC_APP_NAME`, `NEXT_PUBLIC_APP_TAGLINE`, `NEXT_PUBLIC_APP_DESCRIPTION`, `NEXT_PUBLIC_COMPANY_NAME`, `NEXT_PUBLIC_AUTHOR`, `NEXT_PUBLIC_LICENSE` |
| Versioning | `NEXT_PUBLIC_APP_VERSION`, `NEXT_PUBLIC_FRONTEND_VERSION`, `NEXT_PUBLIC_GIT_COMMIT`, `NEXT_PUBLIC_BUILD_DATE`, `NEXT_PUBLIC_ENVIRONMENT`, `NEXT_PUBLIC_APP_URL` |
| Repository | `NEXT_PUBLIC_REPOSITORY_URL`, `NEXT_PUBLIC_DOCUMENTATION_URL`, `NEXT_PUBLIC_ISSUES_URL`, `NEXT_PUBLIC_RELEASES_URL`, `NEXT_PUBLIC_DISCUSSIONS_URL`, `NEXT_PUBLIC_WIKI_URL`, `NEXT_PUBLIC_ROADMAP_URL`, `NEXT_PUBLIC_CHANGELOG_URL` |
| Socials | `NEXT_PUBLIC_SOCIAL_GITHUB`, `NEXT_PUBLIC_SOCIAL_OPENWRT` |
| Donations | `NEXT_PUBLIC_DONATE_GITHUB`, `NEXT_PUBLIC_DONATE_BUYMEACOFFEE`, `NEXT_PUBLIC_DONATE_KOFI`, `NEXT_PUBLIC_DONATE_PAYPAL`, `NEXT_PUBLIC_DONATE_AMAZON`, `NEXT_PUBLIC_DONATE_BITCOIN`, `NEXT_PUBLIC_DONATE_ETHEREUM`, `NEXT_PUBLIC_DONATE_LIGHTNING` |

All donation variables default to **empty** — the UI shows "Not configured"
until a maintainer supplies a real URL.

`frontend/lib/version.ts` is the centralized **version module**:

- `getFrontendVersionInfo()` — synchronous, build-time stamped set (app version,
  frontend version, git commit short hash, build date, environment).
- `fetchBackendVersion()` — fetches the live backend version from
  `GET /api/v1/health` (already-exposed endpoint; the backend was not modified),
  with a graceful "unavailable" fallback.

`githubUrl()` maps repository sections (repo/issues/releases/discussions/wiki) to
their configured URLs so every GitHub button reuses the single configured
repository.

## Footer

`frontend/components/layout/footer.tsx` renders on every page:

- **Brand block** — Logo + product name + tagline.
- **Project links** — About, Support Development, Roadmap, Changelog.
- **Community links** — GitHub, Issues, Discussions, Documentation.
- **Powered-by strip** — Necrodin, OpenWrt, FastAPI, Next.js, TailwindCSS.
- **Meta row** — MIT license notice, current version, current build (git commit
  or build date), GitHub Repository link.

The footer is added to the console shell (`app-shell.tsx`), the landing page
(`app/page.tsx`), and onboarding. All links open in new tabs where external.

## Sidebar additions

`frontend/components/layout/sidebar-open-source.tsx` is pinned to the bottom of
the sidebar, above the collapse toggle:

- A **version pill** ("Open Source · vX.Y.Z") linking to `/about`.
- **GitHub**, **Documentation**, **Report Issue**, **Roadmap**, **License**
  (`/about#license`), **Donate** (`/support`), and **About**.

In the collapsed sidebar it renders icon-only with `aria-label`/`title` tooltips
for accessibility.

## About page

`frontend/app/(console)/about/page.tsx` displays:

- Project Name, Version, Frontend Version, Backend Version (live from health),
  Git Commit (when available), Build Date, Environment.
- License (MIT, with a summary), Author, Company, Contributors.
- Resources: Repository, Documentation, Roadmap, Changelog, Report an Issue,
  Support Development — via the shared `LinkButton`.

Backend version is fetched client-side from the existing health endpoint and
falls back gracefully when the backend is down.

## Donation system

`frontend/app/(console)/support/page.tsx` ("Support Development") lists the
eight donation targets (GitHub Sponsors, Buy Me a Coffee, Ko-fi, PayPal, Amazon
Gift Card, Bitcoin, Ethereum, Lightning Network) from the single
`site-config.ts` file. Each target either:

- opens its configured external URL in a new tab, or
- renders a disabled **"Not configured"** state when no URL is supplied.

There is no licensing, no subscription, and no payment processing anywhere in
the application.

## Professional polish

- **Spacing & typography** — consistent `max-w` containers, vertical rhythm,
  proper heading scales, and muted body text across the new pages.
- **Responsive** — grids collapse to a single column on mobile (`sm:` /
  `md:` breakpoints); the sidebar footer collapses to icon-only.
- **Accessibility** — `aria-label`s on icon-only links, `aria-hidden` on
  decorative icons, `role="note"` on unconfigured donation states, semantic
  `<nav>`/`<footer>`, and an `sr-only` page heading on the landing hero.
- **Dark mode** — the inline `Mark` inherits `currentColor`; all containers use
  theme tokens (`bg-background`, `text-foreground`, `bg-muted`, …), so the new
  components adapt automatically to dark mode.

## License

A standard **MIT** `LICENSE` file was added at the repository root
(`Copyright (c) 2026 Necrodin and other contributors`). The About page renders
the license text; the README and footer reference the MIT license.

## Files changed

### New

- `frontend/components/ui/logo.tsx`
- `frontend/components/ui/link-button.tsx`
- `frontend/components/layout/footer.tsx`
- `frontend/components/layout/sidebar-open-source.tsx`
- `frontend/app/(console)/about/page.tsx`
- `frontend/app/(console)/support/page.tsx`
- `frontend/lib/site-config.ts`
- `frontend/lib/version.ts`
- `frontend/public/logo.svg`, `frontend/public/favicon.svg`, `frontend/public/app-icon.svg`, `frontend/public/manifest.webmanifest`
- `assets/banner.svg`, `assets/logo.svg`
- `assets/screenshots/placeholder.svg`, `assets/architecture/placeholder.svg`
- `LICENSE`
- `docs/SPRINT-29.md`

### Modified

- `frontend/app/layout.tsx` — metadataBase, full metadata, web-app icons.
- `frontend/app/page.tsx` — logo hero + footer.
- `frontend/app/onboarding/page.tsx` — logo + footer.
- `frontend/components/layout/app-shell.tsx` — footer in the console shell.
- `frontend/components/layout/sidebar.tsx` — logo header + open-source section.
- `frontend/.env.example` — new `NEXT_PUBLIC_*` configuration.
- `README.md` — banner, feature badges, screenshots/architecture placeholders,
  license update.