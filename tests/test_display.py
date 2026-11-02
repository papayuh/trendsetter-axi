from concurrent.futures import ThreadPoolExecutor

import pytest

from trendsetter_axi import DisplayPreferences as Prefs, Scalar, Surface, present, resolve_preferences
from trendsetter_axi import compact


def fail(*args, **kwargs):
    pytest.fail('unexpected rendering/encoding call')


def test_scalar_calls_neither_image_route_nor_text_renderer(monkeypatch):
    monkeypatch.setattr(compact, 'render_compact', fail)
    result = present(Scalar(95, '%'), surface=Surface(image_route=fail), saved=Prefs(mode='image'))
    assert result.mode == 'scalar' and result.text == '95 %'


def test_confirmed_user_visible_image_route_gets_source_exactly_once(monkeypatch):
    monkeypatch.setattr(compact, 'render_compact', fail)
    source, calls = object(), []
    def route(figure):
        calls.append(figure)
        return 'delivered visibly'
    result = present(source, surface=Surface(image_route=route), explicit=Prefs(mode='image'))
    assert calls == [source] and result.image_receipt == 'delivered visibly'
    assert result.mode == 'image' and result.text is None


@pytest.mark.parametrize('host', ['unknown', 'pipe', 'transcript', 'text-only', 'Claude Code without installed image route'])
def test_saved_image_falls_back_once_without_term_inference(monkeypatch, host):
    monkeypatch.setenv('TERM', 'xterm-kitty')
    monkeypatch.setenv('TERM_PROGRAM', 'vscode')
    calls = []
    def text(source, **kwargs):
        calls.append((source, kwargs))
        return type('Result', (), {'text': 'compact text'})()
    monkeypatch.setattr(compact, 'render_compact', text)
    result = present(host, saved=Prefs(mode='image', rows=20), surface=Surface(cols=40, rows=8))
    assert result.text == 'compact text' and result.fallback_reason == 'no confirmed user-visible image route'
    assert calls == [(host, dict(cols=40, max_rows=8, ascii=False, color=False))]


def test_text_no_color_is_one_turn_only_then_saved_image_returns(monkeypatch):
    calls = []
    def text(source, **kwargs):
        calls.append(kwargs)
        return type('Result', (), {'text': 'plain text'})()
    monkeypatch.setattr(compact, 'render_compact', text)
    saved = Prefs(mode='image', color=True)
    surface = Surface(color=True, image_route=lambda source: 'image')
    first = present(object(), saved=saved, surface=surface, explicit=Prefs(mode='text', color=False))
    second = present(object(), saved=saved, surface=surface)
    assert first.mode == 'text' and calls[0]['color'] is False
    assert second.mode == 'image' and saved == Prefs(mode='image', color=True)


def test_fieldwise_precedence_including_false_and_auto():
    assert resolve_preferences(explicit=Prefs(mode='auto', color=False), session=Prefs(mode='text', rows=8),
                               saved=Prefs(mode='image', rows=24, color=True, ascii=True)) == Prefs('auto', 8, False, True)


def test_automatic_rows_use_surface_and_explicit_rows_intersect(monkeypatch):
    calls = []
    def text(source, **kwargs):
        calls.append(kwargs)
        return type('Result', (), {'text': 'text'})()
    monkeypatch.setattr(compact, 'render_compact', text)
    present('svg', surface=Surface(rows=18))
    present('svg', surface=Surface(rows=18), explicit=Prefs(rows=40, color=True))
    present('svg', surface=Surface(rows=18), explicit=Prefs(rows=8))
    assert [call['max_rows'] for call in calls] == [18, 18, 8]
    assert calls[1]['color'] is False  # capability caps preference


def test_harness_owned_saved_scopes_reset_and_independent_concurrent_renders():
    # The harness chooses scope and persistence. Axi only consumes immutable snapshots.
    settings = {'user': Prefs(ascii=True), 'project-one': Prefs(mode='text', rows=8)}
    user = settings['user']
    assert resolve_preferences(saved=user).ascii
    assert resolve_preferences(saved=settings['project-one']).ascii is False
    assert resolve_preferences(saved=Prefs()).ascii is False  # explicit harness reset
    assert resolve_preferences(session=Prefs(ascii=False), saved=user).ascii is False
    def call(i):
        return resolve_preferences(explicit=Prefs(rows=i + 1, ascii=bool(i % 2)), saved=user)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(call, range(20)))
    assert [p.rows for p in results] == list(range(1, 21))
    assert [p.ascii for p in results] == [bool(i % 2) for i in range(20)]
    assert settings['user'] == Prefs(ascii=True)


def test_redraw_uses_same_source_and_does_not_save_one_turn_budget(monkeypatch):
    calls = []
    def text(source, **kwargs):
        calls.append((source, kwargs))
        return type('Result', (), {'text': 'text'})()
    monkeypatch.setattr(compact, 'render_compact', text)
    source, saved = object(), Prefs(mode='text', rows=12)
    present(source, saved=saved)
    present(source, saved=saved, explicit=Prefs(rows=6, ascii=True))
    present(source, saved=saved)
    assert all(call[0] is source for call in calls)
    assert [call[1]['max_rows'] for call in calls] == [12, 6, 12]
    assert saved == Prefs(mode='text', rows=12)


def test_concurrent_actual_text_renders_equal_independent_serial_renders():
    source = '<svg width="200" height="100"><path d="M10 80 L80 20 L180 60" fill="none" stroke="blue"/></svg>'
    saved = Prefs(mode='image', ascii=True)
    def call(i):
        return present(source, saved=saved, surface=Surface(cols=40 + i, rows=30),
                       explicit=Prefs(mode='text', ascii=bool(i % 2)))
    expected = [call(i).text for i in range(8)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(call, range(8)))
    assert [result.text for result in results] == expected
    assert all(result.mode == 'text' and result.fallback_reason is None for result in results)
    assert saved == Prefs(mode='image', ascii=True)


@pytest.mark.parametrize('kwargs', [dict(mode='bad'), dict(rows=0), dict(rows=True), dict(color=1), dict(ascii='yes')])
def test_invalid_preferences(kwargs):
    with pytest.raises(ValueError):
        Prefs(**kwargs)
