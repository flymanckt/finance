#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
import socket
import time
from datetime import datetime
from pathlib import Path

ROOT = Path('/home/kent/.openclaw/workspace/stock-agent')
POSITIONS_JSON = ROOT / 'positions.json'
WATCHLIST_JSON = ROOT / 'watchlist.json'
LEDGER_MD = ROOT / 'review-ledger-live.md'
CACHE_JSON = ROOT / 'runtime' / 'last_snapshot.json'

socket.setdefaulttimeout(15)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def http_get(url, retry=3):
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            if i < retry - 1:
                time.sleep(1)
                continue
            return {'error': str(e)}
    return {'error': 'max retry'}


def secid(code):
    return f"1.{code}" if code.startswith(('5', '6')) else f"0.{code}"


def get_quote(code):
    url = f"https://push2.eastmoney.com/api/qt/stock/get?fltt=2&invt=2&fields=f43,f44,f45,f46,f47,f48,f57,f58,f116,f117,f162,f168,f170&secid={secid(code)}"
    data = http_get(url, retry=5)
    if data.get('error') or not data.get('data'):
        return {'error': data.get('error', 'no data')}
    d = data['data']

    def norm_price(v):
        try:
            return round(float(v), 3)
        except Exception:
            return None

    def norm_pct(v):
        try:
            return round(float(v), 2)
        except Exception:
            return None

    return {
        'price': norm_price(d.get('f43')),
        'high': norm_price(d.get('f44')),
        'low': norm_price(d.get('f45')),
        'open': norm_price(d.get('f46')),
        'volume': d.get('f47'),
        'amount': d.get('f48'),
        'turnover': norm_pct(d.get('f168')),
        'changePct': norm_pct(d.get('f170')),
    }


def get_indices():
    url = 'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&fields=f2,f3,f12,f14&secids=1.000001,0.399001,0.399006,1.000688'
    data = http_get(url)
    result = []
    for item in data.get('data', {}).get('diff', []) or []:
        result.append({
            'name': item.get('f14'),
            'price': round(float(item.get('f2', 0)), 2) if item.get('f2') is not None else None,
            'changePct': round(float(item.get('f3', 0)), 2) if item.get('f3') is not None else None,
        })
    return result


def market_bias(indices):
    if not indices:
        return '未知'
    vals = [x['changePct'] for x in indices if isinstance(x.get('changePct'), (int, float))]
    if not vals:
        return '未知'
    avg = sum(vals) / len(vals)
    if avg >= 1.2:
        return '偏多'
    if avg >= 0.2:
        return '中性偏多'
    if avg > -0.5:
        return '中性'
    if avg > -1.2:
        return '中性偏空'
    return '偏空'


def build_position_alerts(positions, last_snapshot):
    alerts = []
    current_snapshot = {}
    for p in positions:
        quote = get_quote(p['symbol'])
        time.sleep(0.3)
        current_snapshot[p['symbol']] = quote
        if quote.get('error'):
            alerts.append({
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '中',
                'action': '观察',
                'summary': f"{p['name']} 行情获取失败：{quote['error']}"
            })
            continue

        price = quote.get('price')
        pct = quote.get('changePct')
        stop = p.get('hardStop')
        last_price = (last_snapshot.get(p['symbol']) or {}).get('price')

        if price is not None and stop is not None and price <= stop:
            alerts.append({
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '高',
                'action': '减仓/止损',
                'summary': f"{p['name']} 现价 {price} 已接近或跌破硬止损 {stop}，优先防守。"
            })
        elif pct is not None and pct <= -5:
            alerts.append({
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '中',
                'action': '重点观察',
                'summary': f"{p['name']} 当日跌幅 {pct}% ，需警惕弱势延续。"
            })
        elif pct is not None and pct >= 5:
            alerts.append({
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '中',
                'action': '观察/分批止盈',
                'summary': f"{p['name']} 当日涨幅 {pct}% ，若冲高回落需防兑现。"
            })
        elif last_price and price and abs(price - last_price) / last_price >= 0.03:
            direction = '上行' if price > last_price else '下行'
            alerts.append({
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '低',
                'action': '观察',
                'summary': f"{p['name']} 较上次快照明显{direction}，现价 {price}。"
            })
    return alerts, current_snapshot


def format_message(mode, indices, bias, alerts, positions):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"【Finance {mode}】{now}", f"市场环境：{bias}"]
    if indices:
        idx_line = '；'.join([f"{x['name']} {x['changePct']}%" for x in indices if x.get('changePct') is not None])
        lines.append(f"指数：{idx_line}")

    if mode == '盘前':
        lines.append('持仓计划：')
        for p in positions:
            lines.append(f"- {p['name']}({p['symbol']})：硬止损 {p.get('hardStop')}，优先按纪律处理")

    if alerts:
        lines.append('重点变化：')
        for a in alerts[:6]:
            lines.append(f"- {a['name']}：{a['summary']} | 建议：{a['action']} | 风险：{a['level']}")
    else:
        lines.append('重点变化：暂无显著增量信号，维持原计划。')

    lines.append('原则：先风险，后机会；持仓优先。')
    return '\n'.join(lines)


def append_ledger(mode, alerts):
    if not alerts:
        return
    LEDGER_MD.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_MD.exists():
        LEDGER_MD.write_text('# 实时复盘台账\n\n', encoding='utf-8')
    with LEDGER_MD.open('a', encoding='utf-8') as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} {mode}\n")
        for a in alerts:
            f.write(f"- {a['symbol']} {a['name']} | 建议：{a['action']} | 风险：{a['level']} | {a['summary']}\n")


def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else '巡检'
    positions_data = load_json(POSITIONS_JSON, {'positions': []})
    positions = positions_data.get('positions', [])
    last_snapshot = load_json(CACHE_JSON, {})
    indices = get_indices()
    bias = market_bias(indices)
    alerts, current_snapshot = build_position_alerts(positions, last_snapshot)
    msg = format_message(mode, indices, bias, alerts, positions)
    append_ledger(mode, alerts)
    save_json(CACHE_JSON, current_snapshot)
    print(msg)


if __name__ == '__main__':
    main()
