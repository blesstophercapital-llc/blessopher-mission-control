exports.handler = async (event) => {
  const { message } = JSON.parse(event.body);

  const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${process.env.OPENROUTER_API_KEY}`
    },
    body: JSON.stringify({
      model: 'anthropic/claude-sonnet-4-5',
      messages: [
        { role: 'system', content: `You are Tom, AI chief of staff for Blessopher Capital LLC. Christopher Bless is acquiring BioWonder (Amazon FBA septic brand, $3,500 offer sent to Matthew at Three Pines Capital). Supplier locked: Invivo Biosciences, Amit Choksi COO, $7.75/unit all-in COGS, 500 MOQ. J&J Q1 commission ~$8,794 expected this week. Murk.r designing logo. Be direct, concise, data-backed. Always address him as Mr. Bless.` },
        { role: 'user', content: message }
      ]
    })
  });

  const data = await response.json();
  return {
    statusCode: 200,
    headers: { 'Access-Control-Allow-Origin': '*' },
    body: JSON.stringify({ reply: data.choices[0].message.content })
  };
};
