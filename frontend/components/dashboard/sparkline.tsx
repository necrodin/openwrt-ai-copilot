type SparklineProps = {
  data: number[];
  stroke?: string;
  className?: string;
};

/**
 * Lightweight SVG line chart for time-series data (bandwidth rates, etc.).
 * Normalizes the values to the view box and joins them with a polyline.
 */
export function Sparkline({ data, stroke = "currentColor", className }: SparklineProps) {
  const width = 100;
  const height = 28;

  if (data.length < 2) {
    return (
      <svg
        className={className}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        aria-hidden
      >
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke={stroke}
          strokeOpacity="0.2"
          strokeWidth="1"
        />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const points = data
    .map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y = height - ((value - min) / span) * (height - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden
    >
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
