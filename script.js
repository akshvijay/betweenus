const $ = (s, p = document) => p.querySelector(s), $$ = (s, p = document) => [...p.querySelectorAll(s)];
let session, room, ticket, matchPoll, chatPoll, activeIncomingInvite, activeOutgoingInvite, invitePoll, jwtToken, userId;
const api = async (url, options = {}) => { const r = await fetch(url, {...options, headers:{'Content-Type':'application/json', ...(jwtToken?{'Authorization':`Bearer ${jwtToken}`}:{}), ...(options.headers||{})}}); const data = await r.json(); if(!r.ok) throw Error(data.error||'Something went wrong'); return data };
const esc = v => String(v||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ago = t => {const n=Math.max(0,Math.floor(Date.now()/1000-t)); return n<60?'now':n<3600?`${Math.floor(n/60)} min ago`:`${Math.floor(n/3600)} hr ago`};

// Linear Interpolation (lerping) for Cursor Glow
let mouseX = window.innerWidth / 2;
let mouseY = window.innerHeight / 2;
let glowX = mouseX;
let glowY = mouseY;
const lerpSpeed = 0.08;

document.addEventListener('mousemove', e => {
  mouseX = e.clientX;
  mouseY = e.clientY;
});

function animateGlow() {
  glowX += (mouseX - glowX) * lerpSpeed;
  glowY += (mouseY - glowY) * lerpSpeed;
  const glow = $('.cursor-glow');
  if (glow) {
    glow.style.left = `${glowX}px`;
    glow.style.top = `${glowY}px`;
  }
  requestAnimationFrame(animateGlow);
}
requestAnimationFrame(animateGlow);

// Magnetic Pull Hover Effect for Primary Controls
function applyMagnetic(el) {
  el.addEventListener('mousemove', e => {
    const rect = el.getBoundingClientRect();
    // Calculate distance from element center
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    // Pull element slightly (24% of distance) towards cursor
    el.style.transform = `translate(${x * 0.24}px, ${y * 0.24}px)`;
  });
  
  el.addEventListener('mouseleave', () => {
    el.style.transform = '';
  });
}

// 3D Tilt Hover Effect for Cards and Panel
function applyTilt(card, intensity = 16) {
  card.addEventListener('mousemove', e => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const xc = rect.width / 2;
    const yc = rect.height / 2;
    const angleX = (yc - y) / intensity;
    const angleY = (x - xc) / intensity;
    card.style.transform = `perspective(1000px) translateY(-8px) rotateX(${angleX}deg) rotateY(${angleY}deg) scale(1.01)`;
  });
  
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
  });
}

// Heart Particle Burst Animation
function createHeartBurst(btn) {
  const container = $('#particle-container');
  if (!container) return;
  const rect = btn.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  
  const count = 10;
  for (let i = 0; i < count; i++) {
    const p = document.createElement('span');
    p.className = 'heart-particle';
    p.textContent = ['♥', '💕', '✨', '🌸', '💖'][Math.floor(Math.random() * 5)];
    p.style.left = `${centerX}px`;
    p.style.top = `${centerY}px`;
    
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.4;
    const distance = 40 + Math.random() * 70;
    const x = Math.cos(angle) * distance;
    const y = Math.sin(angle) * distance - 30; // Float upwards
    const r = (Math.random() - 0.5) * 120;
    
    p.style.setProperty('--x', `${x}px`);
    p.style.setProperty('--y', `${y}px`);
    p.style.setProperty('--r', `${r}deg`);
    
    container.appendChild(p);
    setTimeout(() => p.remove(), 1200);
  }
}

// Radar Visual Coordinate Helpers
function initRadarCrosshairs() {
  const visual = $('.match-visual');
  if (!visual) return;
  const h = document.createElement('div');
  h.className = 'radar-crosshair-h';
  const v = document.createElement('div');
  v.className = 'radar-crosshair-v';
  visual.appendChild(h);
  visual.appendChild(v);
}

let blipInterval;
function startRadarBlips() {
  const visual = $('.match-visual');
  if (!visual) return;
  clearInterval(blipInterval);
  blipInterval = setInterval(() => {
    const modal = $('#match-modal');
    // Stop if modal isn't open or match is already established
    if (!modal || !modal.classList.contains('open') || $('#matcher').classList.contains('is-matched')) {
      clearInterval(blipInterval);
      return;
    }
    const blip = document.createElement('div');
    blip.className = 'radar-blip';
    
    const angle = Math.random() * Math.PI * 2;
    const radius = 25 + Math.random() * 115;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    
    blip.style.left = `calc(50% + ${x}px)`;
    blip.style.top = `calc(50% + ${y}px)`;
    
    visual.appendChild(blip);
    setTimeout(() => blip.remove(), 2000);
  }, 750);
}

// Session & Auth
async function getSession(){session=localStorage.getItem('betweenus-session');jwtToken=localStorage.getItem('betweenus-jwt');userId=localStorage.getItem('betweenus-user-id');if(!session){session=(await api('/api/session',{method:'POST',body:'{}'})).session;localStorage.setItem('betweenus-session',session)}updateAuthButton()}
function updateAuthButton(){const btn=$('#auth-button');if(jwtToken){btn.textContent='View history ✦';btn.dataset.action='history'}else{btn.textContent='Sign in ↗';btn.dataset.action='login'}}
async function signup(email,password){const r=await api('/api/auth/signup',{method:'POST',body:JSON.stringify({email,password})});jwtToken=r.token;userId=r.user_id;localStorage.setItem('betweenus-jwt',jwtToken);localStorage.setItem('betweenus-user-id',userId);updateAuthButton();close('auth-modal');alert('Account created! Your history is now saved.')}
async function login(email,password){const r=await api('/api/auth/login',{method:'POST',body:JSON.stringify({email,password})});jwtToken=r.token;userId=r.user_id;localStorage.setItem('betweenus-jwt',jwtToken);localStorage.setItem('betweenus-user-id',userId);updateAuthButton();close('auth-modal');alert('Signed in! Your history is loaded.')}
async function loadHistory(){if(!jwtToken)return;try{const r=await api('/api/history');const list=$('#history-list');list.innerHTML=r.history.length?r.history.map((h,i)=>`<div class="history-item"><div><strong>Conversation ${i+1}</strong><small>${ago(h.created_at)}</small></div><small>${h.message_count} messages</small></div>`).join(''):'<div class="history-item"><p>No saved conversations yet. Sign in to your future chats to save them here.</p></div>'}catch(e){console.warn(e)}}
function logout(){jwtToken=null;userId=null;localStorage.removeItem('betweenus-jwt');localStorage.removeItem('betweenus-user-id');updateAuthButton();close('history-modal');alert('Signed out.')}

$('#auth-button').addEventListener('click',()=>{if(jwtToken){open('history-modal');loadHistory()}else{open('auth-modal')}});
let isLoginMode=false;
$('#toggle-login').addEventListener('click',e=>{e.preventDefault();isLoginMode=!isLoginMode;$('#auth-form').style.display=isLoginMode?'block':'block';$('#auth-submit').textContent=isLoginMode?'Sign in':'Sign up';$('[data-close="auth-modal"]').click();setTimeout(()=>open('auth-modal'),100)});
$('#auth-form').addEventListener('submit',async e=>{e.preventDefault();const email=$('#auth-email').value,pwd=$('#auth-password').value;try{isLoginMode?await login(email,pwd):await signup(email,pwd);$('#auth-email').value='';$('#auth-password').value=''}catch(err){alert(err.message)}});
$('#logout-btn').addEventListener('click',logout);

// Modal Management
function open(id){const m=$('#'+id);m.classList.add('open');m.setAttribute('aria-hidden','false')}
function close(id){const m=$('#'+id);m.classList.remove('open');m.setAttribute('aria-hidden','true');if(id==='match-modal'){clearInterval(matchPoll);clearInterval(invitePoll)}if(id==='chat-modal')clearInterval(chatPoll)}

$$('[data-close]').forEach(b=>b.addEventListener('click',()=>close(b.dataset.close)));$$('.modal').forEach(m=>m.addEventListener('click',e=>{if(e.target===m)close(m.id)}));

// Smooth Scroll Buttons
$$('[data-scroll]').forEach(el=>el.addEventListener('click',()=>$(el.dataset.scroll)?.scrollIntoView({behavior:'smooth',block:'center'})));

// Scroll Reveal Intersection Observer
const observer=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');observer.unobserve(e.target)}}),{threshold:.1});
$$('.reveal').forEach(el=>observer.observe(el));

// Multi-layered Parallax Scroll Handler
window.addEventListener('scroll',()=>{
  const y=scrollY;
  
  // Parallax background blobs
  const amb1 = $('.ambient-one');
  if (amb1) amb1.style.transform = `translate3d(0, ${y * 0.12}px, 0)`;
  
  const amb2 = $('.ambient-two');
  if (amb2) amb2.style.transform = `translate3d(0, ${-y * 0.08}px, 0)`;
  
  // Float words
  $$('.word').forEach((el,i)=>{
    el.style.transform=`translateY(${y*(i%2?-.05:.07)}px)`;
    el.style.opacity=Math.max(.03,.35-y/2800);
  });
},{passive:true});

// Input handling
const thought=$('#thought');
if (thought) {
  thought.addEventListener('input',()=>$('#count').textContent=`${thought.value.length} / 500`);
}
$$('.choice').forEach(c=>c.addEventListener('click',()=>{$$('.choice').forEach(x=>x.classList.remove('active'));c.classList.add('active')}));
$$('.tag').forEach(t=>t.addEventListener('click',()=>t.classList.toggle('selected')));

// Breathing Scroll Cue Loop
const scrollCue = $('.scroll-cue');
if (scrollCue) {
  let isExhale = true;
  setInterval(() => {
    isExhale = !isExhale;
    scrollCue.childNodes[1].textContent = isExhale ? 'scroll to exhale' : 'scroll to inhale';
  }, 3000);
}

// Card Renderer
function card(p,index){
  let color=['large','lilac','peach','dark'][index%4];
  return `<article class="thought-card ${color} reveal"><div class="card-top"><span class="feeling">${esc(p.category||'life')}</span><time>${ago(p.created_at)}</time></div><blockquote>“${esc(p.body)}”</blockquote><div class="card-bottom"><button class="relate" data-relate="${p.id}"><span>♡</span> I relate <small>${p.relates} people relate</small></button><button class="talk" data-talk>Talk to them <b>→</b></button></div></article>`;
}

async function loadPosts(){
  try{
    const {posts}=await api('/api/posts');
    $('#feed').innerHTML=posts.map(card).join('');
    
    // Apply tilt and scroll reveals to cards
    $$('.thought-card').forEach((el, index) => {
      applyTilt(el);
      el.style.transitionDelay = `${(index % 4) * 0.08}s`;
      observer.observe(el);
    });
  }catch(e){
    console.warn(e);
  }
}

// Feed Interactions
$('#feed').addEventListener('click',async e=>{
  const relate=e.target.closest('[data-relate]');
  if(relate){
    try{
      const r=await api(`/api/posts/${relate.dataset.relate}/relate`,{method:'POST',body:JSON.stringify({session})});
      relate.classList.toggle('relate-active', r.active);
      relate.querySelector('span').textContent = r.active ? '♥' : '♡';
      relate.querySelector('small').textContent = `${r.relates} people relate`;
      if (r.active) {
        createHeartBurst(relate);
      }
    }catch(err){
      alert(err.message);
    }
  }
  const talk=e.target.closest('[data-talk]');
  if(talk){
    const post=talk.closest('.thought-card');
    try{
      const r=await api(`/api/posts/${post.querySelector('[data-relate]').dataset.relate}/interest`,{method:'POST',body:JSON.stringify({session})});
      if(r.invitation) startInvitation(r.invitation.id);
      else beginMatch();
    }catch(err){
      alert(err.message);
    }
  }
});

$('#thought-form').addEventListener('submit',async e=>{
  e.preventDefault();
  if(!thought.value.trim()){
    thought.focus();
    thought.placeholder='A few words is enough…';
    return;
  }
  try{
    await api('/api/posts',{method:'POST',body:JSON.stringify({session,body:thought.value,need:$('.choice.active')?.textContent||'I just want to vent',category:$('.tag.selected')?.textContent||'life'})});
    thought.value='';
    $('#count').textContent='0 / 500';
    open('post-modal');
    loadPosts();
  }catch(err){
    alert(err.message);
  }
});

// Matching Serendipity
async function beginMatch(){
  open('match-modal');
  $('#matcher').classList.remove('is-matched');
  $('#match-status').textContent='Looking for a shared feeling, not a perfect match.';
  startRadarBlips();
  try{
    const r=await api('/api/match',{method:'POST',body:JSON.stringify({session})});
    ticket=r.ticket;
    if(r.status==='matched') found(r.room);
    else {
      clearInterval(matchPoll);
      matchPoll=setInterval(checkMatch,1800);
    }
  }catch(e){
    $('#match-status').textContent=e.message;
  }
}

async function checkMatch(){
  try{
    const r=await api(`/api/match/${ticket}?session=${encodeURIComponent(session)}`);
    if(r.status==='matched') found(r.room);
  }catch(e){
    clearInterval(matchPoll);
    $('#match-status').textContent=e.message;
  }
}

function found(id){
  room=id;
  clearInterval(matchPoll);
  $('#matcher').classList.add('is-matched');
}

function startInvitation(id){
  activeOutgoingInvite=id;
  open('match-modal');
  $('#matcher').classList.remove('is-matched');
  $('#match-status').textContent='Your invitation is waiting for them. Keep this open while they decide.';
  startRadarBlips();
  clearInterval(invitePoll);
  invitePoll=setInterval(async()=>{
    try{
      const r=await api(`/api/invitations/${id}?session=${encodeURIComponent(session)}`);
      if(r.invitation.status==='accepted'){
        room=r.invitation.room;
        clearInterval(invitePoll);
        $('#matcher').classList.add('is-matched');
      }
      if(r.invitation.status==='declined'){
        clearInterval(invitePoll);
        $('#match-status').textContent='They aren’t available to talk right now.';
      }
    }catch(e){
      clearInterval(invitePoll);
    }
  },1500);
}

$('#match-button').addEventListener('click',beginMatch);
$('#open-chat').addEventListener('click',()=>{
  close('match-modal');
  open('chat-modal');
  loadChat();
  clearInterval(chatPoll);
  chatPoll=setInterval(loadChat,1600);
});

// Chat Interface
async function loadChat(){
  if(!room)return;
  try{
    const r=await api(`/api/chat/${room}?session=${encodeURIComponent(session)}`);
    const box=$('#messages');
    const wasBottom=box.scrollTop+box.clientHeight>=box.scrollHeight-60;
    
    box.innerHTML=r.messages.map(m=>`<div class="message ${m.sender===session?'you':'them'}">${esc(m.body)}<time>${ago(m.created_at)}</time></div>`).join('');
    
    if(wasBottom) {
      box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
    }
  }catch(e){
    console.warn(e);
  }
}

$('#chat-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const input=$('#chat-input');
  if(!input.value.trim())return;
  try{
    await api(`/api/chat/${room}`,{method:'POST',body:JSON.stringify({session,body:input.value})});
    input.value='';
    loadChat();
  }catch(err){
    alert(err.message);
  }
});

$('#safety-menu').addEventListener('click',()=>$('#safety-menu-panel').classList.toggle('show'));
$('[data-end]').addEventListener('click',()=>close('chat-modal'));
$('[data-block]').addEventListener('click',async()=>{
  await api('/api/block',{method:'POST',body:JSON.stringify({session,room})});
  close('chat-modal');
  alert('This conversation is blocked. You will not be matched with them again.');
});
$('[data-report]').addEventListener('click',async()=>{
  await api('/api/report',{method:'POST',body:JSON.stringify({session,room,reason:'Reported from chat'})});
  alert('Thank you. This conversation has been sent for review.');
  $('#safety-menu-panel').classList.remove('show');
});

// Notifications & Invites
let notificationCache=[];
let lastNotificationState='';
async function loadNotifications(){
  try{
    const [r,inv]=await Promise.all([api(`/api/notifications?session=${encodeURIComponent(session)}`),api(`/api/invitations?session=${encodeURIComponent(session)}`)]);
    notificationCache=r.notifications;
    activeIncomingInvite=inv.invitations.find(i=>i.recipient===session&&i.status==='pending');
    
    const count=$('#activity-count');
    count.textContent=r.notifications.length;
    count.classList.toggle('show',r.notifications.length>0);
    
    $('#activity-list').innerHTML=r.notifications.length?r.notifications.map(n=>`<div class="activity-item"><i></i><div>${esc(n.message)}<small>${ago(n.created_at)}</small></div></div>`).join(''):'<div class="activity-item"><div>No activity yet. When someone connects with a thought you share, it will appear here.</div></div>';
    
    const known=JSON.parse(localStorage.getItem('betweenus-known-notifications')||'[]');
    const newest=r.notifications.find(n=>!known.includes(n.id));
    const stateKey=`${r.notifications.length}:${activeIncomingInvite?.id||'none'}`;
    const shouldShow=(newest||activeIncomingInvite) && stateKey!==lastNotificationState;

    if(shouldShow){
      $('#notification-message').textContent=activeIncomingInvite?'Someone relates and wants to talk anonymously.':'Someone relates to something you shared.';
      $('#notification-talk').textContent=activeIncomingInvite?'Accept chat →':'Talk anonymously →';
      $('#notification-bar').classList.add('show');
      localStorage.setItem('betweenus-known-notifications',JSON.stringify(r.notifications.map(n=>n.id)));
    } else if(stateKey!==lastNotificationState && !newest && !activeIncomingInvite) {
      $('#notification-bar').classList.remove('show');
    }

    lastNotificationState=stateKey;
  }catch(e){
    console.warn(e);
  }
}

$('#activity-button').addEventListener('click',()=>open('activity-modal'));
$('#notification-close').addEventListener('click',()=>{
  $('#notification-bar').classList.remove('show');
  lastNotificationState = '';
});
$('#notification-talk').addEventListener('click',async()=>{
  if(activeIncomingInvite){
    try{
      const r=await api(`/api/invitations/${activeIncomingInvite.id}/accept`,{method:'POST',body:JSON.stringify({session})});
      room=r.room;
      $('#notification-bar').classList.remove('show');
      open('chat-modal');
      loadChat();
      clearInterval(chatPoll);
      chatPoll=setInterval(loadChat,1600);
      loadNotifications();
    }catch(e){
      alert(e.message);
    }
  }else{
    $('#notification-bar').classList.remove('show');
    beginMatch();
  }
});

// Initialization
(async()=>{
  await getSession();
  await loadPosts();
  await loadNotifications();
  
  // Set up static magnetic controls
  $$('.button, .round-button, .quiet-link, .activity-button').forEach(applyMagnetic);
  
  // Set up 3D tilt on the redesigned Match Panel
  const matchPanel = $('#match-panel');
  if (matchPanel) {
    applyTilt(matchPanel, 35); // Lower intensity for a larger card
  }
  
  // Set up radar graphics
  initRadarCrosshairs();
  
  setInterval(loadNotifications, 5000);
})();
