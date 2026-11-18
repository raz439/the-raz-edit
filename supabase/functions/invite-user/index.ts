// Supabase Edge Function: invite-user
// Deploy with Supabase secrets SUPABASE_URL, SUPABASE_ANON_KEY,
// SUPABASE_SERVICE_ROLE_KEY (or service-role secret key in a secure environment).
import { createClient } from 'npm:@supabase/supabase-js@2';
const cors = {'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization, x-client-info, apikey, content-type','Access-Control-Allow-Methods':'POST, OPTIONS'};
Deno.serve(async (req) => {
  if (req.method==='OPTIONS') return new Response('ok',{headers:cors});
  const respond=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{...cors,'Content-Type':'application/json'}});
  if(req.method!=='POST') return respond({error:'Method not allowed'},405);
  const bearer=req.headers.get('Authorization')||'';
  if(!bearer.startsWith('Bearer ')) return respond({error:'Login required'},401);
  const url=Deno.env.get('SUPABASE_URL'),publishable=Deno.env.get('SUPABASE_ANON_KEY'),secret=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
  if(!url||!publishable||!secret) return respond({error:'Missing server configuration'},500);
  const userClient=createClient(url,publishable,{auth:{persistSession:false,autoRefreshToken:false}});
  const {data:{user},error:authError}=await userClient.auth.getUser(bearer.slice(7));
  if(authError||!user) return respond({error:'Invalid session'},401);
  const {data:profile,error:roleError}=await userClient.from('profiles').select('role').eq('id',user.id).single();
  if(roleError||profile?.role!=='admin') return respond({error:'Admin only'},403);
  const body=await req.json().catch(()=>({}));
  const email=typeof body.email==='string'?body.email.trim().toLowerCase():'';
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return respond({error:'Invalid email'},400);
  const admin=createClient(url,secret,{auth:{persistSession:false,autoRefreshToken:false}});
  const {error}=await admin.auth.admin.inviteUserByEmail(email);
  if(error) return respond({error:error.message},400);
  return respond({ok:true});
});
