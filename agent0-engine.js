import { createClient } from '@supabase/supabase-js';
import { pipeline } from '@xenova/transformers';
import 'dotenv/config';

// Initialize Supabase Client
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY; // Use Service Role Key to bypass RLS during hackathon
const supabase = createClient(supabaseUrl, supabaseKey);

// Shared embedding pipeline token (cached locally after first run)
let embedder = null;
async function getEmbedder() {
  if (!embedder) {
    embedder = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');
  }
  return embedder;
}

/**
 * Helper: Converts text string into a 384-dimension numerical array (vector)
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

  for (const item of mockClaims) {
    const vector = await generateEmbedding(item.claim);
    
    const { error } = await supabase.from('fact_checks').insert({
      claim: item.claim,
      verdict: item.verdict,
      source_url: item.source_url,
      embedding: vector
    });

    if (error) console.error(`❌ Error inserting "${item.claim.slice(0,20)}...":`, error.message);
  }
  console.log("✅ Database successfully seeded and ready for match tests.");
}

/**
 * 🔍 MATCHING FUNCTION: Passes incoming WhatsApp messages against your database
 */
export async function matchIncomingClaim(incomingWhatsAppText) {
  try {
    // 1. Convert user's incoming message into a vector
    const queryVector = await generateEmbedding(incomingWhatsAppText);

    // 2. Call the Supabase RPC function (match_fact_checks) using pgvector
    const { data: matchedClaims, error } = await supabase.rpc('match_fact_checks', {
      query_embedding: queryVector,
      similarity_threshold: 0.5, // 50% semantic similarity floor to catch loose wording
      match_count: 1             // Top match only for a snappy WhatsApp response
    });

    if (error) throw error;

    if (matchedClaims && matchedClaims.length > 0) {
      return matchedClaims[0]; // Returns { claim, verdict, source_url, similarity }
    }
    
    return null;
  } catch (err) {
    console.error("🚨 Agent 0 Core Engine Error:", err.message);
    return null;
  }
}
