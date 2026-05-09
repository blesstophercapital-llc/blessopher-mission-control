const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store'
  }
});

const trimDashboardData = (data = {}) => ({
  meta: data.meta,
  commandCenter: data.commandCenter,
  websiteAnalytics: data.websiteAnalytics,
  seoOpportunities: data.seoOpportunities,
  channelOps: data.channelOps,
  unitEconomics: data.unitEconomics,
  actionQueue: data.actionQueue,
  influencers: data.influencers,
  finance: data.finance,
  blockers: data.blockers
});

export async function onRequestPost({ request, env }) {
  const accessKey = request.headers.get('X-Mission-Control-Key') || '';
  if (!env.MISSION_CONTROL_TOM_KEY || accessKey !== env.MISSION_CONTROL_TOM_KEY) {
    return json({ error: 'Mission Control Tom access key required.' }, 401);
  }

  if (!env.HERMES_API_BASE || !env.HERMES_API_KEY) {
    return json({
      error: 'Hermes operator bridge is not configured. Set HERMES_API_BASE and HERMES_API_KEY in Cloudflare Pages environment variables.'
    }, 503);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'Invalid JSON body.' }, 400);
  }

  const message = String(body.message || '').trim();
  if (!message) return json({ error: 'Missing message.' }, 400);
  if (message.length > 4000) return json({ error: 'Message too long.' }, 413);

  const missionControlData = trimDashboardData(body.missionControlData || {});
  const clientId = String(body.clientId || 'browser').replace(/[^a-zA-Z0-9_.:-]/g, '').slice(0, 80) || 'browser';
  const hermesBase = env.HERMES_API_BASE.replace(/\/$/, '');

  const system = `You are Tom embedded inside Maintane Mission Control for Mr. Bless. Be concise, data-backed, direct, and operational. Use the provided mission-control.json context first. You may use Hermes tools if the backend exposes them, but do not send emails, outreach, payments, or irreversible external actions unless Mr. Bless directly orders that exact action. For sensitive actions, summarize the intended action and request confirmation. Mission Control information architecture: Command Center, Revenue, Channels, Marketing with creators inside Marketing, Product & Inventory combined, Customers, Finance, Tasks, Data Health, Tom. There is no separate Launch section.`;

  const user = `Dashboard context JSON:\n${JSON.stringify(missionControlData).slice(0, 60000)}\n\nMr. Bless asks:\n${message}`;

  let upstream;
  try {
    upstream = await fetch(`${hermesBase}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'authorization': `Bearer ${env.HERMES_API_KEY}`,
        'content-type': 'application/json',
        'X-Hermes-Session-Id': 'maintane-mission-control-tom',
        'X-Hermes-Session-Key': `maintane-mission-control:${clientId}`
      },
      body: JSON.stringify({
        model: env.HERMES_MODEL || 'hermes-agent',
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user }
        ],
        temperature: 0.2,
        stream: false
      })
    });
  } catch (error) {
    return json({ error: `Hermes API unreachable: ${error.message}` }, 502);
  }

  const text = await upstream.text();
  if (!upstream.ok) {
    return json({ error: `Hermes API error ${upstream.status}: ${text.slice(0, 1000)}` }, 502);
  }

  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    return json({ error: 'Hermes API returned non-JSON response.' }, 502);
  }

  const reply = payload.choices?.[0]?.message?.content || payload.output_text || payload.response || '';
  return json({ reply, backend: 'hermes-api-server', session: `maintane-mission-control:${clientId}` });
}

export async function onRequestOptions() {
  return new Response(null, { status: 204 });
}
