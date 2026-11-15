/* Monthly volumes; liquids and standard gas are kept in separate families. */
(function(root){
 'use strict';
 const BBL_M3=0.158987294928,SCF_M3=0.028316846592;
 function number(v){if(v===null||v===undefined||String(v).trim()==='')return null;const n=Number(v);return Number.isFinite(n)?n:null}
 function daysInMonth(year,month){
  year=number(year);month=number(month);
  if(!Number.isInteger(year)||year<1||!Number.isInteger(month)||month<1||month>12)return null;
  const leap=year%400===0||(year%4===0&&year%100!==0);
  return [31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1];
 }
 function convert(row,kind){
  const unit=String(row.unit??'').trim().toUpperCase().replace(/\s/g,'');
  let family,scale;
  if(['BBLD','BBL/D','BBL/DAY'].includes(unit)){family='liquid';scale=BBL_M3}
  else if(['MMSCFD','MMSCF/D','MMSCF/DAY'].includes(unit)){family='gas';scale=1e6*SCF_M3}
  else return {...row,volume_family:null,monthly_m3:null,monthly_native:null,volume_days:null,volume_reason:'ไม่รองรับหน่วยอัตรารายวัน'};
  const fail=reason=>({...row,volume_family:family,monthly_m3:null,monthly_native:null,volume_days:null,volume_reason:reason});
  const calendar=daysInMonth(row.year,row.month),days=kind==='production'?number(row.production_days):calendar;
  if(calendar===null)return fail('ปีหรือเดือนไม่ครบ');
  if(days===null||!Number.isInteger(days)||days<0||days>calendar)return fail('วันผลิตไม่ครบหรือไม่ถูกต้อง');
  const rate=number(kind==='production'?row.quantity:row.daily_rate);
  if(rate===null||rate<0)return fail('อัตรารายวันไม่มีค่าหรือเป็นลบ');
  const native=rate*days,m3=native*scale;
  if(!Number.isFinite(m3))return fail('ปริมาณเกินขอบเขต');
  return {...row,volume_family:family,monthly_m3:m3,monthly_native:native,volume_days:days,volume_reason:''};
 }
 function total(rows,family,key='monthly_m3'){
  const values=rows.filter(r=>r.volume_family===family&&r[key]!==null&&r[key]!==undefined).map(r=>r[key]);
  return values.length?values.reduce((a,b)=>a+b,0):null;
 }
 const api={convert,total,daysInMonth,BBL_M3,SCF_M3};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VolumeMath=api;
})(typeof globalThis!=='undefined'?globalThis:this);
