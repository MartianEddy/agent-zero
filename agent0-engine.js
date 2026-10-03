import { createClient } from '@supabase/supabase-js';
import { pipeline } from '@xenova/transformers';
import 'dotenv/config';

let supabase = null;
function getSupabase() {
  if (!supabase) {
    const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY ||
      process.env.SUPABASE_SECRET_KEY ||
      process.env.SUPABASE_ANON_KEY ||
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    if (!supabaseUrl || !supabaseKey) {
      throw new Error('Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to enable claim matching.');
    }
    supabase = createClient(supabaseUrl, supabaseKey);
  }
  return supabase;
}

// Shared embedding pipeline token (cached locally after first run)
let embedder = null;
async function getEmbedder() {
  if (!embedder) {
    embedder = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');
  }
  return embedder;
}

/**
 * Helper: Converts text string into a 384-dimension numerical array (vect
 */
async function generateEmbedding(text) {
  const pipe = await getEmbedder();
  const output = await pipe(text, { pooling: 'mean', normalize: true });
  return Array.from(output.data);
}

/**
 * 🚀 SEED FUNCTION: Call this once to prime your database for the judges!
 */
export async function seedDemoData() {
  console.log("⏳ Seeding Agent 0 database with Kenyan election fact-checks...");
  
  const mockClaims = [
    {
      claim: "IEBC portal hacked and presidential results changed via an external server in Europe.",
      verdict: "❌ FALSE & FABRICATED",
      source_url: "https://pesacheck.org"
    },
    {
      claim: "Leaked audio of a leading political candidate planning to disrupt voting in Nairobi.",
      verdict: "🤖 DEEPFAKE / SYNTHETIC AUDIO",
      source_url: "https://africacheck.org"
    },
    {
      claim: "Media Council of Kenya bans specific media house from covering the 2027 general election.",
      verdict: "❌ MISLEADING / DOCTORED LETTER",
      source_url: "https://mediacouncil.or.ke"
    }
  ];

  const client = getSupabase();
  for (const item of mockClaims) {
    const vector = await generateEmbedding(item.claim);
    
    const { error } = await client.from('fact_checks').insert({
      claim: item.claim,
      verdict: item.verdict,
      source_url: item.source_url,
      embedding: vector
    });

    if (error) throw new Error(`Failed to insert demo claim "${item.claim.slice(0, 20)}...": ${error.message}`);
  }
  console.log("✅ Database successfully seeded and ready for match tests.");
}

/**
 * 🔍 MATCHING FUNCTION: Passes incoming WhatsApp messages against your database
 */
export async function matchIncomingClaim(incomingWhatsAppText) {
  if (typeof incomingWhatsAppText !== 'string' || !incomingWhatsAppText.trim()) {
    throw new TypeError('A non-empty claim is required for matching.');
  }
  const client = getSupabase();
  const queryVector = await generateEmbedding(incomingWhatsAppText);
  const { data: matchedClaims, error } = await client.rpc('match_fact_checks', {
    query_embedding: queryVector,
    similarity_threshold: 0.5,
    match_count: 1
  });

  if (error) throw new Error(`Supabase claim matching failed: ${error.message}`);
  return matchedClaims?.[0] ?? null;
}
