# Internal Sales Dashboard Generator

这个项目提供一个可自动化执行的内部经营 Dashboard 流水线，按天汇总 Amazon / Shopify / eBay 数据，识别异常 SKU 和库存风险，并导出多种报告格式。

## 功能

- 每日自动汇总多平台销售数据（Amazon / Shopify / eBay）
- 识别销量上升 / 下滑 SKU（对比近 7 天均值）
- 分析广告花费、转化率、客单价、退货率
- 输出缺货风险与低库存预警（按可售天数 + Reorder Point）
- 自动生成：
  - 昨日经营简报（Markdown 邮件内容）
  - 内部 JSON 报表
  - 网页图表 Dashboard（HTML）
  - Excel（若 `openpyxl` 不可用则自动回退 CSV）

## 数据输入

放在 `data/` 目录：

- `amazon_sales.csv`
- `shopify_sales.csv`
- `ebay_sales.csv`
- `inventory.csv`

销售 CSV 字段：

- `date` (`YYYY-MM-DD`)
- `channel`
- `sku`
- `units_sold`
- `gross_sales`
- `ad_spend`
- `sessions`
- `orders`
- `returns`

库存 CSV 字段：

- `sku`
- `available_stock`
- `reorder_point`

## 运行

```bash
python3 dashboard.py --input-dir data --output-dir outputs --as-of-date 2026-04-20
```

`--as-of-date` 是系统运行日，程序会生成 “前一天” 的经营报告。

## 输出

输出到 `outputs/`：

- `report_YYYYMMDD.xlsx` 或 `report_YYYYMMDD.csv`
- `dashboard_YYYYMMDD.html`
- `email_YYYYMMDD.md`
- `internal_report_YYYYMMDD.json`

## 自动调度（Cron）

每天北京时间 08:00 生成前一天报告（UTC 00:00）：

```cron
0 0 * * * /usr/bin/python3 /path/to/repo/dashboard.py --input-dir /path/to/repo/data --output-dir /path/to/repo/outputs
```

## 测试

```bash
python3 -m pytest -q
```
