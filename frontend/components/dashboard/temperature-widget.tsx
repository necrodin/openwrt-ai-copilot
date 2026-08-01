import { Thermometer } from "lucide-react";

import type { TemperatureReading } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = { temperature: TemperatureReading[] };

function toneClass(celsius: number): string {
  if (celsius >= 75) {
    return "bg-red-500 text-white";
  }
  if (celsius >= 60) {
    return "bg-amber-500 text-white";
  }
  return "bg-emerald-500 text-white";
}

export function TemperatureWidget({ temperature }: Props) {
  if (temperature.length === 0) {
    return (
      <Widget title="Temperature" icon={Thermometer}>
        <EmptyState message="No temperature sensors found." />
      </Widget>
    );
  }

  return (
    <Widget title="Temperature" icon={Thermometer} subtitle={`${temperature.length} sensors`}>
      <ul className="space-y-2">
        {temperature.map((reading) => (
          <li
            key={reading.zone}
            className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{reading.zone}</p>
            </div>
            <span
              className={cn(
                "shrink-0 rounded-md px-2 py-1 text-sm font-semibold tabular-nums",
                toneClass(reading.temperature_c),
              )}
            >
              {reading.temperature_c.toFixed(1)}°C
            </span>
          </li>
        ))}
      </ul>
    </Widget>
  );
}
