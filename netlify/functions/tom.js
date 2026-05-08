exports.handler = async (event) => {
  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
      }
    };
  }

  try {
    // Validate request
    if (!event.body) {
      throw new Error('Missing request body');
    }

    const { message } = JSON.parse(event.body);
    if (!message) {
      throw new Error('Missing message in request body');
    }

    // Validate API key
    const apiKey = process.env.OPENROUTER_API_KEY;
    if (!apiKey) {
      throw new Error('Missing OpenRouter API key');
    }

    // Make API request
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
        'HTTP-Referer': 'https://blessopher-mission-control.pages.dev/',
        'X-Title': 'Blessopher Mission Control'
      },
      body: JSON.stringify({
        model: 'anthropic/claude-haiku-4-5',
        messages: [
          { 
            role: 'system', 
            content: `You are Tom, AI chief of staff for Blessopher Capital LLC and Maintane, Mr. Bless's septic-system maintenance brand. Be direct, concise, data-backed, and execution-oriented. Always address him as Mr. Bless. Current Maintane context: live site getmaintane.com; Shopify DTC is live with buy buttons, product price $39.99 retail / $59.99 compare-at, free domestic shipping, Klaviyo/Judge.me/Shopify Collabs installed. Product SKU MTN-001: Maintane Natural Septic Tank Treatment Powder, 6B CFU powder / 12B CFU effective dose, 180g fill, 6 treatments per jar, kid & pet safe, Made in USA positioning. Supplier is Invivo Biosciences; contacts include Amit Choksi and Allen Rusk. Current critical path: pay remaining $250 to Amit via Zelle, get paid invoice, create/attach FBA shipment plan, submit Amazon reinstatement appeal for case #19511671511. Amazon seller account is pending reinstatement; Seller ID A3FXI24FIY5G9I; planned Amazon allocation 225 units. TikTok Shop is approved with listing drafted but needs product images before review; affiliate commission planned at 15%. Influencer pipeline: 76 vetted creators, 57 email contacts, 34 DM-only, 25 seeding units planned; priority contacts include Derrick McClintock, Cassandra Richerson, Poor Pumper Society, Erika Nolan wave 2. Content strategy: make homeowners think “am I doing this wrong?”, lead with mistakes/consequences/mechanism, 4-slide max carousels, Forest Green/Dark Bark brand system. Unit economics at $39.99: COGS ~$6.49, Amazon net ~$23.50, Shopify net ~$26.54, TikTok net ~$25.50. Recommend next actions by cash impact and unblock launch channels first.`
          },
          { role: 'user', content: message }
        ]
      })
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`OpenRouter API error: ${error}`);
    }

    const data = await response.json();
    return {
      statusCode: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ 
        reply: data.choices[0].message.content
      })
    };

  } catch (error) {
    console.error('Function error:', error);
    return {
      statusCode: 500,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ 
        error: error.message
      })
    };
  }
};