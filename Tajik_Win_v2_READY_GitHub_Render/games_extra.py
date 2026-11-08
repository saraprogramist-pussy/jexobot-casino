"""Six independent play-money game engines. Payout tables are public, server is authoritative."""
import math
import random
from collections import Counter
rng=random.SystemRandom()

def plinko(stake:int, risk:str='medium'):
    if risk not in ('low','medium','high'): raise ValueError('invalid_risk')
    # 10 Bernoulli steps; distribution is binomial rather than arbitrary prizes.
    path=[rng.randrange(2) for _ in range(10)]
    slot=sum(path)
    tables={
      'low':[4,2,1.4,1.1,0.9,0.75,0.9,1.1,1.4,2,4],
      'medium':[16,6,2,1,0.45,0.25,0.45,1,2,6,16],
      'high':[55,14,4,0.7,0.07,0,0.07,0.7,4,14,55]
    }
    mult=tables[risk][slot]
    return {'path':path,'slot':slot,'multiplier':mult,'risk':risk},int(stake*mult)

def keno(stake:int, numbers:list):
    if not isinstance(numbers,list) or len(numbers)!=5 or any(type(n)!=int or n not in range(1,41) for n in numbers) or len(set(numbers))!=5: raise ValueError('select_five_unique_numbers')
    draw=rng.sample(range(1,41),10)
    hits=len(set(draw)&set(numbers))
    paytable={0:0,1:0,2:1,3:6,4:14,5:100}
    mult=paytable[hits]
    return {'draw':sorted(draw),'hits':hits,'picks':sorted(numbers),'multiplier':mult},int(stake*mult)

def wheel(stake:int):
    # Fixed 20 equally likely sectors. Published fixed outcomes; nonuniform payout with house edge.
    sectors=[0]*7+[0.5]*5+[1]*4+[2]*3+[5]
    idx=rng.randrange(len(sectors))
    mult=sectors[idx]
    return {'index':idx,'sectors':sectors,'multiplier':mult},int(stake*mult)

def hilo(stake:int,guess:str):
    if guess not in ('higher','lower'): raise ValueError('invalid_guess')
    first=rng.randint(2,14); second=rng.randint(2,14)
    win=(second>first and guess=='higher') or (second<first and guess=='lower')
    # Fixed 1.8x payout; ties lose. Each direction has at most 6/13 chance.
    mult=1.8 if win else 0
    return {'first':first,'second':second,'guess':guess,'multiplier':mult},int(stake*mult)

def videopoker(stake:int):
    # Single five-card draw. No duplicates. Fixed pay table.
    deck=[(r,s) for s in range(4) for r in range(2,15)]
    cards=rng.sample(deck,5)
    counts=Counter(r for r,s in cards)
    freq=sorted(counts.values(),reverse=True)
    suits={s for r,s in cards}; ranks={r for r,s in cards}
    flush=len(suits)==1
    straight=len(ranks)==5 and (max(ranks)-min(ranks)==4 or ranks=={14,2,3,4,5})
    if flush and straight: name,mult='straight_flush',50
    elif freq[0]==4: name,mult='four_kind',20
    elif freq==[3,2]: name,mult='full_house',8
    elif flush: name,mult='flush',6
    elif straight: name,mult='straight',5
    elif freq[0]==3: name,mult='three_kind',3
    elif freq==[2,2,1]: name,mult='two_pair',2
    elif freq[0]==2 and any(r>=11 and c==2 for r,c in counts.items()): name,mult='jacks_or_better',1
    else: name,mult='nothing',0
    return {'cards':[{'rank':r,'suit':'♠♥♦♣'[s]} for r,s in cards],'hand':name,'multiplier':mult},stake*mult

def tower(stake:int,level:int):
    # Each level is an independently resolved 1-of-3 safe tile.
    if type(level)!=int or level not in (1,2,3): raise ValueError('invalid_level')
    path=[rng.randrange(3) for _ in range(level)]
    chosen=[rng.randrange(3) for _ in range(level)]
    survived=all(a==b for a,b in zip(path,chosen))
    # Payout 2.7^level, success chance 3^-level -> 90%^level RTP.
    mult=round(2.7**level,3) if survived else 0
    return {'chosen':chosen,'safe_tiles':path,'level':level,'multiplier':mult,'survived':survived},int(stake*mult)
