"""Tajik Win independent play-credit game rules. All monetary values are integer UZS."""
import math, secrets
from collections import Counter
R=secrets.SystemRandom()
MIN_BET,MAX_BET=3000,1_000_000
RED={1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
SYMBOLS=['CHERRY','LEMON','GRAPE','BELL','DIAMOND','SEVEN']
SLOT_WEIGHTS=[30,26,20,12,8,4]
SLOT_PAY={'CHERRY':8,'LEMON':7,'GRAPE':10,'BELL':18,'DIAMOND':30,'SEVEN':70}
SUITS='♠♥♦♣'
RANKS=list(range(2,15))
WHEEL_SECTORS=[0]*6+[0.5]*6+[1]*3+[2]*4+[5]
PLINKO_TABLES={
 'low':[3.91,1.96,1.37,1.08,.88,.73,.88,1.08,1.37,1.96,3.91],
 'medium':[19.1,7.16,2.39,1.19,.54,.30,.54,1.19,2.39,7.16,19.1],
 'high':[57.1,14.53,4.15,.73,.073,0,.073,.73,4.15,14.53,57.1],
}
# Keno supports 1–10 picks. Multipliers are normalized to ~96% theoretical RTP.
def keno_table(picks):
    if type(picks)!=int or not 1<=picks<=10:raise ValueError('Выбери от 1 до 10 чисел')
    threshold=max(1,math.ceil(picks*.5))
    weights={hits:(2**(hits-threshold) if hits>=threshold else 0) for hits in range(picks+1)}
    ev=sum(math.comb(picks,h)*math.comb(40-picks,10-h)/math.comb(40,10)*weights[h] for h in weights)
    return {h:round(.96*weights[h]/ev,3) for h in weights}

def validate_stake(stake):
    if type(stake) is not int or not MIN_BET<=stake<=MAX_BET: raise ValueError('Ставка должна быть от 3 000 до 1 000 000 сум')

def deck():
    cards=[f'{r}:{s}' for s in range(4) for r in RANKS]
    R.shuffle(cards)
    return cards

def rank(card):return int(card.split(':')[0])
def card_label(card):
    r,s=card.split(':'); r=int(r)
    return f'{ {11:"J",12:"Q",13:"K",14:"A"}.get(r,str(r))}{SUITS[int(s)]}'
def hand_value(hand):
    vals=[rank(c) for c in hand]
    total=sum(11 if r==14 else min(10,r) for r in vals)
    for r in vals:
        if r==14 and total>21:total-=10
    return total

def instant(game,stake,params):
    validate_stake(stake)
    if game=='slots':
        reels=R.choices(SYMBOLS,weights=SLOT_WEIGHTS,k=3)
        mult=SLOT_PAY[reels[0]] if len(set(reels))==1 else 1 if len(set(reels))==2 else 0
        return {'reels':reels,'multiplier':mult},stake*mult
    if game=='roulette':
        typ=str(params.get('type','color')); value=str(params.get('value','red'))
        if typ=='color' and value not in ('red','black'):raise ValueError('Выбери красное или чёрное')
        if typ=='parity' and value not in ('even','odd'):raise ValueError('Выбери чёт или нечёт')
        if typ=='number' and (not value.isdigit() or int(value)>36):raise ValueError('Выбери число 0–36')
        if typ not in ('color','number','parity'):raise ValueError('Неизвестный вид ставки')
        n=R.randrange(37); color='green' if n==0 else 'red' if n in RED else 'black'
        ok=(typ=='number' and int(value)==n) or (typ=='color' and color==value) or (typ=='parity' and n!=0 and ('even' if n%2==0 else 'odd')==value)
        mult=(36 if typ=='number' else 2) if ok else 0
        return {'number':n,'color':color,'bet_type':typ,'bet_value':value,'multiplier':mult},stake*mult
    if game=='dice':
        guess=str(params.get('guess','under'))
        if guess not in ('under','seven','over'):raise ValueError('Выбери меньше / равно / больше 7')
        a,b=R.randint(1,6),R.randint(1,6); total=a+b
        win={'under':total<7,'seven':total==7,'over':total>7}[guess]
        # P(under)=15/36, P(seven)=6/36. Multipliers target 96% RTP.
        mult=(2.3 if guess!='seven' else 5.75) if win else 0
        return {'dice':[a,b],'sum':total,'guess':guess,'multiplier':mult},int(stake*mult)
    if game=='plinko':
        risk=params.get('risk','medium')
        if risk not in PLINKO_TABLES:raise ValueError('Выбери риск')
        path=[R.randrange(2) for _ in range(10)]; idx=sum(path)
        mult=PLINKO_TABLES[risk][idx]
        return {'path':path,'slot':idx,'risk':risk,'multiplier':mult},int(stake*mult)
    if game=='keno':
        picks=params.get('numbers',[])
        if not isinstance(picks,list) or not 1<=len(picks)<=10 or any(type(n)!=int or not 1<=n<=40 for n in picks) or len(set(picks))!=len(picks):raise ValueError('Выбери от одного до десяти разных чисел от 1 до 40')
        draw=R.sample(range(1,41),10);hits=len(set(picks)&set(draw));mult=keno_table(len(picks))[hits]
        return {'picks':sorted(picks),'draw':sorted(draw),'hits':hits,'multiplier':mult},int(stake*mult)
    if game=='wheel':
        i=R.randrange(len(WHEEL_SECTORS));mult=WHEEL_SECTORS[i]
        return {'index':i,'sectors':WHEEL_SECTORS,'multiplier':mult},int(stake*mult)
    raise ValueError('Неизвестная игра')

def new_session(game,stake,params):
    validate_stake(stake)
    if game=='blackjack':
        d=deck();player=[d.pop(),d.pop()];dealer=[d.pop(),d.pop()]
        return {'game':game,'stake':stake,'deck':d,'player':player,'dealer':dealer,'status':'active','phase':'playing'}
    if game=='mines':
        count=params.get('mines',3)
        if type(count)!=int or not 1<=count<=24:raise ValueError('Количество мин: 1–24')
        return {'game':game,'stake':stake,'mines':R.sample(range(25),count),'count':count,'opened':[],'status':'active'}
    if game=='hilo':
        d=deck();first=d.pop()
        return {'game':game,'stake':stake,'deck':d,'current':first,'steps':0,'multiplier':1.0,'status':'active'}
    if game=='poker':
        d=deck();cards=[d.pop() for _ in range(5)]
        return {'game':game,'stake':stake,'deck':d,'cards':cards,'status':'active'}
    if game=='tower':
        return {'game':game,'stake':stake,'safe':[R.randrange(3) for _ in range(7)],'level':0,'status':'active'}
    raise ValueError('Неизвестная игра')

def public_session(s,finished=False):
    game=s['game'];result={'game':game,'stake':s['stake'],'status':s['status']}
    if game=='blackjack':
        result.update(player=[card_label(x) for x in s['player']],player_value=hand_value(s['player']))
        result['dealer']=[card_label(x) for x in s['dealer']] if finished else [card_label(s['dealer'][0]),'🂠']
        if finished:result['dealer_value']=hand_value(s['dealer'])
    elif game=='mines':
        result.update(opened=s['opened'],mines_count=s['count'],multiplier=mines_multiplier(s))
        if finished:result['mines']=s['mines']
    elif game=='hilo':result.update(current=card_label(s['current']),steps=s['steps'],multiplier=s['multiplier'])
    elif game=='poker':result['cards']=[card_label(x) for x in s['cards']]
    elif game=='tower':
        result.update(level=s['level'],multiplier=round((2.85**s['level']),2))
        if finished:result['safe']=s['safe']
    if finished:
        result.update(payout=s.get('payout',0),multiplier=round(s.get('payout',0)/s['stake'],3),outcome=s.get('outcome',''))
    return result

def mines_multiplier(s):
    n=len(s['opened']);safe=25-s['count']
    # Exact combinatorial survival factor with 4% house edge.
    return round(.96*math.comb(25,n)/math.comb(safe,n),3) if n else 1.0

def poker_evaluate(cards):
    rs=[rank(c) for c in cards];freq=sorted(Counter(rs).values(),reverse=True);suits=[c.split(':')[1] for c in cards]
    flush=len(set(suits))==1; unique=set(rs)
    straight=len(unique)==5 and (max(rs)-min(rs)==4 or unique=={14,2,3,4,5})
    if straight and flush and unique=={10,11,12,13,14}:return 'ROYAL FLUSH',250
    if straight and flush:return 'STRAIGHT FLUSH',50
    if freq[0]==4:return 'FOUR OF A KIND',20
    if freq==[3,2]:return 'FULL HOUSE',8
    if flush:return 'FLUSH',6
    if straight:return 'STRAIGHT',5
    if freq[0]==3:return 'THREE OF A KIND',3
    if freq==[2,2,1]:return 'TWO PAIRS',2
    if freq[0]==2 and any(r>=11 and n==2 for r,n in Counter(rs).items()):return 'JACKS OR BETTER',1
    return 'NO WIN',0

def move(s,action,params):
    """Mutates session; returns (public outcome, payout or None). None means ongoing."""
    if s['status']!='active':raise ValueError('Раунд уже завершён')
    g=s['game']; stake=s['stake']; payout=None
    if g=='blackjack':
        if action not in ('hit','stand'):raise ValueError('Выбери Взять или Хватит')
        if action=='hit':
            s['player'].append(s['deck'].pop())
            if hand_value(s['player'])>21:payout=0;s['outcome']='Перебор'
        if action=='stand' or payout is not None:
            if payout is None:
                while hand_value(s['dealer'])<17:s['dealer'].append(s['deck'].pop())
                p,d=hand_value(s['player']),hand_value(s['dealer'])
                payout=stake*2 if d>21 or p>d else stake if p==d else 0
                s['outcome']='Победа' if payout>stake else 'Ничья' if payout==stake else 'Проигрыш'
    elif g=='mines':
        if action=='open':
            idx=params.get('index')
            if type(idx)!=int or not 0<=idx<25 or idx in s['opened']:raise ValueError('Неверная клетка')
            if idx in s['mines']:payout=0;s['outcome']='Мина'
            else:
                s['opened'].append(idx)
                if len(s['opened'])==25-s['count']:payout=int(stake*mines_multiplier(s));s['outcome']='Все клетки открыты'
        elif action=='cashout':
            if not s['opened']:raise ValueError('Сначала открой клетку')
            payout=int(stake*mines_multiplier(s));s['outcome']='Забрано'
        else:raise ValueError('Неверное действие')
    elif g=='hilo':
        if action in ('higher','lower'):
            nxt=s['deck'].pop();a,b=rank(s['current']),rank(nxt)
            win=(b>a if action=='higher' else b<a)
            # Dynamic fair odds using remaining deck composition BEFORE pop (including the selected next card).
            remaining=s['deck']+[nxt]
            favorable=sum(1 for c in remaining if (rank(c)>a if action=='higher' else rank(c)<a))
            s['last_card']=card_label(nxt);s['current']=nxt
            if not win:payout=0;s['outcome']='Не угадал'
            else:
                s['steps']+=1;s['multiplier']=round(s['multiplier']*.96*len(remaining)/favorable,4)
                if s['steps']>=10:payout=int(stake*s['multiplier']);s['outcome']='Десять угадываний'
        elif action=='cashout':
            if not s['steps']:raise ValueError('Сначала угадай карту')
            payout=int(stake*s['multiplier']);s['outcome']='Забрано'
        else:raise ValueError('Неверное действие')
    elif g=='poker':
        if action!='draw':raise ValueError('Выбери карты для удержания')
        holds=params.get('hold',[])
        if not isinstance(holds,list) or any(type(i)!=int or not 0<=i<5 for i in holds) or len(set(holds))!=len(holds):raise ValueError('Неверные карты')
        s['cards']=[c if i in holds else s['deck'].pop() for i,c in enumerate(s['cards'])]
        hand,mult=poker_evaluate(s['cards']);payout=stake*mult;s['outcome']=hand
    elif g=='tower':
        if action=='pick':
            idx=params.get('index')
            if type(idx)!=int or idx not in (0,1,2):raise ValueError('Выбери клетку')
            if idx!=s['safe'][s['level']]:payout=0;s['outcome']='Неверная клетка'
            else:
                s['level']+=1
                if s['level']==len(s['safe']):payout=int(stake*2.85**s['level']);s['outcome']='Башня пройдена'
        elif action=='cashout':
            if not s['level']:raise ValueError('Сначала пройди этаж')
            payout=int(stake*2.85**s['level']);s['outcome']='Забрано'
        else:raise ValueError('Неверное действие')
    else:raise ValueError('Неизвестная игра')
    if payout is not None:s.update(status='finished',payout=payout)
    result=public_session(s,payout is not None)
    if 'last_card' in s:result['last_card']=s['last_card']
    return result,payout

def crash_point():
    """A bounded 1.00..21.00 distribution with target survival P(X>=m)=0.96/m for m>1.
    Mass 0.04 instant bust at 1.00, mass at cap ~0.96/21. Users can verify model.
    """
    u=R.random()
    if u<.04:return 1.0
    return round(min(21.0,.96/(1-u)),2)

def crash_multiplier(elapsed):return min(21.0, round(math.exp(.16*max(0,elapsed)),2))
