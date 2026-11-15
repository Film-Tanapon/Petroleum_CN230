const {test}=require('node:test');
const assert=require('node:assert/strict');
const {calculate,eligible}=require('../Dashborad/carbon-math.js');
const factor={factor_id:'EF-001',product_id:'P02',unit:'SCF',factor_value:'0.057300',activity_type:'Stationary Source - Natural Gas (NCV)',basis:'NCV (Net Calorific Value)'};
const row={product_id:'P02',unit:'MMSCFD',quantity:'2',production_days:29,year:2024,month:2};
test('converts daily rate, production days, kg to tonnes and selected share',()=>{
 assert.equal(calculate(row,factor,100).carbon_tonnes,3323.4);
 assert.equal(calculate(row,factor,50).carbon_tonnes,1661.7);
 assert.equal(calculate(row,factor,0).carbon_tonnes,0);
});
test('missing values remain unknown; zero is a valid observation',()=>{
 for(const change of [{quantity:null},{production_days:null},{quantity:''},{year:null},{month:13},{production_days:30},{quantity:-1}])assert.equal(calculate({...row,...change},factor,100).carbon_tonnes,null);
 assert.equal(calculate({...row,production_days:0},factor,100).carbon_tonnes,0);
});
test('rejects wrong product, rate unit and unsupported factor',()=>{
 assert.equal(calculate({...row,product_id:'P01'},factor,100).carbon_tonnes,null);
 assert.equal(calculate({...row,unit:'BBLD'},factor,100).carbon_tonnes,null);
 for(const f of [null,{...factor,unit:'MJ'},{...factor,activity_type:'Mobile Source'},{...factor,factor_value:null}])assert.equal(calculate(row,f,100).carbon_tonnes,null);
 assert.equal(eligible(factor),true);
});
test('uses leap-year calendar limits and validates scenario range',()=>{
 assert.equal(calculate({...row,year:2025},factor,100).carbon_tonnes,null);
 for(const fraction of [-1,101,NaN,null])assert.equal(calculate(row,factor,fraction).carbon_tonnes,null);
});
