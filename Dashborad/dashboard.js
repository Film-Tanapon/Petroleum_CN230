"use strict";
const $ = id => document.getElementById(id);
const months = ['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน','กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม'];
const datasets = Object.fromEntries(['sale','production','supply','reserve','emission_factor'].map(k=>[k,{rows:[],source:'MySQL',rejected:0}]));
let loadedAt=null;
const configs = {
 emission_factor: {
  title:'ค่าปัจจัยการปล่อยคาร์บอน', subtitle:'Emission Factor หน่วย kgCO₂e ต่อหน่วยเชื้อเพลิง · ไม่ใช่ปริมาณการปล่อยจริง', metric:'factor_value',
  group:'product_name', groupLabel:'เชื้อเพลิง', search:'ค้นเชื้อเพลิงหรือประเภทกิจกรรม', filename:'Emission_Factor',
  columns:[['factor_id','รหัส Factor'],['product_name','เชื้อเพลิง'],['unit','หน่วย'],['factor_value','kgCO₂e ต่อหน่วย'],['activity_type','ประเภทกิจกรรม'],['basis','ฐานการคำนวณ']],
 },
 sale: {
  title:'รายการจำหน่าย', subtitle:'ยอดขาย ค่าภาคหลวง และปริมาตรจำหน่ายรายแหล่งผลิต', metric:'sale_value',
  group:'field_name', groupLabel:'แหล่งผลิต', search:'ค้นชื่อแหล่งผลิต', filename:'Sale',
  columns:[['sale_id','รหัสรายการ'],['year','ปี ค.ศ.'],['month','เดือน'],['field_name','แหล่งผลิต'],['product_name','ผลิตภัณฑ์'],['volume_bbl','บาร์เรล'],['volume_mmscf','ล้าน ลบ.ฟุตมาตรฐาน'],['energy_mmbtu','ล้านบีทียู'],['sale_value','มูลค่าจำหน่าย'],['royalty','ค่าภาคหลวง'],['currency','สกุลเงิน']],
 },
 production: {
  title:'รายการผลิต', subtitle:'ปริมาณผลิตรวม = อัตราผลิตรายวัน × วันผลิตจริง · แสดงของเหลวและก๊าซแยกหน่วย', metric:'quantity',
  group:'field_name', groupLabel:'แหล่งผลิต', search:'ค้นชื่อแหล่งผลิตหรือบล็อก', filename:'Production_Monthly',
  columns:[['production_id','รหัสรายการ'],['year','ปี ค.ศ.'],['month','เดือน'],['field_name','แหล่งผลิต'],['block','บล็อก'],['product_name','ผลิตภัณฑ์'],['quantity','อัตราผลิตตามต้นทาง'],['unit','หน่วย'],['oil_equivalent','เทียบเท่าน้ำมันดิบตามต้นทาง'],['production_days','วันที่ผลิต']],
 },
 supply: {
  title:'รายการจัดหา', subtitle:'ประมาณปริมาณจัดหารายเดือน = อัตราเฉลี่ยรายวัน × จำนวนวันปฏิทินในเดือน', metric:'daily_rate',
  group:'area', groupLabel:'พื้นที่จัดหา', search:'ค้นพื้นที่จัดหา', filename:'Supply_Monthly',
  columns:[['supply_id','รหัสรายการ'],['year','ปี ค.ศ.'],['month','เดือน'],['product_name','ผลิตภัณฑ์'],['area','พื้นที่จัดหา'],['daily_rate','อัตราเฉลี่ยรายวัน'],['unit','หน่วย']],
 },
 reserve: {
  title:'รายการสำรอง', subtitle:'ปริมาณสำรองที่พิสูจน์แล้วรายปี แยกตามบล็อกสำรวจ', metric:'proven_reserves',
  group:'block', groupLabel:'บล็อก', search:'ค้นชื่อหรือรหัสบล็อก', filename:'Reserve_Annual',
  columns:[['reserve_id','รหัสรายการ'],['year','ปี ค.ศ.'],['block','บล็อก'],['product_name','ผลิตภัณฑ์'],['proven_reserves','ปริมาณสำรองที่พิสูจน์แล้ว'],['unit','หน่วย']],
 }
};
const numeric = new Set(['year','month','volume_bbl','volume_mmscf','energy_mmbtu','sale_value','royalty','quantity','oil_equivalent','production_days','daily_rate','proven_reserves','factor_value','monthly_m3','monthly_native','monthly_volume','volume_days','boe_rate','boe_volume','mmboe','gas_boe_per_mmscf','condensate_boe_per_bbl']);
const fmt = (v, digits=2) => v===null || v===undefined ? '—' : Number(v).toLocaleString('en-US',{maximumFractionDigits:digits,minimumFractionDigits:digits});
const compact = v => new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(v);
const esc = v => String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let active='emission_factor', filtered=[], page=1;
const pageSize=15, state={};
months.forEach((m,i)=>$('month').add(new Option(m,i+1)));
function config(){return configs[active]}
function isVolume(){return active==='production'||active==='supply'}
function isBoe(){return active==='reserve'||(isVolume()&&$('volumeUnit').value==='boe')}
function volumeKey(){return $('volumeUnit').value==='native'?'monthly_native':'monthly_m3'}
function volumeUnit(family){if(!family)return 'ไม่ระบุ';return $('volumeUnit').value==='native'?(family==='gas'?'MMSCF':'bbl'):(family==='gas'?'Sm³':'m³')}
function displayColumns(){
 const columns=config().columns;
 if(isBoe())return [...columns,...(active==='reserve'?[]:[['boe_rate','อัตรารายการ BOED'],['boe_volume','ปริมาณในเดือน BOE']]),['mmboe','ปริมาณ MMBOE'],['boe_basis','วิธีแปลง BOE'],['boe_reason','เหตุผลที่คำนวณไม่ได้'],['gas_boe_per_mmscf','อัตราก๊าซ BOE/MMSCF'],['condensate_boe_per_bbl','อัตราคอนเดนเสท BOE/bbl']];
 return isVolume()?[...columns,['volume_days','วันที่ใช้คำนวณ'],['monthly_volume','ปริมาณรวมในเดือน'],['monthly_unit','หน่วยปริมาณรวม'],['volume_reason','เหตุผลที่คำนวณไม่ได้']]:columns;
}
function sum(key, rows=filtered){
 const values=rows.map(r=>r[key]).filter(v=>v!==null && v!==undefined);
 return values.length ? values.reduce((a,b)=>a+b,0) : null;
}
function average(key, rows=filtered){
 const count=rows.filter(r=>r[key]!==null && r[key]!==undefined).length;
 return count ? sum(key,rows)/count : null;
}
function unique(key, rows=filtered){return [...new Set(rows.map(r=>r[key]).filter(v=>v!==null && v!==undefined && v!==''))]}
function fillSelect(id, values, all){
 $(id).replaceChildren(new Option(all,''));
 values.forEach(v=>$(id).add(new Option(v,v)));
}
function remember(){
 state[active]=Object.fromEntries(['year','month','product','unit','search'].map(id=>[id,$(id).value]));
 if(isVolume()){state[active].volumeUnit=$('volumeUnit').value;state[active].volumePhase=$('volumePhase').value}
}
function activate(name, reset=false){
 active=name;
 const c=config(), rows=datasets[name].rows;
 document.querySelectorAll('[data-view]').forEach(b=>b.querySelector('span').textContent=fmt(datasets[b.dataset.view].rows.length,0));
 document.querySelectorAll('[data-view]').forEach(b=>{
  const selected=b.dataset.view===name;
  b.classList.toggle('active',selected);
  b.setAttribute('aria-pressed',selected);
 });
 $('viewTitle').textContent=name==='emission_factor'?c.title:c.title+'ปิโตรเลียม';
 $('viewSubtitle').textContent=c.subtitle;
 $('tableTitle').textContent=c.title;
 $('searchLabel').textContent=c.groupLabel;
 $('search').placeholder=c.search;
 $('source').textContent=datasets[name].source;
 const years=unique('year',rows).sort((a,b)=>b-a);
 $('range').textContent=name==='emission_factor'
  ?fmt(rows.length,0)+' Factors · '+fmt(unique('unit',rows).length,0)+' หน่วย'
  :rows.length ? fmt(rows.length,0)+' รายการ · '+years.at(-1)+'–'+years[0] : '0 รายการในตารางนี้';
 fillSelect('year',years,'ทุกปี');
 fillSelect('product',unique('product_name',rows).sort(),'ทุกผลิตภัณฑ์');
 fillSelect('unit',unique(active==='sale'?'currency':'unit',rows).sort(),active==='sale'?'ทุกสกุลเงิน':'ทุกหน่วย');
 $('unitLabel').textContent=active==='sale'?'สกุลเงิน':'หน่วย';
 $('yearBox').hidden=active==='emission_factor';
 $('monthBox').hidden=active==='reserve'||active==='emission_factor';
 $('month').disabled=active==='reserve'||active==='emission_factor';
 $('volumeControls').hidden=!isVolume();
 const chosen=reset?{}:state[name]||{year:String(years[0]??'')};
 ['year','month','product','unit','search'].forEach(id=>$(id).value=chosen[id]||'');
 if(isVolume()){$('volumeUnit').value=chosen.volumeUnit||'boe';$('volumePhase').value=chosen.volumePhase||'liquid'}
 update();
}
function measure(){
 const c=config();
 if(isBoe())return {key:active==='reserve'?'mmboe':'boe_volume',kind:active,label:active==='reserve'?'ปริมาณสำรองรวมเทียบเท่า':active==='production'?'อัตราผลิตรวมเฉลี่ย':'อัตราจัดหารวมเฉลี่ย',unit:active==='reserve'?'MMBOE':'BOED',method:'boe'};
 if(isVolume()){
  const family=$('volumePhase').value;
  return {key:volumeKey(),family,label:(active==='production'?'ปริมาณผลิต':'ปริมาณจัดหา')+(family==='gas'?'ก๊าซรวม':'ของเหลวรวม'),unit:volumeUnit(family),method:'sum'};
 }
 if(active==='emission_factor')return {key:null,label:'จำนวน Factor',unit:'รายการ',method:'count'};
 if(!filtered.length)return {key:null,label:'จำนวนรายการ',unit:'รายการ'};
 if(active==='sale' && unique('currency').length===1){
  return {key:c.metric,label:'มูลค่าจำหน่าย',unit:unique('currency')[0],method:'sum'};
 }
 if(active!=='sale' && unique('unit').length===1 && unique('unit')[0]!=='ไม่ระบุ' && unique('product_name').length===1){
  return {key:c.metric,label:active==='reserve'?'ปริมาณสำรอง':active==='supply'?'อัตราจัดหาเฉลี่ยต่อรายการ':'อัตราผลิตเฉลี่ยต่อรายการ',
          unit:unique('unit')[0],method:active==='reserve'?'sum':'mean'};
 }
 return {key:null,label:'จำนวนรายการ',unit:'รายการ',method:'count'};
}
function valueOf(rows,m,periodRows=rows){
 if(m.method==='boe')return BoeMath.aggregate(rows,m.kind,periodRows);
 if(m.family)return VolumeMath.total(rows,m.family,m.key);
 if(!m.key)return rows.length;
 return m.method==='mean'?average(m.key,rows):sum(m.key,rows);
}
function update(){
 const c=config(), q=$('search').value.trim().toLowerCase();
 filtered=datasets[active].rows.filter(r=>
  (!$('year').value||r.year==$('year').value)&&
  (active==='reserve'||active==='emission_factor'||!$('month').value||r.month==$('month').value)&&
  (!$('product').value||r.product_name===$('product').value)&&
  (!$('unit').value||r[active==='sale'?'currency':'unit']===$('unit').value)&&
  (!q||[r[c.group],r.block,r.activity_type,r.basis].filter(Boolean).join(' ').toLowerCase().includes(q))
 );
 filtered.sort((a,b)=>b.year-a.year||(b.month||0)-(a.month||0));
 $('boeControls').hidden=!isBoe();$('volumePhaseBox').hidden=isBoe();
 if(isBoe())filtered=filtered.map(r=>({...BoeMath.convert(r,active,$('gasBoe').value,$('condBoe').value),gas_boe_per_mmscf:$('gasBoe').value,condensate_boe_per_bbl:$('condBoe').value}));
 if(isVolume()){
  const families=[...new Set(filtered.map(r=>r.volume_family).filter(Boolean))];
  if(families.length===1)$('volumePhase').value=families[0];
 }
 if(isVolume()&&!isBoe())filtered=filtered.map(r=>({...r,monthly_volume:r[volumeKey()],monthly_unit:volumeUnit(r.volume_family)}));
 page=1;
 const m=measure(), multiReserve=active==='reserve'&&unique('year').length>1;
 const mainValue=multiReserve?null:valueOf(filtered,m);
 $('metricLabel').textContent=m.label+(multiReserve?' · เลือกปีเพื่อรวมยอด':'');
 $('sales').textContent=filtered.length?fmt(mainValue,m.key?2:0):'—';
 $('moneyUnit').textContent=m.unit==='ไม่ระบุ'?'ต้นทางไม่ระบุสกุลเงิน':m.unit;
 $('secondLabel').textContent=active==='sale'?'ค่าภาคหลวงรวม':c.groupLabel+'ที่มีข้อมูล';
 $('royalty').textContent=active==='sale'?(unique('currency').length<=1?fmt(sum('royalty')):'หลายสกุลเงิน'):fmt(unique(c.group).length,0);
 $('royaltyDetail').textContent=active==='sale'?'ผลรวมตามตัวกรองปัจจุบัน':c.groupLabel;
 $('thirdLabel').textContent=active==='sale'?'ปริมาตรของเหลวรวม':'ผลิตภัณฑ์ที่มีข้อมูล';
 $('volume').textContent=active==='sale'?fmt(sum('volume_bbl')):fmt(unique('product_name').length,0);
 $('volumeDetail').textContent=active==='sale'?'บาร์เรล · แยกจากปริมาตรก๊าซ':'จำนวนชนิดตามตัวกรอง';
 $('records').textContent=fmt(filtered.length,0);
 $('fields').textContent='จากทั้งหมด '+fmt(datasets[active].rows.length,0)+' รายการ';
 if(isVolume()&&!isBoe()){
  const activity=active==='production'?'ผลิต':'จัดหา',liquid=VolumeMath.total(filtered,'liquid',volumeKey()),gas=VolumeMath.total(filtered,'gas',volumeKey());
  $('metricLabel').textContent='ปริมาณ'+activity+'ของเหลวรวม';$('sales').textContent=fmt(liquid);
  $('moneyUnit').textContent=volumeUnit('liquid')+' · น้ำมันดิบ + คอนเดนเสท · เฉพาะรายการที่คำนวณได้';
  $('secondLabel').textContent='ปริมาณ'+activity+'ก๊าซรวม';$('royalty').textContent=fmt(gas);
  $('royaltyDetail').textContent=volumeUnit('gas')+' · ไม่รวมกับปริมาณของเหลว';
  const valid=filtered.filter(r=>r.monthly_m3!==null).length;
  $('thirdLabel').textContent='รายการที่คำนวณปริมาณได้';$('volume').textContent=fmt(valid,0)+' / '+fmt(filtered.length,0);
  $('volumeDetail').textContent='ขาดหรือไม่ถูกต้อง '+fmt(filtered.length-valid,0)+' รายการ · ไม่แทนด้วยศูนย์';
 }
 if(isBoe()){
  const valid=filtered.filter(r=>r.boe_volume!==null).length;
  $('metricLabel').textContent=m.label+(multiReserve?' · เลือกปีเดียว':'');
  $('sales').textContent=fmt(mainValue);
  $('moneyUnit').textContent=m.unit+(active==='reserve'?' · ล้านบาร์เรลเทียบเท่าน้ำมันดิบ':' · เฉลี่ยต่อวันปฏิทินของเดือนในผลกรอง');
  if(isVolume()){
   $('secondLabel').textContent='ปริมาณรวมในช่วงที่เลือก';
   $('royalty').textContent=fmt(BoeMath.aggregate(filtered,'reserve'),6);
   $('royaltyDetail').textContent='MMBOE · ล้านบาร์เรลเทียบเท่าน้ำมันดิบ';
  }
  $('thirdLabel').textContent='รายการที่แปลงเป็น BOE ได้';$('volume').textContent=fmt(valid,0)+' / '+fmt(filtered.length,0);
  $('volumeDetail').textContent='ขาดหรือไม่ถูกต้อง '+fmt(filtered.length-valid,0)+' รายการ · ยอดรวมเฉพาะข้อมูลที่คำนวณได้';
 }
 if(active==='emission_factor'){
  $('metricLabel').textContent='จำนวน Emission Factor';
  $('sales').textContent=fmt(filtered.length,0);
  $('moneyUnit').textContent='รายการตามตัวกรอง';
  $('secondLabel').textContent='ชนิดเชื้อเพลิง';
  $('royalty').textContent=fmt(unique('product_name').length,0);
  $('royaltyDetail').textContent='กลุ่มสินค้าในผลกรอง';
  $('thirdLabel').textContent='ชนิดหน่วย';
  $('volume').textContent=fmt(unique('unit').length,0);
  $('volumeDetail').textContent='แสดงหน่วยที่มีในผลกรอง';
  $('trendTitle').textContent='ค่า Factor ตามเชื้อเพลิง';
  $('trendCaption').textContent=$('unit').value?'kgCO₂e ต่อ '+$('unit').value+' · เรียงจากค่าสูง':'เลือกหน่วยเดียวเพื่อเปรียบเทียบค่า Factor';
  $('rankTitle').textContent='จำนวน Factor ตามเชื้อเพลิง';
  $('rankCaption').textContent='จำนวนรายการ · ไม่นำค่า Factor ต่างหน่วยมารวมกัน';
 }
 if(active!=='emission_factor'){
  $('trendTitle').textContent=m.label+(active==='reserve'?'รายปี':'รายเดือน');
  $('trendCaption').textContent=m.unit+(m.method==='mean'?' · ค่าเฉลี่ยของรายการที่มีค่าในแต่ละเดือน':'');
  if(m.method==='boe')$('trendCaption').textContent=m.unit+(active==='reserve'?' · ปริมาณสำรองแต่ละปี ไม่บวกยอดข้ามปี':' · ผลรวม BOE ในเดือน ÷ วันปฏิทินของเดือนนั้น');
  $('rankTitle').textContent=c.groupLabel+' 5 อันดับ';
  $('rankCaption').textContent=m.label+(multiReserve?' · โปรดเลือกปี':' · '+m.unit);
 }
 const negative=filtered.filter(r=>numericValues(r).some(v=>v<0)).length;
 let note='ค่าติดลบ '+negative+' รายการ · ค่าว่างแสดงเป็น —';
 if(!m.key && filtered.length)note+=' · เลือกผลิตภัณฑ์และหน่วยเดียวกันเพื่อดูตัวเลขปริมาณ';
 if(active==='sale'&&unique('currency').includes('ไม่ระบุ'))note+=' · ต้นทางไม่ได้ระบุสกุลเงิน';
 if(isVolume()&&!isBoe())note+=' · '+(active==='production'?'ปริมาณผลิตคูณด้วย production_days ของแต่ละรายการ':'ปริมาณจัดหาเป็นค่าประมาณจากอัตราเฉลี่ย × วันปฏิทินในแต่ละเดือน')+' · 1 bbl = 0.158987294928 m³; 1 MMSCF = 28,316.846592 Sm³ · Sm³ คือปริมาตรก๊าซมาตรฐานตามเงื่อนไขต้นทาง · ไม่รวมก๊าซกับของเหลวเป็นยอดเดียว และไม่ใช่พลังงานเทียบเท่า';
 if(isBoe())note+=' · BOE เป็นค่าประมาณเทียบเท่าพลังงาน ไม่ใช่ปริมาตรจริง · ก๊าซ '+$('gasBoe').value+' BOE/MMSCF; คอนเดนเสท '+$('condBoe').value+' BOE/bbl (ค่าเริ่มต้นอนุมานจาก CSV การผลิต) · ผลิตใช้ oil_equivalent ต้นทางเมื่อมีค่า และคูณวันผลิตจริง · จัดหาคูณวันปฏิทิน · BOED = BOE รวม ÷ วันปฏิทินรวมของเดือนที่มีข้อมูล ไม่บวกอัตรารายวันข้ามเดือน · ช่วงเดือนที่ไม่มีข้อมูลทั้งชุดจะไม่อยู่ในตัวหาร และข้อมูลที่ขาดไม่แทนด้วยศูนย์';
 if(active==='emission_factor')note='ค่า Factor แสดงเป็น kgCO₂e ต่อหน่วยเชื้อเพลิง · ไม่ใช่ยอดปล่อยจริง · ต้องมีปริมาณเชื้อเพลิงที่ใช้และหน่วยตรงกันจึงคำนวณการปล่อยจริงได้';
 if(multiReserve)note+=' · ปริมาณสำรองแสดงแยกรายปี เลือกปีเดียวเพื่อจัดอันดับบล็อก';
 if(!datasets[active].rows.length)note=loadedAt?'ตารางนี้ยังไม่มีข้อมูลใน MySQL สามารถ export หัวคอลัมน์ CSV ได้':'ยังไม่ได้รับข้อมูลจาก MySQL';
 if(datasets[active].rejected)note+=' · ข้าม '+datasets[active].rejected+' แถวที่รูปแบบไม่ถูกต้อง';
 $('notice').textContent=note;
 renderTable();renderBars(m,multiReserve);draw(m);
}
function numericValues(r){return displayColumns().filter(([k])=>numeric.has(k)&&!['year','month'].includes(k)).map(([k])=>r[k]).filter(v=>v!==null&&v!==undefined)}
function renderTable(){
 const cols=displayColumns(), pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(page,pages);
 $('headers').innerHTML=cols.map(([k,title])=>'<th class="'+(numeric.has(k)?'num':'')+'">'+esc(title)+'</th>').join('');
 $('body').innerHTML=filtered.length?filtered.slice((page-1)*pageSize,page*pageSize).map(r=>'<tr>'+cols.map(([k])=>{
  const v=r[k],n=numeric.has(k);
  const text=k==='year'&&v!==null?String(v):n?fmt(v,['mmboe','gas_boe_per_mmscf','condensate_boe_per_bbl'].includes(k)?6:k==='factor_value'?4:['month','production_days','volume_days'].includes(k)?0:2):esc(v||'—');
  return '<td class="'+(n?'num ':'')+(n&&v<0?'negative':'')+'">'+(k==='product_name'?'<span class="pill">'+text+'</span>':text)+'</td>';
 }).join('')+'</tr>').join(''):'<tr><td colspan="'+cols.length+'" class="empty">'+(datasets[active].rows.length?'ไม่พบข้อมูลตามตัวกรอง':'ยังไม่มีข้อมูลในชุดนี้ · นำเข้า CSV เพื่อเริ่มต้น')+'</td></tr>';
 $('page').textContent=page+' / '+pages;
 $('prev').disabled=page<=1;$('next').disabled=page>=pages;
 $('pageInfo').textContent=filtered.length?'แสดง '+((page-1)*pageSize+1)+'–'+Math.min(page*pageSize,filtered.length)+' จาก '+fmt(filtered.length,0)+' รายการ':'0 รายการ';
 $('export').textContent=filtered.length?'Export ผลกรอง CSV':'Export หัวคอลัมน์ CSV';
 $('exportAll').textContent='Export ทั้งหมด ('+fmt(datasets[active].rows.length,0)+')';
}
function grouped(rows,key){
 const map=new Map();
 rows.forEach(r=>{const name=r[key]||'ไม่ระบุ';if(!map.has(name))map.set(name,[]);map.get(name).push(r)});
 return map;
}
function renderBars(m,disabled){
 if(disabled){$('bars').innerHTML='<div class="empty">เลือกปีเดียวเพื่อเปรียบเทียบปริมาณสำรอง</div>';return}
 if(active==='emission_factor'){
  const counts=[...grouped(filtered,'product_name')].map(([name,rows])=>[name,rows.length]).sort((a,b)=>b[1]-a[1]);
  const maximum=Math.max(1,...counts.map(r=>r[1]));
  $('bars').innerHTML=counts.length?counts.map(([name,count])=>'<div class="bar-row"><div class="bar-meta"><span title="'+esc(name)+'">'+esc(name)+'</span><span>'+fmt(count,0)+' Factor</span></div><div class="track"><div class="fill" style="width:'+count/maximum*100+'%"></div></div></div>').join(''):'<div class="empty">ไม่มีข้อมูลสำหรับจัดอันดับ</div>';
  return;
 }
 const top=[...grouped(filtered,config().group)].map(([name,r])=>[name,valueOf(r,m,filtered)]).filter(r=>r[1]!==null).sort((a,b)=>b[1]-a[1]).slice(0,5);
 const maximum=Math.max(1,...top.map(r=>Math.abs(r[1])));
 $('bars').innerHTML=top.length?top.map(([name,v])=>'<div class="bar-row"><div class="bar-meta"><span title="'+esc(name)+'">'+esc(name)+'</span><span>'+compact(v)+'</span></div><div class="track"><div class="fill" style="width:'+Math.abs(v)/maximum*100+'%;background:'+(v<0?'#b74f32':'#136c54')+'"></div></div></div>').join(''):'<div class="empty">ไม่มีข้อมูลสำหรับจัดอันดับ</div>';
}
function draw(m=measure()){
 const canvas=$('trend'),w=canvas.clientWidth,h=270,dpr=devicePixelRatio||1;
 canvas.width=w*dpr;canvas.height=h*dpr;
 const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.font='11px Arial';ctx.fillStyle='#687773';
 if(active==='emission_factor'){
  ctx.clearRect(0,0,w,h);
  const unit=$('unit').value;
  if(!unit){ctx.fillText('เลือกหน่วยจากตัวกรองเพื่อเปรียบเทียบค่า Factor ในหน่วยเดียวกัน',24,135);canvas.setAttribute('aria-label','เลือกหน่วยเพื่อแสดงกราฟค่า Factor');return}
  const rows=filtered.slice().sort((a,b)=>b.factor_value-a.factor_value).slice(0,8);
  if(!rows.length){ctx.fillText('ไม่มีข้อมูลสำหรับหน่วยนี้',24,135);canvas.setAttribute('aria-label','ไม่มีข้อมูล');return}
  const max=Math.max(1,...rows.map(r=>r.factor_value)),labelWidth=Math.min(310,Math.max(130,w*.48)),barX=labelWidth+20,barWidth=Math.max(50,w-barX-82),rowHeight=29;
  rows.forEach((r,i)=>{
   const y=24+i*rowHeight;
   let label=r.activity_type||r.factor_id;
   while(label.length>12&&ctx.measureText(label+'…').width>labelWidth)label=label.slice(0,-2);
   if(label!==(r.activity_type||r.factor_id))label+='…';
   ctx.fillStyle='#687773';ctx.textAlign='left';ctx.fillText(label,12,y+12,labelWidth);
   ctx.fillStyle='#eff3ed';ctx.fillRect(barX,y,barWidth,12);
   ctx.fillStyle='#136c54';ctx.fillRect(barX,y,Math.max(2,r.factor_value/max*barWidth),12);
   ctx.fillStyle='#172d29';ctx.textAlign='right';ctx.fillText(fmt(r.factor_value,4),w-12,y+11);
  });
  canvas.setAttribute('aria-label','ค่า Factor สูงสุดใน '+unit+': '+rows.map(r=>r.activity_type+' '+fmt(r.factor_value,4)).join('; '));return;
 }
 const groups=new Map();
 filtered.forEach(r=>{const period=String(r.year)+(active==='reserve'?'':'-'+String(r.month).padStart(2,'0'));if(!groups.has(period))groups.set(period,[]);groups.get(period).push(r)});
 const data=[...groups].sort((a,b)=>a[0].localeCompare(b[0])).map(([k,r])=>[k,valueOf(r,m)]);
 const values=data.map(r=>r[1]).filter(v=>v!==null);
 if(!values.length){ctx.fillText('No data',45,130);canvas.setAttribute('aria-label','ไม่มีข้อมูล');return}
 const max=Math.max(1,...values),min=Math.min(0,...values),left=65,right=w-25,top=28,bottom=225;
 const x=i=>left+(right-left)*(data.length===1?.5:i/(data.length-1)),y=v=>bottom-(v-min)/(max-min)*(bottom-top);
 for(let i=0;i<=4;i++){const v=min+(max-min)*i/4,yy=y(v);ctx.strokeStyle='#edf1ea';ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();ctx.fillText(compact(v),8,yy+3)}
 ctx.strokeStyle='#136c54';ctx.fillStyle='#136c54';ctx.lineWidth=2.5;ctx.beginPath();let connected=false;
 data.forEach((r,i)=>{if(r[1]===null){connected=false;return}if(connected)ctx.lineTo(x(i),y(r[1]));else ctx.moveTo(x(i),y(r[1]));connected=true});ctx.stroke();
 data.forEach((r,i)=>{if(r[1]!==null&&data.length<=24){ctx.beginPath();ctx.arc(x(i),y(r[1]),3,0,Math.PI*2);ctx.fill()}});
 ctx.fillStyle='#687773';ctx.textAlign='center';
 const step=Math.max(1,Math.ceil(data.length/6));data.forEach((r,i)=>{if(i%step===0)ctx.fillText(r[0],x(i),249)});
 canvas.setAttribute('aria-label',m.label+' '+data.map(([k,v])=>k+' '+fmt(v)).join('; '));
}
function downloadCSV(rows,filename){
 if(isBoe())rows=rows.map(r=>({...BoeMath.convert(r,active,$('gasBoe').value,$('condBoe').value),gas_boe_per_mmscf:$('gasBoe').value,condensate_boe_per_bbl:$('condBoe').value}));
 else if(isVolume())rows=rows.map(r=>({...r,monthly_volume:r[volumeKey()],monthly_unit:volumeUnit(r.volume_family)}));
 const cols=displayColumns().map(([k])=>k);
 const quote=(v,isNumeric=false)=>{
  let s=String(v??'');
  if(!isNumeric&&typeof v==='string'&&/^[=+\-@\t\r]/.test(s))s="'"+s;
  return '"'+s.replace(/"/g,'""')+'"';
 };
 const csv=[cols.map(v=>quote(v)).join(','),...rows.map(r=>cols.map(k=>quote(r._raw?.[k] ?? r[k],numeric.has(k))).join(','))].join('\r\n');
 const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{remember();activate(b.dataset.view)});
['year','month','product','unit'].forEach(id=>$(id).onchange=update);
$('search').oninput=update;
$('reset').onclick=()=>{['year','month','product','unit','search'].forEach(id=>$(id).value='');update()};
$('prev').onclick=()=>{page--;renderTable()};$('next').onclick=()=>{page++;renderTable()};
$('export').onclick=()=>downloadCSV(filtered,config().filename+'_filtered.csv');
$('exportAll').onclick=()=>downloadCSV(datasets[active].rows,config().filename+'_all.csv');
 ['volumeUnit','volumePhase'].forEach(id=>$(id).onchange=update);
 ['gasBoe','condBoe'].forEach(id=>$(id).oninput=update);

window.addEventListener('resize',()=>draw());
async function refreshData(){
 const controls=[...document.querySelectorAll('button,input,select')];
 controls.forEach(el=>el.disabled=true);
 $('refresh').textContent='กำลังโหลด…';
 $('connection').textContent='กำลังอ่านข้อมูลจาก MySQL…';
 try{
  const response=await fetch('/api/data',{cache:'no-store'});
  const payload=await response.json();
  if(!response.ok)throw Error(payload.error+(payload.code?' (MySQL '+payload.code+')':''));
  const prepared={};
  for(const name of Object.keys(configs)){
   const incoming=payload.datasets[name];
   if(!incoming||!Array.isArray(incoming.rows))throw Error('รูปแบบข้อมูลจากเซิร์ฟเวอร์ไม่ถูกต้อง');
   prepared[name]={...incoming,rows:incoming.rows.map(row=>{
    const result={...row,_raw:{...row}};
    for(const key of numeric){
     if(result[key]!==undefined&&result[key]!==null){
      result[key]=Number(result[key]);
      if(!Number.isFinite(result[key]))throw Error('พบค่าตัวเลขไม่ถูกต้องใน '+name);
     }
    }
    return name==='production'||name==='supply'?VolumeMath.convert(result,name):result;
   })};
  }
  if(loadedAt)remember();
  Object.assign(datasets,prepared);
  loadedAt=payload.loaded_at;
  $('connection').textContent='เชื่อมต่อ MySQL สำเร็จ · โหลดล่าสุด '+new Date(loadedAt).toLocaleString('th-TH')+' · กดรีเฟรชเพื่อรับข้อมูลที่เปลี่ยนในฐาน';
  document.querySelector('.status').textContent='ข้อมูลจาก MySQL';
 }catch(error){
  $('connection').textContent='โหลดไม่สำเร็จ: '+error.message+(loadedAt?' · กำลังแสดงข้อมูลรอบเดิม':' · ตรวจ .env และ MySQL แล้วกดรีเฟรช');
  document.querySelector('.status').textContent=loadedAt?'ข้อมูล MySQL รอบก่อน':'ยังเชื่อม MySQL ไม่สำเร็จ';
 }finally{
  controls.forEach(el=>el.disabled=false);
  $('refresh').textContent='รีเฟรชจาก MySQL';
  activate(active);
 }
}
$('refresh').onclick=refreshData;
activate(active);
refreshData();
