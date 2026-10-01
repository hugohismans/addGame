#!/usr/bin/env python3
"""Génère AddGame.sb3 : une version Scratch 3 du jeu AddGame.

Le projet est construit entièrement ici : blocs (project.json), costumes SVG et sons WAV.
Architecture Scratch :
  - Scène      : décors, « quand la scène est cliquée » → message « clic », touches clavier.
  - Moteur     : toute la logique (listes = état des bulles et briques), dessin au stylo (tampon).
  - Opérateur  : 4 costumes (+ − × ÷), clic = opération suivante, affiche les messages.
  - Égal, Inverser : boutons.
"""
import hashlib, io, json, math, os, random, struct, wave, zipfile

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AddGame.sb3')

# ---------------------------------------------------------------- utilitaires ids
_uid = [0]
def nid(prefix='b'):
    _uid[0] += 1
    return f'{prefix}{_uid[0]:04d}'

# ---------------------------------------------------------------- variables / listes / messages
VARS = {}      # nom -> id
LISTS = {}
BROADCASTS = {}
def var_id(name):
    if name not in VARS: VARS[name] = nid('v')
    return VARS[name]
def list_id(name):
    if name not in LISTS: LISTS[name] = nid('l')
    return LISTS[name]
def bc_id(name):
    if name not in BROADCASTS: BROADCASTS[name] = nid('m')
    return BROADCASTS[name]

# ---------------------------------------------------------------- DSL des blocs
class Blk:
    def __init__(self, opcode, inputs=None, fields=None, sub=None, mutation=None, kind='stmt'):
        self.opcode, self.inputs, self.fields = opcode, inputs or {}, fields or {}
        self.sub, self.mutation, self.kind = sub or {}, mutation, kind

class Var:
    def __init__(self, name): self.name = name; var_id(name)

def R(opcode, **inputs):            # bloc reporter
    return Blk(opcode, inputs, kind='rep')
def Bo(opcode, **inputs):           # bloc booléen
    return Blk(opcode, inputs, kind='bool')
def S(opcode, inputs=None, fields=None, sub=None, mutation=None):
    return Blk(opcode, inputs, fields, sub, mutation)

# opérateurs
def add(a, b): return R('operator_add', NUM1=a, NUM2=b)
def sub(a, b): return R('operator_subtract', NUM1=a, NUM2=b)
def mul(a, b): return R('operator_multiply', NUM1=a, NUM2=b)
def div(a, b): return R('operator_divide', NUM1=a, NUM2=b)
def rnd(a, b): return R('operator_random', FROM=a, TO=b)
def lt(a, b): return Bo('operator_lt', OPERAND1=a, OPERAND2=b)
def gt(a, b): return Bo('operator_gt', OPERAND1=a, OPERAND2=b)
def eq(a, b): return Bo('operator_equals', OPERAND1=a, OPERAND2=b)
def AND(a, b): return Bo('operator_and', OPERAND1=a, OPERAND2=b)
def OR(a, b): return Bo('operator_or', OPERAND1=a, OPERAND2=b)
def NOT(a): return Bo('operator_not', OPERAND=a)
def join(a, b): return R('operator_join', STRING1=a, STRING2=b)
def joins(*parts):
    e = parts[-1]
    for p in reversed(parts[:-1]): e = join(p, e)
    return e
def letter(i, s): return R('operator_letter_of', LETTER=i, STRING=s)
def strlen(s): return R('operator_length', STRING=s)
def rround(a): return R('operator_round', NUM=a)
def mathop(fn, a):
    b = R('operator_mathop', NUM=a); b.fields = {'OPERATOR': [fn, None]}; return b
def sqrt(a): return mathop('sqrt', a)
def ABS(a): return mathop('abs', a)
def cos(a): return mathop('cos', a)
def sin(a): return mathop('sin', a)
def mousex(): return R('sensing_mousex')
def mousey(): return R('sensing_mousey')
def timer(): return R('sensing_timer')

# variables et listes
def v(name): return Var(name)
def setv(name, val): return S('data_setvariableto', {'VALUE': val}, {'VARIABLE': [name, var_id(name)]})
def chg(name, val): return S('data_changevariableby', {'VALUE': val}, {'VARIABLE': [name, var_id(name)]})
def item(lst, idx):
    b = R('data_itemoflist', INDEX=idx); b.fields = {'LIST': [lst, list_id(lst)]}; return b
def length(lst):
    b = R('data_lengthoflist'); b.fields = {'LIST': [lst, list_id(lst)]}; return b
def push(lst, val): return S('data_addtolist', {'ITEM': val}, {'LIST': [lst, list_id(lst)]})
def delete(lst, idx): return S('data_deleteoflist', {'INDEX': idx}, {'LIST': [lst, list_id(lst)]})
def clear(lst): return S('data_deletealloflist', {}, {'LIST': [lst, list_id(lst)]})
def replace(lst, idx, val): return S('data_replaceitemoflist', {'INDEX': idx, 'ITEM': val}, {'LIST': [lst, list_id(lst)]})
def showlist(lst): return S('data_showlist', {}, {'LIST': [lst, list_id(lst)]})
def hidelist(lst): return S('data_hidelist', {}, {'LIST': [lst, list_id(lst)]})

# contrôle
def forever(*body): return S('control_forever', sub={'SUBSTACK': list(body)})
def repeat(n, *body): return S('control_repeat', {'TIMES': n}, sub={'SUBSTACK': list(body)})
def until(cond, *body): return S('control_repeat_until', {'CONDITION': cond}, sub={'SUBSTACK': list(body)})
def IF(cond, *body): return S('control_if', {'CONDITION': cond}, sub={'SUBSTACK': list(body)})
def IFELSE(cond, yes, no): return S('control_if_else', {'CONDITION': cond}, sub={'SUBSTACK': list(yes), 'SUBSTACK2': list(no)})
def wait(t): return S('control_wait', {'DURATION': t})
def stop(what='this script'):
    return S('control_stop', {}, {'STOP_OPTION': [what, None]},
             mutation={'tagName': 'mutation', 'children': [], 'hasnext': 'false'})

# apparence, mouvement, son, stylo, événements
def goto(x, y): return S('motion_gotoxy', {'X': x, 'Y': y})
def costume(c): return S('looks_switchcostumeto', {'COSTUME': ('menu', 'looks_costume', 'COSTUME', c)})
def backdrop(c): return S('looks_switchbackdropto', {'BACKDROP': ('menu', 'looks_backdrops', 'BACKDROP', c)})
def size(s): return S('looks_setsizeto', {'SIZE': s})
def show(): return S('looks_show')
def hide(): return S('looks_hide')
def front(): return S('looks_gotofrontback', {}, {'FRONT_BACK': ['front', None]})
def say(m): return S('looks_say', {'MESSAGE': m})
def sayfor(m, t): return S('looks_sayforsecs', {'MESSAGE': m, 'SECS': t})
def nextcostume(): return S('looks_nextcostume')
def costumenum():
    b = R('looks_costumenumbername'); b.fields = {'NUMBER_NAME': ['number', None]}; return b
def play(snd): return S('sound_play', {'SOUND_MENU': ('menu', 'sound_sounds_menu', 'SOUND_MENU', snd)})
def pen_clear(): return S('pen_clear')
def stamp(): return S('pen_stamp')
def broadcast(name): return S('event_broadcast', {'BROADCAST_INPUT': ('bcast', name)})
def reset_timer(): return S('sensing_resettimer')
def call(proc): return S('procedures_call', mutation={'tagName': 'mutation', 'children': [], 'proccode': proc,
                                                      'argumentids': '[]', 'warp': 'true'})

# chapeaux (scripts)
def when_flag(*body): return ('hat', S('event_whenflagclicked'), list(body))
def when_clicked(*body): return ('hat', S('event_whenthisspriteclicked'), list(body))
def when_stage_clicked(*body): return ('hat', S('event_whenstageclicked'), list(body))
def when_key(key, *body): return ('hat', S('event_whenkeypressed', {}, {'KEY_OPTION': [key, None]}), list(body))
def when_bc(name, *body): return ('hat', S('event_whenbroadcastreceived', {}, {'BROADCAST_OPTION': [name, bc_id(name)]}), list(body))
def define(proc, *body): return ('def', proc, list(body))

# ---------------------------------------------------------------- compilation en JSON Scratch
NUM_INPUTS = {'NUM1', 'NUM2', 'NUM', 'X', 'Y', 'SIZE', 'TIMES', 'DURATION', 'SECS', 'FROM', 'TO'}
BOOL_INPUTS = {'CONDITION', 'OPERAND'}

class Compiler:
    def __init__(self):
        self.blocks = {}

    def lit(self, name, value, opcode):
        if opcode == 'data_changevariableby' and name == 'VALUE': t = 4
        elif opcode in ('data_itemoflist', 'data_deleteoflist', 'data_replaceitemoflist') and name == 'INDEX': t = 7
        elif opcode == 'operator_letter_of' and name == 'LETTER': t = 6
        elif name in NUM_INPUTS: t = 4
        else: t = 10
        return t, str(value)

    def input(self, parent, name, value, opcode):
        if isinstance(value, tuple) and value[0] == 'menu':
            _, mop, field, val = value
            sid = nid('s')
            dynamic = isinstance(val, (Blk, Var))
            self.blocks[sid] = {'opcode': mop, 'next': None, 'parent': parent, 'inputs': {},
                                'fields': {field: ['' if dynamic else val, None]}, 'shadow': True, 'topLevel': False}
            if dynamic:
                if isinstance(val, Var):
                    return [3, [12, val.name, var_id(val.name)], sid]
                return [3, self.expr(val, parent), sid]
            return [1, sid]
        if isinstance(value, tuple) and value[0] == 'bcast':
            return [1, [11, value[1], bc_id(value[1])]]
        if name in BOOL_INPUTS and opcode in ('operator_not',) or name == 'CONDITION' or \
           (opcode in ('operator_and', 'operator_or') and name in ('OPERAND1', 'OPERAND2')):
            return [2, self.expr(value, parent)]
        if isinstance(value, Var):
            t, _ = self.lit(name, 0, opcode)
            return [3, [12, value.name, var_id(value.name)], [t, '']]
        if isinstance(value, Blk):
            t, _ = self.lit(name, 0, opcode)
            return [3, self.expr(value, parent), [t, '']]
        t, s = self.lit(name, value, opcode)
        return [1, [t, s]]

    def expr(self, b, parent):
        bid = nid()
        node = {'opcode': b.opcode, 'next': None, 'parent': parent, 'inputs': {}, 'fields': dict(b.fields),
                'shadow': False, 'topLevel': False}
        self.blocks[bid] = node
        for k, val in b.inputs.items():
            node['inputs'][k] = self.input(bid, k, val, b.opcode)
        return bid

    def stmts(self, lst, parent):
        first = prev = None
        for b in lst:
            bid = nid()
            node = {'opcode': b.opcode, 'next': None, 'parent': prev or parent, 'inputs': {},
                    'fields': dict(b.fields), 'shadow': False, 'topLevel': False}
            if b.mutation: node['mutation'] = b.mutation
            self.blocks[bid] = node
            for k, val in b.inputs.items():
                node['inputs'][k] = self.input(bid, k, val, b.opcode)
            for k, body in b.sub.items():
                if body: node['inputs'][k] = [2, self.stmts(body, bid)]
            if prev: self.blocks[prev]['next'] = bid
            else: first = bid
            prev = bid
        return first

    def script(self, s, x, y):
        if s[0] == 'hat':
            _, hat, body = s
            hid = nid()
            node = {'opcode': hat.opcode, 'next': None, 'parent': None, 'inputs': {}, 'fields': dict(hat.fields),
                    'shadow': False, 'topLevel': True, 'x': x, 'y': y}
            self.blocks[hid] = node
            node['next'] = self.stmts(body, hid)
        else:
            _, proc, body = s
            did, pid = nid(), nid()
            self.blocks[did] = {'opcode': 'procedures_definition', 'next': None, 'parent': None,
                                'inputs': {'custom_block': [1, pid]}, 'fields': {}, 'shadow': False,
                                'topLevel': True, 'x': x, 'y': y}
            self.blocks[pid] = {'opcode': 'procedures_prototype', 'next': None, 'parent': did, 'inputs': {},
                                'fields': {}, 'shadow': True, 'topLevel': False,
                                'mutation': {'tagName': 'mutation', 'children': [], 'proccode': proc,
                                             'argumentids': '[]', 'argumentnames': '[]',
                                             'argumentdefaults': '[]', 'warp': 'true'}}
            self.blocks[did]['next'] = self.stmts(body, did)

def compile_scripts(scripts):
    c = Compiler()
    for k, s in enumerate(scripts):
        c.script(s, (k % 3) * 520, (k // 3) * 900)
    return c.blocks

# ---------------------------------------------------------------- dessins SVG
CYAN, ORANGE, ICE, GOLD, PINK, VOID = '#3ef0ff', '#ff9d2e', '#e9fdff', '#ffe066', '#ff4fd8', '#03060d'

def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg>')

# chiffres à 7 segments (style néon), boîte 24 × 36
SEG = {'a': (4, 3, 20, 3), 'b': (21, 4, 21, 17), 'c': (21, 19, 21, 32), 'd': (4, 33, 20, 33),
       'e': (3, 19, 3, 32), 'f': (3, 4, 3, 17), 'g': (4, 18, 20, 18)}
DIGITS = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc', '5': 'afgcd',
          '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg'}
def digit_svg(d):
    lines = ''.join(f'<line x1="{SEG[s][0]}" y1="{SEG[s][1]}" x2="{SEG[s][2]}" y2="{SEG[s][3]}"/>' for s in DIGITS[d])
    return svg(24, 36, f'<g stroke="{ICE}" stroke-width="4" stroke-linecap="round">{lines}</g>')

def bubble_svg():
    return svg(56, 56, f'<circle cx="28" cy="28" r="26" fill="none" stroke="{CYAN}" stroke-opacity=".25" stroke-width="4"/>'
                       f'<circle cx="28" cy="28" r="23" fill="#04121e" stroke="{CYAN}" stroke-width="3.5"/>'
                       f'<circle cx="28" cy="28" r="18" fill="none" stroke="{CYAN}" stroke-opacity=".35" stroke-width="1"/>')

def brick_svg():
    return svg(56, 56, f'<rect x="2" y="2" width="52" height="52" rx="12" fill="none" stroke="{ORANGE}" stroke-opacity=".25" stroke-width="4"/>'
                       f'<rect x="5" y="5" width="46" height="46" rx="10" fill="#1a0c02" stroke="{ORANGE}" stroke-width="3.5"/>')

def operator_svg(sym):
    ticks = ''.join(
        f'<line x1="{40 + 27 * math.cos(a):.1f}" y1="{40 + 27 * math.sin(a):.1f}" x2="{40 + 32 * math.cos(a):.1f}" y2="{40 + 32 * math.sin(a):.1f}"/>'
        for a in [i * math.pi / 8 for i in range(16)])
    s = {
        '+': '<line x1="25" y1="40" x2="55" y2="40"/><line x1="40" y1="25" x2="40" y2="55"/>',
        '-': '<line x1="25" y1="40" x2="55" y2="40"/>',
        'x': '<line x1="29" y1="29" x2="51" y2="51"/><line x1="51" y1="29" x2="29" y2="51"/>',
        '/': '<line x1="25" y1="40" x2="55" y2="40"/><circle cx="40" cy="29" r="3.5" fill="%s" stroke="none"/><circle cx="40" cy="51" r="3.5" fill="%s" stroke="none"/>' % (ICE, ICE),
    }[sym]
    return svg(80, 80, f'<circle cx="40" cy="40" r="37" fill="#061a28" stroke="{ICE}" stroke-width="4"/>'
                       f'<g stroke="{CYAN}" stroke-width="2.5" stroke-linecap="round">{ticks}</g>'
                       f'<g stroke="{ICE}" stroke-width="7" stroke-linecap="round">{s}</g>')

def equal_btn_svg():
    return svg(64, 44, f'<rect x="2" y="2" width="60" height="40" rx="9" fill="#2a1404" stroke="{ORANGE}" stroke-width="3"/>'
                       f'<g stroke="{ORANGE}" stroke-width="5" stroke-linecap="round"><line x1="20" y1="16" x2="44" y2="16"/><line x1="20" y1="28" x2="44" y2="28"/></g>')

def swap_btn_svg():
    return svg(48, 48, f'<circle cx="24" cy="24" r="21" fill="#0a1620" stroke="{ICE}" stroke-width="3"/>'
                       f'<g fill="none" stroke="{ICE}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
                       f'<path d="M13 19h21M29 14l5 5-5 5"/><path d="M35 29H14M19 24l-5 5 5 5"/></g>')

def backdrop_svg(title=None):
    grid = ''.join(f'<line x1="{x}" y1="0" x2="{x}" y2="320"/>' for x in range(0, 481, 40)) + \
           ''.join(f'<line x1="0" y1="{y}" x2="480" y2="{y}"/>' for y in range(0, 321, 40))
    extra = ''
    if title:
        extra = (f'<text x="148" y="70" font-family="Sans Serif" font-size="44" font-weight="bold" fill="{GOLD}">{title}</text>'
                 f'<text x="96" y="100" font-family="Sans Serif" font-size="14" fill="{ICE}">Drapeau vert pour rejouer</text>')
    return svg(480, 360,
               f'<rect width="480" height="360" fill="{VOID}"/>'
               f'<g stroke="{CYAN}" stroke-opacity=".08" stroke-width="1">{grid}</g>'
               f'<rect x="1" y="1" width="478" height="318" fill="none" stroke="{CYAN}" stroke-opacity=".5" stroke-width="2"/>'
               f'<rect x="0" y="320" width="480" height="40" fill="#07111d"/>'
               f'<line x1="0" y1="320" x2="480" y2="320" stroke="{CYAN}" stroke-opacity=".5" stroke-width="2"/>'
               f'<text x="10" y="337" font-family="Sans Serif" font-size="11" fill="#7fa3b3">Clic : accrocher / décrocher une bulle</text>'
               f'<text x="10" y="352" font-family="Sans Serif" font-size="11" fill="#7fa3b3">Clic sur l\'opérateur : changer · Espace : =</text>'
               f'<text x="404" y="16" font-family="Sans Serif" font-size="13" font-weight="bold" fill="{CYAN}">ADD<tspan fill="{ORANGE}">GAME</tspan></text>'
               + extra)

# ---------------------------------------------------------------- sons (WAV 22 050 Hz mono)
RATE = 22050
def wav_bytes(samples):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, s)) * 32000)) for s in samples))
    return buf.getvalue(), len(samples)

def tone(f0, f1, dur, vol=.5, shape='sine'):
    n = int(RATE * dur); out = []; ph = 0
    for i in range(n):
        t = i / n
        f = f0 * (f1 / f0) ** t
        ph += 2 * math.pi * f / RATE
        s = math.sin(ph) if shape == 'sine' else (2 * ((ph / (2 * math.pi)) % 1) - 1)
        env = min(1, i / (RATE * .005)) * (1 - t) ** 2
        out.append(s * env * vol)
    return out

def noise(dur, vol=.5):
    rng = random.Random(4); n = int(RATE * dur)
    return [rng.uniform(-1, 1) * vol * (1 - i / n) ** 3 for i in range(n)]

def mix(*parts):
    n = max(len(p) for p in parts); out = [0.0] * n
    for p in parts:
        for i, s in enumerate(p): out[i] += s
    return out

def seq(*parts):
    out = []
    for p in parts: out += p
    return out

SOUNDS = {
    'plouc': mix(tone(170, 760, .12, .6), [0] * 1000 + tone(950, 280, .2, .2)),
    'accroche': mix(tone(1400, 700, .05, .4, 'saw'), tone(220, 220, .12, .3)),
    'pop': mix(noise(.25, .5), tone(520, 70, .22, .4)),
    # buzzer grave haché (« brrr ») + souffle d'explosion
    'buzz': mix([((2 * ((80 * i / RATE) % 1) - 1) * (.5 if math.sin(2 * math.pi * 26 * i / RATE) > 0 else .05) * (1 - i / (RATE * .7)))
                 for i in range(int(RATE * .7))], noise(.6, .5)),
    'resultat': seq(tone(660, 660, .1, .4), tone(880, 880, .1, .4), tone(1320, 1320, .18, .4)),
    'bravo': seq(*[tone(f, f, .16, .45) for f in (523, 659, 784, 1047)], tone(1319, 1319, .4, .45)),
    'clic': tone(1900, 1500, .04, .3, 'saw'),
}

# ---------------------------------------------------------------- assets
ASSETS = {}   # md5ext -> bytes
def asset(data, ext):
    if isinstance(data, str): data = data.encode('utf-8')
    md5 = hashlib.md5(data).hexdigest()
    ASSETS[f'{md5}.{ext}'] = data
    return md5

def svg_costume(name, data, cx, cy):
    md5 = asset(data, 'svg')
    return {'assetId': md5, 'name': name, 'md5ext': f'{md5}.svg', 'dataFormat': 'svg',
            'rotationCenterX': cx, 'rotationCenterY': cy}

def sound(name):
    data, n = wav_bytes(SOUNDS[name])
    md5 = asset(data, 'wav')
    return {'assetId': md5, 'name': name, 'dataFormat': 'wav', 'format': '', 'rate': RATE,
            'sampleCount': n, 'md5ext': f'{md5}.wav'}

# ---------------------------------------------------------------- logique du jeu (Moteur)
# Listes parallèles : une entrée par bulle (type B) ou brique (type R).
#   type, val, x, y, vx, vy, etat (L libre, A accroché, X explose, Z consommé), cote (G/D), cd (pause), ord
LST = ['type', 'val', 'x', 'y', 'vx', 'vy', 'etat', 'cote', 'cd', 'ord']
I, J, K = v('i'), v('j'), v('k')
XMIN, XMAX, YMIN, YMAX = -232, 232, -132, 150
OPX, OPY, OPR = 0, 10, 34

def it(lst, idx=None): return item(lst, idx if idx is not None else I)

moteur_scripts = [
    when_flag(
        hide(), pen_clear(),
        *[clear(n) for n in LST], clear('Mes calculs'), hidelist('Mes calculs'),
        setv('Objectif', rnd(1, 99)), setv('Opérations', 0), setv('fini', 0), setv('compteur', 0),
        setv('spawnT', 0), setv('message', ''),
        repeat(4, call('nouvelle bulle')),
        forever(
            IF(eq(v('fini'), 0), call('physique'), call('apparitions')),
            call('dessin'),
        ),
    ),

    define('nouvelle bulle',
        setv('nv', rnd(1, 9)),
        setv('ok', 0), setv('essais', 0),
        until(OR(eq(v('ok'), 1), gt(v('essais'), 40)),
            setv('px', rnd(-200, 200)), setv('py', rnd(-100, 125)), chg('essais', 1),
            setv('ok', 1),
            IF(lt(sqrt(add(mul(v('px'), v('px')), mul(sub(v('py'), OPY), sub(v('py'), OPY)))), 110), setv('ok', 0)),
            setv('k', 1),
            repeat(length('type'),
                IF(lt(sqrt(add(mul(sub(v('px'), item('x', K)), sub(v('px'), item('x', K))),
                               mul(sub(v('py'), item('y', K)), sub(v('py'), item('y', K))))), 70), setv('ok', 0)),
                chg('k', 1)),
        ),
        setv('ang', rnd(0, 359)),
        setv('sp', sub(3.6, mul(0.2, v('nv')))),
        push('type', 'B'), push('val', v('nv')), push('x', v('px')), push('y', v('py')),
        push('vx', mul(v('sp'), cos(v('ang')))), push('vy', mul(v('sp'), sin(v('ang')))),
        push('etat', 'L'), push('cote', 'G'), push('cd', 15), push('ord', 0),
    ),

    define('apparitions',
        IF(lt(v('nb'), 4),
            IFELSE(eq(v('spawnT'), 0),
                [setv('spawnT', add(timer(), rnd('1.0', '2.0')))],
                [IF(gt(timer(), v('spawnT')), call('nouvelle bulle'), setv('spawnT', 0))])),
    ),

    # rayon de l'élément d'indice i (variable r), à partir de son type et de sa valeur
    define('rayon',
        IFELSE(eq(it('type'), 'B'),
               [setv('r', div(add(60, mul(7.5, sub(it('val'), 1))), 100 / 23))],
               [setv('r', 24)]),
    ),

    define('physique',
        setv('nb', 0),
        setv('i', 1),
        repeat(length('type'),
            IF(eq(it('type'), 'B'), chg('nb', 1)),
            IF(eq(it('etat'), 'L'),
                call('rayon'),
                # vitesse ramenée doucement vers la vitesse de croisière (le 1 file, le 9 traîne)
                setv('spd', sqrt(add(mul(it('vx'), it('vx')), mul(it('vy'), it('vy'))))),
                setv('cible', 2.4),
                IF(eq(it('type'), 'B'), setv('cible', sub(3.6, mul(0.2, it('val'))))),
                IFELSE(lt(v('spd'), 0.3),
                    [setv('ang', rnd(0, 359)), replace('vx', I, mul(v('cible'), cos(v('ang')))),
                     replace('vy', I, mul(v('cible'), sin(v('ang'))))],
                    [setv('fac', div(add(v('spd'), mul(sub(v('cible'), v('spd')), 0.03)), v('spd'))),
                     replace('vx', I, mul(it('vx'), v('fac'))), replace('vy', I, mul(it('vy'), v('fac')))]),
                replace('x', I, add(it('x'), it('vx'))),
                replace('y', I, add(it('y'), it('vy'))),
                # rebonds sur les bords (miroir)
                IF(gt(it('x'), sub(XMAX, v('r'))), replace('x', I, sub(XMAX, v('r'))), replace('vx', I, mul(-1, ABS(it('vx'))))),
                IF(lt(it('x'), add(XMIN, v('r'))), replace('x', I, add(XMIN, v('r'))), replace('vx', I, ABS(it('vx')))),
                IF(gt(it('y'), sub(YMAX, v('r'))), replace('y', I, sub(YMAX, v('r'))), replace('vy', I, mul(-1, ABS(it('vy'))))),
                IF(lt(it('y'), add(YMIN, v('r'))), replace('y', I, add(YMIN, v('r'))), replace('vy', I, ABS(it('vy')))),
                # rebond sur l'opérateur (rien ne s'y accroche par hasard)
                setv('dx', sub(it('x'), OPX)), setv('dy', sub(it('y'), OPY)),
                setv('d', sqrt(add(mul(v('dx'), v('dx')), mul(v('dy'), v('dy'))))),
                IF(AND(lt(v('d'), add(OPR, v('r'))), gt(v('d'), 0)),
                    setv('nx', div(v('dx'), v('d'))), setv('ny', div(v('dy'), v('d'))),
                    replace('x', I, add(OPX, mul(v('nx'), add(OPR, v('r'))))),
                    replace('y', I, add(OPY, mul(v('ny'), add(OPR, v('r'))))),
                    setv('vn', add(mul(it('vx'), v('nx')), mul(it('vy'), v('ny')))),
                    IF(lt(v('vn'), 0),
                       replace('vx', I, sub(it('vx'), mul(mul(2, v('vn')), v('nx')))),
                       replace('vy', I, sub(it('vy'), mul(mul(2, v('vn')), v('ny')))))),
                IF(gt(it('cd'), 0), replace('cd', I, sub(it('cd'), 1))),
            ),
            chg('i', 1),
        ),
        # rencontres entre bulles libres
        setv('i', 1),
        repeat(length('type'),
            setv('j', add(v('i'), 1)),
            until(gt(v('j'), length('type')),
                IF(AND(AND(eq(it('etat'), 'L'), eq(item('etat', J), 'L')),
                       AND(AND(eq(it('type'), 'B'), eq(item('type', J), 'B')),
                           AND(eq(it('cd'), 0), eq(item('cd', J), 0)))),
                    call('rayon'), setv('ri', v('r')),
                    setv('tmp', v('i')), setv('i', v('j')), call('rayon'), setv('i', v('tmp')),
                    setv('dx', sub(item('x', J), it('x'))), setv('dy', sub(item('y', J), it('y'))),
                    setv('d', sqrt(add(mul(v('dx'), v('dx')), mul(v('dy'), v('dy'))))),
                    IF(lt(v('d'), add(v('ri'), v('r'))), call('rencontre')),
                ),
                chg('j', 1),
            ),
            chg('i', 1),
        ),
        call('nettoyer'),
    ),

    # deux bulles se touchent : l'une gagne 1, l'autre perd 1, jamais la même paire, puis choc de billard
    define('rencontre',
        setv('a', it('val')), setv('b', item('val', J)),
        IFELSE(eq(sub(v('a'), v('b')), 1), [setv('choix', 1)],
               [IFELSE(eq(sub(v('b'), v('a')), 1), [setv('choix', 2)], [setv('choix', rnd(1, 2))])]),
        IFELSE(eq(v('choix'), 1),
               [replace('val', I, add(v('a'), 1)), replace('val', J, sub(v('b'), 1))],
               [replace('val', I, sub(v('a'), 1)), replace('val', J, add(v('b'), 1))]),
        # choc élastique, masses = valeurs
        IF(gt(v('d'), 0),
            setv('nx', div(v('dx'), v('d'))), setv('ny', div(v('dy'), v('d'))),
            setv('rv', add(mul(sub(item('vx', J), it('vx')), v('nx')), mul(sub(item('vy', J), it('vy')), v('ny')))),
            IF(lt(v('rv'), 0),
                setv('imp', div(mul(2, v('rv')), add(v('a'), v('b')))),
                replace('vx', I, add(it('vx'), mul(mul(v('imp'), v('b')), v('nx')))),
                replace('vy', I, add(it('vy'), mul(mul(v('imp'), v('b')), v('ny')))),
                replace('vx', J, sub(item('vx', J), mul(mul(v('imp'), v('a')), v('nx')))),
                replace('vy', J, sub(item('vy', J), mul(mul(v('imp'), v('a')), v('ny'))))),
            # écarte les deux bulles
            setv('ov', sub(add(v('ri'), v('r')), v('d'))),
            replace('x', I, sub(it('x'), mul(v('nx'), div(v('ov'), 2)))),
            replace('y', I, sub(it('y'), mul(v('ny'), div(v('ov'), 2)))),
            replace('x', J, add(item('x', J), mul(v('nx'), div(v('ov'), 2)))),
            replace('y', J, add(item('y', J), mul(v('ny'), div(v('ov'), 2)))),
        ),
        replace('cd', I, 12), replace('cd', J, 12),
        play('plouc'),
        IF(OR(eq(it('val'), 0), eq(it('val'), 10)), replace('etat', I, 'X')),
        IF(OR(eq(item('val', J), 0), eq(item('val', J), 10)), replace('etat', J, 'X')),
    ),

    # retire les éléments qui explosent (X) ou ont été utilisés dans un calcul (Z)
    define('nettoyer',
        setv('k', length('type')),
        until(lt(v('k'), 1),
            IF(OR(eq(item('etat', K), 'X'), eq(item('etat', K), 'Z')),
                IF(eq(item('etat', K), 'X'), play('pop')),
                *[delete(n, K) for n in LST]),
            chg('k', -1)),
    ),

    define('dessin',
        pen_clear(), show(),
        setv('i', 1),
        repeat(length('type'),
            IF(eq(it('etat'), 'A'),
                # place dans la file de son côté : gauche (G) ou droite (D) de l'opérateur
                setv('k', 0), setv('j', 1),
                repeat(length('type'),
                    IF(AND(eq(item('etat', J), 'A'), AND(eq(item('cote', J), it('cote')), lt(item('ord', J), it('ord')))),
                       chg('k', 1)),
                    chg('j', 1)),
                setv('sens', 1), IF(eq(it('cote'), 'G'), setv('sens', -1)),
                replace('x', I, mul(v('sens'), add(66, mul(48, v('k'))))),
                replace('y', I, OPY),
            ),
            IFELSE(eq(it('type'), 'B'),
                   [costume('bulle'), setv('taille', add(60, mul(7.5, sub(it('val'), 1)))),
                    IF(OR(eq(it('val'), 0), eq(it('val'), 10)), costume('bulle rouge'))],
                   [costume('brique'), setv('taille', 92)]),
            size(v('taille')), goto(it('x'), it('y')), stamp(),
            # le nombre, chiffre par chiffre
            setv('s', it('val')), setv('L', strlen(v('s'))),
            setv('tc', div(mul(v('taille'), 0.62), add(1, mul(0.28, sub(v('L'), 1))))),
            setv('dw', mul(26, div(v('tc'), 100))),
            size(v('tc')),
            setv('k', 1),
            repeat(v('L'),
                costume(join('d', letter(K, v('s')))),
                goto(add(it('x'), mul(sub(v('k'), div(add(v('L'), 1), 2)), v('dw'))), it('y')),
                stamp(), chg('k', 1)),
            chg('i', 1),
        ),
        hide(),
    ),

    # clic sur la scène : la bulle ou brique la plus proche du pointeur s'accroche ou se décroche
    # les réactions aux clics sont des blocs « sans rafraîchissement d'écran » : ils s'exécutent d'un seul coup,
    # sans que la boucle de physique (qui utilise les mêmes variables i, d, r…) ne passe au milieu
    when_bc('clic', call('clic souris')),
    define('clic souris',
        IF(eq(v('fini'), 0),
            setv('cible', 0), setv('dmin', 9999), setv('i', 1),
            repeat(length('type'),
                IF(OR(eq(it('etat'), 'L'), eq(it('etat'), 'A')),
                    call('rayon'),
                    setv('d', sqrt(add(mul(sub(mousex(), it('x')), sub(mousex(), it('x'))),
                                       mul(sub(mousey(), it('y')), sub(mousey(), it('y')))))),
                    IF(AND(lt(v('d'), add(v('r'), 10)), lt(v('d'), v('dmin'))), setv('dmin', v('d')), setv('cible', v('i')))),
                chg('i', 1)),
            IF(gt(v('cible'), 0),
                setv('i', v('cible')),
                IFELSE(eq(it('etat'), 'A'),
                    [replace('etat', I, 'L'), replace('cd', I, 10),
                     setv('dx', sub(it('x'), OPX)), setv('dy', sub(it('y'), OPY)),
                     setv('d', sqrt(add(mul(v('dx'), v('dx')), mul(v('dy'), v('dy'))))),
                     IF(eq(v('d'), 0), setv('d', 1)),
                     replace('vx', I, mul(4, div(v('dx'), v('d')))), replace('vy', I, mul(4, div(v('dy'), v('d')))),
                     play('clic')],
                    [replace('etat', I, 'A'), chg('compteur', 1), replace('ord', I, v('compteur')),
                     IFELSE(lt(it('x'), OPX), [replace('cote', I, 'G')], [replace('cote', I, 'D')]),
                     replace('vx', I, 0), replace('vy', I, 0), play('accroche')]),
            ),
        ),
    ),

    # demi-tour de l'opérateur : gauche et droite s'échangent
    when_bc('inverser', call('inverser')),
    define('inverser',
        setv('i', 1),
        repeat(length('type'),
            IF(eq(it('etat'), 'A'),
               IFELSE(eq(it('cote'), 'G'), [replace('cote', I, 'D')], [replace('cote', I, 'G')])),
            chg('i', 1)),
        play('clic'),
    ),

    when_bc('calculer', IF(eq(v('fini'), 0), call('calcul'))),

    define('calcul',
        setv('sG', 0), setv('sD', 0), setv('nG', 0), setv('nD', 0), setv('prod', 1), setv('nA', 0),
        setv('txtG', ''), setv('txtD', ''), setv('txtAll', ''),
        setv('signe', item('signes', v('op'))),
        setv('i', 1),
        repeat(length('type'),
            IF(eq(it('etat'), 'A'),
                chg('nA', 1), setv('prod', mul(v('prod'), it('val'))),
                IFELSE(eq(v('txtAll'), ''), [setv('txtAll', it('val'))],
                       [setv('txtAll', joins(v('txtAll'), ' ', v('signe'), ' ', it('val')))]),
                IFELSE(eq(it('cote'), 'G'),
                    [chg('sG', it('val')), chg('nG', 1),
                     IFELSE(eq(v('txtG'), ''), [setv('txtG', it('val'))], [setv('txtG', joins(v('txtG'), '+', it('val')))])],
                    [chg('sD', it('val')), chg('nD', 1),
                     IFELSE(eq(v('txtD'), ''), [setv('txtD', it('val'))], [setv('txtD', joins(v('txtD'), '+', it('val')))])])),
            chg('i', 1)),
        # il faut au moins deux nombres pour + et ×, un de chaque côté pour − et ÷
        IFELSE(OR(eq(v('op'), 1), eq(v('op'), 3)),
               [setv('ok', 0), IF(gt(v('nA'), 1), setv('ok', 1))],
               [setv('ok', 0), IF(AND(gt(v('nG'), 0), gt(v('nD'), 0)), setv('ok', 1))]),
        IF(eq(v('ok'), 0),
            IFELSE(OR(eq(v('op'), 1), eq(v('op'), 3)),
                   [setv('message', 'Accroche au moins deux nombres')],
                   [setv('message', 'Il faut un nombre à gauche et un à droite')]),
            broadcast('message'), stop('this script')),
        chg('Opérations', 1),
        IF(eq(v('op'), 1), setv('res', add(v('sG'), v('sD')))),
        IF(eq(v('op'), 2), setv('res', sub(v('sG'), v('sD')))),
        IF(eq(v('op'), 3), setv('res', v('prod'))),
        IF(eq(v('op'), 4), setv('res', div(v('sG'), v('sD')))),
        # texte du calcul : les groupes de plusieurs nombres d'un même côté entre parenthèses
        IFELSE(OR(eq(v('op'), 1), eq(v('op'), 3)),
            [setv('expr', v('txtAll'))],
            [IF(gt(v('nG'), 1), setv('txtG', joins('(', v('txtG'), ')'))),
             IF(gt(v('nD'), 1), setv('txtD', joins('(', v('txtD'), ')'))),
             setv('expr', joins(v('txtG'), ' ', v('signe'), ' ', v('txtD')))]),
        # les nombres utilisés disparaissent
        setv('i', 1),
        repeat(length('type'), IF(eq(it('etat'), 'A'), replace('etat', I, 'Z')), chg('i', 1)),
        call('nettoyer'),
        IFELSE(lt(v('res'), 0),
            [setv('message', 'Pas un nombre positif !'), push('Mes calculs', joins(v('expr'), ' : pas un nombre positif')),
             play('buzz'), broadcast('message')],
            [IFELSE(NOT(eq(rround(v('res')), v('res'))),
                [setv('message', 'Pas un nombre entier !'), push('Mes calculs', joins(v('expr'), ' : pas un nombre entier')),
                 play('buzz'), broadcast('message')],
                [IFELSE(eq(v('res'), 0),
                    [setv('message', joins(v('expr'), ' = 0 : la brique explose')), push('Mes calculs', joins(v('expr'), ' = 0')),
                     play('pop'), broadcast('message')],
                    [push('type', 'R'), push('val', v('res')), push('x', OPX), push('y', OPY), push('vx', 0), push('vy', 0),
                     push('etat', 'A'), chg('compteur', 1), push('ord', v('compteur')), push('cd', 0),
                     IFELSE(eq(rnd(1, 2), 1), [push('cote', 'G')], [push('cote', 'D')]),
                     push('Mes calculs', joins(v('expr'), ' = ', v('res'))),
                     setv('message', joins(v('expr'), ' = ', v('res'))),
                     IFELSE(eq(v('res'), v('Objectif')),
                            [setv('fini', 1), broadcast('gagné')],
                            [play('resultat'), broadcast('message')])])])]),
    ),

    when_bc('gagné', play('bravo'), showlist('Mes calculs')),
]

# ---------------------------------------------------------------- Opérateur
operator_scripts = [
    when_flag(
        goto(OPX, OPY), costume('plus'), setv('op', 1), show(), front(),
        clear('signes'), push('signes', '+'), push('signes', '−'), push('signes', '×'), push('signes', '÷'),
    ),
    when_clicked(
        IF(eq(v('fini'), 0), nextcostume(), setv('op', costumenum()), play('clic')),
    ),
    when_bc('message', sayfor(v('message'), 2)),
    when_bc('gagné', say(joins('Bravo ! ', v('Objectif'), ' en ', v('Opérations'), ' opération(s)'))),
]

equal_scripts = [
    when_flag(goto(196, -160), show()),
    when_clicked(broadcast('calculer')),
]
swap_scripts = [
    when_flag(goto(130, -160), show()),
    when_clicked(IF(eq(v('fini'), 0), broadcast('inverser'))),
]
stage_scripts = [
    when_flag(backdrop('jeu')),
    when_stage_clicked(broadcast('clic')),
    when_key('space', broadcast('calculer')),
    when_key('s', IF(eq(v('fini'), 0), broadcast('inverser'))),
    when_key('o', IF(eq(v('fini'), 0), broadcast('opération suivante'))),
    when_bc('gagné', backdrop('bravo')),
]
operator_scripts.append(when_bc('opération suivante', nextcostume(), setv('op', costumenum()), play('clic')))

# ---------------------------------------------------------------- assemblage
def target_base(name, is_stage, blocks, costumes, sounds, layer, **extra):
    t = {'isStage': is_stage, 'name': name, 'variables': {}, 'lists': {}, 'broadcasts': {}, 'blocks': blocks,
         'comments': {}, 'currentCostume': 0, 'costumes': costumes, 'sounds': sounds, 'volume': 100,
         'layerOrder': layer}
    t.update(extra)
    return t

def build():
    moteur_blocks = compile_scripts(moteur_scripts)
    op_blocks = compile_scripts(operator_scripts)
    eq_blocks = compile_scripts(equal_scripts)
    sw_blocks = compile_scripts(swap_scripts)
    st_blocks = compile_scripts(stage_scripts)

    digit_costumes = [svg_costume(f'd{d}', digit_svg(d), 12, 18) for d in '0123456789']
    red_bubble = bubble_svg().replace(CYAN, '#ff3b5c')
    moteur_costumes = [svg_costume('bulle', bubble_svg(), 28, 28), svg_costume('bulle rouge', red_bubble, 28, 28),
                       svg_costume('brique', brick_svg(), 28, 28)] + digit_costumes
    moteur_sounds = [sound(n) for n in ('plouc', 'accroche', 'pop', 'buzz', 'resultat', 'bravo', 'clic')]

    stage = target_base('Stage', True, st_blocks,
                        [svg_costume('jeu', backdrop_svg(), 240, 180), svg_costume('bravo', backdrop_svg('BRAVO !'), 240, 180)],
                        [], 0, tempo=60, videoTransparency=50, videoState='on', textToSpeechLanguage=None)
    defaults = {'Objectif': 0, 'Opérations': 0}
    stage['variables'] = {vid: [name, defaults.get(name, 0)] for name, vid in VARS.items()}
    stage['lists'] = {lid: [name, []] for name, lid in LISTS.items()}
    stage['broadcasts'] = {bid: name for name, bid in BROADCASTS.items()}

    def sprite(name, blocks, costumes, sounds, layer, x=0, y=0, visible=True):
        return target_base(name, False, blocks, costumes, sounds, layer, visible=visible, x=x, y=y, size=100,
                           direction=90, draggable=False, rotationStyle='all around')

    targets = [
        stage,
        sprite('Moteur', moteur_blocks, moteur_costumes, moteur_sounds, 1, visible=False),
        sprite('Opérateur', op_blocks,
               [svg_costume(n, operator_svg(s), 40, 40) for n, s in (('plus', '+'), ('moins', '-'), ('fois', 'x'), ('divise', '/'))],
               [sound('clic')], 2, OPX, OPY),
        sprite('Égal', eq_blocks, [svg_costume('égal', equal_btn_svg(), 32, 22)], [], 3, 196, -160),
        sprite('Inverser', sw_blocks, [svg_costume('inverser', swap_btn_svg(), 24, 24)], [], 4, 130, -160),
    ]

    monitors = [
        {'id': VARS['Objectif'], 'mode': 'default', 'opcode': 'data_variable', 'params': {'VARIABLE': 'Objectif'},
         'spriteName': None, 'value': 0, 'width': 0, 'height': 0, 'x': 5, 'y': 5, 'visible': True,
         'sliderMin': 0, 'sliderMax': 100, 'isDiscrete': True},
        {'id': VARS['Opérations'], 'mode': 'default', 'opcode': 'data_variable', 'params': {'VARIABLE': 'Opérations'},
         'spriteName': None, 'value': 0, 'width': 0, 'height': 0, 'x': 5, 'y': 32, 'visible': True,
         'sliderMin': 0, 'sliderMax': 100, 'isDiscrete': True},
        {'id': LISTS['Mes calculs'], 'mode': 'list', 'opcode': 'data_listcontents', 'params': {'LIST': 'Mes calculs'},
         'spriteName': None, 'value': [], 'width': 230, 'height': 170, 'x': 240, 'y': 125, 'visible': False},
    ]

    project = {'targets': targets, 'monitors': monitors, 'extensions': ['pen'],
               'meta': {'semver': '3.0.0', 'vm': '0.2.0', 'agent': 'AddGame generator'}}

    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('project.json', json.dumps(project, ensure_ascii=False))
        for name, data in ASSETS.items():
            z.writestr(name, data)
    total = sum(len(t['blocks']) for t in targets)
    print(f'OK {OUT} — {total} blocs, {len(ASSETS)} fichiers')

if __name__ == '__main__':
    build()
