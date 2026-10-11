const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// HTML escaping alone does not protect a JavaScript string inside an event attribute.
const jsArg=s=>esc(JSON.stringify(String(s??"")).replace(/</g,"\\u003c").replace(/\u2028/g,"\\u2028").replace(/\u2029/g,"\\u2029"));
const num=n=>n==null||!Number.isFinite(Number(n))?"-":Number(n).toLocaleString(undefined,{maximumFractionDigits:0});
const fixed=n=>n==null||!Number.isFinite(Number(n))?"-":Number(n).toFixed(2);
const pct=(n,max=100)=>Math.max(0,Math.min(max,Number(n)||0));
const safeURL=value=>{try{const u=new URL(String(value));return ["http:","https:"].includes(u.protocol)?u.href:"";}catch{return "";}};
const externalLink=(url,html)=>{const href=safeURL(url);return href?`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${html}</a>`:html;};
const own=(obj,key)=>Object.prototype.hasOwnProperty.call(obj,key)?obj[key]:undefined;
const decisionText=s=>String(s??"").replace(/\bmission archive\b/gi,"decision archive").replace(/\bmissions\b/gi,"sample decisions");
function refreshIcons(){try{window.lucide?.createIcons();}catch{/* Icons must not block the report. */}}
function status(id,message,error=false){const node=$(id);if(node){node.className=error?"status err":"status";node.textContent=message;}}

const REQUESTS=new Map();
function cancelRequest(scope){const previous=REQUESTS.get(scope);if(previous)previous.controller.abort();REQUESTS.delete(scope);}
function beginRequest(scope){cancelRequest(scope);const ticket={scope,controller:new AbortController()};REQUESTS.set(scope,ticket);return ticket;}
const isCurrent=ticket=>REQUESTS.get(ticket.scope)===ticket;
function finishRequest(ticket){if(isCurrent(ticket))REQUESTS.delete(ticket.scope);}
async function requestJSON(ticket,url,options={},timeout=120000){
  let timer,abortListener,timedOut=false;
  const {signal}=ticket.controller;
  try{
    const aborted=new Promise((_,reject)=>{
      abortListener=()=>reject(new Error(timedOut?"The request timed out. Please retry; the server may still be finishing the previous request.":"Request cancelled."));
      signal.addEventListener("abort",abortListener,{once:true});
      if(signal.aborted)abortListener();
    });
    timer=setTimeout(()=>{timedOut=true;ticket.controller.abort();},timeout);
    const read=async()=>{
      const response=await fetch(url,{...options,signal});
      if(!response.ok){
        const hint=response.status===404?"This item is no longer available.":response.status===422?"Please check the submitted fields.":response.status===429?"Too many requests. Please wait and retry.":response.status>=500?"The service could not complete this request. Please retry.":"The request could not be completed.";
        throw new Error(`${hint} (HTTP ${response.status})`);
      }
      let data;try{data=await response.json();}catch{throw new Error("The service returned an unreadable response. Please retry.");}
      if(!data||typeof data!=="object"||Array.isArray(data))throw new Error("The service returned an unexpected response.");
      return data;
    };
    return await Promise.race([read(),aborted]);
  }catch(error){
    if(error instanceof TypeError)throw new Error("Unable to reach Brahma. Check your connection and retry.");
    throw error;
  }finally{clearTimeout(timer);signal.removeEventListener("abort",abortListener);}
}
function validateInvestigation(d){
  if(!d.supplier||typeof d.supplier.name!=="string"||!d.risk||!d.sanctions||!d.media_summary||!d.entity_resolution||!d.litigation||!d.agent_summary||!d.graph||
    !Array.isArray(d.adverse_media)||!Array.isArray(d.ownership)||!Array.isArray(d.risk.contributions))
    throw new Error("The service returned an incomplete investigation. Please retry; the previous report has been kept.");
  return d;
}
function validateStrategy(d){
  if(d.available!==false&&(!d.verdict||!Array.isArray(d.seats)))throw new Error("The service returned an incomplete strategy report. Please retry.");
  return d;
}

const CATEGORIES=[
  {key:"financial_crime",label:"Financial Crime",color:"#c2410c"},
  {key:"legal_reputational",label:"Legal & Reputational Risk",color:"#b45309"},
  {key:"regulatory",label:"FINRA & Regulatory Bodies",color:"#0e7490"},
  {key:"terrorism_serious_crime",label:"Terrorism & Serious Crime",color:"#b91c1c"},
  {key:"sanctions",label:"Sanctions & Watchlists",color:"#527c78"},
];
const CAT_COLOR=Object.fromEntries(CATEGORIES.map(c=>[c.key,c.color]));

let DATA=null,TYPE="organization",GRAPH="resolution",SELECTED=null;
let F={cats:new Set(),bias:new Set(),terms:new Set(),severe:false};
let SUBJECTS_LIST=[],ENT_FILTER="all",CURRENT_ID=null;
let MODE="screen",STEP=1,DATA_ORIGIN=null,STRAT_ORIGIN=null,SERVICE_STATUS="Checking service";
async function checkHealth(){
  const ticket=beginRequest("health");
  try{
    const d=await requestJSON(ticket,"/api/v1/health",{},15000);
    if(isCurrent(ticket))SERVICE_STATUS=d.status==="ok"?"Service ready":"Service unavailable";
  }catch{if(isCurrent(ticket))SERVICE_STATUS="Service unavailable";}
  finally{if(isCurrent(ticket))updateWorkspace();finishRequest(ticket);}
}
function isSample(d,origin){
  const m=d?.metadata||{};
  return origin==="sample"||[d?.demo,d?.sample,d?.is_sample,m.demo,m.sample,m.is_sample,m.is_demo].some(v=>v===true)||
    d?.evidence_audit?.verification_mode==="illustrative_sample"||
    /sample|demo|archive/i.test(String(m.mode||m.data_mode||m.provenance||""))||
    /sample|demo dataset|mission archive/i.test(String(d?.generated_by||d?.agent_summary?.generated_by||""));
}
function provenance(d,origin){
  if(!d)return "No report loaded";
  if(isSample(d,origin))return "Sample / offline";
  if(d.available===false)return "Unavailable";
  const m=d.metadata||{};
  if(d.offline===true||m.offline===true||/offline/i.test(String(m.mode||"")))return "Offline";
  return origin==="live"?"Live request":"Source mode unknown";
}
function sourceSummary(d,origin){
  if(!d)return "Source status will appear with a report.";
  const parts=[];
  if(isSample(d,origin))parts.push("Illustrative sample; no live source checks.");
  else if(d.available===false)parts.push(decisionText(d.notice||"Live analysis unavailable."));
  else{
    const sources=d.sources_consulted||{};
    const entries=Object.entries(sources);
    if(entries.length)parts.push(entries.map(([name,ok])=>`${name.toUpperCase()}: ${ok===true&&(name!=="courtlistener"||d.litigation?.available!==false)&&(name!=="ofac"||Number(d.sanctions?.list_size)>0)?"responded":"unavailable"}`).join("; "));
    else parts.push("Source coverage not reported.");
    const mocked=Object.entries(d.optional_sources||{}).filter(([,s])=>s?.mocked).map(([name])=>name);
    if(mocked.length)parts.push(`Placeholder sources: ${mocked.join(", ")}.`);
  }
  const generator=d.generated_by||d.agent_summary?.generated_by;
  if(generator)parts.push(`Report: ${decisionText(generator)}.`);
  return parts.join(" ");
}
function updateWorkspace(){
  const strategy=MODE==="strategy"&&STEP===1;
  const d=strategy?STRAT:STEP===2||STEP===3?DATA:null;
  const origin=strategy?STRAT_ORIGIN:DATA_ORIGIN;
  const title=strategy?"Strategy board":STEP===1?"Entity screening":STEP===2?(DATA?.supplier?.name||"Investigation"):STEP===3?"Entity relationships":"API & MCP";
  const subtitle=strategy?(STRAT?.question||"Strategic decision analysis"):STEP===1?"Third-party risk investigations":STEP===2?"Evidence, adverse media and risk assessment":STEP===3?(DATA?.supplier?.name||"Relationship graph"):"Brahma integrations";
  if($("workspaceTitle"))$("workspaceTitle").textContent=title;
  if($("workspaceSubtitle"))$("workspaceSubtitle").textContent=subtitle;
  if($("sampleBadge"))$("sampleBadge").textContent=provenance(d,origin);
  if($("sourceHealth")){
    const summary=sourceSummary(d,origin),deterministic=/deterministic/i.test(String(d?.generated_by||d?.agent_summary?.generated_by||""));
    const unavailable=(summary.match(/unavailable/gi)||[]).length;
    $("sourceHealth").textContent=SERVICE_STATUS;
    $("sourceHealth").title=`${SERVICE_STATUS}. ${!d?"External source availability is reported per investigation.":summary}`;
    $("sourceHealth").dataset.state=SERVICE_STATUS==="Service ready"?"ready":SERVICE_STATUS==="Checking service"?"pending":"unavailable";
    if(d&&$("sampleBadge"))$("sampleBadge").title=`${unavailable?"Coverage gaps reported. ":""}${deterministic?"Deterministic report. ":""}${summary}`;
  }
  if($("downloadReport")){
    $("downloadReport").disabled=!DATA||strategy;
    $("downloadReport").title=strategy?"Investigation download is available in entity screening":DATA?`Download investigation JSON: ${DATA.supplier.name}${isSample(DATA,DATA_ORIGIN)?" (sample)":""}`:"Load an investigation to download JSON";
  }
  document.title=`${title} | Brahma`;
}
function downloadReport(){
  if(MODE==="strategy"&&STEP===1){status("stratStatus","Open the entity investigation to download its JSON report.");return;}
  if(!DATA){status("status","Load an investigation before downloading a report.");return;}
  let url;
  try{
    const report={application:"Brahma",exported_at:new Date().toISOString(),sample:isSample(DATA,DATA_ORIGIN),provenance:provenance(DATA,DATA_ORIGIN),data:DATA};
    url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;
    link.download=`brahma-${report.sample?"sample-":""}${String(DATA.supplier.name).replace(/[^a-z0-9_-]+/gi,"-").slice(0,70)||"report"}.json`;
    document.body.appendChild(link);link.click();link.remove();
    status("status","JSON report download requested"+(report.sample?" (sample data).":"."));
  }catch{status("status","The report could not be downloaded. Please retry.",true);}
  finally{if(url)setTimeout(()=>URL.revokeObjectURL(url),10000);}
}

/* intake */
function setType(t){TYPE=t;
  $("tOrg").classList.toggle("on",t==="organization");
  $("tInd").classList.toggle("on",t==="individual");
  $("tOrg").setAttribute("aria-pressed",String(t==="organization"));
  $("tInd").setAttribute("aria-pressed",String(t==="individual"));
  $("wrapDob").style.display=t==="individual"?"":"none";
  $("lblName").innerHTML=(t==="individual"?"Full name":"Legal name")+' <span class="dim">(required)</span>';
  $("f_name").placeholder=t==="individual"?"Jane Q Smith":"ABC Manufacturing Ltd";}

async function loadEntities(){
  const ticket=beginRequest("entities");
  try{
    const d=await requestJSON(ticket,"/api/v1/demo/subjects",{},30000);
    if(!isCurrent(ticket))return;
    if(!Array.isArray(d.subjects))throw new Error("Invalid entity list");
    SUBJECTS_LIST=d.subjects.filter(s=>s&&typeof s.id==="string"&&typeof s.name==="string");
    $("hStatEnt").textContent=SUBJECTS_LIST.length;
    renderEntityList();renderEntityRail();
  }catch(e){if(isCurrent(ticket))$("entList").innerHTML='<span class="no">Sample entities unavailable. </span><button type="button" onclick="loadEntities()">Retry</button>';}
  finally{finishRequest(ticket);}
}
function filterEntities(f){ENT_FILTER=f;
  document.querySelectorAll(".subseg button").forEach(b=>b.classList.toggle("on",b.dataset.f===f));
  renderEntityList();}
function matchEntity(s,q){
  if(!q)return true;q=q.toLowerCase();
  return s.name.toLowerCase().includes(q)||(s.tagline||"").toLowerCase().includes(q);
}
function renderEntityList(){
  const q=($("entSearch")?.value||"").trim();
  const rows=SUBJECTS_LIST.filter(s=>(ENT_FILTER==="all"||s.entity_type===ENT_FILTER)&&matchEntity(s,q));
  $("entList").innerHTML=rows.length?rows.map(s=>`
    <button type="button" class="${s.id===CURRENT_ID?"on":""}" onclick="loadDemo(${jsArg(s.id)})" title="${esc(s.tagline)}">
      <span>${esc(s.name)}</span><span class="en">${esc(s.article_count)}</span></button>`).join("")
    : `<div class="no">${q?`No sample cases match "${esc(q)}". Use a live investigation above.`:"No sample cases available."}</div>`;
  const types=ENT_FILTER==="all"?["organization","individual"]:[ENT_FILTER];
  $("entitySearchActions").innerHTML=q?`<p>Investigate <strong>${esc(q)}</strong> using live sources</p>
    ${types.map(type=>`<button type="button" class="ghost" onclick="startEntitySearch('${type}')">${type==="individual"?"Search person":"Search company"}<span aria-hidden="true"> →</span></button>`).join("")}
    <small>Queries external sources. Source availability varies.</small>`:"";
}
function startEntitySearch(type){
  const name=$("entSearch").value.trim();
  if(!name||!["organization","individual"].includes(type))return;
  cancelRequest("screen");
  const sameSubject=TYPE===type&&$("f_name").value.trim().toLowerCase()===name.toLowerCase();
  if(!sameSubject){
    for(const id of ["f_aliases","f_dob","f_reg","f_country","f_city","f_website","f_address"])$(id).value="";
  }
  setType(type);$("f_name").value=name;$("f_name").removeAttribute("aria-invalid");
  $("run").disabled=false;
  $("f_name").focus();
  return runInvestigation();
}
function renderEntityRail(){
  const q=($("railSearch")?.value||"").trim().toLowerCase();
  const rows=SUBJECTS_LIST.filter(s=>!q||s.name.toLowerCase().includes(q)||(s.tagline||"").toLowerCase().includes(q));
  $("entRail").innerHTML=rows.length?rows.map(s=>`
    <button type="button" class="${s.id===CURRENT_ID?"on":""}" onclick="loadDemo(${jsArg(s.id)})">
      <span>${esc(s.name)}</span><span class="en">${esc(s.article_count)}</span></button>`).join("")
    : '<div class="no">No match.</div>';
  if(!SUBJECTS_LIST.length)$("entRail").innerHTML='<span class="dim" style="font-size:12px">Live investigation</span>';
}
async function loadDemo(id){
  const ticket=beginRequest("screen");
  $("run").disabled=false;
  status("status","Loading sample entity...");
  status("evidenceStatus","Loading sample entity...");
  try{
    const data=validateInvestigation(await requestJSON(ticket,"/api/v1/demo/investigate/"+encodeURIComponent(id),{},60000));
    if(!isCurrent(ticket))return;
    DATA=data;CURRENT_ID=id;DATA_ORIGIN="sample";
    afterData("Loaded sample: "+DATA.supplier.name+" ("+DATA.adverse_media.length+" articles)");
  }catch(e){if(isCurrent(ticket)){status("status",e.message,true);status("evidenceStatus",e.message,true);}}
  finally{finishRequest(ticket);}
}
function normalizeInvestigationIdentifier(){
  if(TYPE!=="organization"||$("f_reg").value.trim())return;
  const aliases=$("f_aliases").value.split(",").map(s=>s.trim()).filter(Boolean);
  const index=aliases.findIndex(value=>/^[A-Z0-9]{18}[0-9]{2}$/i.test(value));
  if(index<0)return;
  $("f_reg").value=aliases[index].toUpperCase();aliases.splice(index,1);
  $("f_aliases").value=aliases.join(", ");
}
function cancelInvestigation(){
  cancelRequest("screen");$("run").disabled=false;$("cancelInvestigation").hidden=true;
  status("status","Investigation cancelled. You can edit the details and retry.");
}
async function runInvestigation(){
  const name=$("f_name").value.trim();
  if(!name){$("status").textContent="Enter a name to screen.";return;}
  normalizeInvestigationIdentifier();
  const ticket=beginRequest("screen");
  $("cancelInvestigation").hidden=false;
  $("run").disabled=true;$("status").className="status";
  $("status").textContent="Querying OFAC, SEC EDGAR, GLEIF, GDELT and CourtListener...";
  const t0=performance.now();
  const progress=setInterval(()=>{
    if(!isCurrent(ticket))return;
    const seconds=Math.floor((performance.now()-t0)/1000);
    status("status",seconds<60?`Checking live sources… ${seconds}s elapsed. Some sources can take about a minute.`:`Waiting for the report… ${seconds}s elapsed. You can cancel and retry.`);
  },1000);
  try{
    const data=validateInvestigation(await requestJSON(ticket,"/api/v1/supplier/investigate",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({name,entity_type:TYPE,
        country:$("f_country").value.trim()||null,city:$("f_city").value.trim()||null,
        address:$("f_address").value.trim()||null,website:$("f_website").value.trim()||null,
        date_of_birth:TYPE==="individual"?($("f_dob").value.trim()||null):null,
        registration_number:$("f_reg").value.trim()||null,
        aliases:$("f_aliases").value.split(",").map(s=>s.trim()).filter(Boolean)})}));
    if(!isCurrent(ticket))return;
    DATA=data;CURRENT_ID=null;DATA_ORIGIN="live";
    afterData(`Received report in ${((performance.now()-t0)/1000).toFixed(1)}s. ${provenance(DATA,DATA_ORIGIN)}; review source coverage.`);
    if(!Object.values(data.sources_consulted||{}).some(Boolean)){
      status("evidenceStatus","No live sources responded. This report cannot verify the entity or provide a completed risk check. Check access to the data sources, then retry.",true);
    }
  }catch(e){if(isCurrent(ticket))status("status",e.message,true);}
  finally{clearInterval(progress);if(isCurrent(ticket)){$("run").disabled=false;$("cancelInvestigation").hidden=true;}finishRequest(ticket);}
}
function afterData(msg){
  cancelRequest("insight");
  F={cats:new Set(),bias:new Set(),terms:new Set(),severe:false};SELECTED=null;
  $("sevChk").checked=false;$("onlyFlagged").checked=false;
  $("s2").disabled=false;$("s3").disabled=false;
  $("s2").removeAttribute("title");$("s3").removeAttribute("title");
  status("status",msg);
  status("evidenceStatus","");
  renderEntityList();renderEntityRail();renderDashboard();go(2);refreshIcons();
}
function go(step){
  if(![1,2,3,4].includes(step))return;
  if((step===2||step===3)&&!DATA)return;
  STEP=step;
  [1,2,3,4].forEach(i=>{$("view"+i).classList.toggle("on",i===step);
    $("s"+i).classList.toggle("active",i===step);$("s"+i).classList.toggle("done",i<step&&i<4);
    if(i===step)$("s"+i).setAttribute("aria-current","page");else $("s"+i).removeAttribute("aria-current");});
  if(step===3)setGraph(GRAPH);
  else if(typeof window.cancelAnimationFrame==="function"){window.cancelAnimationFrame(Graph.raf);Graph.raf=null;}
  if(step===4)renderConnectors();
  updateWorkspace();refreshIcons();
  window.scrollTo({top:0,behavior:window.matchMedia?.("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});
}
function setMode(mode){
  if(!["screen","strategy"].includes(mode))return;
  MODE=mode;
  document.querySelectorAll(".modeseg button").forEach(b=>{const selected=b.dataset.mode===mode;b.classList.toggle("on",selected);b.setAttribute("aria-pressed",String(selected));});
  $("modeStrategy").classList.toggle("on",mode==="strategy");
  $("modeScreen").classList.toggle("on",mode==="screen");
  if(STEP!==1)go(1);
  if(mode==="strategy")initStrategy();
  updateWorkspace();refreshIcons();
}
function newScreening(){$("cancelInvestigation").hidden=true;cancelRequest("screen");$("run").disabled=false;status("status","");status("evidenceStatus","");setMode("screen");go(1);}

/* strategy board */
const SEAT_ICONS={
  market:'<path d="M4 20V11M9 20V5M14 20v-8M19 20V8"/>',
  finance:'<path d="M12 3v18M8 7h6a3 3 0 0 1 0 6H8.5a3 3 0 0 0 0 6H16"/>',
  tech:'<rect x="3.5" y="4.5" width="17" height="12" rx="1.5"/><path d="M8 20h8M12 16.5V20"/>',
  competition:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.4"/><path d="M12 4v3M12 17v3M4 12h3M17 12h3"/>',
  legal:'<path d="M12 3v18M6 20h12M5 7h14M8 3.5L5 7M8 3.5L19 7M5 7l-2.5 5a2.6 2.6 0 0 0 5 0zM19 7l-2.5 5a2.6 2.6 0 0 0 5 0z"/>',
};
let STRAT=null,STRAT_SORT={key:"risk_score",dir:-1},MISSION_TIMERS=[];
function decColor(d){return d==="GO"?"var(--low)":d==="NO-GO"?"var(--critical)":"var(--medium)";}
function decClass(d){return d==="GO"?"vd-go":d==="NO-GO"?"vd-nogo":"vd-more";}
function decLabel(d){return d==="GO"?"GO":d==="NO-GO"?"NO-GO":"REVIEW";}
function riskClass(l){const key=String(l||"").toLowerCase();return "rk-"+(["low","medium","high","critical"].includes(key)?key:"unknown");}
function voteClass(v){v=String(v||"").toUpperCase();
  return v==="GO"?"vb-go":v.startsWith("NO")?"vb-nogo":v.includes("CONDITIONAL")?"vb-cond":"vb-more";}

const CREW_ROLES=[
  {key:"__lead",label:"Decision chair",always:true},
  {key:"Market",label:"Market Intelligence"},
  {key:"Finance",label:"Financial Systems"},
  {key:"Technology",label:"Engineering"},
  {key:"Competition",label:"Competitive analysis"},
  {key:"Legal",label:"Legal Operations"},
];
function seatByKey(seats,key){return (seats||[]).find(s=>s.seat===key);}
function buildTimeline(strat){
  const seats=strat.seats||[],v=strat.verdict||{},atks=strat.attacks||[],
    ea=strat.evidence_audit||{},votes=strat.board_vote||[];
  const mkt=seatByKey(seats,"Market"),fin=seatByKey(seats,"Finance");
  const dealBreakers=atks.filter(a=>a.deal_breaker).length;
  const goVotes=votes.filter(x=>String(x.vote).toUpperCase()==="GO").length;
  return [
    {t:"01",head:"Market assessment",
      detail:(mkt&&mkt.staffed)?mkt.headline:"Market seat not included in this decision."},
    {t:"02",head:"Financial assessment",
      detail:(fin&&fin.staffed)?fin.headline:"Finance seat not included in this decision."},
    {t:"03",head:`Adversarial review ${atks.length?"included":"not recorded"}`,
      detail:atks.length
        ?`${atks.length} attack(s) filed${dealBreakers?`, ${dealBreakers} marked DEAL BREAKER`:""}.`+
          (strat.kill_shot?` Critical objection: "${strat.kill_shot}"`:"")
        :"No adversarial attacks filed."},
    {t:"04",head:isSample(strat,STRAT_ORIGIN)?"Illustrative sample audit":"Model self-assessment",
      detail:`Not independently verified. ${ea.verified_pct||0}% classified as verified, ${ea.unsupported_pct||0}% as unsupported by ${isSample(strat,STRAT_ORIGIN)?"the sample audit":"the model"}.`+
        (ea.integrity_note?` ${ea.integrity_note}`:"")},
    {t:"05",head:"Decision panel",
      detail:votes.length?`${goVotes} of ${votes.length} board members voted GO.`:"No board vote recorded."},
    {t:"06",head:decLabel(v.decision),detail:String(v.chair_summary||"").trim(),final:true},
  ];
}

async function initStrategy(){
  if($("sampChips").dataset.loaded||REQUESTS.has("strategySamples"))return;
  const ticket=beginRequest("strategySamples");
  try{
    const d=await requestJSON(ticket,"/api/v1/strategy/samples",{},30000);
    if(!isCurrent(ticket))return;
    if(!Array.isArray(d.samples))throw new Error("Invalid strategy samples");
    $("sampChips").innerHTML=`<span class="dim" style="font-size:11.5px;align-self:center;margin-right:2px">Sample decisions:</span>`+
      d.samples.map(s=>`<button type="button" class="sampchip" onclick="loadStratSample(${jsArg(s.id)})">
        <b>${esc(s.question)}</b>
        <span class="cd" style="color:${decColor(s.decision)}">${decLabel(s.decision)} &middot; ${esc(s.confidence)}% &middot; Sample</span>
      </button>`).join("");
    $("sampChips").dataset.loaded="true";
  }catch(e){if(isCurrent(ticket))$("sampChips").innerHTML='<span class="dim">Strategy samples unavailable. </span><button type="button" onclick="initStrategy()">Retry</button>';}
  finally{finishRequest(ticket);}
}
async function loadStratSample(id){
  const ticket=beginRequest("strategy");$("stratRun").disabled=false;
  $("stratStatus").className="status";$("stratStatus").textContent="Loading sample decision...";
  try{
    const data=validateStrategy(await requestJSON(ticket,"/api/v1/strategy/sample/"+encodeURIComponent(id),{},30000));
    if(!isCurrent(ticket))return;
    STRAT=data;STRAT_ORIGIN="sample";$("stratQ").value=STRAT.question;status("stratStatus","Sample / offline scenario loaded.");renderStrategy();
  }catch(e){if(isCurrent(ticket))status("stratStatus",e.message,true);}
  finally{finishRequest(ticket);}
}
async function runStrategy(){
  const q=$("stratQ").value.trim();
  if(q.length<6){$("stratStatus").className="status err";$("stratStatus").textContent="Enter a decision question.";return;}
  const ticket=beginRequest("strategy");
  $("stratRun").disabled=true;$("stratStatus").className="status";
  $("stratStatus").textContent="Requesting decision analysis...";
  try{
    const data=validateStrategy(await requestJSON(ticket,"/api/v1/strategy/decide",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q})}));
    if(!isCurrent(ticket))return;
    STRAT=data;STRAT_ORIGIN="live";status("stratStatus",provenance(STRAT,STRAT_ORIGIN));renderStrategy();
  }catch(e){if(isCurrent(ticket))status("stratStatus",e.message,true);}
  finally{if(isCurrent(ticket))$("stratRun").disabled=false;finishRequest(ticket);}
}
function sortSeats(value){
  const [key,direction]=String(value).split(":");
  if(!["seat","risk_score","conviction"].includes(key))return;
  STRAT_SORT={key,dir:direction==="asc"?1:-1};
  $("reportSpecialists").innerHTML=renderSpecialists(STRAT.seats||[]);
}
function renderStrategy(){
  updateWorkspace();
  const el=$("stratResult");if(!STRAT){el.innerHTML="";return;}
  MISSION_TIMERS.forEach(clearTimeout);MISSION_TIMERS=[];
  if(STRAT.available===false){
    el.innerHTML=`<div class="stratnotice">${esc(decisionText(STRAT.notice||"Live board unavailable."))}</div>`;
    return;
  }
  const v=STRAT.verdict,seats=STRAT.seats||[];
  const conf=v.confidence||0;
  const crewReady=k=>{const s=seatByKey(seats,k);return s&&s.staffed;};
  const stages=buildTimeline(STRAT);

  // Display the completed response, not a simulated agent-progress replay.
  let html=`<div class="missionhead">
    <div class="misstop">
      <div><span class="misslabel">Decision</span><div class="missq">${esc(STRAT.question||"")}</div><div class="dim">${isSample(STRAT,STRAT_ORIGIN)?"Illustrative sample / offline":"Model self-assessment / not independently verified"}</div></div>
      <span class="missstatus ${v.decision==="GO"?"ms-launch":v.decision==="NO-GO"?"ms-scrub":"ms-hold"}" id="missStatus">${decLabel(v.decision)}</span>
    </div>
    <div class="crew">
      ${CREW_ROLES.map(r=>`<span class="crewitem${(r.always||crewReady(r.key))?" ready":" bench"}">
        <span class="ck">${(r.always||crewReady(r.key))?"&#10003;":""}</span>${esc(r.label)}</span>`).join("")}
    </div>
    <div class="missstats">
      <span>Confidence<b>${esc(conf)}%</b></span>
      <span>Strategic fit<b class="rk-fit">${esc(v.strategic_fit)}/10</b></span>
      <span>Financial<b class="${riskClass(v.financial_risk)}">${esc(v.financial_risk)}</b></span>
      <span>Regulatory<b class="${riskClass(v.regulatory_risk)}">${esc(v.regulatory_risk)}</b></span>
      <span>Execution<b class="${riskClass(v.execution_risk)}">${esc(v.execution_risk)}</b></span>
    </div>
    <div class="timeline" id="missTimeline">
      ${stages.map((s,i)=>`<div class="tstage shown${s.final?" final":""}" data-i="${i}">
        <div class="tmark">${esc(s.t)}</div>
        <div class="tcontent">
          <div class="thead">${esc(s.head)}</div>
          ${s.detail?`<div class="tdetail">${esc(s.detail)}</div>`:""}
        </div></div>`).join("")}
    </div>
  </div>`;

  html+=renderAnalysisReport();

  html+=`<p class="missfoot">Analysis by ${esc(decisionText(STRAT.generated_by||"-"))}.</p>`;
  el.innerHTML=html;
  refreshIcons();

}
function setReportTab(key,focus=false){
  if(!["overview","team","evidence","challenges"].includes(key))return;
  const report=$("analysisReport");
  report.querySelectorAll('[role="tab"]').forEach(tab=>{
    const active=tab.dataset.reportTab===key;
    tab.setAttribute("aria-selected",String(active));tab.tabIndex=active?0:-1;
    if(active&&focus)tab.focus();
  });
  report.querySelectorAll('[role="tabpanel"]').forEach(panel=>panel.hidden=panel.dataset.reportPanel!==key);
}
function reportTabKey(event){
  const keys=["overview","team","evidence","challenges"];
  const index=keys.indexOf(event.target.dataset.reportTab);
  if(index<0)return;
  let next;
  if(event.key==="ArrowRight")next=(index+1)%keys.length;
  else if(event.key==="ArrowLeft")next=(index+keys.length-1)%keys.length;
  else if(event.key==="Home")next=0;
  else if(event.key==="End")next=keys.length-1;
  else return;
  event.preventDefault();setReportTab(keys[next],true);
}
function reportList(items,empty){
  return items.length?`<ol class="report-list">${items.map(c=>`<li>${esc(c)}</li>`).join("")}</ol>`:
    `<p class="report-empty">${esc(empty)}</p>`;
}
function renderAnalysisReport(){
  const v=STRAT.verdict||{},seats=STRAT.seats||[],votes=STRAT.board_vote||[];
  const attacks=[...(STRAT.attacks||[])].sort((a,b)=>(Number(b.severity)||0)-(Number(a.severity)||0));
  const claims=STRAT.evidence_audit?.audited_claims||[];
  const sample=isSample(STRAT,STRAT_ORIGIN);
  const tabs=[["overview","Overview"],["team","Team views"],["evidence","Evidence"],["challenges","Challenges"]];
  return `<details open class="analysis-report" id="analysisReport">
    <summary class="report-heading"><span><span class="report-title">Analysis report</span>
      <span class="report-meta">${seats.filter(s=>s.staffed).length} specialists &middot; ${claims.length} audited claims &middot; ${attacks.length} challenges</span></span>
      <i data-lucide="chevron-down" aria-hidden="true"></i></summary>
    <div class="report-tabs" role="tablist" aria-label="Analysis report sections" onkeydown="reportTabKey(event)">
      ${tabs.map(([key,label],i)=>`<button type="button" role="tab" id="report-tab-${key}" data-report-tab="${key}"
        aria-controls="report-panel-${key}" aria-selected="${i===0}" tabindex="${i===0?0:-1}"
        onclick="setReportTab('${key}')">${label}</button>`).join("")}
    </div>
    <section class="report-panel" role="tabpanel" id="report-panel-overview" data-report-panel="overview" aria-labelledby="report-tab-overview" tabindex="0">
      <div class="report-conclusion">
        <div class="report-section-heading"><h3>Bottom line</h3><span class="votebadge ${decClass(v.decision)}">${decLabel(v.decision)}</span></div>
        <p class="report-lead">${esc(v.chair_summary||"No decision rationale recorded.")}</p>
      </div>
      <section class="report-section"><h3>What's at stake</h3><p class="report-prose">${esc(STRAT.stakes||"No stakes recorded.")}</p></section>
      <div class="report-columns">
        <section class="report-section"><div class="report-section-heading"><h3>Success criteria</h3><span class="report-period">24 months</span></div>
          ${reportList(STRAT.success_criteria||[],"No success criteria recorded.")}</section>
        <section class="report-section"><h3>Conditions to proceed</h3>
          ${reportList(STRAT.conditions||[],"No conditions recorded.")}</section>
      </div>
      ${STRAT.would_change_mind?`<section class="report-reconsider"><h3>What would change the decision</h3><p>${esc(STRAT.would_change_mind)}</p></section>`:""}
    </section>
    <section class="report-panel" role="tabpanel" id="report-panel-team" data-report-panel="team" aria-labelledby="report-tab-team" tabindex="0" hidden>
      <div class="report-section-heading"><h3>Board perspectives</h3><span class="report-period">${votes.filter(m=>String(m.vote).toUpperCase()==="GO").length} of ${votes.length} voted GO</span></div>
      <div class="report-votes">${votes.length?votes.map(m=>`<article class="report-vote">
        <div class="report-section-heading"><h4>${esc(m.member)}</h4><span class="votebadge ${voteClass(m.vote)}">${esc(m.vote)}</span></div>
        <p>${esc(m.rationale||"No rationale recorded.")}</p></article>`).join(""):'<p class="report-empty">No board votes recorded.</p>'}</div>
      <section class="report-section">
        <div class="report-section-heading report-specialist-heading"><h3>Specialist assessments</h3>
          <label class="report-sort">Sort by <select aria-label="Sort specialist assessments" onchange="sortSeats(this.value)">
            ${[["risk_score:desc","Highest risk"],["risk_score:asc","Lowest risk"],["conviction:desc","Highest conviction"],["conviction:asc","Lowest conviction"],["seat:asc","Name A to Z"],["seat:desc","Name Z to A"]].map(([value,label])=>
              `<option value="${value}"${value===STRAT_SORT.key+":"+(STRAT_SORT.dir>0?"asc":"desc")?" selected":""}>${label}</option>`).join("")}
          </select></label></div>
        <div id="reportSpecialists">${renderSpecialists(seats)}</div>
      </section>
    </section>
    <section class="report-panel" role="tabpanel" id="report-panel-evidence" data-report-panel="evidence" aria-labelledby="report-tab-evidence" tabindex="0" hidden>
      <h3>${sample?"Illustrative sample audit":"Evidence audit"}</h3>${renderAudit(STRAT.evidence_audit)}
    </section>
    <section class="report-panel" role="tabpanel" id="report-panel-challenges" data-report-panel="challenges" aria-labelledby="report-tab-challenges" tabindex="0" hidden>
      ${STRAT.kill_shot?`<div class="report-objection"><h3>Critical objection</h3><p>${esc(STRAT.kill_shot)}</p></div>`:""}
      <div class="report-section-heading"><h3>Adversarial review</h3><span class="report-period">Highest severity first</span></div>
      <div class="report-challenges">${attacks.length?attacks.map((a,i)=>`<article class="report-challenge">
        <div class="report-challenge-index">${String(i+1).padStart(2,"0")}</div>
        <div><div class="report-claim-meta"><span>${esc(a.target_seat)}</span><span class="report-severity">Severity ${esc(a.severity??"-")}/10</span>${a.deal_breaker?'<span class="db-flag">Deal breaker</span>':""}</div>
          <h4>${esc(a.claim_attacked||"No claim recorded.")}</h4><p>${esc(a.why_it_breaks||"No challenge rationale recorded.")}</p></div>
        </article>`).join(""):'<p class="report-empty">No challenges recorded.</p>'}</div>
    </section>
  </details>`;
}
function renderSpecialists(seats){
  const sorted=[...seats].sort((a,b)=>{
    if(a.staffed!==b.staffed)return Number(Boolean(b.staffed))-Number(Boolean(a.staffed));
    const k=STRAT_SORT.key;
    return STRAT_SORT.dir*(k==="seat"?String(a.seat).localeCompare(String(b.seat)):(Number(a[k])||0)-(Number(b[k])||0));
  });
  if(!sorted.length)return '<p class="report-empty">No specialist assessments recorded.</p>';
  return sorted.map(s=>`<article class="report-specialist${s.staffed?"":" report-benched"}">
    <div class="report-specialist-identity"><h4>${esc(s.seat)}</h4><p>${esc(s.role||"")}</p><span class="${s.staffed?"chip-staffed":"chip-bench"}">${s.staffed?"Staffed":"Benched"}</span></div>
    <div class="report-specialist-body">${s.staffed?`<p class="report-specialist-headline">${esc(s.headline||"No assessment recorded.")}</p>
      <div class="report-scores">${[["risk_score","Risk","risk"],["conviction","Conviction","conviction"]].map(([key,label,kind])=>`<div class="report-score">
        <div><span>${label}</span><strong>${esc(s[key]??"-")}<small>/10</small></strong></div>
        <span class="report-score-track ${kind}" aria-hidden="true"><i data-motion-bar style="width:${pct(s[key],10)*10}%"></i></span></div>`).join("")}</div>
      ${(s.risks||[]).length?`<h5>Key risks</h5><ul class="report-risks">${s.risks.map(r=>`<li>${esc(r)}</li>`).join("")}</ul>`:""}`:
      `<p class="report-empty">${esc(s.bench_reason||"Not staffed.")}</p>`}</div></article>`).join("");
}
function renderAudit(a){
  if(!a)return '<p class="report-empty">No evidence audit recorded.</p>';
  const sample=isSample(STRAT,STRAT_ORIGIN);
  const seg=[["verified_pct","au-verified",sample?"Sample-rated verified":"Model-rated verified"],["weak_pct","au-weak","Weak"],
    ["speculation_pct","au-spec","Speculation"],["unsupported_pct","au-unsup","Unsupported"]];
  const bar=seg.map(([k,c])=>{const p=pct(a[k]);return p>0?`<div class="${c}" style="flex:${p}"></div>`:"";}).join("");
  const key=seg.map(([k,c,l])=>`<div class="report-audit-stat"><span><i class="${c}"></i>${l}</span><strong>${esc(a[k]??0)}<small>%</small></strong></div>`).join("");
  const vClass={VERIFIED:"vb-go",WEAK:"vb-more",SPECULATION:"vb-cond",UNSUPPORTED:"vb-nogo"};
  return `<div class="report-audit-notice"><i data-lucide="info" aria-hidden="true"></i><p><strong>${sample?"Illustrative sample":"Model self-assessment"}. Not independently verified.</strong>
      These ratings are not evidence of retrieved or verified citations.</p></div>
    <div class="report-audit-stats">${key}</div><div class="report-audit-bar" aria-hidden="true">${bar}</div>
    ${a.integrity_note?`<p class="report-integrity"><strong>Integrity note</strong> ${esc(a.integrity_note)}</p>`:""}
    <div class="report-section-heading"><h3>Claim-by-claim review</h3><span class="report-period">${(a.audited_claims||[]).length} claims</span></div>
    <div class="report-claims">${(a.audited_claims||[]).length?a.audited_claims.map(c=>`<article class="report-claim">
      <div class="report-claim-meta"><span class="votebadge ${own(vClass,c.verdict)||"vb-more"}">${esc(c.verdict==="VERIFIED"?(sample?"Sample-rated verified":"Model-rated verified"):c.verdict)}</span><span>${esc(c.seat)}</span></div>
      <h4>${esc(c.claim)}</h4>${c.reason?`<p>${esc(c.reason)}</p>`:""}</article>`).join(""):'<p class="report-empty">No audited claims recorded.</p>'}</div>`;
}

/* dashboard */
let EVIDENCE_TERMS_EXPANDED=false;
function evidenceScore(value,max=1){
  if(value==null||typeof value==="boolean"||String(value).trim()===""||!Number.isFinite(Number(value)))return null;
  return Math.max(0,Math.min(max,Number(value)));
}
function renderDashboard(){
  const d=DATA,s=d.supplier,r=d.risk,ms=d.media_summary;
  const level=["low","medium","high","critical"].includes(r.level)?r.level:"neutral";
  const sanctionsAvailable=d.sanctions.available!==false&&d.sources_consulted?.ofac!==false&&Number(d.sanctions.list_size)>0;
  const mediaUnavailable=ms.available===false||d.sources_consulted?.gdelt===false;
  const litigationUnavailable=d.litigation.available===false||d.sources_consulted?.courtlistener===false;
  const coverage=r.coverage_assessment||{},missing=coverage.missing_sources||[];
  const sample=isSample(d,DATA_ORIGIN);
  const catCount=Object.fromEntries(CATEGORIES.map(c=>[c.key,0]));
  (ms.categories||[]).forEach(c=>catCount[c.key]=c.count);

  EVIDENCE_TERMS_EXPANDED=false;
  $("biasTable").innerHTML="";
  setEvidenceTab("media");
  $("rTab").textContent=s.name;
  $("caseMeta").innerHTML=`<span class="case-meta-item">${esc(s.country||"Country not reported")}</span>
    <span class="case-meta-item">${esc(s.entity_type||"Type not reported")}</span>
    <span class="case-meta-item">Identity: ${esc(s.status||"Not resolved")}</span>
    <span class="case-mode">${esc(provenance(d,DATA_ORIGIN))}</span>`;
  if(!sample&&d.query?.name&&d.query.name!==s.name){
    $("caseMeta").innerHTML+=`<span class="case-meta-item">Searched as ${esc(d.query.name)} · ${esc(s.primary_source||"Source")} legal name shown</span>`;
  }
  $("riskbox").classList.add("risk-overview");
  $("riskbox").innerHTML=`
    <div class="risk-score-block"><span class="risk-label">Overall risk</span>
      <div><strong class="risk-score-number">${num(evidenceScore(r.score,100))}</strong><span class="risk-score-denom">/100</span>
      <span class="badge b-${level}">${esc(String(r.level||"unknown").toUpperCase())}</span></div></div>
    <dl class="risk-facts">
      <div><dt>Identity</dt><dd>${esc(s.status||"Not resolved")} &middot; ${fixed(s.identity_confidence)}</dd></div>
      <div><dt>Sanctions</dt><dd>${d.sanctions.match?"MATCH":sanctionsAvailable?"No match":"Unavailable / not screened"}</dd></div>
      <div><dt>Adverse media</dt><dd>${mediaUnavailable?"Unavailable / not screened":`${num(ms.total??d.adverse_media.length)} articles`}</dd></div>
      <div><dt>Litigation</dt><dd>${litigationUnavailable?"Unavailable / not screened":`${(d.litigation.cases||[]).length} ${(d.litigation.cases||[]).length===1?"docket":"dockets"}`}</dd></div>
    </dl>
    <div class="risk-recommendation"><strong>Recommendation</strong> <p>${esc(d.agent_summary?.recommendation||"Not provided")}</p>
    ${sample||missing.length||coverage.complete===false||!sanctionsAvailable?`<div class="risk-coverage">
    ${sample?'<p class="risk-caveat">Illustrative sample; no live source checks.</p>':""}
    ${missing.length?`<p class="risk-caveat"><strong>Missing required sources:</strong> ${missing.map(name=>esc(String(name).toUpperCase())).join(", ")}. Screening incomplete; not a clearance.</p>`:
      coverage.complete===false?'<p class="risk-caveat">Required screening incomplete; not a clearance.</p>':""}
    ${!sanctionsAvailable?'<p class="risk-caveat">Sanctions unavailable / not screened; not a clearance.</p>':""}</div>`:""}</div>`;

  // left category filters
  $("catFilters").innerHTML=CATEGORIES.map(c=>`
    <label class="fitem" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}" data-cat="${c.key}" onclick="toggleCat('${c.key}')">
      <span class="swatch" style="background:${c.color}"></span>
      <span class="lab">${esc(c.label)}</span>
      <span class="cnt">${esc(catCount[c.key]||0)}</span></label>`).join("");

  const bc=ms.bias||{};
  const biasDefs=[["Polarized",bc.polarized,"polarized"],["Mixed",bc.mixed,"mixed"],["Factual",bc.factual,"factual"]];
  $("biasFilters").innerHTML=biasDefs.map(([label,n,cls])=>`
    <label class="fitem" role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}" data-bias="${label}" onclick="toggleBias('${label}')">
      <span class="badge b-${cls}" style="padding:1px 8px">${label}</span>
      <span class="lab"></span><span class="cnt">${esc(n??0)}</span></label>`).join("");

  // sanctions / contribs / litigation / ownership / report
  const sc=d.sanctions;
  $("sanctions").innerHTML=sc.match?`
    <div><span class="badge b-critical">${esc(sc.match_strength||"match").toUpperCase()}</span>
      <b style="margin-left:8px">${esc(sc.matched_entity?.name)}</b></div>
    <div class="kv" style="margin-top:11px">
      <div>Program</div><div>${esc(sc.matched_entity?.program||"-")}</div>
      <div>Similarity</div><div>${esc(sc.confidence)}</div>
      ${sc.dob_check?`<div>DOB check</div><div><span class="badge ${sc.dob_check.status==="match"?"b-critical":sc.dob_check.status==="conflict"?"b-low":"b-neutral"}">${esc(sc.dob_check.status)}</span> <span class="dim">${esc(sc.dob_check.note)}</span></div>`:""}
      ${sc.matched_entity?.remarks?`<div>Remarks</div><div class="dim">${esc(String(sc.matched_entity.remarks).slice(0,240))}</div>`:""}</div>`:!sanctionsAvailable?`
    <div><span class="badge b-neutral">UNAVAILABLE</span> <span class="dim">${esc(sc.note||"No usable sanctions list was returned. This is not a clearance.")}</span></div>`:`
    <div><span class="badge b-low">NO MATCH</span>
      <span class="dim" style="margin-left:8px">screened against ${num(sc.list_size)} SDN names</span></div>`;

  $("contribs").innerHTML=r.contributions.length?`<table>
    <tr><th>Signal</th><th>Points</th><th>Source</th></tr>
    ${r.contributions.map(c=>`<tr><td>${esc(String(c.category).replace(/_/g," "))}</td><td>+${esc(c.points)}</td>
      <td class="dim">${esc(c.source)}</td></tr>`).join("")}</table>`:`<div class="empty">No risk signals fired.</div>`;

  const cases=d.litigation.cases||[];
  $("litigation").innerHTML=cases.length?`<table>
    <tr><th>Case</th><th>Court</th><th>Filed</th></tr>
    ${cases.slice(0,10).map(c=>`<tr><td>${externalLink(c.url,esc(c.case))}</td>
      <td class="dim">${esc(c.court)}</td><td class="dim">${esc(c.date)}</td></tr>`).join("")}</table>`:`<div class="empty">${esc(litigationUnavailable?"Unavailable / not screened. "+(d.litigation.note||""):d.litigation.note||"No matching dockets.")}</div>`;

  $("ownership").innerHTML=d.ownership.length?`<table>
    <tr><th>Name</th><th>Role</th><th>Conf.</th></tr>
    ${d.ownership.slice(0,12).map(o=>`<tr><td>${esc(o.name)}</td><td class="dim">${esc(o.role)}</td>
      <td>${fixed(o.confidence)}</td></tr>`).join("")}</table>`:`<div class="empty">No ownership records.</div>`;

  const a=d.agent_summary;
  $("report").innerHTML=`<div class="dim" style="font-size:11.5px;margin-bottom:8px">${esc(a.generated_by||"")}</div>
    <p style="margin:0 0 12px">${esc(a.summary)}</p>
    <div class="kv"><div>Sanctions</div><div>${esc(a.sanctions_assessment)}</div>
      <div>Litigation</div><div>${esc(a.litigation_assessment)}</div>
      <div>Adverse media</div><div>${esc(a.adverse_media_assessment)}</div>
      <div>Recommendation</div><div><b>${esc(a.recommendation)}</b></div></div>`;

  $("raw").textContent=JSON.stringify(d,null,2);
  refresh();
}
function refresh(){syncFilterUI();renderResults();renderBreadcrumb();renderBias();renderCloud();renderCoverage();}
function setEvidenceTab(key,focus=false){
  if(!["media","signals","records"].includes(key))return;
  const view=$("view2");if(!view)return;
  $("breadcrumb").hidden=key==="records";
  view.querySelectorAll("[data-evidence-tab]").forEach(tab=>{
    const active=tab.dataset.evidenceTab===key;
    tab.setAttribute("aria-selected",String(active));tab.tabIndex=active?0:-1;
    if(active&&focus)tab.focus();
  });
  view.querySelectorAll("[data-evidence-panel]").forEach(panel=>panel.hidden=panel.dataset.evidencePanel!==key);
}
function evidenceTabKey(event){
  const keys=["media","signals","records"];
  const target=event.target.closest?.("[data-evidence-tab]")||event.target;
  const index=keys.indexOf(target.dataset?.evidenceTab);
  if(index<0)return;
  let next;
  if(event.key==="ArrowRight")next=(index+1)%keys.length;
  else if(event.key==="ArrowLeft")next=(index+keys.length-1)%keys.length;
  else if(event.key==="Home")next=0;
  else if(event.key==="End")next=keys.length-1;
  else return;
  event.preventDefault();setEvidenceTab(keys[next],true);
}
function toggleEvidenceFilters(){
  const view=$("view2"),button=$("filterToggle");if(!view||!button)return;
  const open=view.classList.toggle("filters-open");button.setAttribute("aria-expanded",String(open));
}

function toggleCat(k){F.cats.has(k)?F.cats.delete(k):F.cats.add(k);refresh();}
function toggleBias(l){F.bias.has(l)?F.bias.delete(l):F.bias.add(l);refresh();}
function toggleTerm(t){F.terms.has(t)?F.terms.delete(t):F.terms.add(t);refresh();}
function toggleSevere(){F.severe=$("sevChk").checked;refresh();}
function clearFilters(){F={cats:new Set(),bias:new Set(),terms:new Set(),severe:false};
  $("sevChk").checked=false;refresh();}

function renderBreadcrumb(){
  const chips=[];
  F.cats.forEach(k=>{const c=CATEGORIES.find(x=>x.key===k);
    chips.push(`<button type="button" class="fchip" onclick="toggleCat(${jsArg(k)})"><b>Category</b> ${esc(c?c.label:k)} &times;</button>`);});
  F.bias.forEach(l=>chips.push(`<button type="button" class="fchip" onclick="toggleBias(${jsArg(l)})"><b>Objectivity</b> ${esc(l)} &times;</button>`));
  F.terms.forEach(t=>chips.push(`<button type="button" class="fchip" onclick="toggleTerm(${jsArg(t)})"><b>Term</b> ${esc(t)} &times;</button>`));
  if(F.severe)chips.push(`<button type="button" class="fchip" onclick="document.getElementById('sevChk').checked=false;toggleSevere()"><b>Severity</b> high only &times;</button>`);
  $("breadcrumb").innerHTML=chips.length
    ? `Filtered evidence: ${chips.join(" ")} <button type="button" class="fchip" onclick="clearFilters()">Clear all</button>`
    : `<span class="dim">All evidence</span>`;
}

/* Facets retain alternatives while term selections narrow the evidence. */
function renderCloud(){
  const rows=filtered(true),freq=new Map(),cloud=$("cloud");
  const focusTerm=document.activeElement?.dataset?.term;
  const focusExpander=document.activeElement?.classList?.contains("term-expand");
  rows.forEach(a=>{const seen=new Set();(a.risk_terms||[]).forEach(t=>{
    const name=String(t.term??"");if(!name)return;
    if(!freq.has(name))freq.set(name,{term:name,count:0,peak:0});
    const entry=freq.get(name);
    if(!seen.has(name)){entry.count++;seen.add(name);}
    entry.peak=Math.max(entry.peak,evidenceScore(t.score)||0);
  });});
  const terms=[...freq.values()].sort((a,b)=>b.count-a.count||b.peak-a.peak||a.term.localeCompare(b.term));
  $("cloudCount").textContent=`${terms.length} terms`;
  if(!terms.length){cloud.innerHTML='<p class="empty">No risk terms in this evidence set.</p>';return;}
  const max=terms[0].count,shown=EVIDENCE_TERMS_EXPANDED?terms:terms.slice(0,8);
  cloud.innerHTML=`<div class="term-list" id="termRows">${shown.map(t=>{
    const on=F.terms.has(t.term)?" on":"";
    return `<button type="button" class="term-row${on}" data-term="${esc(t.term)}" aria-label="${esc(t.term)}: ${t.count} ${t.count===1?"article":"articles"}" aria-pressed="${F.terms.has(t.term)}" onclick="toggleTerm(${jsArg(t.term)})">
      <span class="term-label">${esc(t.term)}</span><span class="term-count">${t.count}</span>
      <span class="term-track" aria-hidden="true"><i data-motion-bar style="width:${Math.round(t.count/max*100)}%"></i></span></button>`;
  }).join("")}</div>${terms.length>8?`<button type="button" class="term-expand term-more" aria-expanded="${EVIDENCE_TERMS_EXPANDED}" aria-controls="termRows" onclick="toggleTermsExpanded()">${EVIDENCE_TERMS_EXPANDED?"Show fewer terms":`Show all ${terms.length} terms`}</button>`:""}<p class="term-scope">Article counts across ${rows.length} articles${F.terms.size?"; excludes term selections":""}.</p>`;
  if(focusTerm!==undefined)[...cloud.querySelectorAll("[data-term]")].find(el=>el.dataset.term===focusTerm)?.focus();
  else if(focusExpander)cloud.querySelector(".term-expand")?.focus();
}
function toggleTermsExpanded(){EVIDENCE_TERMS_EXPANDED=!EVIDENCE_TERMS_EXPANDED;renderCloud();}

function renderCoverage(){
  const rows=filtered(),all=DATA?.adverse_media||[];
  const active=F.cats.size||F.bias.size||F.terms.size||F.severe;
  const scope=active?"Filtered evidence":"All evidence",counts=new Map(),months=new Map();
  let undated=0;
  rows.forEach(a=>{
    new Set([...(a.category_keys||[]),...(a.categories||[]).map(c=>c.key)]).forEach(key=>counts.set(key,(counts.get(key)||0)+1));
    const month=String(a.date||"").slice(0,7);
    if(/^\d{4}-(0[1-9]|1[0-2])$/.test(month))months.set(month,(months.get(month)||0)+1);
    else undated++;
  });
  const scopeLabel=$("catbars").closest?.(".signal-section")?.querySelector(".section-scope");
  if(scopeLabel)scopeLabel.textContent=scope;
  $("catbars").innerHTML=`<p class="coverage-scope coverage-note">${scope} &middot; ${active?`${rows.length} of ${all.length}`:rows.length} articles</p>`+
    CATEGORIES.map(c=>{const n=counts.get(c.key)||0;return `<div class="coverage-row">
      <span class="coverage-name">${esc(c.label)}</span><span class="coverage-count" aria-label="${n} of ${rows.length} articles" title="${n} of ${rows.length} articles">${n}</span>
      <span class="coverage-track" aria-hidden="true"><i data-motion-bar style="width:${rows.length?Math.round(n/rows.length*100):0}%"></i></span></div>`;}).join("")+
    '<p class="coverage-note">Articles may appear in more than one category.</p>';
  const timeline=[...months].sort(([a],[b])=>a.localeCompare(b)),max=Math.max(1,...months.values());
  const years=timeline.length?[...new Set([timeline[0][0].slice(0,4),timeline[timeline.length-1][0].slice(0,4)])].join(" - "):"";
  $("timeline").innerHTML=`<h3 class="timeline-heading volume-heading">Articles by month <span>${years}</span></h3>${timeline.length?`<ol class="volume-chart" aria-label="Monthly article counts: ${scope}">${timeline.map(([month,count])=>{
    const date=new Date(`${month}-01T00:00:00Z`);
    const label=date.toLocaleDateString("en-US",{month:"long",year:"numeric",timeZone:"UTC"});
    const short=date.toLocaleDateString("en-US",{month:"short",timeZone:"UTC"});
    return `<li aria-label="${esc(label)}: ${count} ${count===1?"article":"articles"}"><span class="volume-count">${count}</span>
      <span class="volume-bar" aria-hidden="true"><i style="height:${Math.round(count/max*100)}%"></i></span>
      <time class="volume-label" datetime="${month}" title="${esc(label)}" aria-label="${esc(label)}">${esc(short)}</time></li>`;
  }).join("")}</ol>`:'<p class="empty">No dated articles.</p>'}${undated?`<p class="dim">${undated} ${undated===1?"article":"articles"} with no valid month.</p>`:""}`;
}
function syncFilterUI(){
  document.querySelectorAll("#catFilters .fitem").forEach(el=>{el.classList.toggle("on",F.cats.has(el.dataset.cat));el.setAttribute("aria-pressed",String(F.cats.has(el.dataset.cat)));});
  document.querySelectorAll("#biasFilters .fitem").forEach(el=>{el.classList.toggle("on",F.bias.has(el.dataset.bias));el.setAttribute("aria-pressed",String(F.bias.has(el.dataset.bias)));});
  $("sevItem")?.classList.toggle("on",F.severe);
}
function filtered(ignoreTerms=false){
  return (DATA?.adverse_media||[]).filter(a=>{
    if(F.severe&&(evidenceScore(a.severity)??0)<0.8)return false;
    if(F.cats.size&&!(a.category_keys||[]).some(k=>F.cats.has(k)))return false;
    if(F.bias.size&&!F.bias.has((a.bias||{}).label))return false;
    if(!ignoreTerms&&F.terms.size&&!(a.risk_terms||[]).some(t=>F.terms.has(t.term)))return false;
    return true;});
}
function catTag(c){return `<span class="tag" style="background:${own(CAT_COLOR,c.key)||'#64748b'}">${esc(String(c.label).split(" ")[0])}</span>`;}
function biasBadge(b){const cls=String(b?.label||"").toLowerCase();return `<span class="badge b-${["polarized","mixed","factual"].includes(cls)?cls:'neutral'}">${esc(b?b.label:"-")}</span>`;}

// Highlight the cosine-matched risk-term spans inside an article's text.
function highlightTerms(text,a){
  const raw=String(text||"");
  const spans=[...new Set((a.risk_terms||[]).map(t=>t.matched_span).filter(Boolean))]
    .sort((x,y)=>y.length-x.length);
  if(!spans.length)return esc(raw);
  const re=new RegExp("\\b("+spans.map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")).join("|")+")\\b","gi");
  let result="",last=0;
  for(const match of raw.matchAll(re)){result+=esc(raw.slice(last,match.index))+`<mark class="hl">${esc(match[0])}</mark>`;last=match.index+match[0].length;}
  return result+esc(raw.slice(last));
}
function renderResults(){
  const all=DATA.adverse_media||[];
  let rows=filtered();
  const sort=$("sortSel").value;
  if(sort==="date")rows=[...rows].sort((a,b)=>(b.date||"").localeCompare(a.date||""));
  else if(sort==="bias")rows=[...rows].sort((a,b)=>((b.bias||{}).score||0)-((a.bias||{}).score||0));
  else rows=[...rows].sort((a,b)=>b.severity-a.severity);
  const unavailable=DATA.media_summary?.available===false||DATA.sources_consulted?.gdelt===false;
  const windowNote=DATA.media_summary?.lookback_months?` · Last ${num(DATA.media_summary.lookback_months)} months`:"";
  $("mediaCount").textContent=unavailable&&!all.length?"Live media source unavailable":`Showing ${rows.length} of ${all.length} matches${windowNote}`;
  if(!rows.length){
    const message=all.length?"No articles match the selected filters.":unavailable
      ?"The live news source did not respond. Media coverage is unavailable; this is not a clean screening result."
      :"No adverse headlines were returned for this name. This limited news search is not a complete media review or a clean risk finding.";
    $("resultsList").innerHTML=`<tr><td colspan="6" class="empty-cell">${message}</td></tr>`;return;
  }
  $("resultsList").innerHTML=rows.map((a,i)=>{
    const title=externalLink(a.url,highlightTerms(a.title,a));
    const cats=(a.categories||[]).slice(0,2).map(catTag).join(" ");
    const severity=evidenceScore(a.severity);
    return `<tr>
      <td class="rnum">${i+1}</td>
      <td class="rtitle-cell">${title}<div class="article-source"><span>${esc(a.source||"Source not reported")}</span><span>${esc(a.date||"Undated")}</span><span>Objectivity ${biasBadge(a.bias)}</span></div>${cats?`<div class="tags">${cats}</div>`:""}</td>
      <td class="dim">${esc(a.source)}</td>
      <td class="dim">${esc(a.date)}</td>
      <td>${biasBadge(a.bias)}</td>
      <td><span class="severity-value">${severity===null?"Not scored":severity.toFixed(2)}</span><span class="sevbar" aria-hidden="true"><i data-motion-bar style="width:${Math.round((severity||0)*100)}%"></i></span></td>
    </tr>`;
  }).join("");
}

function annotate(sent){
  if(!sent.spans||!sent.spans.length)return esc(sent.text);
  let html="",last=0;
  for(const sp of [...sent.spans].sort((a,b)=>a.start-b.start)){
    if(sp.start<last)continue;
    html+=esc(sent.text.slice(last,sp.start));
    html+=`<mark class="t-${String(sp.type).replace(/[^a-z0-9_-]/gi,"")}" title="${esc(String(sp.type).replace(/_/g," "))}">${esc(sent.text.slice(sp.start,sp.end))}</mark>`;
    last=sp.end;}
  html+=esc(sent.text.slice(last));return html;
}
function renderBias(){
  const onlyFlagged=$("onlyFlagged").checked;
  const rows=filtered().filter(a=>a.bias&&a.bias.total_sentences>0);
  const flaggedArticles=rows.filter(a=>(a.bias.sentences||[]).some(s=>s.biased)).length;
  $("biasCount").textContent=`${rows.length} articles · ${flaggedArticles} with language flags`;
  rows.sort((a,b)=>b.bias.score-a.bias.score);
  const container=$("biasTable"),open=new Set([...container.querySelectorAll("details[open]")].map(el=>el.id));
  container.innerHTML='<p class="bias-note dim">Language signals, not a factual accuracy check.</p>'+(rows.length?rows.map(a=>{
    const b=a.bias,sentences=b.sentences||[],flagged=sentences.filter(s=>s.biased);
    const shown=onlyFlagged?flagged:sentences,id="bd"+DATA.adverse_media.indexOf(a);
    return `<details class="bias-item" id="${id}"${open.has(id)?" open":""}>
      <summary><span class="bias-title">${esc(a.title)}</span><span class="bias-meta">
        <span class="bias-source">${esc(a.source||"Source not reported")}</span>
        <span class="bias-objectivity">Objectivity ${biasBadge(b)}</span>
        <span class="bias-score">Bias score ${fixed(evidenceScore(b.score))}</span>
        <span class="bias-flag-count">${flagged.length}/${esc(b.total_sentences)} flagged lines</span></span><i class="bias-chevron" data-lucide="chevron-down" aria-hidden="true"></i></summary>
      <div class="bias-body"><div class="bias-types">${(b.bias_types||[]).map(t=>`<span class="flagchip">${esc(t.label)} &middot; ${esc(t.count)}</span>`).join("")}</div>
        <div class="bias-sentences">${shown.length?shown.map(s=>`<p class="sent ${s.biased?"flag":"factual"}">${annotate(s)}</p>`).join(""):'<p class="dim">No flagged lines.</p>'}</div>
      </div></details>`;
  }).join(""):'<p class="empty">No articles with analyzable content.</p>');
  refreshIcons();
}
function toggleDetail(i){const el=$("bd"+i);if(el)el.open=!el.open;}

/* ---- interactive force-directed graph engine (vanilla SVG, no deps) ---- */
const SVGNS="http://www.w3.org/2000/svg";
const TYPE_STYLE={
  query:{c:"#164a7b",r:16,l:"Search subject"},selected:{c:"#185634",r:15,l:"Selected identity"},
  match:{c:"#527c78",r:12,l:"Above threshold"},rejected:{c:"#94a3a0",r:9,l:"Rejected candidate"},
  entity:{c:"#164a7b",r:17,l:"Subject entity"},
  person:{c:"#185634",r:12,l:"Person"},holding:{c:"#185634",r:14,l:"Holding / parent"},
  parent:{c:"#185634",r:13,l:"Corporate parent"},company:{c:"#488b82",r:13,l:"External firm"},
  trust:{c:"#164a7b",r:12,l:"Trust / family office"}};
const nstyle=t=>own(TYPE_STYLE,t)||{c:"#94a3a0",r:10,l:t};
const el=(tag,a)=>{const e=document.createElementNS(SVGNS,tag);for(const k in a)e.setAttribute(k,a[k]);return e;};

// Per-node-type glyph (building / person / house / magnifier ...) drawn inside
// each node circle so the graph reads at a glance instead of as plain dots.
// Authored in a 24x24 box centered on (12,12); buildIcon() scales it to fit.
const TYPE_ICON={
  query:[["circle",{cx:10,cy:10,r:6}],["line",{x1:14.2,y1:14.2,x2:19,y2:19}]],
  selected:[["path",{d:"M8 12.5l2.7 2.7L16.5 9"}]],
  match:[["rect",{x:5,y:9,width:14,height:11}],["path",{d:"M9 9V6a3 3 0 0 1 6 0v3"}]],
  rejected:[["path",{d:"M9 9l6 6M15 9l-6 6"}]],
  entity:[["rect",{x:5,y:5,width:14,height:16}],["path",{d:"M9 21v-5h6v5"}],["path",{d:"M8 9h2M14 9h2M8 13h2M14 13h2"}]],
  person:[["circle",{cx:12,cy:8.5,r:3.2}],["path",{d:"M5.5 20c1-4 4-6 6.5-6s5.5 2 6.5 6"}]],
  holding:[["path",{d:"M4 10l8-5 8 5"}],["path",{d:"M5 10v9M9 10v9M15 10v9M19 10v9"}],["path",{d:"M4 19h16"}]],
  parent:[["path",{d:"M4 10l8-5 8 5"}],["path",{d:"M5 10v9M9 10v9M15 10v9M19 10v9"}],["path",{d:"M4 19h16"}]],
  company:[["rect",{x:5,y:5,width:14,height:16}],["path",{d:"M9 21v-5h6v5"}],["path",{d:"M8 9h2M14 9h2M8 13h2M14 13h2"}]],
  trust:[["path",{d:"M4 11l8-6 8 6"}],["path",{d:"M6 10v10h12V10"}],["path",{d:"M10 20v-5h4v5"}]],
};
function buildIcon(type){
  const defs=own(TYPE_ICON,type)||TYPE_ICON.company;
  const g=el("g",{fill:"none",stroke:"#fff","stroke-width":2.3,"stroke-linecap":"round",
    "stroke-linejoin":"round","pointer-events":"none"});
  defs.forEach(([tag,attrs])=>g.appendChild(el(tag,attrs)));
  return g;
}
function iconTransform(n,st){const s=(st.r*1.45)/24;return{s,t:`translate(${n.x-12*s} ${n.y-12*s}) scale(${s})`};}

const Graph={
  svg:null,vp:null,eLayer:null,nLayer:null,bg:null,edgeLabel:null,
  nodes:[],edges:[],byId:Object.create(null),kind:null,expandable:false,
  k:1,tx:0,ty:0,alpha:0,raf:null,drag:null,pan:null,hoverId:null,selNode:null,selEdge:null,W:900,H:520,

  init(){this.svg=$("svg");
    this.svg.addEventListener("wheel",e=>this.onWheel(e),{passive:false});
    window.addEventListener("mousemove",e=>this.onMove(e));
    window.addEventListener("mouseup",()=>this.onUp());
    if(typeof ResizeObserver!=="undefined"){
      this.resizeObserver=new ResizeObserver(()=>{
        if(!this.svg.clientWidth||!this.nodes.length)return;
        if(Math.abs(this.svg.clientWidth-this.W)>1||Math.abs(this.svg.clientHeight-this.H)>1){this.sizeCanvas();this.fit();}
      });
      this.resizeObserver.observe(this.svg);
    }},

  sizeCanvas(){const oldW=this.W,oldH=this.H;
    this.W=Math.max(280,this.svg.clientWidth||900);this.H=Math.max(280,this.svg.clientHeight||520);
    this.nodes.forEach(n=>{n.x*=this.W/oldW;n.y*=this.H/oldH;if(n.fx!=null){n.fx*=this.W/oldW;n.fy*=this.H/oldH;}});
    this.svg.setAttribute("viewBox",`0 0 ${this.W} ${this.H}`);},
  nodeStyle(n){const st=nstyle(n.type),factor=1/Math.max(0.75,Math.min(1,this.k));return {...st,r:Math.max(14,st.r)*factor};},
  fit(){if(!this.nodes.length)return;
    const minX=Math.min(...this.nodes.map(n=>n.x-Math.max(24,Math.min(24,n.label.length)*3.7))),
      maxX=Math.max(...this.nodes.map(n=>n.x+Math.max(24,Math.min(24,n.label.length)*3.7))),
      minY=Math.min(...this.nodes.map(n=>n.y-26)),maxY=Math.max(...this.nodes.map(n=>n.y+52));
    this.k=Math.max(0.75,Math.min(2,(this.W-44)/Math.max(1,maxX-minX),(this.H-94)/Math.max(1,maxY-minY)));
    this.tx=this.W/2-(minX+maxX)/2*this.k;
    this.ty=(this.H-44)/2-(minY+maxY)/2*this.k;
    this.applyTransform();},

  isCenter(n){return n.center===true||n.id==="query"||n.id==="entity";},
  edgeColor(){return "#b6c0cf";},
  edgeW(e){return 1+(e.confidence||e.weight||0.3)*2.4;},

  load(kind){this.kind=kind;this.selNode=this.selEdge=this.hoverId=null;
    cancelRequest("insight");cancelAnimationFrame(this.raf);this.raf=null;this.drag=this.pan=null;this.vp=null;this.edgeLabel=null;
    this.svg.classList.remove("panning");
    this.sizeCanvas();
    this.expandable=kind==="network"&&!!(DATA&&DATA.graph&&DATA.graph.network_full);
    const g=(DATA&&DATA.graph&&DATA.graph[kind])||{nodes:[],edges:[]};
    this.k=1;this.tx=0;this.ty=0;
    this.nodes=(g.nodes||[]).map(n=>({...n,label:String(n.label??n.id)}));
    this.byId=Object.assign(Object.create(null),Object.fromEntries(this.nodes.map(n=>[n.id,n])));
    this.edges=(g.edges||[]).filter(e=>this.byId[e.source]&&this.byId[e.target]).map(e=>({...e}));
    const cx=this.W/2,cy=this.H/2,R=Math.min(this.W,this.H)*0.32,N=this.nodes.length;
    this.nodes.forEach((nd,i)=>{const c=this.isCenter(nd);const ang=(i/Math.max(1,N))*Math.PI*2;
      nd.x=c?cx:cx+Math.cos(ang)*R;nd.y=c?cy:cy+Math.sin(ang)*R;nd.vx=0;nd.vy=0;});
    if(!this.nodes.length){this.showEmpty();this.applyTransform();return;}
    this.renderDom();this.updateLegend();
    // Settle before fitting so the first frame uses the actual network bounds.
    this.alpha=1;for(let i=0;i<90;i++)this.tick(false);
    this.fit();this.reheat(0.05);
    $("side").innerHTML=`<div class="empty">Select a node or connection to inspect it.</div>`;},

  showEmpty(){this.svg.innerHTML=`<text x="${this.W/2}" y="${this.H/2}" text-anchor="middle" fill="#8b94a3" font-size="13">No graph data.</text>`;
    $("side").innerHTML=`<div class="empty">Nothing to inspect.</div>`;$("legend").innerHTML="";},

  renderDom(){const svg=this.svg;svg.innerHTML="";
    this.bg=el("rect",{x:-6000,y:-6000,width:12000,height:12000,fill:"transparent"});
    this.bg.addEventListener("mousedown",e=>this.panStart(e));svg.appendChild(this.bg);
    this.vp=el("g",{});svg.appendChild(this.vp);
    this.eLayer=el("g",{});this.vp.appendChild(this.eLayer);
    this.nLayer=el("g",{});this.vp.appendChild(this.nLayer);
    this.edges.forEach((e,i)=>{const a=this.byId[e.source],b=this.byId[e.target];if(!a||!b)return;
      const line=el("line",{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:this.edgeColor(e),"stroke-width":this.edgeW(e),class:"gedge pickable"});
      line.addEventListener("click",ev=>{ev.stopPropagation();this.selectEdge(i);});
      line.addEventListener("mouseenter",()=>{this.hoverId=null;this.hoverEdge=i;});
      e._line=line;this.eLayer.appendChild(line);});
    this.edgeLabel=el("text",{class:"edge-label","text-anchor":"middle"});this.eLayer.appendChild(this.edgeLabel);
    this.nodes.forEach(n=>{const st=this.nodeStyle(n);
      const g=el("g",{class:"gnode"+(n.pinned?" pinned":""),tabindex:0,role:"button","aria-label":n.label});
      const c=el("circle",{r:st.r,fill:st.c,stroke:"#fff","stroke-width":2,cx:n.x,cy:n.y});
      const icon=buildIcon(n.type);
      const {s,t:tf}=iconTransform(n,st);icon.setAttribute("transform",tf);
      const lab=n.label.length>24?n.label.slice(0,23)+"…":n.label;
      const t=el("text",{"text-anchor":"middle",x:n.x,y:n.y+st.r+13});t.textContent=lab;
      g.appendChild(c);g.appendChild(icon);g.appendChild(t);
      g.addEventListener("mousedown",e=>this.dragStart(n,e));
      g.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();this.selectNode(n.id);}});
      g.addEventListener("dblclick",e=>{e.stopPropagation();this.unpin(n);});
      g.addEventListener("mouseenter",()=>{this.hoverId=n.id;this.applyEmphasis();});
      g.addEventListener("mouseleave",()=>{this.hoverId=null;this.applyEmphasis();});
      n._g=g;n._c=c;n._icon=icon;n._iconScale=s;n._t=t;this.nLayer.appendChild(g);});
    this.applyTransform();this.updateStrokes();this.applyEmphasis();},

  tick(schedule=true){const nodes=this.nodes,cx=this.W/2,cy=this.H/2;
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j];
      let dx=b.x-a.x,dy=b.y-a.y,d2=dx*dx+dy*dy||0.01,d=Math.sqrt(d2),f=17000/d2,fx=f*dx/d,fy=f*dy/d;
      a.vx-=fx;a.vy-=fy;b.vx+=fx;b.vy+=fy;}
    this.edges.forEach(e=>{const a=this.byId[e.source],b=this.byId[e.target];if(!a||!b)return;
      const dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||0.01,tgt=185-62*(e.confidence||e.weight||0.5),
      f=(d-tgt)*0.035,fx=f*dx/d,fy=f*dy/d;a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;});
    nodes.forEach(nd=>{if(nd.fx!=null){nd.x=nd.fx;nd.y=nd.fy;nd.vx=0;nd.vy=0;return;}
      const gc=this.isCenter(nd)?0.06:0.006,gcy=this.isCenter(nd)?0.06:0.008;
      nd.vx+=(cx-nd.x)*gc;nd.vy+=(cy-nd.y)*gcy;
      nd.x+=Math.max(-16,Math.min(16,nd.vx));nd.y+=Math.max(-16,Math.min(16,nd.vy));
      nd.vx*=0.82;nd.vy*=0.82;nd.x=Math.max(40,Math.min(this.W-40,nd.x));nd.y=Math.max(28,Math.min(this.H-28,nd.y));});
    this.updatePositions();this.alpha*=0.98;
    if(schedule){if(!document.hidden && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches && (this.alpha>0.03||this.drag))this.raf=requestAnimationFrame(()=>this.tick());else this.raf=null;}},

  reheat(a){
    this.alpha=Math.max(this.alpha,a);
    if(document.hidden)return;
    if(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches){
      cancelAnimationFrame(this.raf);this.raf=null;
      for(let i=0;i<90;i++)this.tick(false);
      this.alpha=0;return;
    }
    if(!this.raf)this.raf=requestAnimationFrame(()=>this.tick());
  },

  updatePositions(){this.nodes.forEach(n=>{const st=this.nodeStyle(n);
    n._c.setAttribute("r",st.r);
    n._c.setAttribute("cx",n.x);n._c.setAttribute("cy",n.y);
    const s=st.r*1.45/24;n._iconScale=s;n._icon.setAttribute("transform",`translate(${n.x-12*s} ${n.y-12*s}) scale(${s})`);
    n._t.style.fontSize=`${13/Math.max(0.75,Math.min(1,this.k))}px`;
    n._t.setAttribute("x",n.x);n._t.setAttribute("y",n.y+st.r+13);});
    this.edges.forEach(e=>{const a=this.byId[e.source],b=this.byId[e.target];if(!a||!b)return;
      e._line.setAttribute("x1",a.x);e._line.setAttribute("y1",a.y);e._line.setAttribute("x2",b.x);e._line.setAttribute("y2",b.y);});
    if(this.selEdge!=null){const e=this.edges[this.selEdge],a=this.byId[e.source],b=this.byId[e.target];
      this.edgeLabel.setAttribute("x",(a.x+b.x)/2);this.edgeLabel.setAttribute("y",(a.y+b.y)/2-5);
      this.edgeLabel.textContent=e.relationship||e.label||"";}else if(this.edgeLabel)this.edgeLabel.textContent="";},

  updateStrokes(){this.nodes.forEach(n=>{const sel=n.id===this.selNode;
    n._c.setAttribute("stroke",sel?"#141a24":"#fff");n._c.setAttribute("stroke-width",sel?3:2);});},

  applyEmphasis(){const focus=this.hoverId||this.selNode;
    this.nodes.forEach(n=>n._g&&n._g.classList.remove("dim-el"));
    this.edges.forEach(e=>e._line&&e._line.classList.remove("dim-el"));
    if(this.selEdge!=null){const e=this.edges[this.selEdge],keep=new Set([e.source,e.target]);
      this.nodes.forEach(n=>{if(!keep.has(n.id))n._g.classList.add("dim-el");});
      this.edges.forEach((x,i)=>{if(i!==this.selEdge)x._line.classList.add("dim-el");});return;}
    if(focus){const keep=new Set([focus]);
      this.edges.forEach(e=>{if(e.source===focus||e.target===focus){keep.add(e.source);keep.add(e.target);}});
      this.nodes.forEach(n=>{if(!keep.has(n.id))n._g.classList.add("dim-el");});
      this.edges.forEach(e=>{if(!(e.source===focus||e.target===focus))e._line.classList.add("dim-el");});}},

  updateLegend(){const types=[...new Set(this.nodes.map(n=>n.type))];
    $("legend").innerHTML=types.map(t=>{const st=nstyle(t);return `<span><i style="background:${st.c}"></i>${esc(st.l||t)}</span>`;}).join("");},

  applyTransform(){this.vp&&this.vp.setAttribute("transform",`translate(${this.tx} ${this.ty}) scale(${this.k})`);
    if(this.vp)this.updatePositions();
    $("zoomTip").textContent=Math.round(this.k*100)+"%";},
  worldPt(e){const p=this.svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(this.vp.getScreenCTM().inverse());},
  viewBoxPt(e){const p=this.svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(this.svg.getScreenCTM().inverse());},
  zoomAround(px,py,f){const gx=(px-this.tx)/this.k,gy=(py-this.ty)/this.k;
    this.k=Math.max(0.3,Math.min(3.5,this.k*f));this.tx=px-gx*this.k;this.ty=py-gy*this.k;this.applyTransform();},
  onWheel(e){if(!this.vp)return;e.preventDefault();const p=this.viewBoxPt(e);this.zoomAround(p.x,p.y,e.deltaY<0?1.12:0.89);},
  zoomBy(f){this.zoomAround(this.W/2,this.H/2,f);},
  reset(){this.fit();},

  panStart(e){this.pan={p0:this.viewBoxPt(e),tx0:this.tx,ty0:this.ty};this.svg.classList.add("panning");},
  dragStart(n,e){e.stopPropagation();const w=this.worldPt(e);n.fx=w.x;n.fy=w.y;
    this.drag={node:n,moved:false,downX:e.clientX,downY:e.clientY};this.reheat(0.5);},
  onMove(e){if(!this.vp||!this.vp.getScreenCTM())return;if(this.drag){const w=this.worldPt(e);this.drag.node.fx=w.x;this.drag.node.fy=w.y;
      if(Math.hypot(e.clientX-this.drag.downX,e.clientY-this.drag.downY)>4)this.drag.moved=true;this.reheat(0.25);}
    else if(this.pan){const p=this.viewBoxPt(e);this.tx=this.pan.tx0+(p.x-this.pan.p0.x);this.ty=this.pan.ty0+(p.y-this.pan.p0.y);this.applyTransform();}},
  onUp(){if(this.drag){const n=this.drag.node;
      if(!this.drag.moved){n.fx=n.fy=null;this.selectNode(n.id);}
      else{n.pinned=true;n._g.classList.add("pinned");}this.drag=null;}
    if(this.pan){this.pan=null;this.svg.classList.remove("panning");}},
  unpin(n){n.fx=n.fy=null;n.pinned=false;n._g.classList.remove("pinned");this.reheat(0.4);},

  selectNode(id){if(!this.byId[id])return;cancelRequest("insight");this.selEdge=null;this.selNode=id;this.hoverId=null;
    this.updateStrokes();this.applyEmphasis();this.renderNodePanel(this.byId[id]);},
  selectEdge(i){if(!this.edges[i])return;cancelRequest("insight");this.selNode=null;this.selEdge=i;this.hoverId=null;
    this.updateStrokes();this.applyEmphasis();this.renderEdgePanel(i);},

  hasMore(id){if(!this.expandable)return false;const have=new Set(this.nodes.map(n=>n.id));
    return (DATA.graph.network_full.edges||[]).some(e=>(e.source===id&&!have.has(e.target))||(e.target===id&&!have.has(e.source)));},
  expand(id){if(!this.expandable)return;const full=DATA.graph.network_full;const have=new Set(this.nodes.map(n=>n.id));
    const src=this.byId[id];
    if(!src)return;
    full.edges.forEach(e=>{if(e.source!==id&&e.target!==id)return;
      [e.source,e.target].forEach(nid=>{if(!have.has(nid)){const fn=full.nodes.find(x=>x.id===nid);
        if(fn){const nn={...fn,label:String(fn.label??fn.id),x:src.x+(Math.random()*80-40),y:src.y+(Math.random()*80-40),vx:0,vy:0};
          this.nodes.push(nn);this.byId[nid]=nn;have.add(nid);}}});
      if(this.byId[e.source]&&this.byId[e.target]&&!this.edges.some(x=>x.source===e.source&&x.target===e.target))this.edges.push({...e});});
    this.renderDom();this.updateLegend();this.reheat(0.8);this.selectNode(id);
    $("graphHint").textContent=`${this.nodes.length} entities / ${this.edges.length} connections`;},

  renderNodePanel(n){if(!n)return;const st=nstyle(n.type);
    const linked=this.edges.filter(e=>e.source===n.id||e.target===n.id);
    let h=`<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <span style="width:12px;height:12px;border-radius:50%;background:${st.c};display:inline-block"></span>
      <b style="font-size:14px">${esc(n.label)}</b></div>
      <div class="kv"><div>Type</div><div>${esc(st.l||n.type)}</div>
      ${n.detail?`<div>Detail</div><div class="dim">${esc(n.detail)}</div>`:""}
      ${n.source?`<div>Source</div><div>${esc(n.source)}</div>`:""}
      ${n.confidence!=null?`<div>Confidence</div><div>${fixed(n.confidence)}<div class="bar"><i data-motion-bar style="width:${pct(n.confidence*100)}%"></i></div></div>`:""}</div>`;
    if(n.breakdown&&Object.keys(n.breakdown).length){h+=`<div style="margin-top:12px"><h2>Match features</h2><div class="kv">`+
      Object.entries(n.breakdown).map(([k,v])=>`<div>${esc(k)}</div><div>${fixed(v)}<div class="bar"><i data-motion-bar style="width:${pct(v*100)}%"></i></div></div>`).join("")+`</div></div>`;}
    if(linked.length){h+=`<div style="margin-top:12px"><h2>Connections (${linked.length})</h2><div class="neigh">`+
      linked.map(e=>{const other=e.source===n.id?e.target:e.source,on=this.byId[other];
        return `<a role="button" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click()}" onclick="Graph.selectNode(${jsArg(other)})">${esc(on?on.label:other)} <span class="dim">· ${esc(e.relationship||e.label||"")}</span></a>`;}).join("")+`</div></div>`;}
    h+=`<div style="margin-top:6px">`;
    if(this.hasMore(n.id))h+=`<button type="button" class="btn alt" onclick="Graph.expand(${jsArg(n.id)})"><i data-lucide="expand"></i> Expand connections</button> `;
    h+=`<button type="button" class="btn" id="insightBtn" onclick="Graph.runInsight()"><i data-lucide="scan-text"></i> Generate insight</button></div><div id="insightBox" aria-live="polite"></div>`;
    $("side").innerHTML=h;refreshIcons();window.BrahmaMotion?.enter($("side"));},

  renderEdgePanel(i){const e=this.edges[i],s=this.byId[e.source],t=this.byId[e.target];
    $("side").innerHTML=`<h2>Connection</h2>
      <div class="conn"><b>${esc(s.label)}</b><span class="rel">${esc(e.relationship||e.label||"linked")}</span><b>${esc(t.label)}</b></div>
      <div class="kv">${e.confidence!=null?`<div>Confidence</div><div>${(+e.confidence).toFixed(2)}<div class="bar"><i data-motion-bar style="width:${Math.round(e.confidence*100)}%"></i></div></div>`:""}
      ${e.description?`<div>Known facts</div><div class="dim">${esc(e.description)}</div>`:""}</div>
      <button type="button" class="btn" id="insightBtn" onclick="Graph.runInsight()"><i data-lucide="scan-text"></i> Generate connection insight</button>
      <div id="insightBox" aria-live="polite"></div>`;refreshIcons();window.BrahmaMotion?.enter($("side"));},

  buildPayload(){const subj=DATA.supplier&&DATA.supplier.name,rl=DATA.risk&&DATA.risk.level;
    if(this.selEdge!=null){const e=this.edges[this.selEdge],s=this.byId[e.source],t=this.byId[e.target];
      return {kind:"edge",subject:subj,risk_level:rl,source_label:s.label,source_type:s.type,
        target_label:t.label,target_type:t.type,relationship:e.relationship||e.label,
        confidence:e.confidence!=null?+e.confidence:(e.weight!=null?+e.weight:null),description:e.description};}
    if(this.selNode){const n=this.byId[this.selNode];
      return {kind:"node",subject:subj,risk_level:rl,node_label:n.label,node_type:n.type,node_detail:n.detail};}
    return null;},

  async runInsight(){const payload=this.buildPayload();if(!payload)return;
    const btn=$("insightBtn"),box=$("insightBox");if(!box)return;
    const ticket=beginRequest("insight"),sample=isSample(DATA,DATA_ORIGIN);
    if(btn){btn.disabled=true;btn.textContent="Generating...";}
    try{const d=await requestJSON(ticket,"/api/v1/graph/insight",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)},60000);
      if(!isCurrent(ticket)||!box.isConnected)return;
      if(typeof d.insight!=="string")throw new Error("The service returned an incomplete insight. Please retry.");
      box.innerHTML=`<div class="insight"><div class="tag">${/deterministic/i.test(d.generated_by||"")?"Deterministic insight":"Generated insight"}${sample?" / sample context":""}</div>${esc(d.insight)}<div class="src">${esc(d.generated_by||"Generation method not reported")}</div></div>`;
    }catch(err){if(isCurrent(ticket)&&box.isConnected)box.innerHTML=`<div class="insight">${esc(err.message)}</div>`;}
    finally{if(isCurrent(ticket)&&btn?.isConnected){btn.disabled=false;btn.innerHTML='<i data-lucide="scan-text"></i> Generate insight';refreshIcons();}finishRequest(ticket);}},
};

function setGraph(kind){
  if(!DATA||!["resolution","network"].includes(kind))return;
  GRAPH=kind;
  ["resolution","network"].forEach((k,i)=>{const b=$("gt"+i);b.classList.toggle("on",k===kind);b.setAttribute("aria-pressed",String(k===kind));});
  Graph.load(kind);renderGraphDetail();
  window.BrahmaMotion?.enter($("graphDetail"));
  $("graphHint").textContent=kind==="network"
    ? `${Graph.nodes.length} entities / ${Graph.edges.length} connections`
    : `${num(DATA.entity_resolution.candidates_considered)} candidates / ${DATA.entity_resolution.selected?1:0} selected identity`;}

function renderGraphDetail(){
  const d=DATA;
  if(GRAPH==="resolution"){const er=d.entity_resolution;$("detailTitle").textContent="Why this identity was selected";
    const rows=[er.selected,...(er.alternatives||[])].filter(Boolean);
    $("graphDetail").innerHTML=rows.length?`<table><tr><th>Candidate</th><th>Source</th><th>Confidence</th><th>Feature breakdown</th></tr>
      ${rows.map(c=>`<tr><td>${c===er.selected?"<b>":""}${esc(c.name)}${c===er.selected?"</b> <span class='badge b-low'>selected</span>":""}</td>
        <td class="dim">${esc(c.source)}</td>
        <td>${fixed(c.confidence)}<div class="bar"><i data-motion-bar style="width:${pct(c.confidence*100)}%"></i></div></td>
        <td class="dim">${Object.entries(c.confidence_breakdown||{}).map(([k,v])=>`${esc(k)} ${fixed(v)}`).join(" · ")}</td></tr>`).join("")}</table>
      <div class="dim" style="margin-top:9px;font-size:12px">Embeddings: ${esc(er.embedding_backend)} · ${esc(er.candidates_considered)} candidates · threshold ${esc(er.match_threshold)}</div>`:`<div class="empty">No candidates.</div>`;
  }else{$("detailTitle").textContent="Related parties";
    $("graphDetail").innerHTML=d.ownership.length?`<table><tr><th>Name</th><th>Role</th><th>Relationship</th><th>Source</th><th>Conf.</th></tr>
      ${d.ownership.map(o=>`<tr><td>${esc(o.name)}</td><td class="dim">${esc(o.role)}</td>
        <td class="dim">${esc(o.relationship_type)}</td><td class="dim">${esc(o.source)}</td><td>${fixed(o.confidence)}</td></tr>`).join("")}</table>`:`<div class="empty">No related parties.</div>`;
  }
}
/* ---- API & MCP connectors tab ---- */
// Developer navigation shares the report's tab and keyboard behavior.
function setDeveloperTab(key){
  if(!["setup","playground","contract"].includes(key))return;
  document.querySelectorAll("[data-developer-tab]").forEach(button=>{
    const selected=button.dataset.developerTab===key;
    button.setAttribute("aria-selected",String(selected));button.tabIndex=selected?0:-1;
  });
  document.querySelectorAll("[data-developer-panel]").forEach(panel=>{
    panel.hidden=panel.dataset.developerPanel!==key;
  });
}
function developerTabKey(event){
  const tabs=Array.from(event.currentTarget.querySelectorAll('[role="tab"]'));
  const index=tabs.indexOf(event.target);if(index<0)return;
  let next;
  if(event.key==="ArrowRight")next=(index+1)%tabs.length;
  else if(event.key==="ArrowLeft")next=(index+tabs.length-1)%tabs.length;
  else if(event.key==="Home")next=0;
  else if(event.key==="End")next=tabs.length-1;
  else return;
  event.preventDefault();setDeveloperTab(tabs[next].dataset.developerTab);tabs[next].focus();
}
const CONTRACT=[
  ["supplier","Resolved identity, verification status and confidence"],
  ["entity_resolution","Selected candidate, scored alternatives, feature breakdown"],
  ["sanctions","OFAC SDN screening result (+ DOB check for individuals)"],
  ["adverse_media","Tagged negative articles with risk categories, bias and risk terms"],
  ["media_summary","Category counts, bias split, timeline, risk-term frequencies"],
  ["litigation","Federal court dockets"],
  ["ownership","Officers, directors and corporate parents"],
  ["transactions","SEC Form 4 insider transactions"],
  ["graph","Entity-resolution, connection and transaction networks"],
  ["risk","Explainable score, level, and per-signal contributions"],
  ["agent_summary","AI (or deterministic) narrative report with recommendation"],
];
function renderConnectors(){
  const origin=esc(location.origin);
  $("apiCurl").innerHTML=`<button class="cp" onclick="copyCode('apiCurl')">copy</button>`+
    `<span class="c"># One call → one JSON intelligence object</span>\n`+
    `<span class="k">curl</span> -X POST ${origin}/api/v1/supplier/investigate \\\n`+
    `  -H <span class="s">"Content-Type: application/json"</span> \\\n`+
    `  -d <span class="s">'{"name": "Wells Fargo &amp; Company", "country": "United States"}'</span>`;
  $("mcpSnippet").innerHTML=`<button class="cp" onclick="copyCode('mcpSnippet')">copy</button>`+
    `<span class="c"># MCP server tool (Python) - feeds any agentic platform</span>\n`+
    `<span class="k">import</span> httpx\n`+
    `<span class="k">from</span> mcp.server.fastmcp <span class="k">import</span> FastMCP\n\n`+
    `mcp = FastMCP(<span class="s">"Brahma"</span>)\n\n`+
    `<span class="k">@mcp.tool</span>()\n`+
    `<span class="k">async def</span> investigate_supplier(name: str, country: str = <span class="s">""</span>) -> dict:\n`+
    `    <span class="s">"""Investigate a supplier/entity; returns an evidence-backed risk object."""</span>\n`+
    `    <span class="k">async with</span> httpx.AsyncClient() <span class="k">as</span> c:\n`+
    `        r = <span class="k">await</span> c.post(<span class="s">"${origin}/api/v1/supplier/investigate"</span>,\n`+
    `                         json={<span class="s">"name"</span>: name, <span class="s">"country"</span>: country}, timeout=120)\n`+
    `        r.raise_for_status()\n`+
    `        <span class="k">return</span> r.json()`;
  $("mcpSchema").innerHTML=`<button class="cp" onclick="copyCode('mcpSchema')">copy</button>`+
    esc(JSON.stringify({name:"investigate_supplier",description:"Investigate a supplier, company or person for third-party risk. Returns sanctions, adverse media, litigation, ownership graph and an explainable risk score.",input_schema:{type:"object",properties:{name:{type:"string"},country:{type:"string"},entity_type:{type:"string",enum:["organization","individual"]},date_of_birth:{type:"string"}},required:["name"]}},null,2));
  $("contract").innerHTML=`<table><tr><th>Key</th><th>Contains</th></tr>`+
    CONTRACT.map(([k,v])=>`<tr><td><code style="color:var(--accent)">${esc(k)}</code></td><td class="dim">${esc(v)}</td></tr>`).join("")+`</table>`;
  // quick-start step 1
  $("qs1").innerHTML=`<button class="cp" onclick="copyCode('qs1')">copy</button>`+
    `<span class="c"># install and run the wrapper</span>\n`+
    `<span class="k">pip install</span> <span class="s">"mcp[cli]"</span> httpx\n`+
    `BRAHMA_URL=<span class="s">${origin}</span> <span class="k">python</span> mcp_server.py`;
  platformTab("claude");
}
const PLATFORMS={
  claude:{desc:"Run once in your project folder. Claude Code lists it under /mcp and the tool becomes available in chat.",
    code:o=>`<span class="c"># from your project folder</span>\n`+
      `<span class="k">claude</span> mcp add brahma \\\n  --env BRAHMA_URL=<span class="s">${esc(o)}</span> \\\n  -- <span class="k">python</span> mcp_server.py\n\n`+
      `<span class="c"># or commit .mcp.json (shown above) to share it</span>`},
  codex:{desc:"Add the block to ~/.codex/config.toml, then restart Codex; the tool appears automatically.",
    code:o=>`<span class="c"># ~/.codex/config.toml</span>\n`+
      `[mcp_servers.brahma]\n`+
      `command = <span class="s">"python"</span>\n`+
      `args = [<span class="s">"mcp_server.py"</span>]\n`+
      `env = { BRAHMA_URL = <span class="s">"${esc(o)}"</span> }`},
  other:{desc:"Most MCP clients accept this stdio config. Point BRAHMA_URL at this host.",
    code:o=>esc(JSON.stringify({mcpServers:{brahma:{command:"python",args:["mcp_server.py"],env:{BRAHMA_URL:o}}}},null,2))},
};
function platformTab(p){
  document.querySelectorAll("#ptabs button").forEach(b=>b.classList.toggle("on",b.dataset.p===p));
  const o=location.origin,spec=own(PLATFORMS,p);if(!spec)return;
  $("pdesc").textContent=spec.desc;
  $("qs2").innerHTML=`<button class="cp" onclick="copyCode('qs2')">copy</button>`+spec.code(o);
  window.BrahmaMotion?.enter($("qs2"));
}
async function copyCode(id){
  const code=$(id);if(!code)return;
  const b=code.querySelector(".cp");if(b?.disabled)return;
  const clone=code.cloneNode(true);clone.querySelectorAll(".cp").forEach(button=>button.remove());
  if(b){b.disabled=true;b.textContent="copying...";}
  let timer;
  try{
    if(!navigator.clipboard?.writeText)throw new Error("Clipboard unavailable");
    await Promise.race([navigator.clipboard.writeText(clone.textContent.trim()),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error("Clipboard timed out")),10000);})]);
    if(b?.isConnected){b.textContent="copied";b.title="Copied to clipboard";}
  }catch{
    if(b?.isConnected){b.textContent="copy failed";b.title="Clipboard access failed. Select and copy the code manually.";}
    status("status","Clipboard access failed. Select and copy the code manually.",true);
  }finally{
    clearTimeout(timer);
    if(b?.isConnected){b.disabled=false;clearTimeout(b.copyTimer);b.copyTimer=setTimeout(()=>{if(b.isConnected&&!b.disabled)b.textContent="copy";},2000);}
  }
}
async function tryApi(){
  const name=$("apiName").value.trim()||"Wells Fargo & Company";
  const btn=$("apiRun"),out=$("apiOut");btn.disabled=true;
  const ticket=beginRequest("api");
  out.innerHTML='<span class="c">// calling… (live sources; cold start can take ~30-60s)</span>';
  try{
    const d=validateInvestigation(await requestJSON(ticket,"/api/v1/supplier/investigate",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({name})}));
    if(!isCurrent(ticket))return;
    const slim={supplier:d.supplier,risk:d.risk,sanctions:{match:d.sanctions.match,list_size:d.sanctions.list_size},
      media_summary:{total:d.media_summary?.total,bias:d.media_summary?.bias},
      agent_summary:{recommendation:d.agent_summary?.recommendation,generated_by:d.agent_summary?.generated_by},
      metadata:d.metadata,demo:d.demo,sources_consulted:d.sources_consulted,duration_seconds:d.duration_seconds};
    out.innerHTML=`<span class="c">// Response received - abridged (full object has ${Object.keys(d).length} keys)\n// ${esc(provenance(d,"live"))}: ${esc(sourceSummary(d,"live"))}</span>\n`+esc(JSON.stringify(slim,null,2));
  }catch(e){if(isCurrent(ticket))out.innerHTML=`<span class="c">// ${esc(e.message)}</span>`;}
  finally{if(isCurrent(ticket))btn.disabled=false;finishRequest(ticket);}
}

const graphMotionPreference=window.matchMedia?.("(prefers-reduced-motion: reduce)");
function suspendGraphMotion(){
  if(document.hidden||graphMotionPreference?.matches){cancelAnimationFrame(Graph.raf);Graph.raf=null;}
}
graphMotionPreference?.addEventListener?.("change",suspendGraphMotion);
document.addEventListener?.("visibilitychange",suspendGraphMotion);
window.addEventListener("pagehide",()=>{for(const key of REQUESTS.keys())cancelRequest(key);MISSION_TIMERS.forEach(clearTimeout);cancelAnimationFrame(Graph.raf);Graph.raf=null;});
setType("organization");setMode("screen");checkHealth();loadEntities();Graph.init();renderConnectors();initStrategy();refreshIcons();
