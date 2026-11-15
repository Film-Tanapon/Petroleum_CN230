/* Energy-equivalent display only. Database values and source units stay intact. */
(function(root){
 'use strict';
 const num=v=>v===null||v===undefined||String(v).trim()===''?null:(Number.isFinite(Number(v))?Number(v):null);
 function fuel(row){
  const name=String(row.product_name??'').trim().toLowerCase();
  if(['crude oil','น้ำมันดิบ'].includes(name))return 'oil';
  if(['natural gas','ก๊าซธรรมชาติ'].includes(name))return 'gas';
  if(['condensate','คอนเดนเสท'].includes(name))return 'condensate';
  return null;
 }
 function convert(row,kind,gas=174.4,condensate=0.9096){
  const fail=reason=>({...row,boe_rate:null,boe_volume:null,mmboe:null,boe_basis:'',boe_reason:reason});
  gas=num(gas);condensate=num(condensate);
  if(gas===null||gas<=0||condensate===null||condensate<=0)return fail('อัตราแปลงต้องเป็นจำนวนบวก');
  const product=fuel(row),unit=String(row.unit??'').trim().toUpperCase();
  if(!product)return fail('ไม่รองรับผลิตภัณฑ์นี้');
  const raw=num(kind==='reserve'?row.proven_reserves:kind==='supply'?row.daily_rate:row.quantity);
  if(raw===null||raw<0)return fail('ปริมาณต้นทางไม่มีค่าหรือเป็นลบ');
  let factor,basis;
  if(kind==='reserve'){
   if(product==='gas'&&unit==='BCF')factor=1000*gas/1e6;
   else if(product==='gas'&&unit==='MMSCF')factor=gas/1e6;
   else if(product!=='gas'&&unit==='MMBBL')factor=product==='oil'?1:condensate;
   else if(product!=='gas'&&unit==='BBL')factor=(product==='oil'?1:condensate)/1e6;
   else return fail('หน่วยสำรองไม่ตรงกับชนิดผลิตภัณฑ์');
   const mmboe=raw*factor;
   if(!Number.isFinite(mmboe))return fail('ผลคำนวณเกินขอบเขต');
   return {...row,boe_rate:null,boe_volume:mmboe*1e6,mmboe,boe_basis:product==='oil'?'น้ำมันดิบ 1 bbl = 1 BOE':`ประมาณการ: gas ${gas} BOE/MMSCF; condensate ${condensate} BOE/bbl`,boe_reason:''};
  }
  if((product==='gas'&&unit!=='MMSCFD')||(product!=='gas'&&unit!=='BBLD'))return fail('หน่วยอัตรารายวันไม่ตรงกับชนิดผลิตภัณฑ์');
  const source=num(row.oil_equivalent);
  let rate;
  if(kind==='production'&&product!=='oil'&&source!==null){
   if(source<0)return fail('oil_equivalent ติดลบ');
   if(raw>0&&source===0)return fail('oil_equivalent เป็นศูนย์แต่ปริมาณผลิตมากกว่าศูนย์ ต้องตรวจต้นทาง');
   rate=source;basis='oil_equivalent จากต้นทาง (BOED)';
  }else{
   factor=product==='oil'?1:product==='gas'?gas:condensate;
   rate=raw*factor;basis=product==='oil'?'น้ำมันดิบ 1 bbl = 1 BOE':`ประมาณการ: ${factor} BOE/${product==='gas'?'MMSCF':'bbl'}`;
  }
  const calendar=root.VolumeMath?.daysInMonth(row.year,row.month);
  const days=kind==='production'?num(row.production_days):calendar;
  if(calendar===null||calendar===undefined||days===null||!Number.isInteger(days)||days<0||days>calendar)return fail('วันที่ใช้คำนวณไม่ครบหรือไม่ถูกต้อง');
  const volume=rate*days;
  if(!Number.isFinite(volume))return fail('ผลคำนวณเกินขอบเขต');
  return {...row,boe_rate:rate,boe_volume:volume,mmboe:volume/1e6,boe_basis:basis,boe_reason:''};
 }
 function aggregate(rows,kind,periodRows=rows){
  const valid=rows.filter(r=>r.boe_volume!==null&&r.boe_volume!==undefined);
  if(!valid.length)return null;
  const total=valid.reduce((a,r)=>a+r.boe_volume,0);
  if(kind==='reserve')return total/1e6;
  // One calendar denominator per represented period, not per field/product row.
  const periods=new Map();
  periodRows.forEach(r=>{const days=root.VolumeMath?.daysInMonth(r.year,r.month);if(days!==null&&days!==undefined)periods.set(r.year+'-'+r.month,days)});
  const days=[...periods.values()].reduce((a,b)=>a+b,0);
  return days?total/days:null;
 }
 const api={convert,aggregate,fuel};
 if(typeof module!=='undefined'&&module.exports){
  // Node tests share the same calendar conversion as the browser.
  root.VolumeMath=require('./volume-math.js');module.exports=api;
 }else root.BoeMath=api;
})(typeof globalThis!=='undefined'?globalThis:this);
