(function (root, factory) {
    const countries = factory();
    if (typeof module === 'object' && module.exports) module.exports = countries;
    else root.ClashShareCountries = countries;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
    'use strict';

    const entries = [
        ['hk', '香港', ['香港', 'hong kong', 'hongkong'], ['hk', 'hkg'], ['港']],
        ['tw', '台湾', ['台湾', '臺灣', '台北', '臺北', '高雄', 'taiwan', 'taipei'], ['tw', 'twn'], ['台', '臺']],
        ['mo', '澳门', ['澳门', '澳門', 'macau', 'macao'], ['mo', 'mac'], []],
        ['jp', '日本', ['日本', '东京', '東京', '大阪', 'japan', 'tokyo', 'osaka'], ['jp', 'jpn', 'nrt', 'kix'], ['日']],
        ['sg', '新加坡', ['新加坡', '狮城', '獅城', 'singapore'], ['sg', 'sgp', 'sin'], ['新']],
        ['us', '美国', ['美国', '美國', '洛杉矶', '洛杉磯', '纽约', '紐約', '西雅图', '圣何塞', 'united states', 'unitedstates', 'america', 'los angeles', 'losangeles', 'new york', 'seattle', 'san jose'], ['us', 'usa', 'lax', 'sfo', 'sjc'], ['美']],
        ['gb', '英国', ['英国', '英國', '伦敦', '倫敦', 'united kingdom', 'unitedkingdom', 'britain', 'england', 'london'], ['gb', 'gbr', 'uk', 'lhr'], ['英']],
        ['kr', '韩国', ['韩国', '韓國', '首尔', '首爾', 'south korea', 'southkorea', 'korea', 'seoul'], ['kr', 'kor', 'icn'], ['韩', '韓']],
        ['de', '德国', ['德国', '德國', '法兰克福', '法蘭克福', '柏林', 'germany', 'frankfurt', 'berlin'], ['de', 'deu', 'ger'], ['德']],
        ['fr', '法国', ['法国', '法國', '巴黎', 'france', 'paris'], ['fr', 'fra', 'cdg'], ['法']],
        ['ca', '加拿大', ['加拿大', '多伦多', '多倫多', '温哥华', '溫哥華', 'canada', 'toronto', 'vancouver'], ['ca', 'can', 'yyz', 'yvr'], []],
        ['au', '澳大利亚', ['澳大利亚', '澳大利亞', '澳洲', '悉尼', '雪梨', '墨尔本', 'melbourne', 'australia', 'sydney'], ['au', 'aus', 'syd', 'mel'], ['澳']],
        ['nz', '新西兰', ['新西兰', '新西蘭', '纽西兰', '紐西蘭', '奥克兰', 'new zealand', 'newzealand', 'auckland'], ['nz', 'nzl', 'akl'], []],
        ['ru', '俄罗斯', ['俄罗斯', '俄羅斯', '莫斯科', 'russia', 'moscow'], ['ru', 'rus'], ['俄']],
        ['nl', '荷兰', ['荷兰', '荷蘭', '阿姆斯特丹', 'netherlands', 'holland', 'amsterdam'], ['nl', 'nld', 'ams'], ['荷']],
        ['ch', '瑞士', ['瑞士', '苏黎世', '蘇黎世', 'switzerland', 'zurich'], ['ch', 'che', 'zrh'], []],
        ['se', '瑞典', ['瑞典', '斯德哥尔摩', 'sweden', 'stockholm'], ['se', 'swe', 'arn'], []],
        ['fi', '芬兰', ['芬兰', '芬蘭', '赫尔辛基', 'finland', 'helsinki'], ['fi', 'fin', 'hel'], []],
        ['no', '挪威', ['挪威', '奥斯陆', 'norway', 'oslo'], ['no', 'nor', 'osl'], []],
        ['dk', '丹麦', ['丹麦', '丹麥', '哥本哈根', 'denmark', 'copenhagen'], ['dk', 'dnk', 'cph'], []],
        ['ie', '爱尔兰', ['爱尔兰', '愛爾蘭', '都柏林', 'ireland', 'dublin'], ['ie', 'irl', 'dub'], []],
        ['it', '意大利', ['意大利', '義大利', '米兰', '米蘭', '罗马', 'italy', 'milan', 'rome'], ['it', 'ita', 'mxp'], ['意']],
        ['es', '西班牙', ['西班牙', '马德里', '巴塞罗那', 'spain', 'madrid', 'barcelona'], ['es', 'esp', 'mad', 'bcn'], []],
        ['pt', '葡萄牙', ['葡萄牙', '里斯本', 'portugal', 'lisbon'], ['pt', 'prt', 'lis'], []],
        ['pl', '波兰', ['波兰', '波蘭', '华沙', 'poland', 'warsaw'], ['pl', 'pol', 'waw'], []],
        ['tr', '土耳其', ['土耳其', '伊斯坦布尔', 'turkey', 'turkiye', 'istanbul'], ['tr', 'tur', 'ist'], []],
        ['in', '印度', ['印度', '孟买', '孟買', '新德里', 'india', 'mumbai', 'delhi'], ['in', 'ind', 'bom', 'del'], []],
        ['th', '泰国', ['泰国', '泰國', '曼谷', 'thailand', 'bangkok'], ['th', 'tha', 'bkk'], ['泰']],
        ['vn', '越南', ['越南', '河内', '河內', '胡志明', 'vietnam', 'hanoi', 'ho chi minh'], ['vn', 'vnm', 'han'], ['越']],
        ['my', '马来西亚', ['马来西亚', '馬來西亞', '吉隆坡', 'malaysia', 'kuala lumpur'], ['my', 'mys', 'kul'], []],
        ['id', '印度尼西亚', ['印度尼西亚', '印度尼西亞', '印尼', '雅加达', '雅加達', 'indonesia', 'jakarta'], ['id', 'idn', 'cgk'], []],
        ['ph', '菲律宾', ['菲律宾', '菲律賓', '马尼拉', 'philippines', 'manila'], ['ph', 'phl', 'mnl'], []],
        ['ae', '阿联酋', ['阿联酋', '阿聯酋', '迪拜', '杜拜', 'united arab emirates', 'dubai'], ['ae', 'are', 'uae', 'dxb'], []],
        ['il', '以色列', ['以色列', '特拉维夫', 'israel', 'tel aviv'], ['il', 'isr', 'tlv'], []],
        ['br', '巴西', ['巴西', '圣保罗', '聖保羅', 'brazil', 'sao paulo'], ['br', 'bra', 'gru'], []],
        ['ar', '阿根廷', ['阿根廷', '布宜诺斯艾利斯', 'argentina', 'buenos aires'], ['ar', 'arg', 'eze'], []],
        ['mx', '墨西哥', ['墨西哥', 'mexico'], ['mx', 'mex'], []],
        ['za', '南非', ['南非', '约翰内斯堡', 'south africa', 'southafrica', 'johannesburg'], ['za', 'zaf', 'jnb'], []],
        ['cn', '中国', ['中国', '中國', '大陆', '大陸', '北京', '上海', '广州', '深圳', 'china', 'beijing', 'shanghai'], ['cn', 'chn'], []]
    ];
    const countries = entries.map(([code, name, aliases, codes, shortNames]) => ({ code, name, aliases, codes, shortNames }));

    function firstMatch(name, candidates, matcher) {
        let best = null;
        countries.forEach(country => {
            country[candidates].forEach(candidate => {
                const offset = matcher(name, candidate);
                if (offset >= 0 && (!best || offset < best.offset || (offset === best.offset && candidate.length > best.length))) {
                    best = { country, offset, length: candidate.length };
                }
            });
        });
        return best?.country || null;
    }

    function inferCountry(value) {
        if (typeof value !== 'string' || !value.trim()) return null;
        const normalized = value.normalize('NFKC');
        const name = normalized.toLowerCase();
        // Explicit flag markers outrank names; country words outrank short codes.
        const flag = name.match(/[\u{1F1E6}-\u{1F1FF}]{2}/u);
        if (flag) {
            const code = [...flag[0]].map(char => String.fromCharCode(char.codePointAt(0) - 0x1F1E6 + 97)).join('');
            const country = countries.find(country => country.code === code);
            if (country) return { code: country.code, name: country.name };
        }
        const named = firstMatch(name, 'aliases', (text, candidate) => {
            if (/^[a-z ]+$/.test(candidate)) {
                const match = new RegExp(`(?:^|[^a-z])${candidate.replace(/ /g, '[\\s_-]*')}(?=$|[^a-z])`, 'i').exec(text);
                return match ? match.index : -1;
            }
            return text.indexOf(candidate);
        });
        const abbreviated = named || firstMatch(name, 'codes', (text, candidate) => {
            // CN2 is a network name, not evidence of a Chinese endpoint.
            if (candidate === 'cn') return /(?:^|[^a-z])cn(?!2)(?=$|[^a-z])/i.exec(text)?.index ?? -1;
            // Avoid treating ordinary English words as country codes.
            if (['in', 'no', 'it', 'id', 'can'].includes(candidate)) {
                const explicit = new RegExp(`(?:^|[^a-zA-Z])${candidate.toUpperCase()}(?=$|[^a-zA-Z])`).exec(normalized);
                return explicit?.index ?? new RegExp(`(?:^|[^a-z])${candidate}(?=\\d)`, 'i').exec(text)?.index ?? -1;
            }
            return new RegExp(`(?:^|[^a-z])${candidate}(?=$|[^a-z])`, 'i').exec(text)?.index ?? -1;
        });
        const country = abbreviated || firstMatch(name, 'shortNames', (text, candidate) => {
            return new RegExp(`(?:^|[\\s|/·_()（）\\-])${candidate}(?=$|[\\s\\d|/·_()（）\\-])`).exec(text)?.index ?? -1;
        });
        return country ? { code: country.code, name: country.name } : null;
    }

    return Object.freeze({ inferCountry, codes: Object.freeze(countries.map(country => country.code)) });
});
