import { IndicatorStyle, LineType, PolygonType } from "klinecharts";

export function getIndicatorLineStyle(): IndicatorStyle["lines"] {
  return [
    {
      style: LineType.Solid,
      smooth: false,
      size: 1,
      dashedValue: [2, 2],
      color: "#F7D471",
    },
    {
      style: LineType.Solid,
      smooth: false,
      size: 1,
      dashedValue: [2, 2],
      color: "#4BB9EB",
    },
    {
      style: LineType.Solid,
      smooth: false,
      size: 1,
      dashedValue: [2, 2],
      color: "#CB92FE",
    },
    {
      style: LineType.Solid,
      smooth: false,
      size: 1,
      dashedValue: [2, 2],
      color: "#E11D74",
    },
    {
      style: LineType.Solid,
      smooth: false,
      size: 1,
      dashedValue: [2, 2],
      color: "#01C5C4",
    },
  ];
}
export function getIndicatorBarStyle(): IndicatorStyle["bars"] {
  return [
    {
      style: PolygonType.Fill,
      borderStyle: LineType.Solid,
      borderSize: 1,
      borderDashedValue: [2, 2],
      upColor: "rgba(52, 190, 134, .4)",
      downColor: "rgba(232, 56, 83, .4)",
      noChangeColor: "rgba(52, 190, 134, .4)",
    },
  ];
}
