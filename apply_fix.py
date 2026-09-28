#!/usr/bin/env python3
"""A.D.A.M fixer: python apply_fix.py [index.html]  ->  writes index.fixed.html"""
import re, sys

path = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
try:
    s = open(path, encoding='utf-8').read()
except FileNotFoundError:
    sys.exit(f'Cannot find {path}. Put this script next to your index.html.')

print('Enter your Firebase details (see the guide).')
DB = input('Database URL (https://xxxx-default-rtdb...firebasedatabase.app): ').strip().rstrip('/')
KEY = input('Web API Key (starts with AIza): ').strip()
EMAIL = input('Owner email (the one you added in Firebase Authentication): ').strip()
if not (DB and KEY and EMAIL):
    sys.exit('All three values are required.')


def sub(old, new, required=True):
    global s
    if old not in s:
        if required:
            sys.exit(f'Patch failed, text not found:\n  {old[:80]}')
        return
    s = s.replace(old, new)


def find_fn(name):
    m = re.search(r'(?:async\s+)?function\s+' + name + r'\s*\(', s)
    if not m:
        sys.exit(f'Could not find function {name}')
    i = s.index('{', s.index(')', m.end()))
    return m, i


def replace_fn(name, new):
    global s
    m, i = find_fn(name)
    depth, j = 0, i
    while True:
        c = s[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    s = s[:m.start()] + new.strip('\n') + s[j + 1:]


def prepend_fn(name, code):
    global s
    _, i = find_fn(name)
    s = s[:i + 1] + '\n            ' + code + s[i + 1:]


CLOUD = r'''
        const CLOUD = { dbUrl: '__DB__', webApiKey: '__KEY__', ownerEmail: '__EMAIL__' };
        let ownerToken = null, ownerPass = '';
        const dbBase = () => CLOUD.dbUrl.replace(/\/$/, '');

        async function fbSignIn(email, password) {
            try {
                const r = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${CLOUD.webApiKey}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password, returnSecureToken: true })
                });
                return r.ok ? (await r.json()).idToken : null;
            } catch (e) { return null; }
        }
        async function fbGet(path) {
            try { const r = await fetch(`${dbBase()}/${path}.json`); return r.ok ? await r.json() : null; }
            catch (e) { return null; }
        }
        async function fbOwner(method, path, body) {
            for (let i = 0; i < 2; i++) {
                try {
                    const r = await fetch(`${dbBase()}/${path}.json?auth=${ownerToken}`, {
                        method, headers: { 'Content-Type': 'application/json' },
                        body: body === undefined ? undefined : JSON.stringify(body)
                    });
                    if (r.status === 401 && i === 0) { ownerToken = await fbSignIn(CLOUD.ownerEmail, ownerPass); continue; }
                    return r.ok ? await r.json() : null;
                } catch (e) { return null; }
            }
            return null;
        }
        function fbBump(key, n) {
            fetch(`${dbBase()}/teamKeys/${encodeURIComponent(key)}/requests.json`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(n)
            }).catch(() => {});
        }
        async function loadCloudOwnerData() {
            const cfg = await fbOwner('GET', 'ownerConfig');
            if (cfg) { appState.geminiKey = cfg.gemini || appState.geminiKey; appState.groqKey = cfg.groq || appState.groqKey; }
            const keys = await fbOwner('GET', 'teamKeys');
            appState.teamKeys = keys ? Object.entries(keys).map(([k, v]) => ({
                key: k, name: v.name, role: v.role || 'Senior DBA Team Member', requests: v.requests || 0, active: v.active === true
            })) : [];
        }
        function withHistory(hist, msg) {
            const prev = hist.slice(0, -1).slice(-10);
            if (!prev.length) return msg;
            return 'Conversation so far:\n' + prev.map(m => (m.role === 'user' ? 'DBA' : 'A.D.A.M') + ': ' + String(m.content).slice(0, 3000)).join('\n\n') + '\n\nLatest message from the DBA:\n' + msg;
        }
'''.replace('__DB__', DB).replace('__KEY__', KEY).replace('__EMAIL__', EMAIL)

# 1. White-screen fix
sub('<html lang="en" class="dark">', '<html lang="en" class="dark" style="background:#020617">')
sub("document.getElementById('app-body').classList.add('bg-amber-950/30');", '')
sub("document.getElementById('app-body').classList.remove('bg-amber-950/30');", '')

# 2. Embedded keys (had a "Key:" typo) -> empty; add cloud helpers
s, n = re.subn(r'const EMBEDDED_TEAM_KEYS = \[[\s\S]*?\];', lambda m: 'const EMBEDDED_TEAM_KEYS = [];\n' + CLOUD, s, count=1)
if n != 1:
    sys.exit('Could not find EMBEDDED_TEAM_KEYS')

# 3. Remove public default owner password
sub("|| 'ASIF-OWNER-2026'", "|| ''")

# 4. targetdb / targetDb mismatch
sub('appState.targetdb', 'appState.targetDb')

# 5. Chat memory
sub('callAiEngine(msg, generalMentorPrompt)', 'callAiEngine(withHistory(appState.askChatHistory, msg), generalMentorPrompt)')
sub('callAiEngine(msg, seniorMentorPrompt)', 'callAiEngine(withHistory(appState.chatHistory, msg), seniorMentorPrompt)')

# 6. Escape names in team table, Enter key on login, copy text, info box
sub('<td class="py-3 px-3 font-bold text-white">${k.name}</td>', '<td class="py-3 px-3 font-bold text-white">${escapeHtml(k.name)}</td>')
sub('id="login-key-input" placeholder=', 'id="login-key-input" onkeydown="if(event.key===\'Enter\') handleLogin()" placeholder=', required=False)
sub('Key copied to clipboard! Note: typing this key in only works on THIS browser — use "Copy Invite Link" to share access across devices.', 'Key copied to clipboard!', required=False)
s = re.sub(r'<strong class="text-slate-300">Static site, no backend:</strong>[\s\S]*?</div>',
           '<strong class="text-slate-300">Cloud keys:</strong> new keys are saved to your Firebase database and work instantly on any device. Share the site link plus the key. Revoke disables a key everywhere.</div>',
           s, count=1)

# 7. Replace logic with cloud versions
replace_fn('handleLogin', r'''
        async function handleLogin() {
            const val = document.getElementById('login-key-input').value.trim();
            const err = document.getElementById('login-error');
            err.classList.add('hidden');
            if (!val) return;
            if (val.startsWith('ADAM-TEAM-')) {
                const rec = await fbGet('teamKeys/' + encodeURIComponent(val));
                if (rec && rec.active === true) {
                    appState.role = 'team'; appState.currentKey = val; appState.currentName = rec.name;
                    appState.geminiKey = rec.gemini || ''; appState.groqKey = rec.groq || '';
                    appState.teamKeys = [{ key: val, name: rec.name, requests: rec.requests || 0, active: true }];
                    return startApp();
                }
            } else {
                const tok = await fbSignIn(CLOUD.ownerEmail, val);
                if (tok) {
                    ownerToken = tok; ownerPass = val;
                    appState.role = 'owner'; appState.currentKey = 'OWNER-MASTER';
                    appState.currentName = 'Master Owner (Mohamed Asif)';
                    await loadCloudOwnerData();
                    return startApp();
                }
            }
            err.classList.remove('hidden');
        }
''')

replace_fn('generateTeamKey', r'''
        async function generateTeamKey() {
            const name = prompt("Enter team member's full name:");
            if (!name) return;
            const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
            const newKey = 'ADAM-TEAM-' + Array.from(crypto.getRandomValues(new Uint8Array(8)), b => chars[b % 32]).join('');
            const ok = await fbOwner('PUT', 'teamKeys/' + newKey, {
                name, role: 'Senior DBA Team Member', requests: 0, active: true,
                gemini: appState.geminiKey, groq: appState.groqKey
            });
            if (ok === null) { alert('Could not save to the cloud. Check your Firebase rules and owner login.'); return; }
            appState.teamKeys.push({ key: newKey, name, role: 'Senior DBA Team Member', requests: 0, active: true });
            renderTeamKeysTable();
            navigator.clipboard.writeText(newKey);
            alert(`Key for ${name}: ${newKey}\n\nCopied. It works immediately on any device. Share the site link and this key.`);
        }
''')

replace_fn('revokeTeamKey', r'''
        async function revokeTeamKey(idx) {
            const k = appState.teamKeys[idx];
            if (await fbOwner('PATCH', 'teamKeys/' + k.key, { active: false }) === null) { alert('Cloud update failed.'); return; }
            k.active = false;
            renderTeamKeysTable();
        }
''')

replace_fn('saveApiKeys', r'''
        async function saveApiKeys() {
            appState.geminiKey = document.getElementById('owner-gemini-key').value.trim();
            appState.groqKey = document.getElementById('owner-groq-key').value.trim();
            localStorage.setItem('adam_gemini_key', appState.geminiKey);
            localStorage.setItem('adam_groq_key', appState.groqKey);
            await fbOwner('PUT', 'ownerConfig', { gemini: appState.geminiKey, groq: appState.groqKey });
            for (const k of appState.teamKeys.filter(k => k.active))
                await fbOwner('PATCH', 'teamKeys/' + k.key, { gemini: appState.geminiKey, groq: appState.groqKey });
            alert('API keys saved and synced. Team members pick them up automatically.');
        }
''')

replace_fn('updateOwnerPassword', r'''
        async function updateOwnerPassword() {
            const pass = document.getElementById('owner-new-password').value.trim();
            if (pass.length < 6) { alert('Use at least 6 characters.'); return; }
            try {
                const r = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:update?key=${CLOUD.webApiKey}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idToken: ownerToken, password: pass, returnSecureToken: true })
                });
                if (!r.ok) throw new Error();
                ownerToken = (await r.json()).idToken; ownerPass = pass;
                document.getElementById('owner-new-password').value = '';
                alert('Owner password updated on all devices.');
            } catch (e) { alert('Password update failed.'); }
        }
''')

replace_fn('trackUsage', r'''
        function trackUsage() {
            if (appState.role !== 'team') return;
            const f = appState.teamKeys.find(k => k.key === appState.currentKey);
            if (!f) return;
            f.requests = (f.requests || 0) + 1;
            fbBump(f.key, f.requests);
        }
''')

prepend_fn('handleLogout', "ownerToken = null; ownerPass = ''; appState.geminiKey = ''; appState.groqKey = '';")
prepend_fn('switchTab', "if (tabId === 'owner' && appState.role === 'owner') loadCloudOwnerData().then(renderTeamKeysTable);")

# 8. Invite links now go through real validation
sub('checkInviteLink();', r'''(function () {
            const k = new URLSearchParams(location.search).get('key');
            if (!k) return;
            document.getElementById('login-key-input').value = k;
            history.replaceState({}, document.title, location.origin + location.pathname);
            handleLogin();
        })();''')

open('index.fixed.html', 'w', encoding='utf-8').write(s)
print('\nDone! Created index.fixed.html. Rename it to index.html, then commit and push.')
