// Oracle d'equivalence : recalcule les agregats avec les formules COPIEES du
// gabarit template_tail.html, sur les MENAGES bruts. Sortie = meme structure que
// rapport_core.agrege(...)["summary"], pour comparaison champ par champ.
const fs = require('fs');
const MENAGES = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

function avg(arr){ return arr.length ? Math.round(arr.reduce((s,v)=>s+v,0)/arr.length) : 0; }
function pct(n,t){ return t ? Math.round(n/t*100) : 0; }
function isValidDate(d){ return !!d && /^\d{8}$/.test(d); }
function hasCarnet(m){ return m.carnet===1 || m.carnet===2; }
function communeOf(m){ return (m.commune && m.commune.trim()) ? m.commune : '(commune inconnue)'; }
function fktKeyOf(m){ return m.fktcode || m.fkt || ''; }

// SEGMENTS : agrege par (sid x fokontany) — template_tail.html l.81-97
const segMap = new Map();
MENAGES.forEach(m=>{
  const fc = fktKeyOf(m);
  const key = m.sid+'|'+fc;
  if(!segMap.has(key)){
    segMap.set(key,{sid:m.sid,agent:m.agent,commune:communeOf(m),fkt:m.fkt,fktcode:fc,
      seg:m.seg,statut:m.statut,rejet:m.rejet,tps:m.tps,bats:new Set(),n:0,nPresent:0,nCarnet:0});
  }
  const s=segMap.get(key);
  s.n++;
  if(m.presence===1) s.nPresent++;
  if(hasCarnet(m)) s.nCarnet++;
  if(m.bat) s.bats.add(m.bat);
});
const SEGMENTS=[...segMap.values()];

const total=MENAGES.length;
const dates=[...new Set(MENAGES.map(m=>m.date).filter(isValidDate))].sort();

// -- general (renderGeneral base) --
const nbPresents=MENAGES.filter(m=>m.presence===1).length;
const nbCarnet=MENAGES.filter(hasCarnet).length;
const tpsSeg=SEGMENTS.filter(s=>s.tps>0).map(s=>s.tps);
const nbBat=new Set(MENAGES.map(m=>m.sid+'-'+m.bat)).size;
const agentsActifs=[...new Set(MENAGES.map(m=>m.agent).filter(Boolean))].sort();
const daily=dates.map(d=>({d,total:MENAGES.filter(m=>m.date===d).length,
  present:MENAGES.filter(m=>m.date===d&&m.presence===1).length}));
const agentsPerDay=dates.map(d=>({d,n:new Set(MENAGES.filter(m=>m.date===d).map(m=>m.agent).filter(Boolean)).size}));
const general={total,nbPresents,nbCarnet,nbSegments:SEGMENTS.length,nbBat,tps:avg(tpsSeg),
  nAgents:agentsActifs.length,dates,daily,agentsPerDay,
  presence:[nbPresents,MENAGES.filter(m=>m.presence===2).length],
  carnet:[1,2,3,4].map(c=>MENAGES.filter(m=>m.carnet===c).length)};

// -- gpscap (renderGpsCaptureSection) --
function hasGps(m){ return typeof m.lat==='number'&&isFinite(m.lat)&&typeof m.lon==='number'&&isFinite(m.lon); }
const ok=MENAGES.filter(hasGps).length;
const gpscap={total,ok,ko:total-ok};

// -- qualite (initQualite) --
const tailles=MENAGES.map(m=>m.taille).filter(t=>t>0);
const maxT=Math.min(Math.max(...tailles,0),15);
const bins=[];
for(let b=1;b<=maxT;b++){ bins.push({b,count:(b===maxT?tailles.filter(t=>t>=b).length:tailles.filter(t=>t===b).length),last:b===maxT}); }
const nbGpsLat=MENAGES.filter(m=>m.lat&&Math.abs(m.lat)<90).length;
const qualite={carnet:general.carnet,presence:general.presence,
  elec:[MENAGES.filter(m=>m.elec===1).length,MENAGES.filter(m=>m.elec===2).length],
  statut:[SEGMENTS.filter(s=>s.statut===120).length,SEGMENTS.filter(s=>s.statut!==120).length],
  gps:[nbGpsLat,total-nbGpsLat],taille:{maxT,bins}};

// -- historique (initHistorique) --
const perDate=dates.map(d=>{
  const ms=MENAGES.filter(m=>m.date===d);
  return {d,menages:ms.length,segments:new Set(ms.map(m=>m.sid)).size,
    agents:new Set(ms.map(m=>m.agent)).size,
    tps:avg(SEGMENTS.filter(s=>ms.some(m=>m.sid===s.sid)&&s.tps>0).map(s=>s.tps))};
});
const historique={dates,perDate,kpis:{jours:dates.length,first:dates[0]??null,
  last:dates[dates.length-1]??null,moy:avg(dates.map(d=>MENAGES.filter(m=>m.date===d).length))}};

// -- par agent (renderAgentSummary) --
const agents=agentsActifs.map(a=>{
  const am=MENAGES.filter(m=>m.agent===a);
  const asg=SEGMENTS.filter(s=>s.agent===a);
  return {agent:a,n:am.length,nSeg:asg.length,
    nPresent:am.filter(m=>m.presence===1).length,
    nCarnet:am.filter(hasCarnet).length,
    presPct:pct(am.filter(m=>m.presence===1).length,am.length),
    carnPct:pct(am.filter(hasCarnet).length,am.length),
    tps:avg(asg.filter(s=>s.tps>0).map(s=>s.tps))};
});

process.stdout.write(JSON.stringify({general,gpscap,qualite,historique,agents}));
