/* Pure scenario calculations shared with the regression tests. */
(function(root){
 'use strict';
 function number(value){
  if(value===null||value===undefined||String(value).trim()==='')return null;
  const n=Number(value);return Number.isFinite(n)?n:null;
 }
 function eligible(f){
  return String(f.unit).trim().toUpperCase()==='SCF' &&
   /^Stationary Source\s*-\s*Natural Gas \(NCV\)$/i.test(String(f.activity_type).trim()) &&
   /NCV/i.test(String(f.basis)) && number(f.factor_value)!==null && number(f.factor_value)>=0;
 }
 function calculate(row,factor,share){
  const fail=reason=>({...row,carbon_tonnes:null,gas_scf:null,reason});
  if(!factor||!eligible(factor))return fail('ไม่มี Factor ก๊าซธรรมชาติ NCV หน่วย SCF ที่รองรับ');
  if(String(row.product_id)!==String(factor.product_id))return fail('ผลิตภัณฑ์ไม่ตรงกับ Factor ก๊าซธรรมชาติ');
  if(String(row.unit).trim().toUpperCase()!=='MMSCFD')return fail('หน่วยผลิตไม่ใช่ MMSCFD');
  const quantity=number(row.quantity),days=number(row.production_days),year=number(row.year),month=number(row.month);
  if(quantity===null||quantity<0)return fail('ไม่มีปริมาณผลิตที่ใช้ได้');
  if(year===null||!Number.isInteger(year)||year<1||month===null||!Number.isInteger(month)||month<1||month>12)return fail('ปีหรือเดือนไม่ครบ');
  const leap=year%400===0||(year%4===0&&year%100!==0);
  const max=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1];
  if(days===null||!Number.isInteger(days)||days<0||days>max)return fail('วันผลิตไม่ครบหรือเกินวันในเดือน');
  const fraction=number(share);
  if(fraction===null||fraction<0||fraction>100)return fail('สัดส่วนต้องอยู่ระหว่าง 0 ถึง 100');
  const gas=quantity*1000000*days*fraction/100;
  const tonnes=gas*number(factor.factor_value)/1000;
  if(!Number.isFinite(tonnes))return fail('ผลคำนวณเกินขอบเขต');
  return {...row,gas_scf:gas,carbon_tonnes:tonnes,factor_id:factor.factor_id,factor_value:factor.factor_value,share:fraction,reason:''};
 }
 const api={number,eligible,calculate};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CarbonMath=api;
})(typeof globalThis!=='undefined'?globalThis:this);
