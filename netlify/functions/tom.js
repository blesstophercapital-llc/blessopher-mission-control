import fetch from 'node-fetch';

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
        'HTTP-Referer': 'https://blessopher-mission-control.netlify.app/',
        'X-Title': 'Blessopher Mission Control'
      },
      body: JSON.stringify({
        model: 'anthropic/claude-3-sonnet-20240229',
        messages: [
          { 
            role: 'system', 
            content: `You are Tom, AI chief of staff for Blessopher Capital LLC. Christopher Bless is acquiring BioWonder (Amazon FBA septic brand, $3,500 offer sent to Matthew at Three Pines Capital). Supplier locked: Invivo Biosciences, Amit Choksi COO, $7.75/unit all-in COGS, 500 MOQ. J&J Q1 commission ~$8,794 expected this week. Murk.r designing logo. Be direct, concise, data-backed. Always address him as Mr. Bless.`
          },
          { role: 'user', content: message }
        ]
      })
    });

    // Handle API errors
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`OpenRouter API error: ${error}`);
    }

    const data = await response.json();
    
    // Validate response format
    if (!data.choices?.[0]?.message?.content) {
      throw new Error('Invalid API response format');
    }

    return {
      statusCode: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ 
        reply: data.choices[0].message.content,
        version: '1.0.1'
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
        error: error.message,
        version: '1.0.1'
      })
    };
  }
};