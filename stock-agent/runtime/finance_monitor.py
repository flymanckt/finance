#!/usr/bin/env python3
import json
import urllib.request
import socket
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path('/home/kent/.openclaw/workspace/stock-agent')
POSITIONS_JSON = ROOT / 'positions.json'
WATCHLIST_JSON = ROOT / 'watchlist.json'
LEDGER_MD = ROOT / 'review-ledger-live.md'
CACHE_JSON = ROOT / 'runtime' / 'last_snapshot.json'
ALERT_STATE_JSON = ROOT / 'runtime' / 'alert_state.json'
RUNTIME_CONFIG_JSON = ROOT / 'runtime' / 'runtime_config.json'

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


def alert_key(kind, symbol, action, summary):
    raw = f"{kind}|{symbol}|{action}|{summary}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def should_send_alert(state, key, dedup_minutes):
    now = datetime.now()
    last = state.get('lastSent', {}).get(key)
    if not last:
        return True
    try:
        ts = datetime.fromisoformat(last)
    except Exception:
        return True
    return now - ts >= timedelta(minutes=dedup_minutes)


def mark_sent(state, key):
    state.setdefault('lastSent', {})[key] = datetime.now().isoformat()


def build_position_alerts(positions, last_snapshot, config):
    alerts = []
    current_snapshot = {}
    for p in positions:
        quote = get_quote(p['symbol'])
        time.sleep(0.3)
        current_snapshot[p['symbol']] = quote
        if quote.get('error'):
            alerts.append({
                'kind': 'position',
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
                'kind': 'position',
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '高',
                'action': '减仓/止损',
                'summary': f"{p['name']} 现价 {price} 已接近或跌破硬止损 {stop}，优先防守。"
            })
        elif pct is not None and pct <= config.get('dropAlertPct', -5):
            alerts.append({
                'kind': 'position',
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '中',
                'action': '重点观察',
                'summary': f"{p['name']} 当日跌幅 {pct}% ，需警惕弱势延续。"
            })
        elif pct is not None and pct >= config.get('surgeAlertPct', 5):
            alerts.append({
                'kind': 'position',
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '中',
                'action': '观察/分批止盈',
                'summary': f"{p['name']} 当日涨幅 {pct}% ，若冲高回落需防兑现。"
            })
        elif last_price and price and abs(price - last_price) / last_price * 100 >= config.get('priceMoveThresholdPct', 3):
            direction = '上行' if price > last_price else '下行'
            alerts.append({
                'kind': 'position',
                'symbol': p['symbol'],
                'name': p['name'],
                'level': '低',
                'action': '观察',
                'summary': f"{p['name']} 较上次快照明显{direction}，现价 {price}。"
            })
    return alerts[:config.get('positionMaxAlerts', 6)], current_snapshot


def build_watchlist_alerts(items, config):
    alerts = []
    for item in items:
        quote = get_quote(item['symbol'])
        time.sleep(0.3)
        if quote.get('error'):
            continue
        price = quote.get('price')
        pct = quote.get('changePct')
        stop = item.get('stop')
        priority = item.get('priority', 'C')
        if priority == 'A' and pct is not None and pct >= 5:
            alerts.append({
                'kind': 'watchlist',
                'symbol': item['symbol'],
                'name': item['name'],
                'level': '中',
                'action': '重点观察',
                'summary': f"观察池 {item['name']} 涨幅 {pct}% ，事件驱动逻辑正在强化，留意是否放量承接。"
            })
        elif stop is not None and price is not None and price <= stop:
            alerts.append({
                'kind': 'watchlist',
                'symbol': item['symbol'],
                'name': item['name'],
                'level': '中',
                'action': '移出观察/谨慎',
                'summary': f"观察池 {item['name']} 现价 {price} 接近/跌破观察止损 {stop}，逻辑需重审。"
            })
    return alerts[:config.get('watchlistMaxAlerts', 3)]


def dedup_alerts(alerts, state, config):
    kept = []
    dedup_minutes = config.get('dedupMinutes', state.get('dedupMinutes', 120))
    for a in alerts:
        key = alert_key(a['kind'], a['symbol'], a['action'], a['summary'])
        if should_send_alert(state, key, dedup_minutes):
            kept.append(a)
            mark_sent(state, key)
    return kept


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

    if mode == '收盘':
        lines.append('收盘要求：先看风控执行，再看明日预案。')

    if alerts:
        lines.append('重点变化：')
        for a in alerts:
            prefix = '持仓' if a['kind'] == 'position' else '观察池'
            lines.append(f"- [{prefix}] {a['name']}：{a['summary']} | 建议：{a['action']} | 风险：{a['level']}")
    else:
        lines.append('重点变化：暂无显著增量信号，维持原计划。')

    lines.append('原则：先风险，后机会；持仓优先。')
    return '\n'.join(lines)


def append_ledger(mode, alerts, bias):
    LEDGER_MD.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_MD.exists():
        LEDGER_MD.write_text('# 实时复盘台账\n\n', encoding='utf-8')
    with LEDGER_MD.open('a', encoding='utf-8') as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} {mode} | 市场环境：{bias}\n")
        if not alerts:
            f.write('- 无显著增量信号，维持原计划。\n')
            return
        for a in alerts:
            f.write(f"- [{a['kind']}] {a['symbol']} {a['name']} | 建议：{a['action']} | 风险：{a['level']} | {a['summary']}\n")


def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else '巡检'
    config = load_json(RUNTIME_CONFIG_JSON, {})
    state = load_json(ALERT_STATE_JSON, {'lastSent': {}, 'dedupMinutes': 120, 'version': 1})
    positions_data = load_json(POSITIONS_JSON, {'positions': []})
    watchlist_data = load_json(WATCHLIST_JSON, {'items': []})
    positions = positions_data.get('positions', [])
    watch_items = watchlist_data.get('items', [])
    last_snapshot = load_json(CACHE_JSON, {})
    indices = get_indices()
    bias = market_bias(indices)
    position_alerts, current_snapshot = build_position_alerts(positions, last_snapshot, config)
    watchlist_alerts = build_watchlist_alerts(watch_items, config)
    alerts = dedup_alerts(position_alerts + watchlist_alerts, state, config)
    msg = format_message(mode, indices, bias, alerts, positions)
    append_ledger(mode, alerts, bias)
    save_json(CACHE_JSON, current_snapshot)
    save_json(ALERT_STATE_JSON, state)
    print(msg)


if __name__ == '__main__':
    main()
