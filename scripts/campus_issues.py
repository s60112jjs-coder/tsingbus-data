#!/usr/bin/env python3
"""Deduplicate shuttle auto-update manual-review and publication failure issues."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '<!-- tsingbus-campus-auto-id:'
PUBLISH = '<!-- tsingbus-campus-publish-failure -->'


class GitHub:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.token = os.environ['GH_TOKEN']

    def request(self, method, path, payload=None):
        request = urllib.request.Request(
            f'https://api.github.com/repos/{self.repo}/{path}',
            data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
            method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
                     'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response) if response.status != 204 else {}

    def issues(self):
        items, page = [], 1
        while True:
            result = self.request('GET', f'issues?state=all&per_page=100&page={page}')
            items.extend(x for x in result if 'pull_request' not in x)
            if len(result) < 100:
                return items
            page += 1


def sync(api):
    report = json.loads((ROOT / 'campus-review.json').read_text(encoding='utf-8'))
    existing = api.issues()
    pending = {v['id'] for v in report['reviews']}
    completed = {v['id'] for v in report['processed']} - pending
    for problem in report['reviews']:
        marker = PREFIX + problem['id'] + ' -->'
        found = next((x for x in existing if marker in (x.get('body') or '')), None)
        title = '[需更新資料] 清Bus 校內公告無法安全自動更新：' + problem['title'][:70]
        body = (marker + '\n\n'
                '官方公告需要人工核對，未將不可靠的班表／停駛日期發布至正式資料。\n\n'
                f'來源：{problem["url"]}\n\n原因：{problem["reason"]}\n\n'
                '請核對校方原始資料，避免憑圖片猜測班次。')
        if not found:
            api.request('POST', 'issues', {'title': title, 'body': body})
        elif found['state'] != 'open':
            api.request('PATCH', f'issues/{found["number"]}', {'state': 'open', 'title': title, 'body': body})
        elif found['title'] != title or (found.get('body') or '') != body:
            api.request('PATCH', f'issues/{found["number"]}', {'title': title, 'body': body})
    for issue in existing:
        if issue['state'] != 'open':
            continue
        for ident in completed:
            if PREFIX + ident + ' -->' in (issue.get('body') or ''):
                api.request('PATCH', f'issues/{issue["number"]}', {'state': 'closed'})
                break


def publication(api, failed):
    issue = next((x for x in api.issues() if PUBLISH in (x.get('body') or '')), None)
    if failed:
        if issue and issue['state'] == 'open':
            return
        title = '[需更新資料] 清Bus 校內公車發布後兩次複檢失敗'
        body = (PUBLISH + '\n\n'
                '校內資料已自動更新，但發布後5分鐘複檢失敗；'
                '已嘗試重新發布，再等待5分鐘，仍無法確認 Pages 與 GitHub 內容一致。'
                '請檢查校內自動化 GitHub Actions。')
        if issue:
            api.request('PATCH', f'issues/{issue["number"]}', {'state': 'open', 'title': title, 'body': body})
        else:
            api.request('POST', 'issues', {'title': title, 'body': body})
    elif issue and issue['state'] == 'open':
        api.request('PATCH', f'issues/{issue["number"]}', {'state': 'closed'})


def main():
    api = GitHub()
    command = sys.argv[1] if len(sys.argv) > 1 else '--sync'
    if command == '--sync':
        sync(api)
    elif command == '--publication-failed':
        publication(api, True)
    elif command == '--publication-ok':
        publication(api, False)
    else:
        raise SystemExit('Unknown command')


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as err:
        raise SystemExit(f'GitHub Issue action failed: HTTP {err.code}') from None
