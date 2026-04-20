from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List


@dataclass
class DailyRecord:
    date: dt.date
    channel: str
    sku: str
    units_sold: int
    gross_sales: float
    ad_spend: float
    sessions: int
    orders: int
    returns: int


@dataclass
class InventoryRecord:
    sku: str
    available_stock: int
    reorder_point: int


@dataclass
class SkuSummary:
    sku: str
    yesterday_units: int
    yesterday_sales: float
    ad_spend: float
    conversion_rate: float
    aov: float
    return_rate: float
    trend: str
    trend_pct: float
    available_stock: int
    reorder_point: int
    days_of_cover: float
    inventory_risk: str


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def load_sales_records(csv_files: Iterable[Path]) -> List[DailyRecord]:
    records: List[DailyRecord] = []
    for file in csv_files:
        if not file.exists():
            continue
        with file.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(
                    DailyRecord(
                        date=parse_date(row["date"]),
                        channel=row["channel"],
                        sku=row["sku"],
                        units_sold=int(row["units_sold"]),
                        gross_sales=float(row["gross_sales"]),
                        ad_spend=float(row.get("ad_spend", 0) or 0),
                        sessions=int(row.get("sessions", 0) or 0),
                        orders=int(row.get("orders", 0) or 0),
                        returns=int(row.get("returns", 0) or 0),
                    )
                )
    return records


def load_inventory(path: Path) -> Dict[str, InventoryRecord]:
    inventory: Dict[str, InventoryRecord] = {}
    if not path.exists():
        return inventory
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            inventory[row["sku"]] = InventoryRecord(
                sku=row["sku"],
                available_stock=int(row["available_stock"]),
                reorder_point=int(row.get("reorder_point", 0) or 0),
            )
    return inventory


def classify_trend(yesterday_units: int, baseline_units: float) -> tuple[str, float]:
    if baseline_units <= 0 and yesterday_units > 0:
        return "上升", 100.0
    if baseline_units <= 0:
        return "持平", 0.0
    delta = (yesterday_units - baseline_units) / baseline_units * 100
    if delta >= 15:
        return "上升", delta
    if delta <= -15:
        return "下滑", delta
    return "持平", delta


def inventory_risk_level(available_stock: int, avg_daily_units: float, reorder_point: int) -> tuple[str, float]:
    if avg_daily_units <= 0:
        days_of_cover = float("inf")
    else:
        days_of_cover = available_stock / avg_daily_units

    if available_stock <= reorder_point or days_of_cover <= 3:
        return "高风险", days_of_cover
    if days_of_cover <= 7:
        return "中风险", days_of_cover
    return "低风险", days_of_cover


def build_summaries(records: List[DailyRecord], inventory: Dict[str, InventoryRecord], as_of_date: dt.date) -> List[SkuSummary]:
    yesterday = as_of_date - dt.timedelta(days=1)
    grouped: Dict[str, List[DailyRecord]] = defaultdict(list)
    for r in records:
        grouped[r.sku].append(r)

    summaries: List[SkuSummary] = []
    for sku, sku_rows in grouped.items():
        y_rows = [r for r in sku_rows if r.date == yesterday]
        if not y_rows:
            continue

        history_rows = [r for r in sku_rows if yesterday - dt.timedelta(days=7) <= r.date < yesterday]
        baseline = mean([r.units_sold for r in history_rows]) if history_rows else 0.0

        y_units = sum(r.units_sold for r in y_rows)
        y_sales = sum(r.gross_sales for r in y_rows)
        y_ad = sum(r.ad_spend for r in y_rows)
        y_sessions = sum(r.sessions for r in y_rows)
        y_orders = sum(r.orders for r in y_rows)
        y_returns = sum(r.returns for r in y_rows)

        conversion_rate = (y_orders / y_sessions) if y_sessions else 0.0
        aov = (y_sales / y_orders) if y_orders else 0.0
        return_rate = (y_returns / y_orders) if y_orders else 0.0

        trend, trend_pct = classify_trend(y_units, baseline)

        inv = inventory.get(sku, InventoryRecord(sku=sku, available_stock=0, reorder_point=0))
        avg_daily_units = mean([r.units_sold for r in history_rows + y_rows]) if (history_rows or y_rows) else 0.0
        risk, days_of_cover = inventory_risk_level(inv.available_stock, avg_daily_units, inv.reorder_point)

        summaries.append(
            SkuSummary(
                sku=sku,
                yesterday_units=y_units,
                yesterday_sales=y_sales,
                ad_spend=y_ad,
                conversion_rate=conversion_rate,
                aov=aov,
                return_rate=return_rate,
                trend=trend,
                trend_pct=trend_pct,
                available_stock=inv.available_stock,
                reorder_point=inv.reorder_point,
                days_of_cover=days_of_cover,
                inventory_risk=risk,
            )
        )

    summaries.sort(key=lambda x: x.yesterday_sales, reverse=True)
    return summaries


def render_email_md(report_date: dt.date, summaries: List[SkuSummary], output_path: Path) -> None:
    top_up = [s for s in summaries if s.trend == "上升"][:5]
    top_down = [s for s in summaries if s.trend == "下滑"][:5]
    top_risk = [s for s in summaries if s.inventory_risk != "低风险"][:5]

    lines = [
        f"# 昨日经营简报（{report_date.isoformat()}）",
        "",
        "## 1) 销量上升 SKU",
    ]
    if not top_up:
        lines.append("- 无明显上升 SKU")
    else:
        lines.extend([f"- {s.sku}: 销量 {s.yesterday_units}（{s.trend_pct:.1f}%）" for s in top_up])

    lines.extend(["", "## 2) 销量下滑 SKU"])
    if not top_down:
        lines.append("- 无明显下滑 SKU")
    else:
        lines.extend([f"- {s.sku}: 销量 {s.yesterday_units}（{s.trend_pct:.1f}%）" for s in top_down])

    lines.extend(["", "## 3) 缺货/低库存预警"])
    if not top_risk:
        lines.append("- 无库存风险 SKU")
    else:
        lines.extend([
            f"- {s.sku}: 库存 {s.available_stock}, 可售天数 {s.days_of_cover:.1f}, 风险 {s.inventory_risk}"
            for s in top_risk
        ])

    output_path.write_text("\n".join(lines), encoding="utf-8")


def export_internal_json(report_date: dt.date, summaries: List[SkuSummary], output_path: Path) -> None:
    payload = {
        "report_date": report_date.isoformat(),
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "summary": [s.__dict__ for s in summaries],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_excel_or_csv(summaries: List[SkuSummary], excel_path: Path, fallback_csv_path: Path) -> str:
    headers = list(SkuSummary.__annotations__.keys())
    try:
        from openpyxl import Workbook  # type: ignore

        wb = Workbook()
        ws = wb.active
        ws.title = "SKU日报"
        ws.append(headers)
        for s in summaries:
            ws.append([getattr(s, h) for h in headers])
        wb.save(excel_path)
        return f"Excel 已输出: {excel_path}"
    except Exception:
        with fallback_csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for s in summaries:
                writer.writerow([getattr(s, h) for h in headers])
        return f"openpyxl 不可用，已输出 CSV: {fallback_csv_path}"


def render_dashboard_html(report_date: dt.date, summaries: List[SkuSummary], output_path: Path) -> None:
    labels = [s.sku for s in summaries[:15]]
    sales = [s.yesterday_sales for s in summaries[:15]]

    rows = "\n".join(
        f"<tr><td>{s.sku}</td><td>{s.yesterday_units}</td><td>{s.yesterday_sales:.2f}</td><td>{s.ad_spend:.2f}</td>"
        f"<td>{s.conversion_rate:.2%}</td><td>{s.aov:.2f}</td><td>{s.return_rate:.2%}</td><td>{s.trend}</td>"
        f"<td>{s.inventory_risk}</td></tr>"
        for s in summaries
    )

    html = f"""<!doctype html>
<html lang=\"zh\">
<head>
  <meta charset=\"utf-8\" />
  <title>经营Dashboard {report_date.isoformat()}</title>
  <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 13px; }}
    th {{ background: #f3f3f3; }}
  </style>
</head>
<body>
  <h1>昨日经营Dashboard（{report_date.isoformat()}）</h1>
  <canvas id=\"salesChart\" height=\"100\"></canvas>
  <h2>SKU明细</h2>
  <table>
    <thead>
      <tr><th>SKU</th><th>销量</th><th>销售额</th><th>广告花费</th><th>转化率</th><th>客单价</th><th>退货率</th><th>趋势</th><th>库存风险</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

<script>
new Chart(document.getElementById('salesChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(labels, ensure_ascii=False)},
    datasets: [{{
      label: '昨日销售额',
      data: {json.dumps(sales)},
      backgroundColor: '#4f46e5'
    }}]
  }},
  options: {{plugins: {{legend: {{display: false}}}}}}
}});
</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def run(input_dir: Path, output_dir: Path, as_of_date: dt.date) -> List[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sales_files = [
        input_dir / "amazon_sales.csv",
        input_dir / "shopify_sales.csv",
        input_dir / "ebay_sales.csv",
    ]
    records = load_sales_records(sales_files)
    inventory = load_inventory(input_dir / "inventory.csv")

    summaries = build_summaries(records, inventory, as_of_date)
    report_date = as_of_date - dt.timedelta(days=1)
    stamp = report_date.strftime("%Y%m%d")

    messages = []
    messages.append(
        export_excel_or_csv(
            summaries,
            output_dir / f"report_{stamp}.xlsx",
            output_dir / f"report_{stamp}.csv",
        )
    )

    html_path = output_dir / f"dashboard_{stamp}.html"
    render_dashboard_html(report_date, summaries, html_path)
    messages.append(f"网页图表已输出: {html_path}")

    email_path = output_dir / f"email_{stamp}.md"
    render_email_md(report_date, summaries, email_path)
    messages.append(f"邮件内容已输出: {email_path}")

    json_path = output_dir / f"internal_report_{stamp}.json"
    export_internal_json(report_date, summaries, json_path)
    messages.append(f"内部报表已输出: {json_path}")
    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description="多平台经营 Dashboard 生成器")
    parser.add_argument("--input-dir", default="data", type=Path)
    parser.add_argument("--output-dir", default="outputs", type=Path)
    parser.add_argument("--as-of-date", default=dt.date.today().isoformat())
    args = parser.parse_args()

    as_of_date = parse_date(args.as_of_date)
    messages = run(args.input_dir, args.output_dir, as_of_date)
    print("\n".join(messages))


if __name__ == "__main__":
    main()
