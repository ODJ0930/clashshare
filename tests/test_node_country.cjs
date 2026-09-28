const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { inferCountry, codes } = require('../static/js/node-country.js');

test('country names, cities and traditional Chinese aliases', () => {
    const cases = [
        ['香港-专线01', 'hk'], ['Hong_Kong 01', 'hk'], ['HongKong-01', 'hk'],
        ['臺灣台北 01', 'tw'], ['Taipei 02', 'tw'], ['澳门 01', 'mo'],
        ['日本-东京', 'jp'], ['Tokyo 02', 'jp'], ['大阪 03', 'jp'],
        ['Singapore 01', 'sg'], ['洛杉矶 01', 'us'], ['Los Angeles 02', 'us'],
        ['UnitedStates-03', 'us'], ['英國倫敦', 'gb'], ['Seoul 01', 'kr'],
        ['法兰克福 01', 'de'], ['Paris 01', 'fr'], ['加拿大', 'ca'],
        ['Sydney 01', 'au'], ['新西兰 01', 'nz'], ['Moscow 01', 'ru'],
        ['印度尼西亚 01', 'id'], ['India 01', 'in'], ['Dubai 01', 'ae']
    ];
    cases.forEach(([name, expected]) => assert.equal(inferCountry(name)?.code, expected, name));
});

test('country codes, compact codes with numbers and short Chinese labels', () => {
    const cases = [
        ['HK01', 'hk'], ['hkg-02', 'hk'], ['JP-01', 'jp'], ['SGP_03', 'sg'],
        ['US01', 'us'], ['USA-02', 'us'], ['UK_01', 'gb'], ['KR 01', 'kr'],
        ['DEU-01', 'de'], ['FRA-01', 'fr'], ['AU01', 'au'], ['NZ-02', 'nz'],
        ['IN01', 'in'], ['in02', 'in'], ['ID 01', 'id'], ['CN 01', 'cn'],
        ['港01', 'hk'], ['日-02', 'jp'], ['台03', 'tw'], ['美 04', 'us'],
        ['德01', 'de'], ['新-01', 'sg'], ['HK｜日本 01', 'jp']
    ];
    cases.forEach(([name, expected]) => assert.equal(inferCountry(name)?.code, expected, name));
});

test('explicit flags take priority; full country names outrank codes', () => {
    assert.equal(inferCountry('🇯🇵 HK01')?.code, 'jp');
    assert.equal(inferCountry('🇺🇸 美国 01')?.code, 'us');
    assert.equal(inferCountry('SG-HK-日本')?.code, 'jp');
    assert.equal(inferCountry('香港→日本')?.code, 'hk');
    assert.equal(inferCountry('JP CN2 GIA')?.code, 'jp');
    assert.equal(inferCountry('ＨＫ０１')?.code, 'hk');
});

test('unknown names, protocol names and ordinary English words stay neutral', () => {
    ['SS节点', 'VLESS', 'Trojan', 'manual node', 'node in use', 'node id test',
        'can connect', 'no limit', 'it works', 'message', 'internal', 'direct',
        'CN2 GIA', 'CN2-01', 'CN20', '', '🇪🇺 01', null, 123, {}]
        .forEach(name => assert.equal(inferCountry(name), null, String(name)));
});

test('each supported country has a bundled flag', () => {
    assert.equal(new Set(codes).size, codes.length);
    codes.forEach(code => {
        assert.match(code, /^[a-z]{2}$/);
        const asset = path.join(__dirname, '..', 'static', 'img', 'flags', `${code}.svg`);
        assert.match(fs.readFileSync(asset, 'utf8'), /<svg\b/);
    });
});
