const DEFAULT_ACCOUNTS_BASE = 'https://accounts.zoho.com';
const DEFAULT_API_BASE = 'https://www.zohoapis.com/inventory/v1';

function firstEnv(env, names, fallback = '') {
  for (const name of names) {
    const value = String(env[name] || '').trim();
    if (value) return value;
  }
  return fallback;
}

function defaultZohoInventory(status = 'missing_credentials', message = 'Set Zoho OAuth env vars to enable live inventory data.') {
  return {
    updatedLabel: 'Zoho unavailable',
    status,
    message,
    scorecards: [
      { label: 'Zoho stock on hand', value: '—', tone: 'amber', note: message, source: 'future:zoho' },
      { label: 'Zoho sales orders', value: '—', tone: 'amber', note: 'Requires Zoho Inventory API.', source: 'future:zoho' },
      { label: 'Zoho invoices', value: '—', tone: 'amber', note: 'Requires Zoho Inventory API.', source: 'future:zoho' },
    ],
    lowStockItems: [],
    recentSalesOrders: [],
    recentInvoices: [],
  };
}

function fmtInt(value) {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return '0';
  return Math.round(n).toLocaleString('en-US');
}

function qty(item) {
  for (const key of ['available_stock', 'actual_available_stock', 'stock_on_hand', 'quantity_available']) {
    const n = Number(item[key] || 0);
    if (Number.isFinite(n)) return n;
  }
  return 0;
}

function reorderLevel(item) {
  const n = Number(item.reorder_level || 0);
  return Number.isFinite(n) ? n : 0;
}

async function readJson(response) {
  const text = await response.text();
  let payload = {};
  try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = {}; }
  if (!response.ok) {
    const message = payload.message || payload.error || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function zohoGet(apiBase, path, accessToken, organizationId, params = {}) {
  const url = new URL(`${apiBase.replace(/\/$/, '')}/${path.replace(/^\//, '')}`);
  url.searchParams.set('organization_id', organizationId);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  const response = await fetch(url.toString(), {
    headers: { Authorization: `Zoho-oauthtoken ${accessToken}` },
  });
  return readJson(response);
}

async function fetchZohoInventory(env) {
  const clientId = firstEnv(env, ['ZOHO_CLIENT_ID', 'ZOHO_INVENTORY_CLIENT_ID']);
  const clientSecret = firstEnv(env, ['ZOHO_CLIENT_SECRET', 'ZOHO_INVENTORY_CLIENT_SECRET']);
  const refreshToken = firstEnv(env, ['ZOHO_REFRESH_TOKEN', 'ZOHO_INVENTORY_REFRESH_TOKEN']);
  const organizationId = firstEnv(env, ['ZOHO_ORGANIZATION_ID', 'ZOHO_INVENTORY_ORGANIZATION_ID', 'ZOHO_ORG_ID']);
  const accountsBase = firstEnv(env, ['ZOHO_ACCOUNTS_BASE', 'ZOHO_ACCOUNTS_URL'], DEFAULT_ACCOUNTS_BASE).replace(/\/$/, '');
  const apiBase = firstEnv(env, ['ZOHO_INVENTORY_API_BASE', 'ZOHO_API_BASE'], DEFAULT_API_BASE).replace(/\/$/, '');
  const missing = [];
  if (!clientId) missing.push('client_id');
  if (!clientSecret) missing.push('client_secret');
  if (!refreshToken) missing.push('refresh_token');
  if (!organizationId) missing.push('organization_id');
  if (missing.length) return defaultZohoInventory('missing_credentials', `Missing Zoho env vars: ${missing.join(', ')}.`);

  const body = new URLSearchParams({
    refresh_token: refreshToken,
    client_id: clientId,
    client_secret: clientSecret,
    grant_type: 'refresh_token',
  });
  const tokenResponse = await fetch(`${accountsBase}/oauth/v2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const tokenPayload = await readJson(tokenResponse);
  const accessToken = tokenPayload.access_token;
  if (!accessToken) throw new Error('Zoho token response did not include an access token.');

  const [itemsPayload, ordersPayload, invoicesPayload] = await Promise.all([
    zohoGet(apiBase, 'items', accessToken, organizationId, { per_page: '200' }),
    zohoGet(apiBase, 'salesorders', accessToken, organizationId, { per_page: '20', sort_column: 'created_time', sort_order: 'D' }),
    zohoGet(apiBase, 'invoices', accessToken, organizationId, { per_page: '20', sort_column: 'created_time', sort_order: 'D' }),
  ]);

  const items = Array.isArray(itemsPayload.items) ? itemsPayload.items : [];
  const salesOrders = Array.isArray(ordersPayload.salesorders) ? ordersPayload.salesorders : [];
  const invoices = Array.isArray(invoicesPayload.invoices) ? invoicesPayload.invoices : [];
  const lowStock = items.filter((item) => reorderLevel(item) && qty(item) <= reorderLevel(item));
  const openOrders = salesOrders.filter((order) => !['closed', 'void', 'cancelled'].includes(String(order.status || '').toLowerCase()));
  const unpaidInvoices = invoices.filter((invoice) => !['paid', 'void', 'cancelled'].includes(String(invoice.status || '').toLowerCase()));
  const paidTotal = invoices
    .filter((invoice) => String(invoice.status || '').toLowerCase() === 'paid')
    .reduce((sum, invoice) => sum + Number(invoice.total || 0), 0);

  return {
    updatedLabel: `Zoho synced ${new Date().toLocaleString('en-US', { timeZoneName: 'short' })}`,
    status: 'ok',
    message: 'Live read-only Zoho Inventory API pull from Cloudflare runtime.',
    scorecards: [
      { label: 'Zoho stock on hand', value: fmtInt(items.reduce((sum, item) => sum + qty(item), 0)), tone: 'green', note: `Across ${items.length} item(s).`, source: 'zoho_inventory' },
      { label: 'Zoho sales orders', value: fmtInt(salesOrders.length), tone: 'blue', note: `${openOrders.length} open in recent pull.`, source: 'zoho_inventory' },
      { label: 'Zoho invoices', value: fmtInt(invoices.length), tone: 'blue', note: `${unpaidInvoices.length} unpaid in recent pull; paid total $${paidTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.`, source: 'zoho_inventory' },
    ],
    lowStockItems: lowStock.slice(0, 10).map((item) => ({
      name: item.name || 'Unnamed item',
      sku: item.sku || '',
      stock: fmtInt(qty(item)),
      reorderLevel: fmtInt(reorderLevel(item)),
    })),
    recentSalesOrders: salesOrders.slice(0, 8).map((order) => ({
      number: order.salesorder_number || '',
      customer: order.customer_name || '',
      status: order.status || '',
      total: `$${Number(order.total || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    })),
    recentInvoices: invoices.slice(0, 8).map((invoice) => ({
      number: invoice.invoice_number || '',
      customer: invoice.customer_name || '',
      status: invoice.status || '',
      total: `$${Number(invoice.total || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    })),
  };
}

export async function onRequestGet({ env }) {
  try {
    const zohoInventory = await fetchZohoInventory(env || {});
    return Response.json({ zohoInventory }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    return Response.json(
      { zohoInventory: defaultZohoInventory('error', `Zoho refresh failed: ${error.message}`) },
      { status: 200, headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
