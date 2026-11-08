/* Tajik Win Mini App — UI; game outcomes always originate at the server. */
const tg=window.Telegram?.WebApp;
if(tg){tg.ready();tg.expand();tg.setHeaderColor('#10100f');tg.setBackgroundColor('#10100f')}
const initData=tg?.initData||'';
let me=null, rates=null, game='slots', stake=10000, busy=false, showingHidden=false, soundOn=true, ac=null, active=null;
let countdownAbort=false;const ROUND_WAIT_MS=15000;const ANIMATION_MS={slots:6500,roulette:7000,dice:4900,blackjack:2500,crash:1800,mines:1600,plinko:6100,keno:5200,wheel:6700,hilo:4700,poker:5800,tower:5300};
const $=id=>document.getElementById(id), fmt=n=>Number(n||0).toLocaleString('ru-RU');
const games=[
{id:'slots',name:'Слоты',icon:'♛',sub:'3 барабана',desc:'Три одинаковых символа дают выигрыш по таблице выплат. Два одинаковых символа возвращают ставку. RTP приблизительно 92,55%.'},
{id:'roulette',name:'Рулетка',icon:'♛',sub:'Европейская',desc:'Числа 0–36. Красное/чёрное ×2, зелёное ×36, число ×36, чёт/нечет ×2. Ноль проигрывает на чётности.'},
{id:'dice',name:'Кости',icon:'♛',sub:'Угадай число',desc:'Угадай число 1–6. За угаданное число выплата ×5.'},
{id:'blackjack',name:'Блэкджек',icon:'♛',sub:'Карты 21',desc:'Набери 21 или ближе к 21, чем дилер. Дилер добирает до 17. Выигрыш ×2, ничья ×1.'},
{id:'crash',name:'Crash',icon:'♛',sub:'Поймай множитель',desc:'Множитель растёт со временем. Забери выигрыш до случайной остановки. Результат рассчитывает сервер.'},
{id:'mines',name:'Mines',icon:'♛',sub:'Поле 5×5',desc:'Открывай безопасные клетки или забери выигрыш. Мина завершает раунд.'},
{id:'plinko',name:'Plinko',icon:'♛',sub:'Шар и штифты',desc:'10 случайных направлений шарика, выплата зависит от ячейки и уровня риска.'},
{id:'keno',name:'Keno',icon:'♛',sub:'Выбери 5 чисел',desc:'Выбери пять чисел 1–40. В розыгрыше участвуют 10 чисел. Выплаты зависят от совпадений.'},
{id:'wheel',name:'Wheel',icon:'♛',sub:'20 секторов',desc:'Все 20 секторов равновероятны: возможны ×0, ×0.5, ×1, ×2 и ×5.'},
{id:'hilo',name:'Hi-Lo',icon:'♛',sub:'Выше или ниже',desc:'Угадай, будет ли следующая карта выше или ниже. Совпадения проигрывают. Выигрыш ×1.8.'},
{id:'poker',name:'Покер',icon:'♛',sub:'Пятикарточный',desc:'Пять карт из одной колоды, результат по таблице покерных комбинаций. Обмена карт нет.'},
{id:'tower',name:'Tower',icon:'♛',sub:'Башня',desc:'Пройди от одного до трёх уровней, на каждом одна из трёх клеток безопасна. Выигрыш ×2.7^уровень.'}
];
const tr={
 ru:{balance:'Баланс',request:'Начислить',chooseGame:'Выбери игру',heroSub:'Выбери игру, настрой ставку и начинай.',allGames:'Все игры',bet:'Сумма ставки',history:'История ставок',rewards:'Промокоды',profile:'Профиль',home:'Главная',nickname:'Никнейм',avatar:'Аватар',language:'Язык',currency:'Валюта отображения',sounds:'Звуки включены',save:'Сохранить',support:'Связь с администратором',rules:'Правила и выплаты'},
 uz:{balance:'Balans',request:'Hisob so‘rash',chooseGame:'O‘yinni tanlang',heroSub:'O‘yinni tanlang, stavkani kiriting.',allGames:'Barcha o‘yinlar',bet:'Stavka miqdori',history:'O‘yin tarixi',rewards:'Promokodlar',profile:'Profil',home:'Asosiy',nickname:'Taxallus',avatar:'Avatar',language:'Til',currency:'Ko‘rsatiladigan valyuta',sounds:'Ovoz yoqilgan',save:'Saqlash',support:'Administratorga yozish',rules:'Qoidalar va to‘lovlar'},
 en:{balance:'Balance',request:'Request credits',chooseGame:'Choose a game',heroSub:'Choose a game, set a stake and play.',allGames:'All games',bet:'Bet amount',history:'Bet history',rewards:'Promo codes',profile:'Profile',home:'Home',nickname:'Nickname',avatar:'Avatar',language:'Language',currency:'Display currency',sounds:'Sound enabled',save:'Save',support:'Contact admin',rules:'Rules & payouts'}
};
let lang='ru',currency='UZS';
function translate(){document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=(tr[lang]||tr.ru)[el.dataset.i18n]||el.textContent)}
function notify(message){const e=$('notice');e.textContent=message;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),3800)}
function money(n){if(currency==='UZS')return fmt(n)+' сум';if(!rates?.rates?.[currency])return fmt(n)+' сум';return new Intl.NumberFormat(lang==='en'?'en-US':'ru-RU',{style:'currency',currency,maximumFractionDigits:2}).format(n/rates.rates[currency])}
function repaintBalance(){if(!me)return;$('balance').innerHTML=money(me.balance);$('currency-btn').textContent=currency+' ▾';$('rate-indicator').textContent=currency==='UZS'?'UZS · основной баланс':rates?.rates?.[currency]?'ЦБ Узбекистана · '+rates.as_of:'Курс недоступен · показан UZS'}
function sfx(type='tap'){
 if(!soundOn)return;
 if(['credit','win','lose','slots','roulette','dice','blackjack','crash','mines','plinko','keno','wheel','hilo','poker','tower'].includes(type)){
  try{const audio=new Audio('/static/sounds/'+type+'.wav');audio.volume=type==='credit'?0.92:0.50;audio.play().catch(()=>{});return}catch{}
 }
 try{
  ac??=new (window.AudioContext||window.webkitAudioContext)();
  if(ac.state==='suspended')ac.resume().catch(()=>{});
  const patterns={
   tap:[740],start:[420,610],tick:[660],card:[880,1100],
   win:[523,659,784,1047],lose:[330,245],credit:[880,1174,1568],
   slots:[520,760,920],roulette:[330,440,550],dice:[370,295],blackjack:[590,900],
   crash:[370,480,650],mines:[740,520],plinko:[1300,940,700],keno:[780,980,1175],
   wheel:[400,700,470],hilo:[440,660],poker:[650,820],tower:[390,510,730]
  };
  let tones=patterns[type]||patterns.tap;
  const now=ac.currentTime, spacing=type==='credit'?.105:type==='win'?.085:.065;
  tones.forEach((f,i)=>{
   const oscillator=ac.createOscillator(),volume=ac.createGain();
   oscillator.type=type==='lose'?'triangle':type==='tick'?'square':type==='tap'?'sine':'sine';
   oscillator.frequency.setValueAtTime(f,now+i*spacing);
   volume.gain.setValueAtTime(.0001,now+i*spacing);
   volume.gain.exponentialRampToValueAtTime(type==='tap'||type==='tick'?.017:.055,now+i*spacing+.016);
   volume.gain.exponentialRampToValueAtTime(.0001,now+i*spacing+(type==='credit'?.30:.16));
   oscillator.connect(volume);volume.connect(ac.destination);
   oscillator.start(now+i*spacing);oscillator.stop(now+i*spacing+(type==='credit'?.31:.17));
  });
 }catch(e){console.debug('Audio unavailable',e)}
}
async function api(path,data=null){if(!initData)throw Error('Открой приложение через кнопку Telegram-бота.');const options=data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({initData,...data})}:{};const url=path+(data?'':(path.includes('?')?'&':'?')+'initData='+encodeURIComponent(initData));const r=await fetch(url,options);let value;try{value=await r.json()}catch{throw Error('Ошибка ответа сервера')}if(!r.ok)throw Error(({invalid_init_data:'Сессия истекла. Открой Mini App заново.',insufficient_balance:'Недостаточно баланса.',invalid_stake:'Ставка должна быть 3 000–1 000 000 сум.',active_session_exists:'Заверши текущую игру.',finish_active_game_first:'Сначала заверши текущую игру.',pending_request_exists:'Сначала дождись решения по текущей заявке.',promo_already_used:'Этот промокод уже использован.',promo_not_found:'Промокод не найден.',promo_exhausted:'Активации закончились.',no_session:'Активная игра не найдена.'})[value.error]||value.error||'Ошибка API');return value}
async function refresh(){try{me=await api('/api/me');active=me.active_session;lang=me.preferences?.lang||'ru';currency=me.preferences?.currency||'UZS';soundOn=me.preferences?.sound!==0;repaintBalance();translate();fillProfile();if(active)restoreSession()}catch(e){notify(e.message)}}
function show(page){if(busy&&page!=='game')return;if(page==='catalog')renderCatalog();document.querySelectorAll('.view').forEach(el=>el.classList.remove('active'));$('view-'+page).classList.add('active');document.querySelectorAll('#bottom-nav button').forEach(b=>b.classList.toggle('selected',b.dataset.page===page));window.scrollTo({top:0,behavior:'smooth'});sfx();if(page==='history')loadHistory();if(page==='rewards')loadLeaderboard();if(page==='profile')loadSupport()}
function setupHome(){
 $('game-grid').innerHTML=games.map((g,i)=>`<button class="game-tile" data-game="${g.id}" style="--delay:${i*55}ms"><span class="tile-art"><img loading="lazy" src="/static/assets/${g.id}.svg" alt="Иллюстрация: ${g.name}"></span><span class="tile-copy"><strong>${g.name}</strong><small>${g.sub}</small></span><span class="tile-shine"></span></button>`).join('');
 $('game-grid').addEventListener('click',e=>{const btn=e.target.closest('[data-game]');if(btn)openGame(btn.dataset.game)});
 const search=$('game-search'),categories=$('game-categories');let filter='all';
 function filterGames(){const q=search.value.trim().toLowerCase();document.querySelectorAll('#game-grid [data-game]').forEach(el=>{const name=el.querySelector('strong')?.textContent.toLowerCase()||'';const id=el.dataset.game;const match=filter==='all'||(filter==='popular'&&['slots','roulette','crash','mines'].includes(id))||(filter==='cards'&&['blackjack','poker','hilo'].includes(id))||(filter==='fast'&&['dice','plinko','wheel','keno'].includes(id));el.classList.toggle('hidden',!match||!name.includes(q))})}
 search.addEventListener('input',filterGames);categories.onclick=e=>{const b=e.target.closest('[data-filter]');if(!b)return;filter=b.dataset.filter;categories.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));filterGames()};
 document.querySelectorAll('#bottom-nav button').forEach(b=>b.addEventListener('click',()=>show(b.dataset.page)));
 $('back-games').onclick=()=>show('home');$('settings-open').onclick=()=>show('profile');
}
function renderCatalog(){$('catalog-grid').innerHTML=$('game-grid').innerHTML;$('catalog-grid').querySelectorAll('[data-game]').forEach(x=>x.classList.remove('hidden'));$('catalog-grid').onclick=e=>{const b=e.target.closest('[data-game]');if(b)openGame(b.dataset.game)}}
function betSet(v){stake=Math.max(3000,Math.min(1000000,Math.round(Number(v)||3000)));$('stake-input').value=stake;document.querySelectorAll('.quick-bets button').forEach(b=>b.classList.toggle('on',Number(b.dataset.n)===stake))}
function setupBet(){$('quick-bets').innerHTML=[10000,100000,200000,300000,400000,500000].map(n=>`<button data-n="${n}">${fmt(n)}</button>`).join('');$('quick-bets').onclick=e=>{const b=e.target.closest('[data-n]');if(b){betSet(b.dataset.n);sfx()}};$('stake-input').onchange=e=>betSet(e.target.value);$('stake-minus').onclick=()=>betSet(stake-10000);$('stake-plus').onclick=()=>betSet(stake+10000);betSet(10000)}
const icon=(g)=>`<img class='history-art' src='/static/assets/${games.some(x=>x.id===g)?g:'slots'}.svg' alt=''>`;
function openGame(id){
 game=id;const g=games.find(x=>x.id===id);if(!g)return;
 show('game');$('round-status').classList.add('hidden');$('game-icon').innerHTML=`<img src="/static/assets/${id}.svg" alt="">`;
 $('game-title').textContent=g.name;$('game-kicker').textContent=g.sub.toUpperCase();$('game-rules').textContent=g.desc;
 $('result-box').classList.add('hidden');$('play-btn').classList.remove('hidden');$('play-btn').disabled=false;
 $('play-btn').textContent='НАЧАТЬ ИГРУ →';$('game-actions').innerHTML='';
 $('arena').className='arena arena--'+id;
 $('arena').innerHTML=`<div class="arena-splash"><img src="/static/assets/${id}.svg" alt="${g.name}"><div class="arena-overlay">${g.name}</div></div>`;
 $('arena').onclick=null;
 const controls=$('game-controls');let html='';
 if(id==='roulette')html='<select id="roulette-type"><option value="color">Цвет</option><option value="number">Число</option><option value="parity">Чётность</option></select><select id="roulette-value"><option value="red">Красное</option><option value="black">Чёрное</option><option value="green">Зеро</option></select>';
 if(id==='dice')html='<label>Число:</label><select id="dice-guess">'+Array.from({length:6},(_,i)=>`<option>${i+1}</option>`).join('')+'</select>';
 if(id==='mines')html='<label>Мин:</label><select id="mines-count"><option>2</option><option>3</option><option>5</option><option>7</option></select>';
 if(id==='plinko')html='<label>Риск:</label><select id="risk"><option value="low">Низкий</option><option value="medium" selected>Средний</option><option value="high">Высокий</option></select>';
 if(id==='hilo')html='<select id="hilo-choice"><option value="higher">Выше</option><option value="lower">Ниже</option></select>';
 if(id==='tower')html='<label>Уровней:</label><select id="tower-level"><option>1</option><option>2</option><option>3</option></select>';
 controls.innerHTML=html;if(id==='roulette')$('roulette-type').onchange=updateRoulette;
 if(id==='keno')renderKeno();if(id==='mines')renderMineGrid([],false);$('play-btn').onclick=play;
}
function updateRoulette(){const t=$('roulette-type').value;$('roulette-value').outerHTML=t==='number'?'<select id="roulette-value">'+Array.from({length:37},(_,i)=>`<option>${i}</option>`).join('')+'</select>':t==='parity'?'<select id="roulette-value"><option value="even">Чётное</option><option value="odd">Нечётное</option></select>':'<select id="roulette-value"><option value="red">Красное</option><option value="black">Чёрное</option><option value="green">Зеро</option></select>'}
let kenoPicks=new Set(), minePicks=new Set();
function renderKeno(draw=[],hits=[]){$('arena').innerHTML='<div class="keno-board">'+Array.from({length:40},(_,i)=>`<button class="keno-num ${kenoPicks.has(i+1)?'chosen':''} ${hits.includes(i+1)?'hit':''} ${draw.includes(i+1)?'drawn':''}" data-pick="${i+1}">${i+1}</button>`).join('')+'</div>';$('arena').onclick=e=>{const b=e.target.closest('[data-pick]');if(!b||busy)return;const n=Number(b.dataset.pick);if(kenoPicks.has(n))kenoPicks.delete(n);else if(kenoPicks.size<5)kenoPicks.add(n);else return notify('Выбери ровно пять чисел');renderKeno();sfx()}}
function renderMineGrid(revealed=[],blocked=false){$('arena').innerHTML='<div class="mine-grid">'+Array.from({length:25},(_,i)=>`<button class="mine-cell ${revealed.includes(i)?'revealed':''}" data-tile="${i}" ${revealed.includes(i)||blocked?'disabled':''}>${revealed.includes(i)?'✦':'?'}</button>`).join('')+'</div>';$('arena').onclick=e=>{let b=e.target.closest('[data-tile]');if(b&&!busy&&active?.game==='mines')mineReveal(Number(b.dataset.tile))}}
function renderOutcome(result){
 const arena=$('arena');const safe=t=>escapeHTML(String(t));const reelSymbol=t=>({'🍒':'●','🍋':'✦','🍇':'◆','🔔':'♛','💎':'⬖','7️⃣':'7'}[t]||'◆');
 if(game==='slots'){arena.innerHTML=`<div class="reels final-reels">${result.reels.map((x,i)=>`<div class="reel" style="--i:${i}">${reelSymbol(x)}</div>`).join('')}</div>`}
 else if(game==='roulette'){arena.innerHTML=`<div class="wheel-stage complete"><div class="wheel-inner"><div class="roulette-result ${result.color}">${result.number}</div></div><div class="wheel-pointer"></div></div>`}
 else if(game==='dice'){arena.innerHTML=`<div class="dice-stage stopped"><div class="dice-cube">${['⚀','⚁','⚂','⚃','⚄','⚅'][result.result-1]}</div></div>`}
 else if(game==='plinko'){arena.innerHTML=`<div class="plinko-stage complete">${Array.from({length:8},(_,r)=>`<div class="peg-row">${'● '.repeat(r+3)}</div>`).join('')}<div class="plinko-ball stopped"></div><h2>Ячейка ${Number(result.slot)+1} · ×${Number(result.multiplier)}</h2></div>`}
 else if(game==='keno'){renderKeno(result.draw,result.draw.filter(x=>kenoPicks.has(x)))}
 else if(game==='wheel'){arena.innerHTML=`<div class="wheel-stage complete"><div class="wheel-inner"><strong>×${result.multiplier}</strong></div><div class="wheel-pointer"></div></div>`}
 else if(game==='hilo'){arena.innerHTML=`<div class="cards-stage settled"><div class="playing-card">${safe(result.first)}</div><div class="playing-card">${safe(result.second)}</div></div>`}
 else if(game==='poker'){arena.innerHTML=`<div class="cards settled">${result.cards.map(c=>`<div class="playing-card ${'♥♦'.includes(c.suit)?'red':''}">${safe(c.rank===14?'A':c.rank===13?'K':c.rank===12?'Q':c.rank===11?'J':c.rank)}${safe(c.suit)}</div>`).join('')}</div><p>${safe(result.hand.replaceAll('_',' '))}</p>`}
 else if(game==='tower'){arena.innerHTML=`<div class="tower-stage done">${Array.from({length:Math.max(1,Number(result.level))},(_,i)=>`<div class="tower-floor ${result.survived?'passed':'failed'}" style="--i:${i}"></div>`).join('')}<h2>${result.survived?'Уровень пройден':'Башня завершена'}</h2></div>`}
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function animate(response,duration=ANIMATION_MS[game]||5500){
 const arena=$('arena');const selected=game;
 arena.classList.add('spinning','playing--'+selected);
 const stage=selected==='slots'?'<div class="reel-stage">'+[0,1,2].map((_,i)=>`<div class="reel-window"><div class="reel-strip" style="animation-delay:${i*110}ms">7<br>◆<br>♛<br>7<br>♦<br>7</div></div>`).join('')+'</div>':
 selected==='roulette'?'<div class="wheel-stage"><div class="wheel-inner">0 · 7 · 21 · 18</div><div class="wheel-pointer"></div></div>':
 selected==='dice'?'<div class="dice-stage"><div class="dice-cube">⚄</div><div class="dice-cube second">⚅</div></div>':
 selected==='plinko'?'<div class="plinko-stage">'+Array.from({length:8},(_,r)=>`<div class="peg-row">${'● '.repeat(r+3)}</div>`).join('')+'<div class="plinko-ball"></div></div>':
 selected==='wheel'?'<div class="wheel-stage wheel-game"><div class="wheel-inner">×2 · ×5 · ×0</div><div class="wheel-pointer"></div></div>':
 selected==='poker'||selected==='hilo'?'<div class="cards-stage">'+[0,1,2,3,4].slice(0,selected==='hilo'?2:5).map((_,i)=>`<div class="card-back" style="--i:${i}">TW</div>`).join('')+'</div>':
 selected==='tower'?'<div class="tower-stage">'+Array.from({length:5},(_,i)=>`<div class="tower-floor" style="--i:${i}"></div>`).join('')+'</div>':
 selected==='keno'?'<div class="theatre-keno"><div class="keno-orbit">'+[1,2,3,4,5,6,7,8].map((x,i)=>`<span style="--i:${i}">${x}</span>`).join('')+'</div><strong>РОЗЫГРЫШ</strong></div>':
 `<div class="arena-splash ${selected}-theatre"><img src="/static/assets/${selected}.svg" alt=""><div class="arena-overlay">Игра идёт…</div></div>`;
 arena.innerHTML=stage;
 sfx(selected);const start=Date.now();
 const clock=setInterval(()=>{if(Date.now()-start<duration-180)sfx('tick');const progress=Math.min(100,100*(Date.now()-start)/duration);$('round-status').innerHTML='<div class="phase-line"><span>Анимация '+Math.ceil((duration-Date.now()+start)/1000)+' с</span><span>'+Math.round(progress)+'%</span></div><div class="phase-track"><div style="width:'+progress+'%"></div></div>';},650);
 try{await sleep(window.matchMedia('(prefers-reduced-motion: reduce)').matches?150:duration)}finally{clearInterval(clock);arena.classList.remove('spinning','playing--'+selected)}
 if(response){renderOutcome(response);$('round-status').innerHTML='<div class="phase-complete">Раунд завершён</div>'}
}
function resultShow(r,stakeUsed){$('round-status').innerHTML='<div class="phase-complete">Результат раунда</div>'; let payout=r.payout||0,net=payout-stakeUsed;const el=$('result-box');el.className='result-box '+(net>=0?'win':'loss');el.innerHTML=`<span>${net>0?'Выигрыш':net===0?'Возврат ставки':'Без выигрыша'}</span><strong>${net>0?'+':net<0?'−':''}${money(Math.abs(net))}</strong><small>Выплата: ${money(payout)}</small>`;if(me){me.balance=r.balance;repaintBalance()}sfx(net>0?'win':'lose');if(net>0){$('win-text').textContent='+'+money(net);$('win-overlay').classList.remove('hidden');setTimeout(()=>$('win-overlay').classList.add('hidden'),2450)}}
async function waitForRound(){
 countdownAbort=false;const status=$('round-status');status.classList.remove('hidden');
 const total=Math.round(ROUND_WAIT_MS/1000);const start=performance.now();
 while(performance.now()-start<ROUND_WAIT_MS){
  if(countdownAbort){status.classList.add('hidden');return false}
  const left=Math.ceil((ROUND_WAIT_MS-(performance.now()-start))/1000);
  status.innerHTML='<div class="round-countdown"><span>Следующий раунд через</span><strong>00:'+String(Math.max(0,left)).padStart(2,'0')+'</strong><button id="cancel-round" type="button">Отмена</button></div><div class="phase-track"><div style="width:'+(100*(total-left)/total)+'%"></div></div>';
  $('cancel-round').onclick=()=>{countdownAbort=true};await sleep(140);
 }
 status.innerHTML='<div class="phase-line">Раунд начался</div>';return true;
}
async function play(){if(busy)return;stake=Number($('stake-input').value);if(!Number.isInteger(stake)||stake<3000||stake>1000000)return notify('Ставка от 3 000 до 1 000 000 сум');if(me&&stake>me.balance)return notify('Недостаточно средств');if(active)return notify('Заверши текущую игру');if(game==='keno'&&kenoPicks.size!==5)return notify('Выбери ровно 5 чисел');busy=true;$('play-btn').disabled=true;$('result-box').classList.add('hidden');sfx(game);let path='/api/'+game,body={stake};if(game==='roulette'){body.bet_type=$('roulette-type').value;body.bet_value=$('roulette-value').value}if(game==='dice')body.guess=Number($('dice-guess').value);if(game==='mines'){path+='/start';body.mines_count=Number($('mines-count').value)}if(game==='blackjack'||game==='crash')path+='/start';if(game==='plinko')body.choice=$('risk').value;if(game==='keno')body.numbers=[...kenoPicks];if(game==='hilo')body.choice=$('hilo-choice').value;if(game==='tower')body.level=Number($('tower-level').value);try{if(!(await waitForRound()))return;const response=await api(path,body);if(['blackjack','crash','mines'].includes(game)){active={game,stake,state:{}};if(me){me.balance=response.balance;repaintBalance()}if(game==='blackjack'){await animate(null,ANIMATION_MS.blackjack);renderBj(response)}if(game==='crash'){startCrashUI()}if(game==='mines'){await animate(null,ANIMATION_MS.mines);minePicks=new Set();renderMineGrid();$('game-actions').innerHTML='<button class="gold-button wide" id="mines-cashout">Забрать выигрыш</button>';$('mines-cashout').onclick=mineCashout}$('play-btn').classList.add('hidden')}else{await animate(response);resultShow(response,stake)}}catch(e){notify(e.message)}finally{busy=false;$('play-btn').disabled=false}}
function renderBj(r){
 const card=c=>`<div class="playing-card card-flip">${escapeHTML(String(c))}</div>`;
 const dealer=r.dealer||[r.dealer_visible,'🂠'];
 $('arena').innerHTML=`<div class="blackjack-table"><p>Дилер</p><div class="cards">${dealer.map(card).join('')}</div><p>Твои карты · ${r.player_value??''}</p><div class="cards">${r.player.map(card).join('')}</div></div>`;
 $('game-actions').innerHTML='<div class="form-row"><button id="bj-hit" class="gold-button">Ещё карту</button><button id="bj-stand" class="gold-button">Хватит</button></div>';
 $('bj-hit').onclick=()=>bjAction('hit');$('bj-stand').onclick=()=>bjAction('stand');sfx('card');
}
async function bjAction(a){if(busy)return;busy=true;try{const r=await api('/api/blackjack/'+a,{});if(r.finished){active=null;$('game-actions').innerHTML='';$('play-btn').classList.remove('hidden');$('arena').innerHTML=`<div><p>Дилер</p><div class="cards">${r.dealer.map(c=>`<div class="playing-card">${c}</div>`).join('')}</div><p>Ты</p><div class="cards">${r.player.map(c=>`<div class="playing-card">${c}</div>`).join('')}</div></div>`;resultShow(r,stake)}else{renderBj(r)}sfx()}catch(e){notify(e.message)}finally{busy=false}}
let crashTimer=null;
function startCrashUI(){
 clearInterval(crashTimer);
 $('arena').className='arena arena--crash crash-live';
 $('arena').innerHTML='<div class="crash-live-scene"><div class="crash-grid"></div><div class="crash-trail"></div><div class="rocket-vector">➤</div><h1 id="crash-multi">×1.00</h1></div>';
 $('game-actions').innerHTML='<button class="gold-button wide" id="crash-cashout">Забрать выигрыш</button>';
 $('crash-cashout').onclick=crashCashout;
 crashTimer=setInterval(async()=>{if(!active||active.game!=='crash'){clearInterval(crashTimer);return}try{
 const r=await api('/api/crash/status');if(r.crashed){clearInterval(crashTimer);active=null;$('game-actions').innerHTML='';$('play-btn').classList.remove('hidden');resultShow({payout:0,balance:r.balance},stake);$('crash-multi').textContent='СТОП ×'+r.multiplier;$('arena').classList.add('crashed')}
 else{$('crash-multi').textContent='×'+r.multiplier;sfx('tick')}
 }catch(e){clearInterval(crashTimer);notify(e.message)}},400);
}
async function crashCashout(){if(busy)return;busy=true;clearInterval(crashTimer);try{const r=await api('/api/crash/cashout',{});active=null;$('game-actions').innerHTML='';$('play-btn').classList.remove('hidden');resultShow(r,stake);$('crash-multi').textContent=r.busted?'СТОП':('×'+r.multiplier)}catch(e){notify(e.message)}finally{busy=false}}
async function mineReveal(n){busy=true;try{const r=await api('/api/mines/reveal',{tile_index:n});if(r.busted||r.cleared_all){active=null;$('play-btn').classList.remove('hidden');$('game-actions').innerHTML='';renderMineGrid([...minePicks,n],true);sfx('lose');resultShow(r,stake)}else{minePicks.add(n);renderMineGrid([...minePicks]);sfx()}}catch(e){notify(e.message)}finally{busy=false}}
async function mineCashout(){if(busy)return;busy=true;try{const r=await api('/api/mines/cashout',{});active=null;$('play-btn').classList.remove('hidden');$('game-actions').innerHTML='';renderMineGrid([...minePicks],true);resultShow(r,stake)}catch(e){notify(e.message)}finally{busy=false}}
function restoreSession(){if(!active)return;openGame(active.game);stake=active.stake;betSet(stake);$('play-btn').classList.add('hidden');if(active.game==='blackjack'){renderBj({...active.state,dealer_visible:active.state.dealer?.[0],player_value:''})}if(active.game==='mines'){minePicks=new Set(active.state.revealed||[]);renderMineGrid([...minePicks]);$('game-actions').innerHTML='<button class="gold-button wide" id="mines-cashout">Забрать выигрыш</button>';$('mines-cashout').onclick=mineCashout}if(active.game==='crash')startCrashUI()}
async function loadHistory(){try{const data=await api('/api/history');const visible=data.filter(x=>showingHidden?x.hidden:!x.hidden);$('history-list').innerHTML=visible.length?visible.map(r=>{const net=r.payout-r.stake;return `<div class="history-item"><div><strong>${icon(r.game)} ${games.find(g=>g.id===r.game)?.name||r.game}</strong><small>${new Date(r.ts*1000).toLocaleString()} · ставка ${fmt(r.stake)} UZS</small><div class="history-actions"><button data-action="${r.pinned?'unpin':'pin'}" data-id="${r.id}">${r.pinned?'Открепить':'Закрепить'}</button><button data-action="${r.hidden?'show':'hide'}" data-id="${r.id}">${r.hidden?'Показать':'Скрыть'}</button></div></div><strong class="${net>=0?'plus':'minus'}">${net>=0?'+':'−'}${fmt(Math.abs(net))}</strong></div>`}).join(''):'<div class="card">Здесь пока нет записей.</div>'}catch(e){notify(e.message)}}
async function loadLeaderboard(){try{const club=await api('/api/club');$('club-status').innerHTML=`<p>Твой уровень: <strong>${club.level}</strong> · Сумма ставок: ${fmt(club.wagered)} сум</p><h3>Недельный рейтинг</h3>`;$('leaderboard').innerHTML=club.weekly.map((r,i)=>`<p>${i+1}. ${escapeHTML(r.username||'Игрок')} — ${fmt(r.points)} очков</p>`).join('')||'<p>Пока нет участников</p>'}catch(e){notify(e.message)}}
function escapeHTML(t){return String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function fillProfile(){if(!me)return;const p=me.preferences||{};$('profile-name').textContent=p.nickname||me.username||'Игрок';$('profile-id').textContent='ID '+me.user_id;$('profile-avatar').textContent=p.avatar||'♠';$('settings-open').textContent=p.avatar||'♠';$('profile-nick').value=p.nickname||'';$('profile-lang').value=p.lang||'ru';$('profile-currency').value=p.currency||'UZS';$('profile-sound').checked=p.sound!==0;document.querySelectorAll('[data-avatar]').forEach(b=>b.classList.toggle('active',b.dataset.avatar===(p.avatar||'♠')))}
async function loadSupport(){try{const msgs=await api('/api/support');$('support-log').innerHTML=msgs.map(m=>`<div class="bubble ${m.sender==='admin'?'admin':''}"><small>${m.sender==='admin'?'Администратор':'Вы'}</small><div>${escapeHTML(m.text||'[Вложение]')}</div></div>`).join('')||'<p class="tiny">Пока нет сообщений</p>'}catch(e){notify(e.message)}}
async function saveProfile(){try{const p=await api('/api/preferences',{nickname:$('profile-nick').value,avatar:document.querySelector('[data-avatar].active')?.dataset.avatar||'♠',lang:$('profile-lang').value,currency:$('profile-currency').value,sound:$('profile-sound').checked?1:0});me.preferences=p;lang=p.lang;currency=p.currency;soundOn=!!p.sound;fillProfile();repaintBalance();translate();notify('Настройки сохранены');sfx('credit')}catch(e){notify(e.message)}}
function modal(id,on){$(id).classList.toggle('hidden',!on);sfx()}
function setupMisc(){$('history-hidden').onclick=()=>{showingHidden=!showingHidden;$('history-hidden').textContent=showingHidden?'Видимые':'Скрытые';loadHistory()};$('history-list').onclick=async e=>{const b=e.target.closest('[data-action]');if(!b)return;try{await api('/api/history/action',{bet_id:Number(b.dataset.id),action:b.dataset.action});loadHistory()}catch(err){notify(err.message)}};$('promo-activate').onclick=async()=>{try{const r=await api('/api/promo/redeem',{code:$('promo-input').value.trim()});me.balance=r.balance;repaintBalance();sfx('credit');notify('Начислено '+fmt(r.amount)+' сум')}catch(e){notify(e.message)}};$('avatar-picks').innerHTML=['♠','♦','♣','♥','★','⚡','👑','🎲'].map(x=>`<button data-avatar="${x}">${x}</button>`).join('');$('avatar-picks').onclick=e=>{const b=e.target.closest('[data-avatar]');if(!b)return;document.querySelectorAll('[data-avatar]').forEach(x=>x.classList.toggle('active',x===b));sfx()};$('save-profile').onclick=saveProfile;$('support-send').onclick=async()=>{const text=$('support-input').value.trim();if(!text)return;try{await api('/api/support',{text});$('support-input').value='';loadSupport();notify('Сообщение отправлено')}catch(e){notify(e.message)}};$('credit-open').onclick=()=>modal('credit-modal',true);$('currency-btn').onclick=()=>{renderCurrencyChoices();modal('currency-modal',true)};document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>modal(b.dataset.close,false));$('credit-send').onclick=async()=>{const amount=Number($('credit-amount').value);try{const r=await api('/api/credits/request',{amount});modal('credit-modal',false);notify('Заявка #'+r.request_id+' отправлена администратору')}catch(e){notify(e.message)}}}
function renderCurrencyChoices(){$('currency-choices').innerHTML=['UZS','USD','EUR','RUB'].map(c=>`<button class="currency-choice" data-cur="${c}">${c}${currency===c?' ✓':''}</button>`).join('');$('currency-source').textContent=rates?'Курс ЦБ Узбекистана на '+rates.as_of:'Сетевой курс недоступен; другие валюты временно отключены.';$('currency-choices').onclick=async e=>{const b=e.target.closest('[data-cur]');if(!b)return;const c=b.dataset.cur;if(c!=='UZS'&&!rates?.rates?.[c])return notify('Курс недоступен');try{const p=await api('/api/preferences',{currency:c});currency=p.currency;me.preferences=p;repaintBalance();$('profile-currency').value=currency;modal('currency-modal',false)}catch(err){notify(err.message)}}}
let lastCreditId=null;async function checkCredits(){try{if(!initData)return;const events=await api('/api/credit-events');const newest=events[0]?.id||0;if(lastCreditId!==null&&newest>lastCreditId){const r=await api('/api/me');me=r;repaintBalance();sfx('credit');notify('Игровые кредиты начислены: +'+fmt(events[0].delta)+' сум')}lastCreditId=newest}catch{}}
(async function init(){setupHome();setupBet();setupMisc();if(!initData){notify('Открой Mini App из Telegram для игры.');$('game-grid').classList.add('waiting');return}await refresh();try{const r=await fetch('/api/rates');if(r.ok)rates=await r.json()}catch{}repaintBalance();await checkCredits();setInterval(checkCredits,12000)})();
