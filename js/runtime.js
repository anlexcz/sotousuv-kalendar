(function(){
  const onPages = location.hostname.endsWith('github.io');
  const first = location.pathname.split('/').filter(Boolean)[0] || '';
  const basePath = onPages && first ? '/' + first : '';
  const url = path => basePath + (path.startsWith('/') ? path : '/' + path);
  async function json(path){const r=await fetch(url(path),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
  function inRange(e,from,to){return (e.dates||[]).some(d=>(!from||d.ends_on>=from)&&(!to||d.starts_on<=to));}
  async function events(params={}){
    if(!onPages){
      const q=new URLSearchParams();Object.entries(params).forEach(([k,v])=>v!=null&&q.set(k,v));
      const r=await fetch('/api/events.php?'+q.toString());if(r.ok)return (await r.json()).events||[];
    }
    const data=await json('/data/events.json');let list=data.events||[];
    if(params.from||params.to)list=list.filter(e=>inRange(e,params.from,params.to));
    if(params.status)list=list.filter(e=>e.status===params.status);
    if(params.q){const s=String(params.q).toLowerCase();list=list.filter(e=>[e.id,e.title,e.city,e.place,e.region,e.route].join(' ').toLowerCase().includes(s));}
    return list;
  }
  async function event(id){
    if(!onPages){const r=await fetch('/api/event.php?id='+encodeURIComponent(id));if(r.ok)return (await r.json()).event;}
    const list=await events({});return list.find(e=>String(e.id)===String(id))||null;
  }
  window.SK_RUNTIME={onPages,basePath,url,events,event};
})();
