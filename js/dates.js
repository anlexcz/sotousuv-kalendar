(function(global){
 const DAY=86400000;
 const parseDate=s=>{const m=String(s||"").match(/(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})/);return m?new Date(+m[3],+m[2]-1,+m[1]):null};
 const dayStart=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate());
 const dateKey=d=>d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
 function occurrenceDates(e){
  const dates=[],add=(y,m,d)=>{const x=new Date(+y,+m-1,+d);if(!isNaN(x))dates.push(x)};
  if(e.recurring&&e.seriesDates){
   for(const raw of e.seriesDates.split(";")){
    const p=raw.trim();let m;
    if((m=p.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))){let a=new Date(+m[5],+m[2]-1,+m[1]),b=new Date(+m[5],+m[4]-1,+m[3]);for(let d=new Date(a);d<=b;d.setDate(d.getDate()+1))dates.push(new Date(d));continue}
    if((m=p.match(/^(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))){for(let d=+m[1];d<=+m[2];d++)add(m[4],m[3],d);continue}
    if((m=p.match(/^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$/))){add(m[3],m[2],m[1]);continue}
    if((m=p.match(/^(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.,?\s*(\d{1,2})\.\s*(\d{4})$/))){for(let d=+m[1];d<=+m[2];d++)add(m[4],m[3],d);continue}
   }
   if(dates.length)return dates;
  }
  const a=parseDate(e.from),b=parseDate(e.to||e.from);if(!a)return dates;
  const end=b||a;for(let d=new Date(a);d<=end;d.setDate(d.getDate()+1))dates.push(new Date(d));return dates
 }
 global.SK=Object.assign(global.SK||{},{DAY,parseDate,dayStart,dateKey,occurrenceDates});
})(window);
