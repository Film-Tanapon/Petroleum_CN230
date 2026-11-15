const {test}=require('node:test');
const assert=require('node:assert/strict');
const {convert,aggregate}=require('../Dashborad/boe-math.js');
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);
test('production preserves source BOED and calendar-average differs from operating-day rate',()=>{
 const r=convert({product_name:'Natural Gas',unit:'MMSCFD',quantity:1,oil_equivalent:174.4,production_days:10,year:2025,month:4},'production');
 near(r.boe_rate,174.4);near(r.boe_volume,1744);near(aggregate([r],'production'),1744/30);
});
test('supply converts gas/condensate and combines on one calendar denominator',()=>{
 const base={year:2024,month:2};
 const gas=convert({...base,product_name:'Natural Gas',unit:'MMSCFD',daily_rate:1},'supply');
 const cond=convert({...base,product_name:'Condensate',unit:'BBLD',daily_rate:100},'supply');
 near(aggregate([gas,cond],'supply'),174.4+90.96);
});
test('multiple months are weighted by days, not summed or averaged per record',()=>{
 const rows=[convert({product_name:'Crude Oil',unit:'BBLD',daily_rate:100,year:2025,month:1},'supply'),convert({product_name:'Crude Oil',unit:'BBLD',daily_rate:200,year:2025,month:2},'supply')];
 near(aggregate(rows,'supply'),(3100+5600)/59);
});
test('reserves convert Bcf and MMbbl into MMBOE',()=>{
 const gas=convert({product_name:'Natural Gas',unit:'Bcf',proven_reserves:1},'reserve');
 const oil=convert({product_name:'Crude Oil',unit:'MMbbl',proven_reserves:1},'reserve');
 const cond=convert({product_name:'Condensate',unit:'MMbbl',proven_reserves:1},'reserve');
 near(gas.mmboe,0.1744);near(aggregate([gas,oil,cond],'reserve'),2.084);
});
test('unknowns and conflicting source equivalents stay unknown; zero is preserved',()=>{
 const r={product_name:'Natural Gas',unit:'MMSCFD',quantity:1,production_days:31,year:2025,month:1};
 assert.equal(convert({...r,oil_equivalent:0},'production').boe_volume,null);
 assert.equal(convert({...r,quantity:null},'production').boe_volume,null);
 assert.equal(convert({...r,quantity:0,oil_equivalent:0},'production').boe_volume,0);
 assert.equal(convert({product_name:'Natural Gas',unit:'Bcf',proven_reserves:null},'reserve').mmboe,null);
 assert.equal(aggregate([],'supply'),null);
 assert.equal(convert(r,'production',0).boe_volume,null);
});
test('custom assumptions apply to estimates but not an explicit source equivalent',()=>{
 const base={product_name:'Natural Gas',unit:'MMSCFD',quantity:1,production_days:31,year:2025,month:1};
 near(convert(base,'production',200).boe_rate,200);
 near(convert({...base,oil_equivalent:175},'production',200).boe_rate,175);
});
