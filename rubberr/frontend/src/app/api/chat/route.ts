import { NextRequest, NextResponse } from 'next/server';
import Anthropic from '@anthropic-ai/sdk';

export async function POST(req: NextRequest) {
  const { message } = await req.json();
  if (!message?.trim()) {
    return NextResponse.json({ error: 'No message provided' }, { status: 400 });
  }

  // BYOK: user-supplied key takes precedence over server key
  const userKey = req.headers.get('x-user-api-key') || undefined;
  const serverKey = process.env.ANTHROPIC_API_KEY;
  const apiKey = userKey || serverKey;

  if (!apiKey) {
    return NextResponse.json(
      { error: 'No API key available. Add your Anthropic key via the ⚡ button to enable coaching.' },
      { status: 503 }
    );
  }

  try {
    const client = new Anthropic({ apiKey });
    const response = await client.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 1024,
      system: `You are Coach Rubberr, an expert table tennis coach and tournament scout.
You help competitive players analyze their game, find nearby tournaments, and develop strategy.
Keep responses concise and actionable. You have access to general table tennis knowledge but not the user's live match data.`,
      messages: [{ role: 'user', content: message }],
    });

    const text = response.content[0]?.type === 'text' ? response.content[0].text : '';
    return NextResponse.json({ response: text });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
