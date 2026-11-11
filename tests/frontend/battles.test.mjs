import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm';

class Element {
    constructor() {
        this.style = {};
        this.dataset = {};
        this.attributes = {};
        this.listeners = {};
        this.slots = new Map();
        this.children = [];
        this.classList = new Set();
        this.classList.remove = name => this.classList.delete(name);
    }

    setAttribute(name, value) {
        this.attributes[name] = value;
    }

    querySelector(selector) {
        if (!this.slots.has(selector)) this.slots.set(selector, new Element());
        return this.slots.get(selector);
    }

    addEventListener(name, listener) {
        this.listeners[name] = listener;
    }

    appendChild(child) {
        if (child.isFragment) this.children = child.children;
        else this.children.push(child);
    }

    click() {
        let stopped = false;
        this.listeners.click({
            currentTarget: this,
            stopPropagation() { stopped = true; },
        });
        assert.equal(stopped, true);
    }
}

async function setupTower() {
    const tower = new Element();
    const label = new Element();
    const state = { sessionKey: 1, selectedDrivers: [1, 16] };
    const actions = [];
    let onFrame;
    const context = createContext({
        AbortController,
        console: { log() {}, error(message) { throw new Error(message); } },
        document: {
            getElementById: id => ({ 'tower-rows': tower, 'active-duel-label': label })[id],
            createElement: () => new Element(),
            createDocumentFragment: () => Object.assign(new Element(), { isFragment: true }),
        },
        fetch: async () => ({ ok: true, json: async () => ({}) }),
    });
    const app = new SyntheticModule(['state', 'sendAction', 'onFrame'], function () {
        this.setExport('state', state);
        this.setExport('sendAction', action => actions.push(action));
        this.setExport('onFrame', callback => { onFrame = callback; });
    }, { context });
    const source = await readFile(
        new URL('../../src/pitwall_telemetry_engine/static/js/timing_tower.js', import.meta.url),
        'utf8',
    );
    const module = new SourceTextModule(source, { context });
    await module.link(specifier => {
        assert.equal(specifier, './app.js');
        return app;
    });
    await module.evaluate();
    await module.namespace.initTimingTower();
    return { tower, label, state, actions, module, frame: value => onFrame(value) };
}

function frame(battles) {
    return {
        positions: [1, 16, 55].map(driver_number => ({ driver_number })),
        intervals: { 1: { position: 1 }, 16: { position: 2 }, 55: { position: 3 } },
        battles,
    };
}

test('close battle button selects the actual pair rather than toggling its row', async () => {
    const view = await setupTower();
    view.frame(frame([{ attacker: 55, defender: 16, gap: 0.6 }]));
    const trailingRow = view.tower.children[2];
    const badge = trailingRow.querySelector('[data-slot="battle"]');
    assert.match(trailingRow.innerHTML, /button type="button"/);
    assert.match(trailingRow.innerHTML, /CLOSE BATTLE/);
    assert.equal(badge.style.display, 'inline-flex');
    assert.match(badge.title, /Not a predicted overtake or DRS eligibility/);
    badge.click();
    assert.deepEqual(Array.from(view.state.selectedDrivers), [55, 16]);
    assert.deepEqual(JSON.parse(JSON.stringify(view.actions.at(-1))), {
        action: 'select_drivers', drivers: [55, 16],
    });
    assert.equal(view.label.textContent, 'COMPARING #55 VS #16');
    assert.equal(trailingRow.classList.has('selected'), true);
    assert.equal(view.tower.children[1].classList.has('selected'), true);
    assert.equal(view.tower.children[0].classList.has('selected'), false);
});

test('updated and cleared battles do not retain the old comparison target', async () => {
    const view = await setupTower();
    view.frame(frame([{ attacker: 55, defender: 16, gap: 0.6 }]));
    const badge = view.tower.children[2].querySelector('[data-slot="battle"]');
    view.frame(frame([{ attacker: 55, defender: 1, gap: 0.7 }]));
    badge.click();
    assert.deepEqual(Array.from(view.state.selectedDrivers), [55, 1]);
    const actionCount = view.actions.length;
    view.frame(frame([]));
    assert.equal(badge.style.display, 'none');
    assert.equal(badge.dataset.defender, undefined);
    badge.click();
    assert.equal(view.actions.length, actionCount);
});

test('legacy or malformed battle payloads cannot offer a guessed comparison', async () => {
    const view = await setupTower();
    for (const battle of [
        { attacker: 55, gap: 0.6 },
        { attacker: 55, defender: 55, gap: 0.6 },
        { attacker: 55, defender: 16, gap: 0 },
        { attacker: 55, defender: 16, gap: '0.6' },
        { attacker: 55, defender: -1, gap: 0.6 },
    ]) {
        view.frame(frame([battle]));
        assert.equal(
            view.tower.children[2].querySelector('[data-slot="battle"]').style.display,
            'none',
        );
    }
});

test('a frame without positions clears existing battle targets', async () => {
    const view = await setupTower();
    view.frame(frame([{ attacker: 55, defender: 16, gap: 0.6 }]));
    const badge = view.tower.children[2].querySelector('[data-slot="battle"]');
    view.frame({ positions: [], battles: [] });
    assert.equal(badge.style.display, 'none');
    assert.equal(badge.dataset.defender, undefined);
});

test('session reset discards old battle rows and comparison labels', async () => {
    const view = await setupTower();
    view.frame(frame([{ attacker: 55, defender: 16, gap: 0.6 }]));
    const oldRow = view.tower.children[2];
    view.state.selectedDrivers = [];
    await view.module.namespace.resetTimingTower();
    view.frame(frame([]));
    assert.notEqual(view.tower.children[2], oldRow);
    assert.equal(view.label.textContent, 'SELECT DRIVERS TO COMPARE');
    assert.equal(
        view.tower.children[2].querySelector('[data-slot="battle"]').style.display,
        'none',
    );
});
