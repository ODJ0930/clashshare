const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function setup(fetchImpl) {
    const code = fs.readFileSync(require.resolve('../static/js/dashboard.js'), 'utf8');
    const status = { textContent: '' };
    const calls = [];
    const alerts = [];
    const table = { setAttribute() {}, removeAttribute() {} };
    const tbody = {
        rows: [],
        closest: () => table,
        appendChild(row) { this.insertBefore(row, null); },
        insertBefore(row, target) {
            this.rows.splice(this.rows.indexOf(row), 1);
            this.rows.splice(target ? this.rows.indexOf(target) : this.rows.length, 0, row);
        },
        querySelectorAll() { return this.rows.map(row => row.handle); }
    };
    const rows = [1, 2, 3].map(id => {
        const row = {
            dataset: { nodeId: String(id) }, parentNode: tbody,
            classList: { add() {}, remove() {} }, badge: { textContent: 0 },
            closest() { return this; },
            getBoundingClientRect() { return { top: 0, height: 20 }; },
            querySelector() { return this.badge; },
            get nextSibling() { return tbody.rows[tbody.rows.indexOf(this) + 1] || null; }
        };
        row.handle = { listeners: {}, closest: () => row,
            addEventListener(name, fn) { this.listeners[name] = fn; } };
        return row;
    });
    tbody.rows = [...rows];
    const context = vm.createContext({
        document: { getElementById: () => status },
        alert: message => alerts.push(message),
        fetch: async (url, options) => { calls.push({ url, options }); return fetchImpl(); }
    });
    vm.runInContext('let allNodes = [1,2,3].map(id => ({id, order: 0}));\n' +
        code.slice(code.indexOf('let nodeOrderSaving = false;')), context);
    context.setupNodeDragSorting(tbody);
    const event = (row, y = 15) => ({ target: row, clientY: y, preventDefault() {},
        dataTransfer: { setData() {} } });
    return { rows, tbody, status, calls, alerts, context, event };
}

test('dragging down saves the displayed order and updates badges', async () => {
    const ui = setup(() => ({ ok: true }));
    ui.rows[0].handle.listeners.dragstart(ui.event(ui.rows[0]));
    ui.tbody.ondragover(ui.event(ui.rows[2]));
    await ui.tbody.ondrop(ui.event(ui.rows[2]));
    ui.rows[0].handle.listeners.dragend();
    assert.deepEqual(ui.tbody.rows.map(row => Number(row.dataset.nodeId)), [2, 3, 1]);
    assert.equal(ui.calls[0].url, '/api/nodes/reorder');
    assert.deepEqual(JSON.parse(ui.calls[0].options.body), { node_ids: [2, 3, 1] });
    assert.deepEqual(ui.tbody.rows.map(row => row.badge.textContent), [0, 1, 2]);
    assert.equal(ui.status.textContent, '排序已保存');
});

test('dragging upwards saves the correct order', async () => {
    const ui = setup(() => ({ ok: true }));
    ui.rows[2].handle.listeners.dragstart(ui.event(ui.rows[2]));
    ui.tbody.ondragover(ui.event(ui.rows[0], 0));
    await ui.tbody.ondrop(ui.event(ui.rows[0]));
    assert.deepEqual(JSON.parse(ui.calls[0].options.body).node_ids, [3, 1, 2]);
});

test('cancelled and unchanged drags do not save', async () => {
    const ui = setup(() => ({ ok: true }));
    ui.rows[0].handle.listeners.dragstart(ui.event(ui.rows[0]));
    ui.tbody.ondragover(ui.event(ui.rows[2]));
    ui.rows[0].handle.listeners.dragend();
    assert.deepEqual(ui.tbody.rows, ui.rows);
    ui.rows[0].handle.listeners.dragstart(ui.event(ui.rows[0]));
    await ui.tbody.ondrop(ui.event(ui.rows[0]));
    assert.equal(ui.calls.length, 0);
});

test('API and network failures restore the original order', async () => {
    for (const failure of [
        () => ({ ok: false, json: async () => ({ message: '节点列表已变化' }) }),
        () => { throw new Error('network failed'); }
    ]) {
        const ui = setup(failure);
        ui.rows[0].handle.listeners.dragstart(ui.event(ui.rows[0]));
        ui.tbody.ondragover(ui.event(ui.rows[2]));
        await ui.tbody.ondrop(ui.event(ui.rows[2]));
        assert.deepEqual(ui.tbody.rows, ui.rows);
        assert.equal(ui.alerts.length, 1);
        assert.equal(vm.runInContext('nodeOrderSaving', ui.context), false);
    }
});

test('a second drag is blocked while saving', async () => {
    let finish;
    const ui = setup(() => new Promise(resolve => { finish = resolve; }));
    ui.rows[0].handle.listeners.dragstart(ui.event(ui.rows[0]));
    ui.tbody.ondragover(ui.event(ui.rows[2]));
    const saving = ui.tbody.ondrop(ui.event(ui.rows[2]));
    let prevented = false;
    ui.rows[1].handle.listeners.dragstart({ preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
    finish({ ok: true });
    await saving;
});
