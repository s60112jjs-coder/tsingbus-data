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


def maintain(api, end, today, run, dry_run=False):
    owner = api.repo.split('/')[0]
    issues = api.issues()
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


def main():
    api = GitHub()
    calendar = json.loads((ROOT / 'scripts/transit-holidays.json').read_text(encoding='utf-8'))
    # Always evaluate latest completed default-branch run, so delayed events cannot reopen stale failures.
    runs = api.request('GET', 'actions/workflows/transit-sync.yml/runs?branch=main&status=completed&per_page=1')['workflow_runs']
    today = dt.datetime.now(ZoneInfo('Asia/Taipei')).date()
    dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
    result = maintain(api, calendar['coverageEnd'], today, runs[0] if runs else None, dry_run)
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
