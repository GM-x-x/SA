"""pets_info.json + riding_by_character.json -> index.html (단일 정적 파일). 원본은 수정하지 않는다.
랭킹 닉네임(게임 내 공개 닉네임) 포함."""
import json, os, collections
B = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(B)
pets = json.load(open(f'{R}/pets_info.json'))['pets']
chars = json.load(open(f'{R}/riding_by_character.json'))['characters']
imgs = {f[:4]: f for f in os.listdir(f'{R}/pet_images')} if os.path.isdir(f'{R}/pet_images') else {}
by_name = collections.defaultdict(list)
for p in pets: by_name[p['name']].append(p['id'])

def grade(s):
    s = (s or '').replace(' ', '')
    if s.startswith('일반'): return '일반'
    if s in ('1등급', '2등급'): return s
    return ''  # 오염값(테르가 등) 숨김

P = []
for p in pets:
    k = f"{p['id']:04d}"
    P.append(dict(id=p['id'], n=p['name'], acq=p['acquisition'], attr=p['attributes'],
        b=[p['base_stats'][x] for x in ('atk','def','agi','hp')],
        g=[p['growth_rates'][x] for x in ('atk','def','agi','hp')], tg=p['total_growth'],
        ride=p['rideable'] == '탑승가능', sg=grade(p['sell_grade']),
        rk=[[e['nick'], e['lv'], e['atk'], e['def'], e['agi'], e['hp']] for e in p['ranking']],
        img=('pet_images/' + imgs[k]) if k in imgs else '', ext=p['image'], url=p['url']))

C, miss = {}, collections.defaultdict(list)
for c, v in chars.items():
    names = v.get('rides') or (v['rides_left_column'] + v['rides_right_column'])
    ids, un = [], []
    for n in names:
        if n in by_name: ids.append(by_name[n])
        else: un.append(n); miss[n].append(c)
    C[c] = dict(ids=ids, un=un, note=v.get('note', ''))
print('미매칭 이름:', len(miss), '(탑승 항목 총', sum(len(v) for v in miss.values()), '건)')
for n, cs in miss.items(): print(' ', n, '←', ', '.join(cs))
print('동명 펫(복수 id 연결):', sorted(n for n, i in by_name.items() if len(i) > 1))
print('이미지 누락:', sum(1 for p in P if not p['img']), '/', len(P))
tpl = open(f'{B}/template.html', encoding='utf-8').read()
J = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))
base = tpl.replace('__PETS__', J(P)).replace('__CHARS__', J(C))

# 공개용: 기록 화면 없음, 로컬 전용 구간(<!--LOCAL-->…<!--/LOCAL-->, /*LOCAL*/…/*/LOCAL*/)은 통째로 제거
import re
def strip_local(s):
    s = re.sub(r'<!--LOCAL-->.*?<!--/LOCAL-->', '', s, flags=re.S)
    return re.sub(r'/\*LOCAL\*/.*?/\*/LOCAL\*/', '', s, flags=re.S)
public = strip_local(base).replace('__HIST__', 'null')
assert '__HIST__' not in public and '"timeline"' not in public
assert 'nickSearch' not in public and '닉네임 검색' not in public and 'LOCAL' not in public, '공개용에 로컬 전용 코드가 남음'
open(f'{R}/index.html', 'w', encoding='utf-8').write(public)  # 저장소 루트 = 사이트 첫 화면

# 로컬 전용: 변화 기록 화면 포함 (index.local.html 은 .gitignore 로 저장소에 올라가지 않는다)
H = f'{R}/history'
hist = None
if os.path.isdir(f'{H}/changes'):
    ev = collections.defaultdict(list)
    for f in sorted(os.listdir(f'{H}/changes')):
        c = json.load(open(f'{H}/changes/{f}', encoding='utf-8'))
        for ch in c['pets']:
            for e in ch['events']:
                ev[str(ch['id'])].append(dict(e, at=c['to']))
    tl = json.load(open(f'{H}/timeline.json', encoding='utf-8')) if os.path.exists(f'{H}/timeline.json') else {}
    hist = dict(events=ev, timeline=tl)
    n = sum(len(v) for v in ev.values())
    print('로컬 기록 화면: 이벤트', n, '건 /', len(ev), '종, 시계열', len(tl), '종')
open(f'{R}/index.local.html', 'w', encoding='utf-8').write(base.replace('__HIST__', J(hist)))
