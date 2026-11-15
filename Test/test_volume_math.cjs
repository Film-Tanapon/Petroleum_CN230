const {test}=require('node:test');
const assert=require('node:assert/strict');
const {convert,total,BBL_M3,SCF_M3}=require('../Dashborad/volume-math.js');
test('production uses actual production days, not all calendar days',()=>{
 const r=convert({quantity:'10',production_days:2,year:2024,month:2,unit:'BBLD'},'production');
 assert.equal(r.monthly_native,20);assert.equal(r.monthly_m3,20*BBL_M3);
});
test('supply uses month length including leap February',()=>{
 const r=convert({daily_rate:'2',year:2024,month:2,unit:'MMSCFD'},'supply');
 assert.equal(r.volume_days,29);assert.equal(r.monthly_native,58);assert.ok(Math.abs(r.monthly_m3-58e6*SCF_M3)<1e-8);
 assert.equal(convert({daily_rate:2,year:2025,month:2,unit:'BBLD'},'supply').volume_days,28);
});
test('unknown values remain null and genuine zeros remain zero',()=>{
 const r={quantity:1,production_days:20,year:2025,month:3,unit:'BBLD'};
 for(const patch of [{production_days:null},{quantity:null},{production_days:32},{quantity:-1},{unit:'kg'},{month:13}])assert.equal(convert({...r,...patch},'production').monthly_m3,null);
 assert.equal(convert({...r,quantity:0},'production').monthly_m3,0);
 assert.equal(convert({...r,production_days:0},'production').monthly_m3,0);
});
test('gas and liquid aggregates stay separate; missing family is not zero',()=>{
 const rows=[convert({quantity:1,production_days:1,year:2025,month:1,unit:'BBLD'},'production'),convert({quantity:1,production_days:1,year:2025,month:1,unit:'MMSCFD'},'production')];
 assert.equal(total(rows,'liquid'),BBL_M3);assert.equal(total(rows,'gas'),1e6*SCF_M3);
 assert.equal(total([rows[0]],'gas'),null);
});
