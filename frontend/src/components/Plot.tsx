import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import { useTheme } from "../theme";

interface Props {
  data: Array<Record<string, unknown>>;
  layout?: Record<string, unknown>;
  height?: number;
}

function baseLayout(dark: boolean): Record<string, unknown> {
  return dark
    ? {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(15,23,42,0.4)",
        font: { color: "#cbd5e1", size: 11 },
        margin: { l: 55, r: 20, t: 40, b: 45 },
        xaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
        yaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
      }
    : {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(255,255,255,0)",
        font: { color: "#3d3d3a", size: 11 },
        margin: { l: 55, r: 20, t: 40, b: 45 },
        xaxis: { gridcolor: "#e6e6df", zerolinecolor: "#d4d4cd" },
        yaxis: { gridcolor: "#e6e6df", zerolinecolor: "#d4d4cd" },
      };
}

export default function Plot({ data, layout = {}, height = 380 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useTheme(); // repaints Plotly on theme toggle without a remount

  useEffect(() => {
    if (!ref.current) return;
    const dark = theme === "dark";
    Plotly.react(
      ref.current,
      data,
      { ...baseLayout(dark), ...layout, height },
      { responsive: true, displaylogo: false, displayModeBar: true },
    );
  }, [data, layout, height, theme]);

  return <div ref={ref} className="w-full" style={{ minHeight: height }} />;
}
