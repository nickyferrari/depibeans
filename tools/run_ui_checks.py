#!/usr/bin/env python3
"""Run the browser checks headlessly against the hardware-blocked preview.

    python3 tools/run_ui_checks.py            load the editor and run preview/ui-test.js
    python3 tools/run_ui_checks.py --smoke    only confirm the page and editor start cleanly

Needs Playwright with Chromium (pip install playwright; playwright install chromium).
A private preview server is started on a free port with a throwaway draft store, so
repeated runs start from the same fixture and never touch .runtime/preview.
"""
from __future__ import annotations
import argparse, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


PAGE_HELPERS = """
window.__t = {
  plan: () => JSON.parse(document.getElementById('plan-editor').value),
  events: () => window.__t.plan().events.map(e => e.kind[0] + ':' + e.delay_ms + ':' + (e.value ?? e.protocol)).join(' '),
  center: (kind, ms, nth = 0) => { const p = window.__t.plan(); const hits = p.events.map((e, i) => [e, i]).filter(([e]) => e.kind === kind && e.delay_ms === ms); const n = document.querySelector(`#graph-timeline [data-event="${hits[nth][1]}"]`); n.scrollIntoView({block: 'center'}); const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; },
  pxPerMs: () => { const p = window.__t.plan(), a = document.querySelector('#graph-timeline [data-event="0"]').getBoundingClientRect(), last = p.events.length - 1, b = document.querySelector(`#graph-timeline [data-event="${last}"]`).getBoundingClientRect(); return (b.x + b.width / 2 - a.x - a.width / 2) / (p.events[last].delay_ms - p.events[0].delay_ms); },
  selected: () => [...document.querySelectorAll('#graph-timeline .ge-on')].length,
  status: () => document.getElementById('graph-message').textContent,
  scriptState: () => document.querySelector('.ge-script-state').textContent,
  button: name => [...document.querySelectorAll('.ge-bar button')].find(b => b.textContent === name),
};
"""


def interaction_checks(page, context, base):
    """Real mouse, keyboard and touch input, and the flows that span save, reopen and other drafts."""
    results = []
    check = lambda name, ok, detail='': results.append({'name': name, 'pass': bool(ok), 'detail': str(detail)})
    t = lambda expression: page.evaluate(expression)

    def open_editor(target=page):
        target.goto(base)
        target.click('.chamber-tile')
        target.get_by_role('button', name='Plan', exact=True).click()
        target.wait_for_selector('#graph-timeline [data-event]', timeout=15000)
        target.evaluate(PAGE_HELPERS)
        target.evaluate("document.getElementById('graph-timeline').scrollIntoView({block:'center'})")
        target.wait_for_timeout(200)

    def drag(start, dx, dy=0, steps=6, modifiers=()):
        for key in modifiers: page.keyboard.down(key)
        page.mouse.move(*start); page.mouse.down()
        for n in range(1, steps + 1): page.mouse.move(start[0] + dx * n / steps, start[1] + dy * n / steps)
        page.mouse.up()
        for key in modifiers: page.keyboard.up(key)

    def type_script(text):
        page.fill('.ge-code', text); page.wait_for_timeout(450)

    open_editor()
    baseline = t('__t.events()')

    # mouse
    scale = t('__t.pxPerMs()')
    drag(t("__t.center('capture', 200000)"), 20000 * scale)
    moved = [e for e in t('__t.plan().events') if e['kind'] == 'capture' and 215000 < e['delay_ms'] < 225000]
    check('mouse drag moves a measurement in 0.1 s steps', len(moved) == 1 and moved[0]['delay_ms'] % 100 == 0, t('__t.events()'))
    check('mouse drag leaves the point selected', t('__t.selected()') == 1)

    # keyboard
    before = moved[0]['delay_ms'] if moved else 0
    page.keyboard.press('ArrowRight'); page.keyboard.press('Shift+ArrowRight')
    check('arrow keys nudge the selection 0.1 s and 1 s', any(e['delay_ms'] == before + 1100 for e in t('__t.plan().events')), t('__t.events()'))

    # script edit, then undo across all three kinds of edit
    type_script(t("document.querySelector('.ge-code').value").replace('light 500', 'light 320'))
    check('typing in the script changes the draft', ':320' in t('__t.events()'), t('__t.events()'))
    page.focus('#graph-timeline')
    for _ in range(3): page.keyboard.press('ControlOrMeta+z')
    check('undo steps back through script, keyboard and mouse edits', t('__t.events()') == baseline, t('__t.events()'))
    for _ in range(3): page.keyboard.press('ControlOrMeta+Shift+z')
    check('redo restores all three', ':320' in t('__t.events()') and t('__t.events()') != baseline)
    for _ in range(3): page.keyboard.press('ControlOrMeta+z')

    # an invalid edit keeps the last valid draft
    valid_text, valid_events = t("document.getElementById('plan-editor').value"), t('__t.events()')
    type_script(t("document.querySelector('.ge-code').value").replace('light 500', 'light 5000'))
    check('an invalid script line is reported', 'Light level' in t('__t.scriptState()'), t('__t.scriptState()'))
    check('an invalid script leaves the draft byte-identical', t("document.getElementById('plan-editor').value") == valid_text)
    type_script(t("document.querySelector('.ge-code').value").replace('light 5000', 'light 500'))
    check('correcting the line clears the error without changing the draft', t('__t.scriptState()') == '' and t('__t.events()') == valid_events)
    page.focus('#graph-timeline')

    # repeat block: Only this, Change all, save, reopen
    type_script(t("document.querySelector('.ge-code').value") + '\n\nrepeat 3 every 60 from 110\n  5  light 300\nend')
    page.focus('#graph-timeline')
    tagged = lambda: [[e['delay_ms'], e['value']] for e in t('__t.plan().events') if e.get('repeat')]
    check('a repeat block expands into tagged events', tagged() == [[115000, '300'], [175000, '300'], [235000, '300']], tagged())
    scale = t('__t.pxPerMs()')
    drag(t("__t.center('set', 175000)"), 8000 * scale)
    check('editing one instance asks before changing anything', page.is_visible('.ge-ask') and tagged()[1][0] == 175000, tagged())
    page.click(".ge-ask button:has-text('Only this')")
    plan = t('__t.plan()')
    check('Only this detaches that instance', len(tagged()) == 2 and plan['studio']['repeats'][0]['skip'] == [[1, 0]] and any(e['delay_ms'] == 183000 and not e.get('repeat') for e in plan['events']), tagged())
    drag(t("__t.center('set', 115000)"), 4000 * scale)
    page.click(".ge-ask button:has-text('Change all')")
    check('Change all moves every remaining instance', [row[0] for row in tagged()] == [119000, 239000], tagged())
    check('Change all is one undo step', (page.keyboard.press('ControlOrMeta+z'), [row[0] for row in tagged()])[1] == [115000, 235000], tagged())
    page.keyboard.press('ControlOrMeta+Shift+z')
    drag(t("__t.center('set', 119000)"), 4000 * scale)
    page.click(".ge-ask button:has-text('Cancel')")
    check('Cancel changes nothing', [row[0] for row in tagged()] == [119000, 239000], tagged())
    stored = t('__t.plan().studio.repeats')
    page.click('#save-plan'); page.wait_for_timeout(900)
    open_editor()      # a fresh page reopens the saved experiment
    check('a saved repeat block reopens with its skipped instance', t('__t.plan().studio.repeats') == stored, t('__t.plan().studio.repeats'))
    check('the reopened script shows the block', 'repeat 3 every 60 from 110' in t("document.querySelector('.ge-code').value"))
    check('a reopened draft starts with empty history', t("__t.button('Undo').disabled && __t.button('Redo').disabled"))

    # switching experiments
    drag(t("__t.center('capture', 300000)"), 5000 * t('__t.pxPerMs()'))
    page.focus('#graph-timeline'); page.keyboard.press('ControlOrMeta+c')
    page.evaluate("document.getElementById('new-experiment').click()"); page.wait_for_timeout(400)   # lives in the Experiment options menu
    other = t('__t.events()')
    check('another experiment clears undo and redo', t("__t.button('Undo').disabled && __t.button('Redo').disabled"))
    page.focus('#graph-timeline'); page.keyboard.press('ControlOrMeta+z')
    check('undo cannot bring the previous experiment into this draft', t('__t.events()') == other, t('__t.events()'))
    check('the script follows the new experiment', 'repeat' not in t("document.querySelector('.ge-code').value"))

    # touch, in a touch-enabled context, using the browser's own touch input
    touch = context.browser.new_context(viewport={'width': 1024, 'height': 900}, has_touch=True)
    finger = touch.new_page(); open_editor(finger)
    session = touch.new_cdp_session(finger)
    start = finger.evaluate("__t.center('capture', 385000)")
    finger.touchscreen.tap(*start)
    check('touch: a tap selects a point', finger.evaluate('__t.selected()') == 1)
    start = finger.evaluate("__t.center('capture', 385000)"); step = finger.evaluate('__t.pxPerMs()') * -10000
    session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': start[0], 'y': start[1]}]})
    for n in range(1, 7): session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': start[0] + step * n / 6, 'y': start[1]}]})
    session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    dragged = [e['delay_ms'] for e in finger.evaluate('__t.plan().events') if e['kind'] == 'capture']
    check('touch: dragging a point moves it without scrolling the page away', 385000 not in dragged and any(370000 < ms < 380000 for ms in dragged), dragged)
    touch.close()
    return results


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--smoke', action='store_true')
    arguments = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Playwright is not installed; see this file\'s docstring.', file=sys.stderr)
        return 2
    port, store = free_port(), Path(tempfile.mkdtemp(prefix='depi-ui-'))
    environment = dict(os.environ, DEPI_PREVIEW_PORT=str(port), DEPI_PREVIEW_ROOT=str(store))
    server = subprocess.Popen([sys.executable, str(ROOT / 'preview/serve.py')], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    print(server.stderr.read().decode(), file=sys.stderr)
                    return 2
                time.sleep(.25)
        problems = []
        with sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('console', lambda message: problems.append(message.text) if message.type == 'error' and 'Applying inline style' not in message.text else None)
            page.on('pageerror', lambda error: problems.append(str(error)))
            posts = []
            page.on('request', lambda request: posts.append(request.url) if request.method != 'GET' else None)
            page.goto(f'http://127.0.0.1:{port}/')
            page.click('.chamber-tile')
            page.get_by_role('button', name='Plan', exact=True).click()
            page.wait_for_selector('#graph-timeline [data-event]', timeout=15000)
            mounted = page.evaluate("({points:document.querySelectorAll('#graph-timeline [data-event]').length,script:document.querySelector('.ge-code').value.split('\\n')[0],tools:document.querySelectorAll('.ge-bar button').length})")
            print('editor mounted:', json.dumps(mounted))
            result = {'failed': []}
            if not arguments.smoke:
                result = page.evaluate("async () => (await import('/__ui-test.js')).run()")
                print(f"browser checks: {result['passed']} of {result['total']} passed")
                for failure in result['failed']:
                    print('  FAIL', failure['name'], '|', failure['detail'][:300])
            if not arguments.smoke:
                extra = interaction_checks(page, page.context, f'http://127.0.0.1:{port}/')
                failed = [item for item in extra if not item['pass']]
                print(f"real-input checks: {len(extra) - len(failed)} of {len(extra)} passed")
                for failure in failed:
                    print('  FAIL', failure['name'], '|', failure['detail'][:300])
                result['failed'] = list(result['failed']) + failed
            browser.close()
        hardware = [url for url in posts if any(part in url for part in ('/api/light', '/api/stop', '/api/preview-light'))]
        for problem in problems:
            print('  console error:', problem[:300])
        if hardware:
            print('  hardware routes were requested:', hardware)
        return 1 if result['failed'] or problems or hardware else 0
    finally:
        server.terminate()
        shutil.rmtree(store, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
