"use client";

import {
  BookOpenText,
  Building2,
  Code2,
  FileText,
  GitBranch,
  Github,
  GitCommitHorizontal,
  Heart,
  Map,
  Package,
  Scale,
  Server,
  User,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LinkButton } from "@/components/ui/link-button";
import { SITE_CONFIG } from "@/lib/site-config";
import {
  fetchBackendVersion,
  getFrontendVersionInfo,
} from "@/lib/version";

const contributors = [
  { name: "Necrodin", role: "Maintainer" },
];

type FieldRowProps = {
  icon: LucideIcon;
  label: string;
  children: React.ReactNode;
};

function FieldRow({ icon: Icon, label, children }: FieldRowProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="flex items-center gap-2 text-muted-foreground">
        <Icon className="size-4" aria-hidden />
        {label}
      </dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}

export default function AboutPage() {
  const info = getFrontendVersionInfo();
  const [backend, setBackend] = useState<{
    version: string;
    service: string;
    environment: string;
  } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchBackendVersion(controller.signal).then((value) =>
      setBackend({ version: value.version, service: value.service, environment: value.environment }),
    );
    return () => controller.abort();
  }, []);

  const resources = [
    { label: "Repository", href: SITE_CONFIG.repositoryUrl, icon: Github },
    { label: "Documentation", href: SITE_CONFIG.documentationUrl, icon: BookOpenText },
    { label: "Roadmap", href: SITE_CONFIG.roadmapUrl, icon: Map },
    { label: "Changelog", href: SITE_CONFIG.changelogUrl, icon: FileText },
    { label: "Report an Issue", href: SITE_CONFIG.issuesUrl, icon: Code2 },
    { label: "Support Development", href: "/support", icon: Heart },
  ];

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 p-6 sm:p-10">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">About</h1>
        <p className="max-w-2xl text-muted-foreground">
          {SITE_CONFIG.description}
        </p>
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Package className="size-4" aria-hidden />
              Version Information
            </CardTitle>
            <CardDescription>Build identity for this deployment.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 text-sm">
              <FieldRow icon={Building2} label="Project">
                {info.appName}
              </FieldRow>
              <FieldRow icon={Package} label="Version">
                {backend ? backend.version : info.version || "N/A"}
              </FieldRow>
              <FieldRow icon={Code2} label="Frontend Version">
                {info.frontendVersion || "N/A"}
              </FieldRow>
              <FieldRow icon={Server} label="Backend Version">
                {backend ? backend.version : "…"}
              </FieldRow>
              <FieldRow icon={GitCommitHorizontal} label="Git Commit">
                {info.gitCommit ? (
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                    {info.gitCommit}
                  </code>
                ) : (
                  <span className="text-muted-foreground">N/A</span>
                )}
              </FieldRow>
              <FieldRow icon={GitBranch} label="Build Date">
                {info.buildDate || "N/A"}
              </FieldRow>
              <FieldRow icon={Code2} label="Environment">
                {info.environment}
              </FieldRow>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Scale className="size-4" aria-hidden />
              License &amp; Authors
            </CardTitle>
            <CardDescription>Who built it and how it is licensed.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 text-sm">
              <FieldRow icon={Scale} label="License">
                <Badge variant="outline">{SITE_CONFIG.license}</Badge>
              </FieldRow>
              <FieldRow icon={User} label="Author">
                {SITE_CONFIG.author}
              </FieldRow>
              <FieldRow icon={Building2} label="Company">
                {SITE_CONFIG.company}
              </FieldRow>
              <FieldRow icon={Users} label="Contributors">
                <span>
                  {contributors.map((contributor) => contributor.name).join(", ")}
                </span>
              </FieldRow>
            </dl>
            <div id="license" className="mt-6 rounded-md border bg-muted/40 p-4 text-xs leading-relaxed text-muted-foreground">
              <p className="mb-2 font-semibold text-foreground">
                {SITE_CONFIG.license}
              </p>
              <p>
                This software is provided for personal, non-commercial use only.
                Commercial use, selling the software, and offering it as a paid
                service are prohibited. Modification for personal use is
                allowed; redistribution for non-commercial purposes is allowed
                only if the license and attribution remain intact. See the
                <a href={SITE_CONFIG.repositoryUrl} target="_blank" rel="noreferrer" className="ml-1 underline">
                  LICENSE
                </a>
                {" "}file in the repository for the full terms.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpenText className="size-4" aria-hidden />
            Resources
          </CardTitle>
          <CardDescription>
            Explore the repository, contribute, or support development.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            {resources.map((resource) => (
              <LinkButton
                key={resource.label}
                href={resource.href}
                external={resource.href.startsWith("http")}
                variant="outline"
                icon={resource.icon}
              >
                {resource.label}
              </LinkButton>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
