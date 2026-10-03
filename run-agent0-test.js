import { seedDemoData, matchIncomingClaim } from './agent0-engine.js';
import 'dotenv/config';

async function executeSprintTest() {
  console.log("🚀 --- Starting Agent 0 Local Testing Sequence ---");

  // 1. Clear out any previous database entries and seed fresh data
  try {
    await seedDemoData();
  } catch (error) {
    console.error("❌ Seeding failed. Ensure your Supabase URL, Service Role Key, and SQL schema are correct.");
    process.exit(1);
  }

  console.log("\n🔍 --- Simulating Live WhatsApp Incoming Messages ---");

  // 2. Test Case A: A close semantic match using different wording than the database
  const userSimulatedForwardA = "Someone just told me the IEBC systems were compromised by hackers in Europe and numbers were modified!! Is this true??";
  console.log(`\n💬 User Forwards text: "${userSimulatedForwardA}"`);
  console.log("⏳ Processing semantic lookup...");

  const matchA = await matchIncomingClaim(userSimulatedForwardA);

  if (matchA) {
    console.log("✅ MATCH FOUND!");
    console.log(`   - Verified Verdict: ${matchA.verdict}`);
    console.log(`   - Closest Database Claim: "${matchA.claim}"`);
    console.log(`   - Confidence Level: ${Math.round(matchA.similarity * 100)}%`);
    console.log(`   - Source URL: ${matchA.source_url}`);
  } else {
    console.log("❌ No match found. Lower your similarity_threshold in the SQL function or verify your vector configurations.");
  }

  // 3. Test Case B: A completely unrelated message that should NOT trigger a match
  const userSimulatedForwardB = "Hey guys, can anyone recommend a good restaurant near Westlands for lunch today?";
  console.log(`\n💬 User Forwards text: "${userSimulatedForwardB}"`);
  console.log("⏳ Processing semantic lookup...");

  const matchB = await matchIncomingClaim(userSimulatedForwardB);

  if (!matchB) {
    console.log("✅ CLEAN FILTER: No unrelated match triggered. Guardrails are structurally intact.");
  } else {
    console.log(`⚠️ FALSE POSITIVE triggered: Matched with "${matchB.claim}" (${Math.round(matchB.similarity * 100)}%). Consider raising your similarity_threshold.`);
  }

  console.log("\n🏁 --- Testing Sequence Complete. Ready to wire up Twilio Gateway. ---");
  process.exit(0);
}

executeSprintTest();
