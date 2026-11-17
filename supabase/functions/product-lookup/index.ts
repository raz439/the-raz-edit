import { createClient } from 'npm:@supabase/supabase-js@2';
const cors={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization, x-client-info, apikey, content-type','Access-Control-Allow-Methods':'POST, OPTIONS'};
const reply=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{...cors,'Content-Type':'application/json'}});
const stores=[
  {domain:'asos.com',name:'ASOS'},{domain:'zara.com',name:'ZARA'},
  {domain:'mango.com',name:'MANGO'},{domain:'hm.com',name:'H&M'},
  {domain:'terminalx.com',name:'TERMINAL X'},{domain:'cos.com',name:'COS'},
  {domain:'urbanoutfitters.com',name:'URBAN OUTFITTERS'},
  {domain:'massimodutti.com',name:'MASSIMO DUTTI'},
  {domain:'pullandbear.com',name:'PULL&BEAR'},
  {domain:'bershka.com',name:'BERSHKA'},
  {domain:'stradivarius.com',name:'STRADIVARIUS'},
  {domain:'arket.com',name:'ARKET'}
];
const safeHost=(host,domain)=>host===domain||host.endsWith('.'+domain);
const meta=(html,key)=>{const tags=html.match(/<meta\\b[^>]*>/gi)||[];for(const tag of tags){const attrs={};for(const match of tag.matchAll(/([\\w:-]+)\\s*=\\s*(?:"([^"]*)"|'([^']*)')/g))attrs[match[1].toLowerCase()]=match[2]??match[3]??'';if(attrs.property===key||attrs.name===key)return attrs.content||''}return ''};
const decode=s=>s.replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;|&#x27;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').trim();
Deno.serve(async req=>{
 if(req.method==='OPTIONS')return new Response('ok',{headers:cors});
 if(req.method!=='POST')return reply({error:'Method not allowed'},405);
 const auth=req.headers.get('Authorization')||'';
 if(!auth.startsWith('Bearer '))return reply({error:'Login required'},401);
 const url=Deno.env.get('SUPABASE_URL'),key=Deno.env.get('SUPABASE_ANON_KEY');
 if(!url||!key)return reply({error:'Missing server configuration'},500);
 const db=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
 const {data:{user},error}=await db.auth.getUser(auth.slice(7));
 if(error||!user)return reply({error:'Invalid session'},401);
 const role=await db.from('profiles').select('role').eq('id',user.id).maybeSingle();
 if(role.error||role.data?.role!=='admin')return reply({error:'Admin only'},403);
 const body=await req.json().catch(()=>({}));
 if(typeof body.url!=='string'||body.url.length>2048)return reply({error:'Invalid product URL'},400);
 let target;try{target=new URL(body.url)}catch{return reply({error:'Invalid URL'},400)}
 const store=stores.find(s=>safeHost(target.hostname.toLowerCase(),s.domain));
 if(target.protocol!=='https:'||target.username||target.password||target.port||!store)return reply({error:'This store is not yet supported for automatic lookup'},400);
 // Never follow redirects to non-allowlisted hosts (or private-network addresses).
 let html='',current=target;
 try{
   for(let i=0;i<3;i++){
     const response=await fetch(current.toString(),{redirect:'manual',signal:AbortSignal.timeout(8000),headers:{'User-Agent':'Mozilla/5.0 (compatible; TheRazEdit/1.0)','Accept':'text/html'}});
     if(response.status>=300&&response.status<400){
       const loc=response.headers.get('location');if(!loc)throw Error('Invalid redirect');
       const next=new URL(loc,current);
       if(next.protocol!=='https:'||next.username||next.password||next.port||!stores.some(s=>safeHost(next.hostname.toLowerCase(),s.domain)))throw Error('Blocked redirect');
       current=next;continue;
     }
     if(!response.ok)throw Error('Store blocked metadata access');
     if(!(response.headers.get('content-type')||'').includes('text/html'))throw Error('Not HTML');
     const size=Number(response.headers.get('content-length')||0);
     if(size>1500000)throw Error('Page too large');
     html=(await response.text()).slice(0,1500000);break;
   }
 }catch{return reply({store:store.name,name:'',image:'',message:'לא הצלחנו לקרוא את פרטי המוצר מהחנות. אפשר למלא ידנית.'})}
 const title=decode(meta(html,'og:title')||meta(html,'twitter:title')||html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]||'');
 let image=decode(meta(html,'og:image')||meta(html,'twitter:image')||'');
 try{if(image){const u=new URL(image,current);image=u.protocol==='https:'?u.href:''}}catch{image=''}
 return reply({store:store.name,name:title.slice(0,180),image,message:title?'הפרטים זוהו. כדאי לבדוק שהתמונה והשם נכונים.':'לא נמצא שם מוצר. אפשר למלא אותו ידנית.'});
});
