---
name: calendar
description: "已合并到 /schedule。Redirects to /schedule for all calendar and catalyst management."
metadata:
  version: 3.0.0
  deprecated: true
  redirect: schedule
---

# /calendar → 已合并到 /schedule

所有催化剂日历功能已合并到 `/schedule` skill。

## 命令映射

| 旧命令 | 新命令 |
|--------|--------|
| `/calendar` | `/schedule events` |
| `/calendar next month` | `/schedule events next month` |
| `/calendar add TICKER "event"` | `/schedule add TICKER "event"` |
| `/calendar archive` | `/schedule archive` |
| `/calendar export` | `/schedule import` (直接推送 Google Calendar) |
| `/calendar calibration` | `/schedule calibration` |

## 请使用 `/schedule`

```
/schedule import              FactSet 数据 → Google Calendar
/schedule events              查看催化剂日历
/schedule add TICKER "event"  手动添加
/schedule archive             归档过期催化剂
/schedule calibration         预测校准统计
/schedule plan                交互式周计划
```
