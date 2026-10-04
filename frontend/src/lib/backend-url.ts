const configuredBackend = process.env.AGENT_ZERO_API_URL?.trim();

export const backendUrl = configuredBackend
  ? `${configuredBackend.includes("://") ? "" : "http://"}${configuredBackend.replace(/\/+$/, "")}`
  : "http://127.0.0.1:18000";
