#!/usr/bin/env python3
"""Maintenance notifications only: no TDX credentials, requests or source logs."""
import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FAILURE_KEY = '<!-- tsingbus-transit-sync-failure -->'
MONITOR_FAILURE_KEY = '<!-- tsingbus-transit-monitor-failure -->'
FEED_STALE_KEY = '<!-- tsingbus-transit-feed-stale -->'
ALERTS_STALE_KEY = '<!-- tsingbus-transit-alerts-stale -->'
# A route that vanished from TDX gets one more scheduled sync (~12 h) before anyone is notified.
ROUTE_STALE_NOTIFY_HOURS = 10
FEED_STALE_HOURS = 30
# Failed step name prefix in transit-sync.yml -> human explanation (step names are API metadata, not logs).
FAILURE_EXPLANATIONS = {
    '失敗：官方 API 暫時異常': 'TDX 連線或回應異常，已自動重試兩輪仍失敗。通常稍後會自行恢復；若連續發生請檢查 TDX 狀態與 Secrets。',
    '失敗：官方資料缺漏': 'TDX 一次缺少太多路線（或缺少沒有可保留版本的路線），已拒收整份資料並保留上一版。',
    '失敗：資料內容錯誤': '官方資料內容不通過驗證（站序、時刻、業者配對等），已停止發布並保留上一版。',
    '失敗：官方資料規格變更': '路線代號、業者或站點與已審核內容不一致，需要人工確認後更新白名單，不可自動猜測。',
    '失敗：設定或日曆': 'Secrets 被拒或假日日曆過期，需人工處理。',
    '提交並推送': 'Git 推送在安全重試後仍失敗（可能是並行修改），資料沒有發布。',
    '發布後複檢': 'GitHub Pages 發布後約 5 分鐘複檢與公開資料不一致，已重新發布一次仍失敗。',
}


def calendar_key(end):
    return f'<!-- tsingbus-transit-calendar:{end} -->'


def due_date(end):
    return dt.date.fromisoformat(end) - dt.timedelta(days=60)


class GitHub:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.token = os.environ['GH_TOKEN']

    def request(self, method, path, body=None):
        request = urllib.request.Request(
            f'https://api.github.com/repos/{self.repo}/{path}',
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={'Authorization': 'Bearer ' + self.token,
                     'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json',
                     'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def issues(self):
        result = []
        page = 1
        while True:
            batch = self.request('GET', f'issues?state=all&per_page=100&page={page}')
            result.extend(x for x in batch if 'pull_request' not in x)
            if len(batch) < 100:
                return result
            page += 1


def maintain(api, end, today, run, dry_run=False, issues=None):
    owner = api.repo.split('/')[0]
    issues = api.issues() if issues is None else issues
    actions = []

    def find(key):
        return next((x for x in issues if key in (x.get('body') or '')), None)

    def create(title, body, key):
        actions.append('Create: ' + title)
        if not dry_run:
            api.request('POST', 'issues', {'title': title, 'body': key + '\n\n' + body,
                                          'assignees': [owner]})

    key = calendar_key(end)
    if today >= due_date(end) and not find(key):
        create('清BUS：請更新校外交通假日日曆',
               f'@{owner}，目前假日日曆有效至 **{end}**，已進入到期前 60 天。\n\n'
               '請把以下工作交給 Codex／Claude Code：\n\n'
               '1. 取得人事行政總處最新官方辦公日曆： https://data.gov.tw/dataset/14718 。\n'
               '2. 更新 `scripts/transit-holidays.json` 的假日、coverageEnd、來源與 reviewedAt；'
               '保留 App 使用 SUNDAY 的現行政策，確認國定假日／補假，勿把普通週末全部加入。\n'
               '3. 跑測試，確認效果後提交；手動執行「校外交通靜態班表同步」，驗證 Pages。\n\n'
               '未處理到期問題時，同步會保留上一版資料。完成後可關閉本 issue；'
               '同一個到期日不會再次建立提醒。', key)

    failure = next((x for x in issues if FAILURE_KEY in (x.get('body') or '')
                    and x['state'] == 'open'), None)
    if run and run.get('conclusion') in ('failure', 'timed_out', 'action_required', 'startup_failure'):
        if not failure or failure['state'] != 'open':
            create('清BUS：校外交通自動同步失敗，請檢查',
                   f'@{owner}，最近完成的校外交通同步失敗。\n\n'
                   f'[查看這次同步工作]({run["html_url"]})\n\n'
                   + (f'**失敗步驟：{run["failed_step"]}**\n\n{explain(run["failed_step"])}\n\n' if run.get('failed_step') else '') +
                   '請交給 Codex／Claude Code檢查失敗步驟：TDX 查詢、資料驗證、提交或 Pages 發布。'
                   '確認 Actions Secrets 仍存在且有效；不要將金鑰貼在 issue、聊天或 log。\n\n'
                   '修復後重新執行完整同步並確認網站資料。相同未解決問題不會每日重複提醒；'
                   '之後同步成功時，系統會自動關閉所有尚未解決的同步失敗提醒。', FAILURE_KEY)
    elif run and run.get('conclusion') == 'success':
        for issue in issues:
            if FAILURE_KEY in (issue.get('body') or '') and issue['state'] == 'open':
                actions.append('Close resolved failure issue')
                if not dry_run:
                    api.request('PATCH', f'issues/{issue["number"]}', {'state': 'closed'})
    if not actions:
        actions.append('No new maintenance notification needed.')
    return actions


def explain(step):
    return next((text for prefix, text in FAILURE_EXPLANATIONS.items() if step.startswith(prefix)), '')


def failed_step(api, run):
    """Name of the first failed step (Actions metadata only; no logs are read)."""
    try:
        jobs = api.request('GET', f'actions/runs/{run["id"]}/jobs')['jobs']
    except Exception:
        return None
    for job in jobs:
        for step in job.get('steps', []):
            if step.get('conclusion') == 'failure':
                return step['name']
        if job.get('conclusion') == 'failure':
            return job['name']
    return None


def parse_time(value):
    return dt.datetime.fromisoformat(value) if value else None


class Episodes:
    """Open/close issues by hidden key; a key never gets a second issue, open or closed."""

    def __init__(self, api, issues, dry_run):
        self.api, self.issues, self.dry_run = api, issues, dry_run
        self.owner = api.repo.split('/')[0]
        self.actions = []

    def has(self, key, open_only=False):
        return any(key in (x.get('body') or '') and (not open_only or x['state'] == 'open') for x in self.issues)

    def open(self, key, title, body, recurring=False):
        """recurring=True for fixed keys: a new episode may follow a closed one."""
        if self.has(key, open_only=recurring):
            return
        self.actions.append('Create: ' + title)
        if not self.dry_run:
            self.api.request('POST', 'issues', {'title': title, 'body': key + '\n\n' + f'@{self.owner}，' + body,
                                                'assignees': [self.owner]})
        self.issues.append({'body': key, 'state': 'open', 'number': None})

    def close_unless(self, prefix, keep):
        """Close open issues whose key starts with prefix but is not in keep."""
        for issue in self.issues:
            body = issue.get('body') or ''
            if issue['state'] != 'open' or prefix not in body or any(k in body for k in keep) or not issue.get('number'):
                continue
            self.actions.append(f'Close resolved issue #{issue["number"]}')
            if not self.dry_run:
                self.api.request('PATCH', f'issues/{issue["number"]}', {'state': 'closed'})
            issue['state'] = 'closed'


def route_key(rid, since):
    return f'<!-- tsingbus-transit-route-stale:{rid}:{since} -->'


def service_key(alert_id):
    return f'<!-- tsingbus-transit-service-alert:{alert_id} -->'


def maintain_status(episodes, status, alerts_doc, now, last_success=None):
    """Issues driven by published status files only (trusted main branch content)."""
    keep = []
    for rid, entry in sorted((status or {}).get('routes', {}).items()):
        key = route_key(rid, entry['since'])
        keep.append(key)
        urgent = (entry.get('reason') in ('SUDDEN_TRIP_DROP', 'SERVICE_DAY_LOST')
                  or entry.get('diagnosis', {}).get('diagnosis') == 'ROUTE_UID_CHANGED')
        overdue = now - parse_time(entry['since']) >= dt.timedelta(hours=ROUTE_STALE_NOTIFY_HOURS)
        if urgent or overdue:
            diag = entry.get('diagnosis') or {}
            episodes.open(key, f'清BUS：校外路線 {rid} 暫用舊班表，請確認',
                          f'路線 **{rid}** 自 {entry["since"]} 起無法使用最新官方資料（原因：`{entry["reason"]}`），'
                          f'App 目前顯示 {entry.get("dataAsOf")} 驗證過的班表並標示「資料可能過期」。\n\n'
                          f'診斷：`{json.dumps(diag, ensure_ascii=False)}`\n\n'
                          '- `ROUTE_UID_CHANGED`：TDX 換了路線代號（常見於換業者），請確認新業者與站序後更新 `scripts/sync_transit.py` 白名單。\n'
                          '- `ROUTE_NOT_LISTED`：TDX 完全查不到這條路線，請到業者／公路局網站確認是否停駛或改號。\n'
                          '- `PARTIAL_RESPONSE`：路線還在但站序或時刻缺漏，通常是 TDX 暫時問題。\n'
                          '- `SERVICE_DAY_LOST`：某些星期突然一班都沒有；確認官方真的停開那幾天後，同樣用 accept_trip_drop 放行。\n'
                          '- `SUDDEN_TRIP_DROP`：班次突然少一半以上；確認是官方真的減班後，手動執行同步並在 accept_trip_drop 填入路線。\n\n'
                          '路線恢復正常同步後，本提醒會自動關閉。')
    episodes.close_unless('tsingbus-transit-route-stale:', keep)

    feed = (status or {}).get('feed')
    overdue = last_success and now - parse_time(last_success) >= dt.timedelta(hours=FEED_STALE_HOURS)
    if feed or overdue:
        episodes.open(FEED_STALE_KEY, '清BUS：校外公車資料超過一天沒有同步成功',
                      f'最後一次同步成功：{last_success or (feed or {}).get("lastSuccessAt")}。'
                      'App 已標示資料可能過期；請查看同步工作的失敗步驟。恢復後自動關閉。', recurring=True)
    else:
        episodes.close_unless(FEED_STALE_KEY, [])

    keep = []
    for alert in (alerts_doc or {}).get('alerts', []):
        states = {e['state'] for e in alert['routes'].values()}
        if not (states & {'SUSPENDED', 'PARTIAL_SUSPENSION'} or alert.get('conflict')):
            continue
        key = service_key(alert['id'])
        keep.append(key)
        routes = '、'.join(f'{rid}（{e["state"]}）' for rid, e in sorted(alert['routes'].items()))
        episodes.open(key, f'清BUS：官方營運異動 — {alert["title"][:40]}',
                      f'TDX 營運通阻公告影響：{routes}。\n\n'
                      f'發布：{alert.get("department")}　{alert.get("publishTime")}\n'
                      f'期間：{alert["startTime"]} ～ {alert.get("endTime") or "未註明（" + alert["expiresAt"] + " 自動失效）"}\n'
                      f'來源：{alert["url"]}\n\n'
                      + ('**官方欄位互相矛盾（Status 與 Effect 不一致），系統只標「營運異動」，請人工判讀。**\n\n'
                         if alert.get('conflict') else '') +
                      '`transit-alerts.json` 已記錄這筆異動；目前 App 版本還不會讀這個檔案，'
                      '若要讓 App 隱藏班次，請確認公告後在 `transit.json` 的 `suspensions` 手動加入。公告結束或撤回後自動關閉。')
    episodes.close_unless('tsingbus-transit-service-alert:', keep)

    valid = parse_time((alerts_doc or {}).get('validUntil'))
    if alerts_doc is not None and (valid is None or valid < now):
        episodes.open(ALERTS_STALE_KEY, '清BUS：營運異動監測已超過一天沒有成功',
                      'TDX 營運通阻來源連續失敗，`transit-alerts.json` 已過期（App 應視為無法確認）。恢復後自動關閉。',
                      recurring=True)
    elif alerts_doc is not None:
        episodes.close_unless(ALERTS_STALE_KEY, [])


def main():
    api = GitHub()
    calendar = json.loads((ROOT / 'scripts/transit-holidays.json').read_text(encoding='utf-8'))
    # Always evaluate latest completed default-branch run, so delayed events cannot reopen stale failures.
    runs = api.request('GET', 'actions/workflows/transit-sync.yml/runs?branch=main&status=completed&per_page=1')['workflow_runs']
    success = api.request('GET', 'actions/workflows/transit-sync.yml/runs?branch=main&status=success&per_page=1')['workflow_runs']
    try:
        monitor = api.request('GET', 'actions/workflows/transit-service-alerts.yml/runs?branch=main&status=completed&per_page=1')['workflow_runs']
    except urllib.error.HTTPError:
        monitor = []  # Monitor workflow not registered yet.
    now = dt.datetime.now(ZoneInfo('Asia/Taipei'))
    today = now.date()
    dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
    run = runs[0] if runs else None
    if run and run.get('conclusion') == 'failure':
        run['failed_step'] = failed_step(api, run)
    issues = api.issues()
    result = maintain(api, calendar['coverageEnd'], today, run, dry_run, issues)
    episodes = Episodes(api, issues, dry_run)
    if monitor and monitor[0].get('conclusion') == 'failure':
        episodes.open(MONITOR_FAILURE_KEY, '清BUS：營運異動監測工作失敗',
                      f'[查看工作]({monitor[0]["html_url"]})。監測失敗不影響班表同步；'
                      'App 會在 transit-alerts.json 過期後視為「無法確認」。恢復後自動關閉。', recurring=True)
    elif monitor and monitor[0].get('conclusion') == 'success':
        episodes.close_unless(MONITOR_FAILURE_KEY, [])
    docs = ROOT / 'docs/v1'
    status = json.loads((docs / 'transit-status.json').read_text(encoding='utf-8')) if (docs / 'transit-status.json').exists() else None
    alerts_doc = json.loads((docs / 'transit-alerts.json').read_text(encoding='utf-8')) if (docs / 'transit-alerts.json').exists() else None
    last_success = success[0]['updated_at'].replace('Z', '+00:00') if success else None
    maintain_status(episodes, status, alerts_doc, now, last_success)
    result = [x for x in result if not x.startswith('No new')] + episodes.actions or result
    summary = (f'Calendar coverage: {calendar["coverageEnd"]}; first reminder: '
               f'{due_date(calendar["coverageEnd"])}; dry run: {dry_run}\n' + '\n'.join(result))
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(summary + '\n')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Maintenance notification API failed: HTTP {error.code}') from None
    except Exception:
        raise SystemExit('Maintenance notification failed; no credentials or source logs were printed.') from None
