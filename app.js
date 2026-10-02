/* Pakistan Floods 2022 — data story app. Fetches cleaned CSVs, renders tables & charts. */
(function(){
"use strict";

/* ---------- tiny CSV parser (handles quotes) ---------- */
function parseCSV(text){
  var rows=[], row=[], cur="", q=false;
  for(var i=0;i<text.length;i++){
    var c=text[i];
    if(q){
      if(c==='"'){ if(text[i+1]==='"'){cur+='"';i++;} else q=false; }
      else cur+=c;
    }else{
      if(c==='"') q=true;
      else if(c===','){row.push(cur);cur="";}
      else if(c==='\n'){row.push(cur);rows.push(row);row=[];cur="";}
      else if(c==='\r'){}
      else cur+=c;
    }
  }
  if(cur!==""||row.length){row.push(cur);rows.push(row);}
  return rows.filter(function(r){return r.length>1||r[0]!=="";});
}
function rowsToObjects(rows){
  var h=rows[0].map(function(x){return x.trim();});
  return rows.slice(1).map(function(r){
    var o={}; h.forEach(function(k,j){o[k]=(r[j]!==undefined?r[j]:"").trim();}); return o;
  });
}
function fetchCSV(path){
  return fetch(path).then(function(r){ if(!r.ok) throw new Error(r.status); return r.text(); })
    .then(function(t){ return rowsToObjects(parseCSV(t)); });
}
function fmt(n){
  n=Number(n); if(!isFinite(n)) return "—";
  if(n>=1e6) return (n/1e6).toFixed(1)+"M";
  if(n>=1e3) return (n/1e3).toFixed(0)+"K";
  return String(Math.round(n));
}
function fmtFull(n){ n=Number(n); return isFinite(n)? n.toLocaleString("en-US") : "—"; }
function esc(s){ return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }

/* ---------- stage navigation ---------- */
var stages=[0,1,2,3,4], cur=0;
function showStage(i){
  cur=Math.max(0,Math.min(4,i));
  stages.forEach(function(s){
    var el=document.getElementById("stage"+s);
    el.classList.toggle("active", s===cur);
    el.hidden = s!==cur;
  });
  document.querySelectorAll(".stagebtn").forEach(function(b){
    b.setAttribute("aria-current", String(Number(b.dataset.stage)===cur));
  });
  document.getElementById("prog").style.width=((cur+1)/5*100)+"%";
  document.getElementById("prevBtn").disabled = cur===0;
  document.getElementById("nextBtn").textContent = cur===4 ? "Done ✓" : "Next →";
  window.scrollTo({top:0,behavior:"smooth"});
  if(cur===3) drawCharts();
}
document.querySelectorAll(".stagebtn").forEach(function(b){
  b.addEventListener("click",function(){showStage(Number(b.dataset.stage));});
});
document.getElementById("prevBtn").addEventListener("click",function(){showStage(cur-1);});
document.getElementById("nextBtn").addEventListener("click",function(){ if(cur<4) showStage(cur+1); });

/* ---------- audience toggle ---------- */
var bC=document.getElementById("audCitizen"), bO=document.getElementById("audOfficial");
function setAud(a){
  document.body.setAttribute("data-aud",a);
  bC.setAttribute("aria-pressed",String(a==="citizen"));
  bO.setAttribute("aria-pressed",String(a==="official"));
}
bC.addEventListener("click",function(){setAud("citizen");});
bO.addEventListener("click",function(){setAud("official");});

/* ---------- data ---------- */
var D={};
function loadAll(){
  return Promise.all([
    fetchCSV("data/cleaned_district_flood.csv").then(function(r){D.flood=r;}),
    fetchCSV("data/gap_analysis.csv").then(function(r){D.gap=r;}),
    fetchCSV("data/cleaned_relief_by_district.csv").then(function(r){D.relief=r;}),
    fetchCSV("data/raw_samples/raw_sample_unosat.csv").then(function(r){D.rawU=r;}).catch(function(){D.rawU=[];}),
    fetchCSV("data/raw_samples/raw_sample_5w.csv").then(function(r){D.rawW=r;}).catch(function(){D.rawW=[];}),
    fetch("data/cleaning_log.json").then(function(r){return r.json();}).then(function(j){D.log=j;}).catch(function(){D.log=null;})
  ]);
}

/* ---------- generic table builder ---------- */
function buildTable(cols, rows, numCols){
  var h="<thead><tr>"+cols.map(function(c){
    return "<th class='"+(numCols.indexOf(c)>=0?"num":"")+"'>"+esc(c)+"</th>";
  }).join("")+"</tr></thead><tbody>";
  rows.forEach(function(r){
    h+="<tr>"+cols.map(function(c){
      var v=r[c]!==undefined?r[c]:"";
      var cls=numCols.indexOf(c)>=0?"num":"";
      return "<td class='"+cls+"'>"+esc(v)+"</td>";
    }).join("")+"</tr>";
  });
  return h+"</tbody>";
}

/* ---------- stage 2: raw samples ---------- */
function renderRaw(){
  if(D.rawU.length){
    var t=document.getElementById("rawUnosat");
    var cols=Object.keys(D.rawU[0]).slice(0,8);
    t.innerHTML="<caption>First rows of the raw UNOSAT district sheet (truncated to 8 columns)</caption>"+
      buildTable(cols,D.rawU,[cols[1],cols[2],cols[5],cols[6]]);
  }
  if(D.rawW.length){
    var t2=document.getElementById("rawW5");
    t2.innerHTML="<caption>First rows of the raw OCHA 5W file (key columns)</caption>"+
      buildTable(Object.keys(D.rawW[0]),D.rawW,[]);
  }
}

/* ---------- stage 3: cleaning ---------- */
function renderIssues(){
  var el=document.getElementById("issueList");
  if(!D.log){el.innerHTML="<p>Cleaning log not available.</p>";return;}
  var h="<ol class='tight'>";
  D.log.issues.forEach(function(it){
    h+="<li><strong>"+esc(it.issue)+"</strong><br>→ "+esc(it.action)+
      (it.count!==undefined&&it.count!==null?" <span class='pill none'>n="+it.count+"</span>":"")+"</li>";
  });
  h+="</ol><div class='note'><strong>Result:</strong> 160 clean districts · 133 with relief records · "+
     "27 flood-hit districts with no relief rows at all, 12 more with activities but 0 beneficiaries reported. "+
     "Full log: <a href='data/cleaning_log.json'>cleaning_log.json</a></div>";
  el.innerHTML=h;
}
var dirtyMode=true;
function renderDirtyClean(){
  var t=document.getElementById("dirtyClean"), cap=document.getElementById("dcCap");
  document.getElementById("btnDirty").setAttribute("aria-pressed",String(dirtyMode));
  document.getElementById("btnClean").setAttribute("aria-pressed",String(!dirtyMode));
  if(dirtyMode){
    cap.textContent="Raw UNOSAT rows — exactly as downloaded";
    if(!D.rawU.length){t.innerHTML="<tbody><tr><td>Raw sample not available.</td></tr></tbody>";return;}
    var cols=Object.keys(D.rawU[0]).slice(0,7);
    t.innerHTML="<caption>Raw UNOSAT rows — exactly as downloaded</caption>"+buildTable(cols,D.rawU,[]);
  }else{
    cap.textContent="Cleaned districts — one row per district";
    var rows=D.flood.slice(0,10).map(function(r){
      return {district:r.district, province:r.province, area_km2:r.area_km2,
              population:fmtFull(r.population), flood_extent_km2:r.flood_extent_km2,
              exposed_pop:fmtFull(r.exposed_pop)};
    });
    t.innerHTML="<caption>Cleaned districts — one row per district</caption>"+
      buildTable(["district","province","area_km2","population","flood_extent_km2","exposed_pop"],rows,
        ["area_km2","population","flood_extent_km2","exposed_pop"]);
  }
}
document.getElementById("btnDirty").addEventListener("click",function(){dirtyMode=true;renderDirtyClean();});
document.getElementById("btnClean").addEventListener("click",function(){dirtyMode=false;renderDirtyClean();});

/* ---------- stage 5: gap table ---------- */
function renderGapTable(){
  var t=document.getElementById("gapTable");
  var rows=D.gap.filter(function(r){return (r.gap_flag||"").indexOf("BIG GAP")===0;})
    .map(function(r){
      var isBig=(r.gap_flag||"").indexOf("BIG GAP")===0;
      return {district:r.district, province:r.province, exposed:fmtFull(r.exposed_pop),
        reached:fmtFull(r.beneficiaries_reached),
        pill:"<span class='pill "+(isBig?"big":"part")+"'>"+esc(r.gap_flag)+"</span>"};
    });
  var h="<caption>Relief-gap districts ("+rows.length+")</caption><thead><tr><th>District</th><th>Province</th>"+
    "<th class='num'>People exposed</th><th class='num'>Beneficiaries reached</th><th>Status</th></tr></thead><tbody>";
  rows.forEach(function(r){
    h+="<tr><td>"+esc(r.district)+"</td><td>"+esc(r.province)+"</td><td class='num'>"+r.exposed+
       "</td><td class='num'>"+r.reached+"</td><td>"+r.pill+"</td></tr>";
  });
  t.innerHTML=h+"</tbody>";
}

/* ---------- stage 4: charts ---------- */
var chartsDrawn=false;
function hasChart(){ return typeof window.Chart!=="undefined"; }
function fallback(id, cols, rows, numCols, cap){
  var el=document.getElementById(id);
  el.style.display="block";
  el.innerHTML="<div class='twrap'><table><caption>"+esc(cap)+"</caption>"+
    buildTable(cols,rows,numCols)+"</table></div>";
}
function provAgg(){
  var m={};
  D.gap.forEach(function(r){
    var p=r.province||"Unknown";
    m[p]=m[p]||{exposed:0,extent:0,ben:0};
    m[p].exposed+=Number(r.exposed_pop)||0;
    m[p].extent+=Number(r.flood_extent_km2)||0;
    m[p].ben+=Number(r.beneficiaries_reached)||0;
  });
  return Object.keys(m).map(function(p){return {province:p,exposed:m[p].exposed,extent:m[p].extent,ben:m[p].ben};})
    .sort(function(a,b){return b.exposed-a.exposed;});
}
function sectorFreq(){
  var f={};
  D.relief.forEach(function(r){
    (r.sectors||"").split(";").forEach(function(s){
      s=s.trim(); if(s) f[s]=(f[s]||0)+1;
    });
  });
  var order=["Shelter/NFI","Food Security, Agriculture & Livelihoods","Health","WASH","Nutrition",
    "Protection - Child Protection","Education","Protection - GBV","Health - SRH","Multi-Purpose Cash","Protection"];
  return order.filter(function(s){return f[s];}).map(function(s){return {sector:s,n:f[s]};});
}
function drawCharts(){
  if(chartsDrawn) return; chartsDrawn=true;
  var pa=provAgg();
  var top10=D.gap.slice().sort(function(a,b){return (Number(b.exposed_pop)||0)-(Number(a.exposed_pop)||0);}).slice(0,10);

  /* 1: exposed by province */
  if(hasChart()){
    new Chart(document.getElementById("chProv"),{type:"bar",
      data:{labels:pa.map(function(x){return x.province;}),
        datasets:[{data:pa.map(function(x){return x.exposed;}),backgroundColor:"#0e6e6e"}]},
      options:{indexAxis:"y",plugins:{legend:{display:false},
        tooltip:{callbacks:{label:function(c){return " "+fmtFull(c.raw)+" people";}}}},
        scales:{x:{ticks:{callback:function(v){return fmt(v);}}}}} });
  }else{
    document.getElementById("chProv").style.display="none";
    fallback("fbProv",["province","exposed"],pa.map(function(x){return {province:x.province,exposed:fmtFull(x.exposed)};}),["exposed"],"People exposed by province");
  }
  /* 2: top 10 districts */
  if(hasChart()){
    new Chart(document.getElementById("chTop"),{type:"bar",
      data:{labels:top10.map(function(x){return x.district;}),
        datasets:[{data:top10.map(function(x){return Number(x.exposed_pop);}),backgroundColor:"#e8930c"}]},
      options:{indexAxis:"y",plugins:{legend:{display:false},
        tooltip:{callbacks:{label:function(c){return " "+fmtFull(c.raw)+" people";}}}},
        scales:{x:{ticks:{callback:function(v){return fmt(v);}}}}} });
  }else{
    document.getElementById("chTop").style.display="none";
    fallback("fbTop",["district","exposed"],top10.map(function(x){return {district:x.district+" ("+x.province+")",exposed:fmtFull(x.exposed_pop)};}),["exposed"],"Top 10 districts by people exposed");
  }
  /* 3: flooded land by province */
  if(hasChart()){
    new Chart(document.getElementById("chLand"),{type:"bar",
      data:{labels:pa.map(function(x){return x.province;}),
        datasets:[{data:pa.map(function(x){return Math.round(x.extent);}),backgroundColor:"#2a9d8f"}]},
      options:{indexAxis:"y",plugins:{legend:{display:false},
        tooltip:{callbacks:{label:function(c){return " "+fmtFull(c.raw)+" km²";}}}},
        scales:{x:{ticks:{callback:function(v){return fmt(v)+" km²";}}}}} });
  }else{
    document.getElementById("chLand").style.display="none";
    fallback("fbLand",["province","km2"],pa.map(function(x){return {province:x.province,km2:fmtFull(Math.round(x.extent))+" km²"};}),["km2"],"Flooded land by province");
  }
  /* 4: need vs relief */
  if(hasChart()){
    new Chart(document.getElementById("chGap"),{type:"bar",
      data:{labels:top10.map(function(x){return x.district;}),
        datasets:[
          {label:"People exposed",data:top10.map(function(x){return Number(x.exposed_pop);}),backgroundColor:"#c0392b"},
          {label:"Beneficiaries reached",data:top10.map(function(x){return Number(x.beneficiaries_reached);}),backgroundColor:"#0e6e6e"}]},
      options:{indexAxis:"y",plugins:{tooltip:{callbacks:{label:function(c){return " "+c.dataset.label+": "+fmtFull(c.raw);}}}},
        scales:{x:{ticks:{callback:function(v){return fmt(v);}}}}} });
  }else{
    document.getElementById("chGap").style.display="none";
    fallback("fbGap",["district","exposed","reached"],top10.map(function(x){
      return {district:x.district,exposed:fmtFull(x.exposed_pop),reached:fmtFull(x.beneficiaries_reached)};}),["exposed","reached"],"Need vs relief, top 10 districts");
  }
  /* 5: sectors */
  var sf=sectorFreq();
  if(hasChart()){
    new Chart(document.getElementById("chSec"),{type:"bar",
      data:{labels:sf.map(function(x){return x.sector;}),
        datasets:[{data:sf.map(function(x){return x.n;}),backgroundColor:"#457b9d"}]},
      options:{indexAxis:"y",plugins:{legend:{display:false},
        tooltip:{callbacks:{label:function(c){return " "+c.raw+" districts";}}}}} });
  }else{
    document.getElementById("chSec").style.display="none";
    fallback("fbSec",["sector","districts"],sf.map(function(x){return {sector:x.sector,districts:x.n};}),["districts"],"Relief sectors by districts reached");
  }
}

/* ---------- findings summary export ---------- */
document.getElementById("btnSummary").addEventListener("click",function(){
  var gaps=D.gap.filter(function(r){return (r.gap_flag||"").indexOf("BIG GAP")===0;});
  var pa=provAgg();
  var L=[];
  L.push("PAKISTAN FLOODS 2022 — FINDINGS SUMMARY");
  L.push("Generated from cleaned snapshots (not live): UNOSAT 22-Oct-2022 assessment + OCHA Pakistan 5W (Aug22-Dec23).");
  L.push("");
  L.push("NATIONAL: 31.25M people exposed (UNOSAT Aug 2022); 83,557 km2 max flood extent; 160 districts analysed;");
  L.push("133 districts with recorded relief; 27 flood-hit districts with no relief rows at all;");
  L.push("12 more districts have relief activities on record but 0 beneficiaries reported (incl. Sialkot).");
  L.push("");
  L.push("BY PROVINCE (exposed / beneficiaries reached):");
  pa.forEach(function(x){L.push(" - "+x.province+": "+fmtFull(x.exposed)+" exposed / "+fmtFull(x.ben)+" reached");});
  L.push("");
  L.push("DISTRICTS WITH THE BIGGEST RELIEF GAPS (exposed people):");
  gaps.forEach(function(r){L.push(" - "+r.district+" ("+r.province+"): "+fmtFull(r.exposed_pop));});
  L.push("");
  L.push("LIMITATIONS: satellite estimates, not ground counts; 5W self-reported (double counting possible);");
  L.push("relief window (to Dec 2023) differs from flood windows (Aug-Nov 2022); no deaths/houses/livestock in these files.");
  var blob=new Blob([L.join("\n")],{type:"text/plain"});
  var a=document.createElement("a");
  a.href=URL.createObjectURL(blob); a.download="flood2022_findings_summary.txt";
  document.body.appendChild(a); a.click();
  setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},500);
});

/* ---------- boot ---------- */
loadAll().then(function(){
  renderRaw(); renderIssues(); renderDirtyClean(); renderGapTable();
  if(cur===3) drawCharts();
}).catch(function(e){
  ["rawUnosat","rawW5","dirtyClean","gapTable"].forEach(function(id){
    var el=document.getElementById(id);
    if(el) el.innerHTML="<tbody><tr><td>Could not load data files. Open this page from the project folder (data/ must sit next to index.html).</td></tr></tbody>";
  });
  document.getElementById("issueList").innerHTML="<p>Could not load the cleaning log.</p>";
});
})();
