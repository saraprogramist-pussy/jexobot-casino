'use strict';
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const initData = tg?.initData || '';
const $ = id => document.getElementById(id);
const fmt = n => Number(n ?? 0).toLocaleString('ru-RU');
let balance=0, active=null, current='slots', busy=false, crashTimer=null, selected='red', guess=3, minesCount=3;
let minesRevealed=new Set(), minesBombs=new Set(), lastResult=null, crashActive=false, bjActive=false, minesActive=false;
const titles={slots:['Слоты','Три одинаковых символа — выигрыш'],roulette:['Рулетка','Число, цвет или чётность'],dice:['Кости','Угадай число от 1 до 6'],blackjack:['Блэкджек','Набери ближе к 21, чем дилер'],crash:['Crash','Забери монеты до обвала'],mines:['Mines','Открывай безопасные клетки']};
const errors={invalid_init_data:'Открой приложение кнопкой из Telegram-бота.',insufficient_balance:'Недостаточно монет.',invalid_stake:'Некорректная ставка.',active_session_exists:'Заверши текущую игру.',finish_active_game_first:'Сначала заверши начатую игру.',no_session:'Раунд уже завершён.',promo_not_found:'Промокод не найден.',promo_expired:'Срок промокода истёк.',promo_exhausted:'Все активации использованы.',promo_already_used:'Ты уже активировал этот промокод.',reveal_first:'Сначала открой одну клетку.',invalid_tile:'Некорректная клетка.',already_revealed:'Клетка уже открыта.'};
const escapeHtml = t => String(t).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(t){ const x=$('toast');x.textContent=t;x.classList.add('show');setTimeout(()=>x.classList.remove('show'),3200); }
function feedback(t,kind=''){const el=$('feedback');el.textContent=t;el.className='feedback '+kind;}
function updateBalance(v){if(v!==undefined && v!==null){balance=v;$('balance').textContent=fmt(v);$('statBalance').textContent=fmt(v);}}
function stake(){const n=Number($('stake').value);if(!Number.isSafeInteger(n)||n<1||n>1000000000)throw Error('Укажи ставку от 1 до 1 000 000 000.');return n;}
async function api(path,body=null){if(!initData)throw Error('Открой Mini App внутри Telegram.');const options=body===null?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({initData,...body})}; const url=path+(body===null?('?initData='+encodeURIComponent(initData)):'');const r=await fetch(url,options);let out;try{out=await r.json();}catch{throw Error('Ошибка ответа сервера.');}if(!r.ok)throw Error(errors[out.error]||out.error||'Ошибка запроса');return out;}
async function action(fn){if(busy)return;busy=true;document.querySelectorAll('#controls button,.promo button').forEach(b=>b.disabled=true);try{await fn();}catch(e){feedback(e.message,'error');toast(e.message);}finally{busy=false;document.querySelectorAll('#controls button,.promo button').forEach(b=>b.disabled=false);}}
function nav(name){document.querySelectorAll('.view').forEach(x=>x.classList.toggle('active',x.id===name));document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('selected',x.dataset.tab===name));if(name==='leaders')loadLeaders();if(name==='profile')loadProfile();}
function drawArena(html){$('arena').innerHTML=html;}
function buttons(html){$('controls').innerHTML=html;}
function btn(label,fn,cls='primary'){const b=document.createElement('button');b.className=cls;b.textContent=label;b.addEventListener('click',()=>action(fn));$('controls').appendChild(b);return b;}
function choices(values,chosen,change){const wrap=document.createElement('div');wrap.className='opts';for(const [val,label] of values){const b=document.createElement('button');b.textContent=label;b.className=String(val)===String(chosen)?'chosen':'';b.addEventListener('click',()=>{change(val);wrap.querySelectorAll('button').forEach(x=>x.classList.remove('chosen'));b.classList.add('chosen');});wrap.appendChild(b);}return wrap;}
function openGame(game){current=game;lastResult=null;minesRevealed=new Set();minesBombs=new Set();$('gameTitle').textContent=titles[game][0];$('gameSubtitle').textContent=titles[game][1];nav('play');render();}
function activeGame(){return active?.game||null;}
function render(){const g=current;const isSession=activeGame()===g;$('stake').disabled=!!active;if(!isSession && active){drawArena('<div class="big-symbol">🔒</div><div class="muted">Сначала закончи игру '+escapeHtml(titles[active.game][0])+'</div>');buttons('');btn('Вернуться в незавершённую игру',async()=>openGame(active.game));return;}
if(g==='slots'){
 drawArena(`<div class="reels">${(lastResult?.reels||['🍒','🍋','💎']).map(v=>'<div class="reel">'+v+'</div>').join('')}</div><div class="muted">3 одинаковых символа — от ×3 до ×50</div>`);
 buttons('');btn('🎰 Крутить',async()=>{const r=await api('/api/slots',{stake:stake()});updateBalance(r.balance);lastResult=r;render();feedback(r.payout?'Выигрыш: '+fmt(r.payout):'Без выигрыша',r.payout?'win':'');});
}else if(g==='roulette'){
 const type=String(selected).split(':')[0],value=String(selected).split(':')[1]||selected;
 drawArena(`<div class="rouletteball">${lastResult?.number ?? '🎯'}</div><div class="muted">${lastResult?('Выпало: '+lastResult.number+' ('+lastResult.color+')'):'Выбери исход'}</div>`);
 buttons('<div class="control-label">ЦВЕТ</div>');$('controls').appendChild(choices([['color:red','🔴 Красное'],['color:black','⚫ Чёрное'],['color:green','🟢 Зеро']],selected,v=>selected=v));
 $('controls').insertAdjacentHTML('beforeend','<div class="control-label">ЧЁТНОСТЬ</div>');$('controls').appendChild(choices([['parity:even','Чётное'],['parity:odd','Нечётное']],selected,v=>selected=v));
 $('controls').insertAdjacentHTML('beforeend','<div class="control-label">ЧИСЛО 0–36</div><input id="rouletteNumber" class="number-field" type="number" min="0" max="36" placeholder="Число (необязательно)" style="width:100%;padding:12px;border-radius:11px;color:white;background:#201936;border:1px solid #72559a;margin-bottom:10px">');
 const input=$('rouletteNumber');input.addEventListener('input',()=>{if(input.value!=='')selected='number:'+input.value;});
 btn('🎯 Сделать ставку',async()=>{const [bet_type,bet_value]=selected.split(':');const r=await api('/api/roulette',{stake:stake(),bet_type,bet_value});updateBalance(r.balance);lastResult=r;render();feedback(r.payout?'Выигрыш: '+fmt(r.payout):'Не повезло',r.payout?'win':'');});
}else if(g==='dice'){
 drawArena(`<div class="big-symbol">${lastResult?['','⚀','⚁','⚂','⚃','⚄','⚅'][lastResult.result]:'🎲'}</div><div class="muted">${lastResult?'Выпало '+lastResult.result:'Выбери число'}</div>`);
 buttons('<div class="control-label">ТВОЙ ПРОГНОЗ</div>');$('controls').appendChild(choices([1,2,3,4,5,6].map(x=>[x,String(x)]),guess,v=>guess=Number(v)));
 btn('🎲 Бросить кубик',async()=>{const r=await api('/api/dice',{stake:stake(),guess});lastResult=r;updateBalance(r.balance);render();feedback(r.payout?'Выигрыш: '+fmt(r.payout):'В этот раз не угадал',r.payout?'win':'');});
}else if(g==='blackjack'){
 const s=active?.state;const p=lastResult?.player||s?.player||[];const d=lastResult?.dealer||s?.dealer||[]; const visible=(activeGame()==='blackjack')?['🂠',d[0]]:(lastResult?.dealer||[]);
 drawArena(`<div class="muted">ДИЛЕР</div><div class="cards">${visible.map(escapeHtml).join(' ')||'🂠 🂠'}</div><div class="muted">ТВОИ КАРТЫ</div><div class="cards">${p.map(escapeHtml).join(' ')||'🂡 🂱'}</div><div class="muted">${lastResult?.player_value??''}</div>`);
 buttons('');if(isSession){btn('Ещё карту',async()=>{const r=await api('/api/blackjack/hit',{});lastResult=r;if(r.finished){active=null;updateBalance(r.balance);feedback('Раунд: '+r.outcome+' · Выплата '+fmt(r.payout),r.payout?'win':'');}render();});btn('Хватит',async()=>{const r=await api('/api/blackjack/stand',{});lastResult=r;active=null;updateBalance(r.balance);render();feedback('Раунд: '+r.outcome+' · Выплата '+fmt(r.payout),r.payout?'win':'');});}
 else btn('Начать раздачу',async()=>{const n=stake();const r=await api('/api/blackjack/start',{stake:n});active={game:'blackjack',stake:n,state:{player:r.player,dealer:[r.dealer_visible,'🂠']}};updateBalance(r.balance);lastResult=r;render();feedback('Твой ход');});
}else if(g==='crash'){
 drawArena(`<div class="crash-mult" id="crashMult">${lastResult?.multiplier?lastResult.multiplier.toFixed(2):'1.00'}×</div><div class="muted">${isSession?'Раунд идёт — забери до обвала':'Множитель увеличивается со временем'}</div>`);
 buttons('');if(isSession)btn('💰 Забрать выигрыш',async()=>{stopCrash();const r=await api('/api/crash/cashout',{});lastResult=r;active=null;updateBalance(r.balance);render();feedback(r.busted?'Обвал! Ставка потеряна':'Выигрыш: '+fmt(r.payout),r.busted?'error':'win');});
 else btn('🚀 Начать раунд',async()=>{const n=stake();const r=await api('/api/crash/start',{stake:n});active={game:'crash',stake:n,state:{}};lastResult=null;updateBalance(r.balance);render();startCrash();feedback('Успей забрать!');});
 if(isSession)startCrash();
}else if(g==='mines'){
 const s=active?.state;if(s?.revealed)minesRevealed=new Set(s.revealed);
 drawArena(`<div class="muted">${isSession?'Открыто клеток: '+minesRevealed.size:'Выбери число мин и начни'}</div><div class="mines-grid">${Array.from({length:25},(_,i)=>`<button data-cell="${i}" class="${minesBombs.has(i)?'bomb':minesRevealed.has(i)?'revealed':''}" ${!isSession||minesRevealed.has(i)||minesBombs.has(i)?'disabled':''}>${minesBombs.has(i)?'💣':minesRevealed.has(i)?'💎':'?'}</button>`).join('')}</div>`);
 document.querySelectorAll('[data-cell]').forEach(b=>b.addEventListener('click',()=>action(async()=>{const r=await api('/api/mines/reveal',{tile_index:Number(b.dataset.cell)});lastResult=r;if(r.busted){minesBombs=new Set(r.mine_positions);active=null;updateBalance(r.balance);feedback('Мина! Ставка потеряна','error');}else{minesRevealed.add(Number(b.dataset.cell));if(r.cleared_all){active=null;updateBalance(r.balance);feedback('Все клетки открыты! Выигрыш '+fmt(r.payout),'win');}else{active.state.revealed=[...minesRevealed];feedback('Множитель: '+r.multiplier+'×');}}render();})));
 buttons('');if(isSession){btn('💎 Забрать монеты',async()=>{const r=await api('/api/mines/cashout',{});lastResult=r;active=null;updateBalance(r.balance);render();feedback('Выигрыш: '+fmt(r.payout),'win');});}
 else{$('controls').insertAdjacentHTML('beforeend','<div class="control-label">КОЛИЧЕСТВО МИН</div>');$('controls').appendChild(choices([1,2,3,5,7,10,15,20,24].map(v=>[v,''+v]),minesCount,v=>minesCount=Number(v)));btn('💣 Начать',async()=>{const n=stake();const r=await api('/api/mines/start',{stake:n,mines_count:minesCount});active={game:'mines',stake:n,state:{mines_count:minesCount,revealed:[]}};minesRevealed=new Set();minesBombs=new Set();updateBalance(r.balance);render();feedback('Открывай клетки');});}
}
}
function stopCrash(){if(crashTimer){clearInterval(crashTimer);crashTimer=null;}}
function startCrash(){if(crashTimer||activeGame()!=='crash')return;crashTimer=setInterval(async()=>{if(activeGame()!=='crash'){stopCrash();return;}try{const r=await api('/api/crash/status');const el=$('crashMult');if(el)el.textContent=Number(r.multiplier).toFixed(2)+'×';if(r.crashed){stopCrash();active=null;lastResult=r;updateBalance(r.balance);render();feedback('Обвал на '+r.crash_point+'×','error');}}catch(e){stopCrash();if(e.message!==errors.no_session)feedback(e.message,'error');}},450);}
async function loadProfile(){try{const r=await api('/api/me');updateBalance(r.balance);$('username').textContent=r.username||'Игрок';$('userid').textContent='Telegram ID: '+r.user_id;$('statWagered').textContent=fmt(r.total_wagered);$('statWon').textContent=fmt(r.total_won);}catch(e){toast(e.message);}}
async function loadLeaders(){try{const rows=await fetch('/api/leaderboard').then(r=>r.json());$('leaderRows').innerHTML=rows.map((r,i)=>`<div class="leaderrow"><span>${i+1}. ${escapeHtml(r.username||'Игрок')}</span><b>${fmt(r.balance)}</b></div>`).join('')||'<p class="muted">Пока нет игроков</p>';}catch(e){toast('Не удалось загрузить рейтинг');}}
$('back').addEventListener('click',()=>nav('home'));
document.querySelectorAll('[data-game]').forEach(b=>b.addEventListener('click',()=>openGame(b.dataset.game)));
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.tab==='play')openGame(activeGame()||current);else nav(b.dataset.tab);}));
$('half').addEventListener('click',()=>{$('stake').value=Math.max(1,Math.floor(stake()/2));});
$('double').addEventListener('click',()=>{$('stake').value=Math.min(1000000000,stake()*2);});
$('promoBtn').addEventListener('click',()=>action(async()=>{const code=$('promoInput').value.trim();if(!code)throw Error('Введи промокод.');const r=await api('/api/promo/redeem',{code});updateBalance(r.balance);$('promoInput').value='';toast('Промокод активирован: +'+fmt(r.amount));}));
(async()=>{if(!initData){$('balance').textContent='Демо';toast('Открой приложение через кнопку Telegram-бота.');return;}try{const me=await api('/api/me');updateBalance(me.balance);active=me.active_session; if(active?.game){current=active.game;toast('У тебя есть незавершённый раунд.');}else current='slots';}catch(e){toast(e.message);} })();
