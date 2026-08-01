import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type WidgetProps = {
  title: string;
  icon: LucideIcon;
  subtitle?: string;
  children: ReactNode;
  className?: string;
};

export function Widget({
  title,
  icon: Icon,
  subtitle,
  children,
  className,
}: WidgetProps) {
  return (
    <Card className={cn("gap-3 py-4", className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 px-4 pb-0">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Icon className="size-4 text-muted-foreground" aria-hidden />
            {title}
          </CardTitle>
          {subtitle ? (
            <CardDescription className="text-xs">{subtitle}</CardDescription>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="px-4">{children}</CardContent>
    </Card>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <p className="text-sm text-muted-foreground">{message}</p>;
}
