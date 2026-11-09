(function(global){
 const CATEGORY_DEFS=[
  {id:"rail",label:"Železnice",icon:"fa-train",color:"#4f9b64"},
  {id:"bus",label:"Autobus",icon:"fa-bus",color:"#55add7"},
  {id:"tram",label:"Tramvaj",icon:"fa-tram",color:"#cf7180"},
  {id:"trolleybus",label:"Trolejbus",icon:"fa-bus-alt",color:"#718fbe"},
  {id:"metro",label:"Metro",icon:"fa-subway",color:"#9c70b8"},
  {id:"water",label:"Loď",icon:"fa-ship",color:"#4fa69d"},
  {id:"air",label:"Letadlo",icon:"fa-plane",color:"#8b79bd"},
  {id:"cableway",label:"Lanovka",icon:"fa-mountain",color:"#b28259"},
  {id:"other",label:"Ostatní",icon:"fa-compass",color:"#7b8084"}
 ];
 const CATEGORY_BY_ID=Object.fromEntries(CATEGORY_DEFS.map(c=>[c.id,c]));
 const categoryIds=e=>{const raw=Array.isArray(e.categories)&&e.categories.length?e.categories:(e.category?[e.category]:["other"]);const ids=raw.filter(id=>CATEGORY_BY_ID[id]);return ids.length?ids:["other"]};
 const categories=e=>categoryIds(e).map(id=>CATEGORY_BY_ID[id]);
 global.SK=Object.assign(global.SK||{},{CATEGORY_DEFS,CATEGORY_BY_ID,categoryIds,categories});
})(window);
