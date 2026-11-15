'use strict';
const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=2)=>v===null||v===undefined?'—':Number(v).toLocaleString('th-TH',{maximumFractionDigits:d});
const short=v=>new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(v);
let production=[],factors=[],filtered=[],page=0,loaded=false,loading=false;
const size=20;
const selectedFactor=()=>factors.find(f=>String(f.factor_id)===$('factor').value);
function options(id,values,label){
 const old=$(id).value;$(id).innerHTML=`<option value="">${label}</option>`+values.map(([key,text])=>`<option value="${esc(key)}">${esc(text)}</option>`).join('');
 if(values.some(([key])=>String(key)===old))$(id).value=old;
}
function render(){
 const share=Number($('share').value),factor=selectedFactor(),q=$('search').value.trim().toLocaleLowerCase();
 $('shareValue').value=share+'%';
 $('factorInfo').textContent=factor?`${factor.factor_id} · ${fmt(factor.factor_value,6)} kgCO₂e/SCF · ${factor.basis}`:'ไม่พบ Factor ที่รองรับ: นำเข้า Emission Factor แล้วกดรีเฟรช';
 filtered=production.filter(r=>(!$('year').value||String(r.year)===$('year').value)&&(!$('month').value||String(r.month)===$('month').value)&&(!$('field').value||String(r.field_id??'')===$('field').value)&&(!q||[r.field_name,r.block,r.production_id,r.product_name].join(' ').toLocaleLowerCase().includes(q))).map(r=>CarbonMath.calculate(r,factor,share));
 const valid=filtered.filter(r=>r.carbon_tonnes!==null),sum=valid.reduce((a,r)=>a+r.carbon_tonnes,0),gas=valid.reduce((a,r)=>a+r.gas_scf,0);
 $('total').textContent=valid.length?(sum>=1e7?fmt(sum/1e6)+' ล้าน':fmt(sum)):'—';$('total').title=fmt(sum)+' tCO₂e';
 $('gas').textContent=valid.length?(gas/1e6>=1e7?short(gas/1e6):fmt(gas/1e6)):'—';$('gas').title=fmt(gas/1e6)+' ล้าน SCF';
 $('coverage').textContent=filtered.length?fmt(valid.length/filtered.length*100,1)+'%':'—';
 $('covered').textContent=`คำนวณได้ ${fmt(valid.length,0)} / ${fmt(filtered.length,0)} รายการ`;
 $('excluded').textContent=loaded?fmt(filtered.length-valid.length,0):'—';
 $('rowCount').textContent=`${fmt(filtered.length,0)} รายการ · คำนวณได้ ${fmt(valid.length,0)} · สัดส่วนสมมติ ${share}%`;
 $('export').disabled=!loaded||!filtered.length||loading;
 const positive=valid.map(r=>Number(r.quantity)).filter(n=>n>0).sort((a,b)=>a-b);
 const median=positive.length?positive[Math.floor(positive.length/2)]:0;
 const unusual=valid.filter(r=>median>0&&Number(r.quantity)>median*100);
 $('quality').hidden=!unusual.length;
 $('quality').textContent=unusual.length?`ตรวจข้อมูลต้นทาง: ${unusual.length} รายการมีอัตราผลิตมากกว่า 100 เท่าของมัธยฐานรายการก๊าซที่มีค่าบวกในผลกรอง เช่น ${unusual.slice(0,3).map(r=>r.production_id+' ('+fmt(r.quantity)+' MMSCFD)').join(', ')} ค่ายังคงรวมในประมาณการ กรุณาตรวจหน่วยและตัวเลขก่อนใช้งาน`:'';
 drawTrend(valid);drawRanking(valid);renderRows();
}
function renderRows(){
 page=Math.max(0,Math.min(page,Math.ceil(filtered.length/size)-1));
 $('rows').innerHTML=filtered.slice(page*size,(page+1)*size).map(r=>`<tr><td>${esc(r.production_id)}<div class="sub">${esc(r.year??'—')}-${String(r.month??'—').padStart(2,'0')}</div></td><td>${esc(r.product_name)}<div class="sub">${esc(r.field_name||'ไม่ทราบแหล่งผลิต')} · ${esc(r.block||'ไม่ทราบบล็อก')}</div></td><td class="num">${fmt(r.quantity,6)}</td><td>${esc(r.unit)}</td><td class="num">${fmt(r.production_days,0)}</td><td class="num">${fmt(r.carbon_tonnes,3)}</td><td>${esc(r.reason||r.factor_id)}${!r.reason?'<div class="sub">ประมาณการตามสถานการณ์</div>':''}</td></tr>`).join('')||`<tr><td colspan="7" class="empty">${loaded?'ไม่มีรายการตรงกับตัวกรอง':'ยังไม่มีข้อมูลจาก MySQL'}</td></tr>`;
 $('pageInfo').textContent=filtered.length?`${fmt(page*size+1,0)}–${fmt(Math.min((page+1)*size,filtered.length),0)} จาก ${fmt(filtered.length,0)} รายการ`:'0 รายการ';
 $('prev').disabled=loading||page===0;$('next').disabled=loading||(page+1)*size>=filtered.length;
}
function drawTrend(rows){
 if(!rows.length){$('trend').innerHTML='<div class="empty">ไม่มีรายการที่คำนวณได้ในช่วงนี้<br>ตรวจ Factor และข้อมูลวันผลิต</div>';return}
 const periods=new Map();rows.forEach(r=>{const key=r.year+'-'+String(r.month).padStart(2,'0');periods.set(key,(periods.get(key)||0)+r.carbon_tonnes)});
 const data=[...periods].sort((a,b)=>a[0].localeCompare(b[0]));
 const W=760,H=260,L=65,R=740,T=25,B=215,max=Math.max(1,...data.map(r=>r[1]));
 const x=i=>L+(R-L)*(data.length===1?.5:i/(data.length-1)),y=n=>B-(B-T)*n/max;
 let html='';for(let i=0;i<=4;i++){const n=max*i/4;html+=`<line x1="${L}" x2="${R}" y1="${y(n)}" y2="${y(n)}" stroke="#e4eae0"/><text x="${L-8}" y="${y(n)+4}" text-anchor="end" fill="#64766e" font-size="11">${short(n)}</text>`}
 // Separate missing months so a line does not imply observations where none exist.
 let d='';data.forEach(([period,n],i)=>{const [yr,mo]=period.split('-').map(Number);const previous=i?data[i-1][0].split('-').map(Number):null;const contiguous=previous&&yr*12+mo===previous[0]*12+previous[1]+1;d+=`${contiguous?'L':'M'}${x(i)},${y(n)} `});
 html+=`<path d="${d}" fill="none" stroke="#18785c" stroke-width="3"/>`;
 const step=Math.max(1,Math.ceil(data.length/6));data.forEach(([period,n],i)=>{html+=`<circle cx="${x(i)}" cy="${y(n)}" r="3" fill="#18785c"><title>${period}: ${fmt(n,3)} tCO₂e</title></circle>`;if(i%step===0)html+=`<text x="${x(i)}" y="244" text-anchor="middle" font-size="11" fill="#64766e">${period}</text>`});
 $('trend').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(data.map(([p,n])=>p+': '+fmt(n,3)+' tCO₂e').join('; '))}">${html}</svg>`;
}
function drawRanking(rows){
 const groups=new Map();rows.forEach(r=>{const key=r.field_id??'unknown';const old=groups.get(key)||{name:r.field_name||'ไม่ทราบแหล่งผลิต',total:0};old.total+=r.carbon_tonnes;groups.set(key,old)});
 const data=[...groups.values()].sort((a,b)=>b.total-a.total).slice(0,8),max=Math.max(1,...data.map(r=>r.total));
 $('ranking').innerHTML=data.map(r=>`<div class="bar"><div class="bar-text"><span title="${esc(r.name)}">${esc(r.name)}</span><span>${fmt(r.total)} tCO₂e</span></div><div class="track"><div class="fill" style="width:${r.total/max*100}%"></div></div></div>`).join('')||'<div class="empty">ไม่มีรายการที่คำนวณได้</div>';
}
async function refresh(){
 if(loading)return;loading=true;$('refresh').disabled=true;$('export').disabled=true;$('status').textContent='กำลังอ่าน MySQL…';
 try{
  const response=await fetch('/api/data',{cache:'no-store'}),payload=await response.json();
  if(!response.ok)throw new Error(payload.error||'อ่านข้อมูลไม่สำเร็จ');
  const data=payload.datasets;if(!Array.isArray(data?.production?.rows)||!Array.isArray(data?.emission_factor?.rows))throw new Error('รูปแบบข้อมูลไม่ถูกต้อง');
  const firstLoad=!loaded;production=data.production.rows;factors=data.emission_factor.rows.filter(CarbonMath.eligible);
  const old=$('factor').value;options('factor',factors.map(f=>[String(f.factor_id),`${f.factor_id} · ${f.activity_type} · ${fmt(f.factor_value,6)} kgCO₂e/SCF`]),'เลือก Factor');
  if(!factors.some(f=>String(f.factor_id)===old)&&factors.length===1)$('factor').value=String(factors[0].factor_id);
  $('factor').disabled=!factors.length;
  options('year',[...new Set(production.map(r=>r.year).filter(v=>v!==null))].sort((a,b)=>b-a).map(v=>[String(v),v]),'ทุกปี');
  if(firstLoad&&$('year').options.length>1)$('year').selectedIndex=1;
  options('month',Array.from({length:12},(_,i)=>[String(i+1),new Date(2024,i,1).toLocaleString('th-TH',{month:'long'})]),'ทุกเดือน');
  const fields=new Map(production.filter(r=>r.field_id!==null).map(r=>[String(r.field_id),r.field_name||r.field_id]));options('field',[...fields].sort((a,b)=>String(a[1]).localeCompare(String(b[1]),'th')),'ทุกแหล่งผลิต');
  loaded=true;$('status').textContent='MySQL · โหลดล่าสุด '+new Date(payload.loaded_at).toLocaleString('th-TH')+' · หน้านี้ไม่เขียนข้อมูลกลับฐาน';
 }catch(error){$('status').textContent='โหลดไม่สำเร็จ: '+error.message+(loaded?' · แสดง snapshot เดิม กรุณารีเฟรชอีกครั้ง':' · ตรวจ .env, MySQL และการนำเข้าข้อมูล')}
 finally{loading=false;$('refresh').disabled=false;page=0;render()}
}
['year','month','field','factor'].forEach(id=>$(id).addEventListener('change',()=>{page=0;render()}));
['search','share'].forEach(id=>$(id).addEventListener('input',()=>{page=0;render()}));
$('reset').onclick=()=>{['year','month','field','search'].forEach(id=>$(id).value='');page=0;render()};
$('prev').onclick=()=>{page--;renderRows()};$('next').onclick=()=>{page++;renderRows()};$('refresh').onclick=refresh;
$('export').onclick=()=>{
 const cols=['production_id','year','month','product_name','field_name','block','quantity','unit','production_days','factor_id','factor_value','share_percent','gas_scf','carbon_tonnes','reason','scenario'];
 const quote=v=>'"'+String(v??'').replace(/^[=+\-@\t\r]/,"'$&").replace(/"/g,'""')+'"';
 const csv=[cols.join(','),...filtered.map(r=>{const output={...r,factor_id:selectedFactor()?.factor_id, factor_value:selectedFactor()?.factor_value,share_percent:Number($('share').value),scenario:'Hypothetical combustion of produced natural gas; not actual production emissions'};return cols.map(k=>quote(output[k])).join(',')})].join('\r\n');
 const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='carbon_scenario_filtered.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
render();refresh();
