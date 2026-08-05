"use client";

import { Coffee, ExternalLink, Heart, Sparkles } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LinkButton } from "@/components/ui/link-button";
import { SITE_CONFIG } from "@/lib/site-config";

export default function SupportPage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 p-6 sm:p-10">
      <div className="flex items-start gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Heart className="size-6" aria-hidden />
        </span>
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">
            Support Development
          </h1>
          <p className="max-w-2xl text-muted-foreground">
            {SITE_CONFIG.name} is completely free and open source. If you find
            it useful, consider supporting the maintainers so we can keep
            building, fixing bugs, and shipping new features. There are no
            subscriptions, no licenses, and no payments inside the app — every
            option below simply opens an external site.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Coffee className="size-4" aria-hidden />
            Ways to support
          </CardTitle>
          <CardDescription>
            Choose any option — every link opens in a new tab.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            {SITE_CONFIG.donations.map((target) => (
              <div
                key={target.id}
                className="flex flex-col rounded-lg border p-4 transition-colors hover:bg-muted/40"
              >
                <p className="font-semibold">{target.label}</p>
                <p className="mt-1 flex-1 text-sm text-muted-foreground">
                  {target.description}
                </p>
                {target.url ? (
                  <LinkButton
                    href={target.url}
                    external
                    variant="outline"
                    className="mt-3"
                    icon={ExternalLink}
                  >
                    Open
                  </LinkButton>
                ) : (
                  <span
                    className="mt-3 inline-flex h-9 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground"
                    role="note"
                  >
                    Not configured
                  </span>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="flex items-start gap-3 rounded-xl border bg-muted/30 p-5 text-sm text-muted-foreground">
        <Sparkles className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>
          Donations are optional and purely a thank-you. The project will
          always remain free and open source under the{" "}
          <span className="font-medium text-foreground">
            {SITE_CONFIG.license}
          </span>{" "}
          license — for everyone, forever.
        </p>
      </div>
    </div>
  );
}
